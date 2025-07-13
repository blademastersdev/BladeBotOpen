"""
User Management System - Updated with Discord Role Sync
Handles user registration, profile management, and user operations
"""

import discord
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from database.models import Database
from database.queries import DatabaseQueries
from config import TIER_ROLES, RANK_ROLES, ELO_CONFIG, get_tier_color
from systems.elo_system import ELOSystem
import asyncio
import aiosqlite

logger = logging.getLogger('BladeBot.UserSystem')

class UserSystem:
    def __init__(self, database: Database):
        self.db = database
        self.queries = DatabaseQueries(database.db_path)
        self.elo_system = ELOSystem()
        self._last_rank_validation = None
    
    async def register_user(self, member: discord.Member, roblox_username: Optional[str] = None) -> bool:
        """
        Register a new user in the database
        
        Args:
            member: Discord member object
            roblox_username: Optional ROBLOX username
            
        Returns:
            True if registration successful, False if user already exists
        """
        try:
            # Check if user already exists
            existing_user = await self.db.get_user(member.id)
            if existing_user:
                # User exists, sync their Discord roles to database
                await self.sync_discord_roles_to_database(member)
                return False
            
            # Get rank from Discord roles
            tier, numeral = self.get_rank_from_discord_roles(member)
            
            # If no rank found in Discord, default to Bronze IV
            if not tier or not numeral:
                # Check if user has Guest or Evaluation role
                for role in member.roles:
                    for tier_name, role_id in TIER_ROLES.items():
                        if role.id == role_id and tier_name in ['Guest', 'Evaluation']:
                            tier, numeral = tier_name, None
                            break
                    if tier:
                        break
                else:
                    # Default to Guest if no roles found
                    tier, numeral = 'Guest', None
            
            success = await self.db.create_user(
                discord_id=member.id,
                username=member.display_name,
                roblox_username=roblox_username
            )
            
            if success:
                # Update with correct rank from Discord
                await self.db.update_user(
                    member.id,
                    tier=tier,
                    rank_numeral=numeral
                )
                
                logger.info(f'New user registered: {member.display_name} ({member.id}) as {tier} {numeral}')
                await self.db.log_action('user_registered', member.id, f'Username: {member.display_name}, Rank: {tier} {numeral}')
                return True
            else:
                logger.info(f'User already exists: {member.display_name} ({member.id})')
                return False
                
        except Exception as e:
            logger.error(f'Error registering user {member.id}: {e}')
            return False
    
    def get_rank_from_discord_roles(self, member: discord.Member) -> Tuple[Optional[str], Optional[str]]:
        """Get rank from Discord roles"""
        
        # Check Guest/Evaluation roles FIRST
        for role in member.roles:
            for tier, role_id in TIER_ROLES.items():
                if role.id == role_id:
                    if tier == 'Guest':
                        logger.info(f'Found Guest role for {member}')
                        return 'Guest', 'N/A'  # FIXED: Use 'N/A' instead of None
                    elif tier == 'Evaluation':
                        logger.info(f'Found Evaluation role for {member}')
                        return 'Evaluation', 'N/A'  # FIXED: Use 'N/A' instead of None
        
        # Check specific rank roles (existing code)
        for role in member.roles:
            for (tier, numeral), role_id in RANK_ROLES.items():
                if role.id == role_id:
                    logger.info(f'Found rank role for {member}: {tier} {numeral}')
                    return tier, numeral
        
        # Check tier roles and default to lowest numeral
        for role in member.roles:
            for tier, role_id in TIER_ROLES.items():
                if role.id == role_id and tier in ['Bronze', 'Silver', 'Gold', 'Platinum', 'Diamond']:
                    from config import NUMERAL_HIERARCHY
                    default_numeral = NUMERAL_HIERARCHY[tier][-1]
                    logger.info(f'Found tier role for {member}: {tier}, defaulting to {default_numeral}')
                    return tier, default_numeral
        
        logger.info(f'No rank role found for {member}')
        return None, None
    
    async def sync_discord_roles_to_database(self, member: discord.Member) -> bool:
        """
        Sync member's Discord roles to database
        
        Args:
            member: Discord member
            
        Returns:
            True if sync successful
        """
        try:
            tier, numeral = self.get_rank_from_discord_roles(member)
            
            if tier and numeral:
                success = await self.db.update_user(
                    member.id,
                    tier=tier,
                    rank_numeral=numeral
                )
                if success:
                    logger.info(f'Synced Discord roles to database for {member}: {tier} {numeral}')
                return success
            
            return False
            
        except Exception as e:
            logger.error(f'Error syncing Discord roles for {member}: {e}')
            return False

    async def get_user_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get complete user profile with calculated stats
        
        Args:
            user_id: Discord user ID
            
        Returns:
            Dictionary with user profile data or None if not found
        """
        user_data = await self.db.get_user(user_id)
        if not user_data:
            return None
        
        # Calculate additional stats
        profile = dict(user_data)
        profile['win_rate'] = self._calculate_win_rate(user_data['wins'], user_data['losses'])
        profile['elo_tier'] = self.elo_system.get_elo_tier(user_data['elo_rating'])
        profile['full_rank'] = f"{user_data['tier']} {user_data['rank_numeral']}"
        profile['tier_color'] = get_tier_color(user_data['tier'])
        
        return profile
    
    async def update_user_stats(self, user_id: int, won: bool, elo_change: int) -> bool:
        """
        Update user's win/loss record and ELO
        
        Args:
            user_id: Discord user ID
            won: True if user won the match
            elo_change: ELO change amount (can be negative)
            
        Returns:
            True if update successful
        """
        user = await self.db.get_user(user_id)
        if not user:
            return False
        
        # Calculate new stats
        new_wins = user['wins'] + (1 if won else 0)
        new_losses = user['losses'] + (0 if won else 1)
        new_games_played = user['games_played'] + 1
        new_elo = user['elo_rating'] + elo_change
        
        # Ensure ELO doesn't go below 0
        new_elo = max(0, new_elo)
        
        success = await self.db.update_user(
            user_id,
            wins=new_wins,
            losses=new_losses,
            games_played=new_games_played,
            elo_rating=new_elo
        )
        
        if success:
            logger.info(f'Updated stats for user {user_id}: ELO {user["elo_rating"]} -> {new_elo}')
            
        return success
    
    async def update_user_rank(self, user_id: int, tier: str, numeral: str) -> bool:
        """
        Update user's rank in the database
        
        Args:
            user_id: Discord user ID
            tier: New tier (Bronze, Silver, Gold, Platinum, Diamond)
            numeral: New numeral (I, II, III, IV)
            
        Returns:
            True if update successful
        """
        success = await self.db.update_user(
            user_id,
            tier=tier,
            rank_numeral=numeral
        )
        
        if success:
            logger.info(f'Updated rank for user {user_id}: {tier} {numeral}')
            await self.db.log_action('rank_updated', user_id, f'New rank: {tier} {numeral}')
        
        return success
    
    async def assign_discord_roles(self, guild: discord.Guild, user_id: int, 
                                 new_tier: str, new_numeral: str) -> bool:
        """
        Assign appropriate Discord roles to user based on rank
        
        Args:
            guild: Discord guild object
            user_id: Discord user ID
            new_tier: User's tier
            new_numeral: User's numeral
            
        Returns:
            True if roles assigned successfully
        """
        try:
            member = guild.get_member(user_id)
            if not member:
                logger.warning(f'Member {user_id} not found in guild')
                return False
            
            # Get current roles to remove
            roles_to_remove = []
            roles_to_add = []
            
            # Remove old rank and tier roles
            for role in member.roles:
                if role.id in TIER_ROLES.values() or role.id in RANK_ROLES.values():
                    roles_to_remove.append(role)
            
            # Add new tier role
            tier_role_id = TIER_ROLES.get(new_tier)
            if tier_role_id:
                tier_role = guild.get_role(tier_role_id)
                if tier_role:
                    roles_to_add.append(tier_role)
            
            # Add new rank role
            rank_role_id = RANK_ROLES.get((new_tier, new_numeral))
            if rank_role_id:
                rank_role = guild.get_role(rank_role_id)
                if rank_role:
                    roles_to_add.append(rank_role)
            
            # Remove old roles
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason='Rank update')
            
            # Add new roles
            if roles_to_add:
                await member.add_roles(*roles_to_add, reason='Rank update')
            
            logger.info(f'Updated Discord roles for {member.display_name}: {new_tier} {new_numeral}')
            return True
            
        except Exception as e:
            logger.error(f'Error updating Discord roles for user {user_id}: {e}')
            return False
    
    async def get_user_leaderboard_rank(self, user_id: int) -> Optional[int]:
        """Get user's current leaderboard ranking position"""
        return await self.db.get_user_leaderboard_position(user_id)

    async def move_user_to_reserve(self, user_id: int, reason: str = "Left server") -> bool:
        """Move user to reserve status (hides from public displays)"""
        success = await self.db.set_user_reserve_status(user_id, is_reserve=True)
        if success:
            await self.db.log_action('user_reserved', user_id, f'Reason: {reason}')
            logger.info(f'Moved user {user_id} to reserve status: {reason}')
        return success

    async def restore_user_from_reserve(self, user_id: int, reason: str = "Returned to server") -> bool:
        """Restore user from reserve to active status"""
        success = await self.db.set_user_reserve_status(user_id, is_reserve=False)
        if success:
            await self.db.log_action('user_restored', user_id, f'Reason: {reason}')
            logger.info(f'Restored user {user_id} from reserve status: {reason}')
        return success

    async def sync_server_membership(self, guild: discord.Guild) -> Dict[str, int]:
        """Sync user reserve status based on server membership"""
        stats = {'moved_to_reserve': 0, 'restored_from_reserve': 0, 'errors': 0}
        
        try:
            # Get all active users from database
            async with aiosqlite.connect(self.db.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    'SELECT discord_id, status FROM users WHERE is_active = TRUE'
                )
                all_users = await cursor.fetchall()
            
            guild_member_ids = {member.id for member in guild.members}
            
            for user_row in all_users:
                user_id = user_row['discord_id']
                current_status = user_row['status']
                
                # Check if user is in server
                is_in_server = user_id in guild_member_ids
                
                if is_in_server and current_status == 'reserve':
                    # User returned to server - restore from reserve
                    if await self.restore_user_from_reserve(user_id, "Returned to server"):
                        stats['restored_from_reserve'] += 1
                    else:
                        stats['errors'] += 1
                        
                elif not is_in_server and current_status == 'active':
                    # User left server - move to reserve
                    if await self.move_user_to_reserve(user_id, "Left server"):
                        stats['moved_to_reserve'] += 1
                    else:
                        stats['errors'] += 1
            
            if stats['moved_to_reserve'] > 0 or stats['restored_from_reserve'] > 0:
                logger.info(f"Server membership sync: {stats}")
            
            return stats
            
        except Exception as e:
            logger.error(f'Error syncing server membership: {e}')
            stats['errors'] += 1
            return stats

    async def get_user_duel_history(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get user's duel history with enhanced information
        
        Args:
            user_id: Discord user ID
            limit: Maximum number of matches to return
            
        Returns:
            List of match dictionaries with additional information
        """
        matches = await self.queries.get_user_duel_history(user_id, limit=limit)
        
        # Enhance match data
        enhanced_matches = []
        for match in matches:
            enhanced_match = dict(match)
            
            # Determine if user won
            enhanced_match['user_won'] = match['winner_id'] == user_id
            
            # Get opponent info
            if match['challenger_id'] == user_id:
                enhanced_match['opponent_id'] = match['challenged_id']
                enhanced_match['opponent_name'] = match['challenged_name']
            else:
                enhanced_match['opponent_id'] = match['challenger_id']
                enhanced_match['opponent_name'] = match['challenger_name']
            
            # Format result
            if enhanced_match['user_won']:
                enhanced_match['result'] = 'Win'
                enhanced_match['user_elo_change'] = match['elo_change_winner']
            else:
                enhanced_match['result'] = 'Loss'
                enhanced_match['user_elo_change'] = match['elo_change_loser']
            
            enhanced_matches.append(enhanced_match)
        
        return enhanced_matches
    
    async def get_user_statistics(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive user statistics
        
        Args:
            user_id: Discord user ID
            
        Returns:
            Dictionary with detailed statistics
        """
        user = await self.get_user_profile(user_id)
        if not user:
            return None
        
        matches = await self.queries.get_user_duel_history(user_id, limit=None)
        
        stats = {
            'basic_stats': user,
            'total_matches': len(matches),
            'official_matches': len([m for m in matches if m['match_type'] == 'official']),
            'bm_matches': len([m for m in matches if m['match_type'] == 'bm']),
            'recent_matches': matches[:5],  # Last 5 matches
        }
        
        # Calculate streaks
        current_streak = self._calculate_current_streak(matches, user_id)
        stats['current_streak'] = current_streak
        
        # Calculate average ELO change
        if matches:
            elo_changes = []
            for match in matches:
                if match['winner_id'] == user_id:
                    elo_changes.append(match['elo_change_winner'])
                else:
                    elo_changes.append(match['elo_change_loser'])
            
            stats['avg_elo_change'] = sum(elo_changes) / len(elo_changes)
        else:
            stats['avg_elo_change'] = 0
        
        return stats
    
    async def ensure_user_registered(self, member: discord.Member) -> bool:
        """
        Ensure user is registered, register if not
        
        Args:
            member: Discord member object
            
        Returns:
            True if user is registered (or was just registered)
        """
        user = await self.db.get_user(member.id)
        if user:
            # User exists, but sync their Discord roles to make sure rank is correct
            await self.sync_discord_roles_to_database(member)
            return True
        
        # Register the user
        return await self.register_user(member)
    
    async def update_challenge_cooldown(self, user_id: int) -> bool:
        """
        Update the user's last challenge date for cooldown tracking
        
        Args:
            user_id: Discord user ID
            
        Returns:
            True if update successful
        """
        return await self.db.update_user(
            user_id,
            last_challenge_date=datetime.now().isoformat()
        )
    
    def _calculate_win_rate(self, wins: int, losses: int) -> float:
        """Calculate win rate percentage"""
        total = wins + losses
        return (wins / total * 100) if total > 0 else 0.0
    
    def _calculate_current_streak(self, matches: List[Dict[str, Any]], user_id: int) -> Dict[str, Any]:
        """
        Calculate current win/loss streak
        
        Args:
            matches: List of matches (most recent first)
            user_id: User ID to calculate streak for
            
        Returns:
            Dictionary with streak information
        """
        if not matches:
            return {'type': 'none', 'count': 0}
        
        # Start with most recent match
        recent_match = matches[0]
        is_win = recent_match['winner_id'] == user_id
        streak_type = 'win' if is_win else 'loss'
        streak_count = 1
        
        # Count consecutive results of same type
        for match in matches[1:]:
            match_is_win = match['winner_id'] == user_id
            if (match_is_win and is_win) or (not match_is_win and not is_win):
                streak_count += 1
            else:
                break
        
        return {
            'type': streak_type,
            'count': streak_count
        }
    
    async def validate_and_fix_user_ranks(self, guild: discord.Guild) -> Dict[str, int]:
        """Automatically validate and fix user rank mismatches"""
        try:
            stats = {'checked': 0, 'fixed': 0, 'errors': 0, 'skipped': 0}
            
            # Get all users from database
            async with aiosqlite.connect(self.db.db_path) as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute('SELECT discord_id, tier, rank_numeral, username FROM users')
                all_users = await cursor.fetchall()
            
            for user_data in all_users:
                stats['checked'] += 1
                
                # Get Discord member
                member = guild.get_member(user_data['discord_id'])
                if not member:
                    stats['skipped'] += 1
                    continue  # User no longer in server
                
                # Get correct rank from Discord roles
                correct_tier, correct_numeral = self.get_rank_from_discord_roles(member)
                
                # FIXED: Default to Guest with 'N/A' instead of None
                if not correct_tier:
                    correct_tier, correct_numeral = 'Guest', 'N/A'
                elif correct_tier in ['Guest', 'Evaluation']:
                    correct_numeral = 'N/A'  # Use 'N/A' instead of None
                
                # Get current database values
                db_tier = user_data['tier']
                db_numeral = user_data['rank_numeral']
                
                # Check if fix is needed
                if db_tier != correct_tier or db_numeral != correct_numeral:
                    # Common mismatch cases
                    needs_fix = (
                        (correct_tier in ['Guest', 'Evaluation'] and db_tier == 'Bronze' and db_numeral == 'IV') or
                        (correct_tier not in ['Guest', 'Evaluation'] and db_tier in ['Guest', 'Evaluation']) or
                        (correct_tier == 'Guest' and db_tier not in ['Guest', 'Evaluation'])
                    )
                    
                    if needs_fix:
                        try:
                            success = await self.db.update_user(
                                user_data['discord_id'],
                                tier=correct_tier,
                                rank_numeral=correct_numeral  # Now 'N/A' instead of None
                            )
                            
                            if success:
                                stats['fixed'] += 1
                                logger.info(f"Auto-fixed rank for {member.display_name}: {db_tier} {db_numeral} → {correct_tier} {correct_numeral}")
                                
                                await self.db.log_action(
                                    'auto_rank_validation',
                                    user_data['discord_id'],
                                    f"Auto-fixed: {db_tier} {db_numeral} → {correct_tier} {correct_numeral}"
                                )
                            else:
                                stats['errors'] += 1
                                
                        except Exception as e:
                            stats['errors'] += 1
                            logger.error(f"Error auto-fixing rank for {member.display_name}: {e}")
            
            if stats['fixed'] > 0:
                logger.info(f"Rank validation complete: {stats['fixed']} users fixed out of {stats['checked']} checked")
            
            return stats
            
        except Exception as e:
            logger.error(f'Error in automatic rank validation: {e}')
            return {'checked': 0, 'fixed': 0, 'errors': 1, 'skipped': 0}

    async def should_run_rank_validation(self) -> bool:
        """
        Check if rank validation should run
        Runs every 6 hours or on bot startup
        """
        if not self._last_rank_validation:
            return True  # Never run before
        
        # Run every 6 hours
        time_since_last = datetime.now() - self._last_rank_validation
        return time_since_last > timedelta(hours=6)
    
    async def reset_challenge_cooldown(self, user_id: int):
        '''Reset BM challenge cooldown for user'''
        try:
            async with aiosqlite.connect(self.db.db_path) as db:
                await db.execute(
                    'UPDATE users SET last_challenge_date = NULL WHERE discord_id = ?',
                    (user_id,)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f'Error resetting challenge cooldown: {e}')
            return False
        
    async def get_bm_challenge_stats(self, user_id: int) -> dict:
        '''Get BM challenge statistics for user'''
        try:
            async with aiosqlite.connect(self.db.db_path) as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute(
                    '''SELECT COUNT(*) as bm_challenges_issued,
                            last_challenge_date,
                            (SELECT COUNT(*) FROM challenges 
                            WHERE challenged_id = ? AND challenge_type = 'bm' 
                            AND status = 'accepted') as bm_challenges_accepted
                    FROM challenges 
                    WHERE challenger_id = ? AND challenge_type = 'bm' ''',
                    (user_id, user_id)
                )
                return await cursor.fetchone() or {}
        except Exception as e:
            logger.error(f'Error getting BM challenge stats: {e}')
            return {}