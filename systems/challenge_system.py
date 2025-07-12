"""
Challenge System
Handles challenge creation, validation, cooldowns, and management
"""

import discord
import asyncio
import aiosqlite
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from database.models import Database
from database.queries import DatabaseQueries
from systems.user_system import UserSystem
from systems.ranking_system import RankingSystem
from config import DUEL_TYPES, SPECIAL_ROLES, BOT_LIMITS, EMBED_COLORS, CLEANUP_TIMINGS

logger = logging.getLogger('BladeBot.ChallengeSystem')

class ChallengeSystem:
    def __init__(self, database: Database, user_system: UserSystem, ranking_system: RankingSystem):
        self.db = database
        self.queries = DatabaseQueries(database.db_path)
        self.user_system = user_system
        self.ranking_system = ranking_system
    
    async def create_challenge(self, challenger: discord.Member, challenged: Optional[discord.Member],
                            challenge_type: str, guild: discord.Guild) -> Tuple[bool, str, Optional[int]]:
        """
        Create a new challenge
        
        Args:
            challenger: Member issuing the challenge
            challenged: Target member (None for general challenges)
            challenge_type: Type of challenge (friendly, official, bm)
            guild: Discord guild
            
        Returns:
            Tuple of (success, message, challenge_id)
        """
        # Ensure challenger is registered
        await self.user_system.ensure_user_registered(challenger)
        
        if challenged:
            await self.user_system.ensure_user_registered(challenged)
            
            # Validate specific user challenge
            can_challenge, reason = await self.queries.can_user_challenge(
                challenger.id, challenged.id, challenge_type
            )
            if not can_challenge:
                return False, reason, None
        
        # Check if challenger already has an active challenge of this type
        async with aiosqlite.connect(self.db.db_path) as db:
            db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
            cursor = await db.execute(
                '''SELECT COUNT(*) as count FROM challenges 
                WHERE challenger_id = ? 
                AND challenge_type = ? 
                AND status = 'pending' 
                AND expires_at > datetime('now')''',
                (challenger.id, challenge_type)
            )
            existing_count = (await cursor.fetchone())['count']
            
            if existing_count > 0:
                return False, f"You already have an active {challenge_type} challenge. Please wait for it to be accepted, declined, or expired.", None
        
        # Additional validation for BM challenges
        if challenge_type == 'bm':
            validation_result = await self._validate_bm_challenge(challenger, challenged)
            if not validation_result[0]:
                return False, validation_result[1], None
        
        # Create challenge in database
        try:
            challenge_id = await self.db.create_challenge(
                challenger_id=challenger.id,
                challenged_id=challenged.id if challenged else None,
                challenge_type=challenge_type,
                expires_in_minutes=BOT_LIMITS['challenge_timeout_minutes']
            )
            
            # Update challenger's last challenge date for BM duels
            if challenge_type == 'bm':
                await self.user_system.update_challenge_cooldown(challenger.id)
            
            logger.info(f'Created {challenge_type} challenge {challenge_id} by {challenger}')
            return True, "Challenge created successfully", challenge_id
            
        except Exception as e:
            logger.error(f'Error creating challenge: {e}')
            return False, "Error creating challenge", None
    
    async def accept_challenge(self, accepter: discord.Member, challenge_id: int) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Accept a challenge
        
        Args:
            accepter: Member accepting the challenge
            challenge_id: Challenge ID to accept
            
        Returns:
            Tuple of (success, message, challenge_data)
        """
        # Get challenge data
        challenge = await self.db.get_challenge(challenge_id)
        if not challenge:
            return False, "Challenge not found", None
        
        if challenge['status'] != 'pending':
            return False, "Challenge is no longer active", None
        
        # Check if challenge has expired
        if datetime.now() > datetime.fromisoformat(challenge['expires_at']):
            await self.db.update_challenge(challenge_id, status='expired')
            return False, "Challenge has expired", None
        
        # Validate accepter
        if challenge['challenged_id'] and challenge['challenged_id'] != accepter.id:
            return False, "You cannot accept this challenge", None
        
        if challenge['challenger_id'] == accepter.id:
            return False, "You cannot accept your own challenge", None
        
        # Ensure accepter is registered
        await self.user_system.ensure_user_registered(accepter)
        
        # Additional validation for BM challenges
        if challenge['challenge_type'] == 'bm':
            # Re-validate BM challenge conditions
            challenger_user = await self.db.get_user(challenge['challenger_id'])
            accepter_user = await self.db.get_user(accepter.id)
            
            if not challenger_user or not accepter_user:
                return False, "User data not found", None
            
            can_challenge, reason = await self.ranking_system.can_user_challenge_rank(
                challenge['challenger_id'],
                accepter_user['tier'],
                accepter_user['rank_numeral']
            )
            if not can_challenge:
                return False, f"Challenge no longer valid: {reason}", None
        
        # Update challenge status
        success = await self.db.update_challenge(
            challenge_id,
            status='accepted',
            challenged_id=accepter.id,
            accepted_date=datetime.now().isoformat()
        )
        
        if success:
            logger.info(f'Challenge {challenge_id} accepted by {accepter}')
            return True, "Challenge accepted!", challenge
        else:
            return False, "Error accepting challenge", None
    
    async def decline_challenge(self, decliner: discord.Member, challenge_id: int) -> Tuple[bool, str]:
        """
        Decline a challenge
        
        Args:
            decliner: Member declining the challenge
            challenge_id: Challenge ID to decline
            
        Returns:
            Tuple of (success, message)
        """
        challenge = await self.db.get_challenge(challenge_id)
        if not challenge:
            return False, "Challenge not found"
        
        if challenge['status'] != 'pending':
            return False, "Challenge is no longer active"
        
        # Only the challenged user can decline (for specific challenges)
        if challenge['challenged_id'] and challenge['challenged_id'] != decliner.id:
            return False, "You cannot decline this challenge"
        
        if challenge['challenger_id'] == decliner.id:
            return False, "You cannot decline your own challenge"
        
        # Update challenge status
        success = await self.db.update_challenge(challenge_id, status='declined')
        
        if success:
            logger.info(f'Challenge {challenge_id} declined by {decliner}')
            return True, "Challenge declined"
        else:
            return False, "Error declining challenge"
    
    async def get_active_challenges_for_user(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Get all active challenges involving a user
        
        Args:
            user_id: Discord user ID
            
        Returns:
            List of active challenges
        """
        challenges = await self.db.get_active_challenges(user_id)
        
        # Also check for general challenges (no specific target) that this user can accept
        async with aiosqlite.connect(self.db.db_path) as db:
            db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
            cursor = await db.execute(
                '''SELECT * FROM challenges 
                   WHERE challenged_id IS NULL 
                   AND challenger_id != ?
                   AND status = 'pending' 
                   AND expires_at > datetime('now')
                   ORDER BY created_date DESC''',
                (user_id,)
            )
            general_challenges = await cursor.fetchall()
        
        # Combine specific and general challenges
        all_challenges = challenges + general_challenges
        
        # Sort by creation date (newest first)
        all_challenges.sort(key=lambda x: x['created_date'], reverse=True)
        
        return all_challenges
    
    async def find_challenge_by_message(self, channel: discord.TextChannel, 
                                      message_author: discord.Member) -> Optional[int]:
        """
        Find the most recent challenge in a channel by a user
        
        Args:
            channel: Discord channel to search
            message_author: Author who issued the challenge
            
        Returns:
            Challenge ID if found, None otherwise
        """
        # Look for recent challenges by this user
        recent_challenges = await self.get_active_challenges_for_user(message_author.id)
        
        # Return the most recent challenge
        if recent_challenges:
            # Sort by creation date and return most recent
            recent_challenges.sort(key=lambda x: x['created_date'], reverse=True)
            return recent_challenges[0]['challenge_id']
        
        return None
    
    async def cleanup_expired_challenges(self) -> int:
        """
        Clean up expired challenges
        
        Returns:
            Number of challenges cleaned up
        """
        return await self.queries.cleanup_expired_challenges()
    
    async def get_challenge_embed_data(self, challenge_id: int, guild: discord.Guild) -> Optional[Dict[str, Any]]:
        """
        Get challenge data formatted for embed display
        
        Args:
            challenge_id: Challenge ID
            guild: Discord guild
            
        Returns:
            Dictionary with embed data or None if not found
        """
        challenge = await self.db.get_challenge(challenge_id)
        if not challenge:
            return None
        
        challenger = guild.get_member(challenge['challenger_id'])
        challenged = guild.get_member(challenge['challenged_id']) if challenge['challenged_id'] else None
        
        challenger_user = await self.db.get_user(challenge['challenger_id'])
        challenged_user = await self.db.get_user(challenge['challenged_id']) if challenge['challenged_id'] else None
        
        duel_info = DUEL_TYPES[challenge['challenge_type']]
        
        embed_data = {
            'challenge_id': challenge_id,
            'challenge_type': challenge['challenge_type'],
            'duel_name': duel_info['name'],
            'duel_description': duel_info['description'],
            'challenger': challenger,
            'challenged': challenged,
            'challenger_rank': f"{challenger_user['tier']} {challenger_user['rank_numeral']}" if challenger_user else "Unknown",
            'challenged_rank': f"{challenged_user['tier']} {challenged_user['rank_numeral']}" if challenged_user else "Unknown",
            'expires_at': challenge['expires_at'],
            'status': challenge['status']
        }
        
        return embed_data
    
    async def _validate_bm_challenge(self, challenger: discord.Member, 
                                   challenged: Optional[discord.Member]) -> Tuple[bool, str]:
        """
        Validate BM challenge specific requirements
        
        Args:
            challenger: Member issuing the challenge
            challenged: Target member (None for general challenges)
            
        Returns:
            Tuple of (is_valid, reason)
        """
        challenger_user = await self.db.get_user(challenger.id)
        if not challenger_user:
            return False, "Challenger not found in database"
        
        # Check if challenger is in Blademaster tier (not Evaluation or Guest)
        if challenger_user['tier'] in ['Evaluation', 'Guest']:
            return False, "You must be a Blademaster to issue BM challenges"
        
        # Check cooldown
        if challenger_user['last_challenge_date']:
            last_challenge = datetime.fromisoformat(challenger_user['last_challenge_date'])
            cooldown_hours = DUEL_TYPES['bm']['cooldown_hours']
            if datetime.now() - last_challenge < timedelta(hours=cooldown_hours):
                remaining = cooldown_hours - (datetime.now() - last_challenge).total_seconds() / 3600
                return False, f"BM challenge cooldown active. {remaining:.1f} hours remaining"
        
        # If specific user challenge, validate target rank
        if challenged:
            challenged_user = await self.db.get_user(challenged.id)
            if not challenged_user:
                return False, "Challenged user not found in database"
            
            can_challenge, reason = await self.ranking_system.can_user_challenge_rank(
                challenger.id,
                challenged_user['tier'],
                challenged_user['rank_numeral']
            )
            if not can_challenge:
                return False, reason
        
        return True, "BM challenge is valid"
    
    async def get_challengeable_users(self, challenger_id: int, challenge_type: str) -> List[Dict[str, Any]]:
        """Get list of users that can be challenged (existing method - enhanced for BM)"""
        if challenge_type == 'bm':
            # ENHANCED: Use automatic targeting instead of manual list
            challenger_user = await self.db.get_user(challenger_id)
            if not challenger_user:
                return []
            
            # Get target rank based on subrank mode
            if self.subrank_mode_enabled:
                from config import get_next_rank
                target_tier, target_numeral = get_next_rank(
                    challenger_user['tier'], 
                    challenger_user['rank_numeral']
                )
            else:
                target_tier, target_numeral = self._get_next_tier_rank(challenger_user['tier'])
            
            if not target_tier:
                return []
            
            return await self._get_users_in_rank(target_tier, target_numeral)
        else:
            # For friendly and official, can challenge anyone who is active (existing logic)
            return await self.ranking_system.get_available_targets_for_challenge(challenger_id)
    
    async def get_ping_role_for_challenge(self, challenge_type: str, challenger_id: int) -> Optional[int]:
        """
        Get the appropriate ping role for a challenge
        
        Args:
            challenge_type: Type of challenge
            challenger_id: Discord ID of challenger
            
        Returns:
            Role ID to ping or None
        """
        if challenge_type in ['friendly', 'official']:
            return DUEL_TYPES[challenge_type]['ping_role']
        elif challenge_type == 'bm':
            # For BM challenges, ping the rank directly above
            challenger_user = await self.db.get_user(challenger_id)
            if challenger_user:
                from config import get_next_rank, get_tier_role_id
                next_tier, next_numeral = get_next_rank(challenger_user['tier'], challenger_user['rank_numeral'])
                if next_tier:
                    return get_tier_role_id(next_tier)
            return None
        
        return None

    async def find_recent_challenge_to_user(self, user: discord.Member) -> Optional[Dict[str, Any]]:
        """
        Find the most recent challenge TO a user (that they can decline)
        
        Args:
            user: Discord member who is the target of challenges
            
        Returns:
            Challenge data if found, None otherwise
        """
        try:
            async with aiosqlite.connect(self.db.db_path) as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute(
                    '''SELECT * FROM challenges 
                       WHERE (challenged_id = ? OR (challenged_id IS NULL AND challenger_id != ?))
                       AND status = 'pending' 
                       AND expires_at > datetime('now')
                       ORDER BY created_date DESC
                       LIMIT 1''',
                    (user.id, user.id)
                )
                challenge = await cursor.fetchone()
                return challenge
        except Exception as e:
            logger.error(f'Error finding recent challenge to user {user}: {e}')
            return None

    async def find_challenge_from_user(self, challenger: discord.Member, 
                                     challenged: discord.Member) -> Optional[Dict[str, Any]]:
        """
        Find a specific challenge FROM challenger TO challenged user
        
        Args:
            challenger: Member who issued the challenge
            challenged: Member who is challenged
            
        Returns:
            Challenge data if found, None otherwise
        """
        try:
            async with aiosqlite.connect(self.db.db_path) as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute(
                    '''SELECT * FROM challenges 
                       WHERE challenger_id = ? 
                       AND (challenged_id = ? OR challenged_id IS NULL)
                       AND status = 'pending' 
                       AND expires_at > datetime('now')
                       ORDER BY created_date DESC
                       LIMIT 1''',
                    (challenger.id, challenged.id)
                )
                challenge = await cursor.fetchone()
                return challenge
        except Exception as e:
            logger.error(f'Error finding challenge from {challenger} to {challenged}: {e}')
            return None

    async def find_challenge_from_message(self, message: discord.Message, 
                                        target_user: discord.Member) -> Optional[Dict[str, Any]]:
        """
        Find a challenge based on a message (for reply-based declining)
        
        Args:
            message: Discord message to analyze
            target_user: User who wants to decline
            
        Returns:
            Challenge data if found, None otherwise
        """
        try:
            # Look for challenges from the message author to the target user
            if hasattr(message.author, 'id'):
                return await self.find_challenge_from_user(message.author, target_user)
            return None
        except Exception as e:
            logger.error(f'Error finding challenge from message: {e}')
            return None

    async def cancel_challenge(self, challenge_id: int, canceller: discord.Member) -> Dict[str, Any]:
        """
        Cancel a challenge (for the canceller's own challenges)
        
        Args:
            challenge_id: ID of challenge to cancel
            canceller: Member attempting to cancel
            
        Returns:
            Dictionary with success status and message
        """
        try:
            challenge = await self.db.get_challenge(challenge_id)
            if not challenge:
                return {'success': False, 'message': 'Challenge not found'}
            
            if challenge['challenger_id'] != canceller.id:
                return {'success': False, 'message': 'You can only cancel your own challenges'}
            
            if challenge['status'] != 'pending':
                return {'success': False, 'message': 'Challenge is no longer active'}
            
            # Update challenge status to cancelled
            success = await self.db.update_challenge(challenge_id, status='cancelled')
            
            if success:
                logger.info(f'Challenge {challenge_id} cancelled by {canceller}')
                return {'success': True, 'message': 'Challenge cancelled successfully'}
            else:
                return {'success': False, 'message': 'Error cancelling challenge'}
                
        except Exception as e:
            logger.error(f'Error cancelling challenge {challenge_id}: {e}')
            return {'success': False, 'message': f'Error cancelling challenge: {str(e)}'}

    async def get_user_challenges(self, user: discord.Member) -> List[Dict[str, Any]]:
        """
        Get all challenges for a user (both challenging and challenged)
        
        Args:
            user: Discord member
            
        Returns:
            List of challenge data
        """
        try:
            # Use the existing database method
            challenges = await self.db.get_active_challenges(user.id)
            return challenges
        except Exception as e:
            logger.error(f'Error getting user challenges for {user}: {e}')
            return []