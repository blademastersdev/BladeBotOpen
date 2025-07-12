"""
Ranking System
Handles rank progression, capacity management, and rank change logic
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from database.models import Database
from database.queries import DatabaseQueries
from config import (
    RANK_STRUCTURE, TIER_HIERARCHY, NUMERAL_HIERARCHY, EVALUATION_RANKS,
    get_next_rank, is_rank_above, RANK_ROLES, TIER_ROLES
)

logger = logging.getLogger('BladeBot.RankingSystem')

class RankingSystem:
    def __init__(self, database: Database):
        self.db = database
        self.queries = DatabaseQueries(database.db_path)
    
    async def can_user_challenge_rank(self, challenger_id: int, target_tier: str, 
                                    target_numeral: str) -> Tuple[bool, str]:
        """
        Check if a user can challenge a specific rank
        
        Args:
            challenger_id: Discord ID of challenger
            target_tier: Target tier to challenge
            target_numeral: Target numeral to challenge
            
        Returns:
            Tuple of (can_challenge, reason)
        """
        challenger = await self.db.get_user(challenger_id)
        if not challenger:
            return False, "Challenger not found in database"
        
        challenger_tier = challenger['tier']
        challenger_numeral = challenger['rank_numeral']
        
        # Check if target rank is directly above challenger's rank
        next_tier, next_numeral = get_next_rank(challenger_tier, challenger_numeral)
        
        if not next_tier:
            return False, "You are already at the highest rank"
        
        if target_tier != next_tier or target_numeral != next_numeral:
            return False, f"You can only challenge users in {next_tier} {next_numeral}"
        
        return True, "Valid challenge target"
    
    async def get_available_targets_for_challenge(self, challenger_id: int) -> List[Dict[str, Any]]:
        """
        Get list of users that challenger can challenge for BM duels
        
        Args:
            challenger_id: Discord ID of challenger
            
        Returns:
            List of users that can be challenged
        """
        challenger = await self.db.get_user(challenger_id)
        if not challenger:
            return []
        
        next_tier, next_numeral = get_next_rank(challenger['tier'], challenger['rank_numeral'])
        if not next_tier:
            return []  # Already at highest rank
        
        # Get all users in the target rank
        targets = await self.db.get_users_by_rank(next_tier, next_numeral)
        return targets
    
    async def can_rank_change_occur(self, winner_id: int, loser_id: int) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check if a rank change can occur and calculate the new ranks
        
        Args:
            winner_id: Discord ID of match winner
            loser_id: Discord ID of match loser
            
        Returns:
            Tuple of (can_change, reason, rank_change_data)
        """
        winner = await self.db.get_user(winner_id)
        loser = await self.db.get_user(loser_id)
        
        if not winner or not loser:
            return False, "One or both users not found", {}
        
        winner_tier = winner['tier']
        winner_numeral = winner['rank_numeral']
        loser_tier = loser['tier']
        loser_numeral = loser['rank_numeral']
        
        # Check if winner's rank is directly below loser's rank
        if not is_rank_above(loser_tier, loser_numeral, winner_tier, winner_numeral):
            return False, "Winner's rank is not directly below loser's rank", {}
        
        # Check if there's space in the loser's current rank for the winner
        capacity_info = await self.queries.get_rank_capacity_info(loser_tier, loser_numeral)
        
        # Winner will take loser's spot, but we need to check if loser's new rank has space
        loser_new_tier = winner_tier
        loser_new_numeral = winner_numeral
        
        loser_capacity_info = await self.queries.get_rank_capacity_info(loser_new_tier, loser_new_numeral)
        
        if loser_capacity_info['is_full']:
            return False, f"No space available in {loser_new_tier} {loser_new_numeral}", {}
        
        rank_change_data = {
            'winner_old_tier': winner_tier,
            'winner_old_numeral': winner_numeral,
            'winner_new_tier': loser_tier,
            'winner_new_numeral': loser_numeral,
            'loser_old_tier': loser_tier,
            'loser_old_numeral': loser_numeral,
            'loser_new_tier': loser_new_tier,
            'loser_new_numeral': loser_new_numeral
        }
        
        return True, "Rank change is valid", rank_change_data
    
    async def create_pending_rank_change(self, match_id: int, winner_id: int, loser_id: int,
                                       rank_change_data: Dict[str, str]) -> int:
        """
        Create a pending rank change that requires admin confirmation
        
        Args:
            match_id: ID of the match that triggered the rank change
            winner_id: Discord ID of winner
            loser_id: Discord ID of loser
            rank_change_data: Dictionary with old and new rank information
            
        Returns:
            Pending rank change ID
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                '''INSERT INTO pending_rank_changes 
                   (match_id, winner_id, loser_id, winner_old_tier, winner_old_rank,
                    winner_new_tier, winner_new_rank, loser_old_tier, loser_old_rank,
                    loser_new_tier, loser_new_rank)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (match_id, winner_id, loser_id,
                 rank_change_data['winner_old_tier'], rank_change_data['winner_old_numeral'],
                 rank_change_data['winner_new_tier'], rank_change_data['winner_new_numeral'],
                 rank_change_data['loser_old_tier'], rank_change_data['loser_old_numeral'],
                 rank_change_data['loser_new_tier'], rank_change_data['loser_new_numeral'])
            )
            await db.commit()
            
            change_id = cursor.lastrowid
            logger.info(f'Created pending rank change {change_id} for match {match_id}')
            return change_id
    
    async def confirm_rank_change(self, change_id: int, confirmed_by: int) -> Tuple[bool, str]:
        """
        Confirm a pending rank change and update user ranks
        
        Args:
            change_id: Pending rank change ID
            confirmed_by: Discord ID of admin who confirmed
            
        Returns:
            Tuple of (success, message)
        """
        async with self.db.get_connection() as db:
            db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
            
            # Get pending rank change
            cursor = await db.execute(
                'SELECT * FROM pending_rank_changes WHERE change_id = ? AND status = "pending"',
                (change_id,)
            )
            change_data = await cursor.fetchone()
            
            if not change_data:
                return False, "Pending rank change not found or already processed"
            
            try:
                # Update winner's rank
                await db.execute(
                    'UPDATE users SET tier = ?, rank_numeral = ? WHERE discord_id = ?',
                    (change_data['winner_new_tier'], change_data['winner_new_rank'], change_data['winner_id'])
                )
                
                # Update loser's rank
                await db.execute(
                    'UPDATE users SET tier = ?, rank_numeral = ? WHERE discord_id = ?',
                    (change_data['loser_new_tier'], change_data['loser_new_rank'], change_data['loser_id'])
                )
                
                # Mark rank change as confirmed
                await db.execute(
                    '''UPDATE pending_rank_changes 
                       SET status = "confirmed", processed_date = datetime('now'), processed_by = ?
                       WHERE change_id = ?''',
                    (confirmed_by, change_id)
                )
                
                # Update the match record
                await db.execute(
                    'UPDATE matches SET rank_change = TRUE WHERE match_id = ?',
                    (change_data['match_id'],)
                )
                
                await db.commit()
                
                logger.info(f'Confirmed rank change {change_id} by admin {confirmed_by}')
                await self.db.log_action('rank_change_confirmed', confirmed_by, f'Change ID: {change_id}')
                
                return True, "Rank change confirmed successfully"
                
            except Exception as e:
                await db.rollback()
                logger.error(f'Error confirming rank change {change_id}: {e}')
                return False, f"Error confirming rank change: {e}"
    
    async def reject_rank_change(self, change_id: int, rejected_by: int, reason: str = "") -> Tuple[bool, str]:
        """
        Reject a pending rank change
        
        Args:
            change_id: Pending rank change ID
            rejected_by: Discord ID of admin who rejected
            reason: Optional reason for rejection
            
        Returns:
            Tuple of (success, message)
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                '''UPDATE pending_rank_changes 
                   SET status = "rejected", processed_date = datetime('now'), processed_by = ?
                   WHERE change_id = ? AND status = "pending"''',
                (rejected_by, change_id)
            )
            await db.commit()
            
            if cursor.rowcount > 0:
                logger.info(f'Rejected rank change {change_id} by admin {rejected_by}: {reason}')
                await self.db.log_action('rank_change_rejected', rejected_by, 
                                       f'Change ID: {change_id}, Reason: {reason}')
                return True, "Rank change rejected"
            else:
                return False, "Pending rank change not found"
    
    async def get_rank_distribution(self) -> Dict[str, Any]:
        """
        Get current rank distribution across all tiers
        
        Returns:
            Dictionary with rank distribution data
        """
        distribution = {}
        total_users = 0
        
        for tier in TIER_HIERARCHY:
            tier_data = {
                'total': 0,
                'ranks': {},
                'capacity': RANK_STRUCTURE[tier]['total_capacity']
            }
            
            for numeral in RANK_STRUCTURE[tier]['numerals']:
                users_in_rank = await self.db.get_users_by_rank(tier, numeral)
                count = len(users_in_rank)
                capacity = RANK_STRUCTURE[tier]['capacities'][numeral]
                
                tier_data['ranks'][numeral] = {
                    'count': count,
                    'capacity': capacity,
                    'available': capacity - count,
                    'percentage': (count / capacity * 100) if capacity > 0 else 0
                }
                tier_data['total'] += count
                total_users += count
            
            distribution[tier] = tier_data
        
        distribution['total_users'] = total_users
        distribution['total_capacity'] = sum(RANK_STRUCTURE[tier]['total_capacity'] for tier in TIER_HIERARCHY)
        
        return distribution
    
    async def get_users_by_rank_sorted(self, tier: str, numeral: str) -> List[Dict[str, Any]]:
        """
        Get users in a rank sorted by ELO (highest first)
        
        Args:
            tier: Rank tier
            numeral: Rank numeral
            
        Returns:
            List of users sorted by ELO
        """
        return await self.db.get_users_by_rank(tier, numeral)
    
    async def is_valid_evaluation_rank(self, tier: str, numeral: str) -> bool:
        """
        Check if a rank is valid for evaluation placement
        
        Args:
            tier: Tier to check
            numeral: Numeral to check
            
        Returns:
            True if valid evaluation rank
        """
        return (tier, numeral) in EVALUATION_RANKS
    
    async def place_user_from_evaluation(self, user_id: int, tier: str, numeral: str) -> Tuple[bool, str]:
        """
        Place a user from evaluation into a specific rank
        
        Args:
            user_id: Discord ID of user
            tier: Target tier
            numeral: Target numeral
            
        Returns:
            Tuple of (success, message)
        """
        # Check if rank is valid for evaluation
        if not await self.is_valid_evaluation_rank(tier, numeral):
            return False, f"{tier} {numeral} is not a valid evaluation placement rank"
        
        # Check if rank has capacity
        capacity_info = await self.queries.get_rank_capacity_info(tier, numeral)
        if capacity_info['is_full']:
            return False, f"{tier} {numeral} is currently full"
        
        # Get user to verify they're in evaluation
        user = await self.db.get_user(user_id)
        if not user:
            return False, "User not found"
        
        if user['tier'] != 'Evaluation':
            return False, "User is not currently in evaluation"
        
        # Update user's rank
        success = await self.db.update_user(
            user_id,
            tier=tier,
            rank_numeral=numeral
        )
        
        if success:
            logger.info(f'Placed user {user_id} from evaluation to {tier} {numeral}')
            await self.db.log_action('evaluation_placement', user_id, f'Placed in {tier} {numeral}')
            return True, f"User placed in {tier} {numeral}"
        else:
            return False, "Failed to update user rank"
    
    async def get_promotion_path(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Get the promotion path for a user showing next possible ranks
        
        Args:
            user_id: Discord ID of user
            
        Returns:
            List of ranks in promotion path
        """
        user = await self.db.get_user(user_id)
        if not user:
            return []
        
        path = []
        current_tier = user['tier']
        current_numeral = user['rank_numeral']
        
        # Show next 5 possible promotions
        for _ in range(5):
            next_tier, next_numeral = get_next_rank(current_tier, current_numeral)
            if not next_tier:
                break
            
            capacity_info = await self.queries.get_rank_capacity_info(next_tier, next_numeral)
            targets = await self.db.get_users_by_rank(next_tier, next_numeral)
            
            path.append({
                'tier': next_tier,
                'numeral': next_numeral,
                'full_rank': f"{next_tier} {next_numeral}",
                'capacity': capacity_info['capacity'],
                'current_count': capacity_info['current_count'],
                'available_spots': capacity_info['available_spots'],
                'is_full': capacity_info['is_full'],
                'targets': len(targets)
            })
            
            current_tier = next_tier
            current_numeral = next_numeral
        
        return path
    
    def get_rank_role_id(self, tier: str, numeral: str) -> Optional[int]:
        """Get Discord role ID for a specific rank"""
        return RANK_ROLES.get((tier, numeral))
    
    def get_tier_role_id(self, tier: str) -> Optional[int]:
        """Get Discord role ID for a specific tier"""
        return TIER_ROLES.get(tier)