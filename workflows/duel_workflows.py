"""
Duel Workflows
Handles complete duel processes from challenge to completion
"""

import discord
from discord.ext import commands
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from database.models import Database
from systems.user_system import UserSystem
from systems.ranking_system import RankingSystem
from systems.challenge_system import ChallengeSystem
from systems.match_system import MatchSystem
from systems.elo_system import ELOSystem
from systems.ticket_system import TicketSystem
from utils.embeds import EmbedTemplates
from utils.role_utils import RoleManager
from config import CHANNELS, DUEL_TYPES

logger = logging.getLogger('BladeBot.DuelWorkflows')

class DuelWorkflows:
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.user_system = UserSystem(self.db)
        self.ranking_system = RankingSystem(self.db)
        self.elo_system = ELOSystem()
        self.challenge_system = ChallengeSystem(
            self.db, self.user_system, self.ranking_system
        )
        self.match_system = MatchSystem(
            self.db, self.elo_system, self.user_system, self.ranking_system
        )
        self.ticket_system = TicketSystem(bot)
    
    async def process_complete_duel_workflow(self, challenge_type: str, challenger: discord.Member,
                                           challenged: Optional[discord.Member], guild: discord.Guild) -> Dict[str, Any]:
        """
        Process a complete duel workflow from challenge to ticket creation
        
        Args:
            challenge_type: Type of duel (friendly, official, bm)
            challenger: Member issuing the challenge
            challenged: Target member (None for general challenges)
            guild: Discord guild
            
        Returns:
            Dictionary with workflow results
        """
        try:
            workflow_result = {
                'success': False,
                'challenge_created': False,
                'challenge_id': None,
                'message': '',
                'embed': None,
                'ping_role': None
            }
            
            # Create challenge
            success, message, challenge_id = await self.challenge_system.create_challenge(
                challenger=challenger,
                challenged=challenged,
                challenge_type=challenge_type,
                guild=guild
            )
            
            if not success:
                workflow_result['message'] = message
                return workflow_result
            
            workflow_result['challenge_created'] = True
            workflow_result['challenge_id'] = challenge_id
            
            # Get challenge data for embed
            challenge_data = await self.challenge_system.get_challenge_embed_data(challenge_id, guild)
            if not challenge_data:
                workflow_result['message'] = "Error retrieving challenge data"
                return workflow_result
            
            # Create challenge embed
            embed = EmbedTemplates.challenge_embed(challenge_data, guild)
            workflow_result['embed'] = embed
            
            # Get ping role for general challenges
            if not challenged:
                ping_role_id = await self.challenge_system.get_ping_role_for_challenge(
                    challenge_type, challenger.id
                )
                if ping_role_id:
                    ping_role = guild.get_role(ping_role_id)
                    workflow_result['ping_role'] = ping_role
            
            workflow_result['success'] = True
            workflow_result['message'] = "Challenge created successfully"
            
            logger.info(f'Duel workflow completed: {challenge_type} challenge {challenge_id} by {challenger}')
            
            return workflow_result
            
        except Exception as e:
            logger.error(f'Error in duel workflow: {e}')
            workflow_result['message'] = f"Error in duel workflow: {e}"
            return workflow_result
    
    async def process_challenge_acceptance(self, accepter: discord.Member, challenge_id: int,
                                            guild: discord.Guild) -> Dict[str, Any]:
            """
            Process challenge acceptance and create coordination channel
            
            Args:
                accepter: Member accepting the challenge
                challenge_id: Challenge ID being accepted
                guild: Discord guild
                
            Returns:
                Dictionary with acceptance results
            """
            try:
                acceptance_result = {
                    'success': False,
                    'challenge_accepted': False,
                    'ticket_created': False,
                    'ticket_channel': None,
                    'message': '',
                    'embed': None
                }
                
                # Get challenge data first for validation
                challenge_data = await self.db.get_challenge(challenge_id)
                if not challenge_data:
                    acceptance_result['message'] = "Challenge not found"
                    return acceptance_result
                
                # Get challenger member
                challenger = guild.get_member(challenge_data['challenger_id'])
                if not challenger:
                    acceptance_result['message'] = "Challenger not found in server"
                    return acceptance_result
                
                # EARLY VALIDATION: Check if ticket can be created BEFORE accepting challenge
                is_valid, validation_message = await self.ticket_system._validate_ticket_creation(
                    challenger.id, accepter.id, challenge_data['challenge_type']
                )
                
                if not is_valid:
                    # Validation failed - reject the entire acceptance
                    acceptance_result['message'] = validation_message
                    embed = EmbedTemplates.error_embed(
                        "Cannot Accept Challenge",
                        validation_message
                    )
                    acceptance_result['embed'] = embed
                    return acceptance_result
                
                # Accept the challenge (only after validation passes)
                success, message, updated_challenge_data = await self.challenge_system.accept_challenge(
                    accepter, challenge_id
                )
                
                if not success:
                    acceptance_result['message'] = message
                    return acceptance_result
                
                acceptance_result['challenge_accepted'] = True
                
                # Create ticket channel for coordination (validation already passed)
                ticket_channel, ticket_error = await self.ticket_system.create_duel_ticket(
                    guild=guild,
                    challenger=challenger,
                    challenged=accepter,
                    duel_type=updated_challenge_data['challenge_type'],
                    challenge_id=challenge_id
                )
                
                if ticket_channel:
                    acceptance_result['ticket_created'] = True
                    acceptance_result['ticket_channel'] = ticket_channel
                    
                    # Update challenge with ticket channel ID
                    await self.db.update_challenge(
                        challenge_id,
                        ticket_channel_id=ticket_channel.id
                    )
                    
                    # Create success embed
                    embed = EmbedTemplates.success_embed(
                        "Challenge Accepted!",
                        f"Coordination channel created: {ticket_channel.mention}\n"
                        f"Good luck to both duelists!"
                    )
                    acceptance_result['embed'] = embed
                    acceptance_result['message'] = "Challenge accepted and ticket created"
                else:
                    # Challenge accepted but ticket creation failed - show specific error
                    embed = EmbedTemplates.error_embed(
                        "Ticket Creation Failed", 
                        f"Challenge accepted but failed to create coordination channel.\n"
                        f"**Reason:** {ticket_error}\n"
                        f"Please coordinate manually with {challenger.mention}"
                    )
                    acceptance_result['embed'] = embed
                    acceptance_result['message'] = f"Challenge accepted but ticket creation failed: {ticket_error}"
                
                acceptance_result['success'] = True
                
                logger.info(f'Challenge acceptance workflow completed: challenge {challenge_id} accepted by {accepter}')
                
                return acceptance_result
                
            except Exception as e:
                logger.error(f'Error in challenge acceptance workflow: {e}')
                acceptance_result['message'] = f"Error in acceptance workflow: {e}"
                return acceptance_result
    
    async def process_match_recording_workflow(self, match_type: str, challenger: discord.Member,
                                             challenged: discord.Member, winner: discord.Member,
                                             score: Optional[str], notes: Optional[str],
                                             recorded_by: discord.Member, guild: discord.Guild) -> Dict[str, Any]:
        """
        Process complete match recording workflow including notifications
        
        Args:
            match_type: Type of match (official, bm)
            challenger: Member who issued the challenge
            challenged: Member who was challenged
            winner: Member who won the match
            score: Optional score string
            notes: Optional match notes
            recorded_by: Member who recorded the match
            guild: Discord guild
            
        Returns:
            Dictionary with recording results
        """
        try:
            recording_result = {
                'success': False,
                'match_recorded': False,
                'match_id': None,
                'rank_change_pending': False,
                'pending_change_id': None,
                'message': '',
                'result_embed': None,
                'admin_notification_embed': None
            }
            
            # Determine loser
            loser = challenged if winner == challenger else challenger
            
            # Record the match based on type
            if match_type == 'official':
                success, message, match_id = await self.match_system.record_official_match(
                    challenger=challenger,
                    challenged=challenged,
                    winner=winner,
                    loser=loser,
                    score=score,
                    notes=notes,
                    recorded_by=recorded_by
                )
                
                if success:
                    recording_result['match_recorded'] = True
                    recording_result['match_id'] = match_id
                else:
                    recording_result['message'] = message
                    return recording_result
                
            elif match_type == 'bm':
                success, message, result_data = await self.match_system.record_bm_match(
                    challenger=challenger,
                    challenged=challenged,
                    winner=winner,
                    loser=loser,
                    score=score,
                    notes=notes,
                    recorded_by=recorded_by
                )
                
                if success:
                    recording_result['match_recorded'] = True
                    recording_result['match_id'] = result_data['match_id']
                    recording_result['rank_change_pending'] = result_data['rank_change_possible']
                    recording_result['pending_change_id'] = result_data.get('pending_change_id')
                else:
                    recording_result['message'] = message
                    return recording_result
            
            # Get match summary for embeds
            match_summary = await self.match_system.get_match_summary(recording_result['match_id'])
            if match_summary:
                recording_result['result_embed'] = EmbedTemplates.match_result_embed(match_summary, guild)
            
            # Create admin notification for BM duels with rank changes
            if match_type == 'bm' and recording_result['rank_change_pending']:
                admin_embed = EmbedTemplates.warning_embed(
                    "🔔 Admin Confirmation Required",
                    f"BM match recorded with pending rank change (ID: {recording_result['pending_change_id']})\n"
                    f"Use `?confirm {recording_result['pending_change_id']}` to approve the rank change"
                )
                recording_result['admin_notification_embed'] = admin_embed
            
            recording_result['success'] = True
            recording_result['message'] = f"{match_type.title()} match recorded successfully"
            
            logger.info(f'Match recording workflow completed: {match_type} match {recording_result["match_id"]} by {recorded_by}')
            
            return recording_result
            
        except Exception as e:
            logger.error(f'Error in match recording workflow: {e}')
            recording_result['message'] = f"Error in match recording workflow: {e}"
            return recording_result
    
    async def send_match_notifications(self, recording_result: Dict[str, Any], guild: discord.Guild):
        """
        Send notifications for recorded matches
        
        Args:
            recording_result: Result from match recording workflow
            guild: Discord guild
        """
        try:
            # Send to duel logs channel
            if recording_result.get('result_embed'):
                duel_logs_channel = guild.get_channel(CHANNELS['duel_logs'])
                if duel_logs_channel:
                    try:
                        await duel_logs_channel.send(embed=recording_result['result_embed'])
                    except Exception as e:
                        logger.warning(f'Could not send to duel logs channel: {e}')
            
            # Send admin notification if needed
            if recording_result.get('admin_notification_embed'):
                bot_logs_channel = guild.get_channel(CHANNELS['bmbot_logs'])
                if bot_logs_channel:
                    try:
                        await bot_logs_channel.send(embed=recording_result['admin_notification_embed'])
                    except Exception as e:
                        logger.warning(f'Could not send to bot logs channel: {e}')
            
        except Exception as e:
            logger.error(f'Error sending match notifications: {e}')
    
    async def process_rank_change_confirmation(self, change_id: int, confirmed_by: discord.Member,
                                             guild: discord.Guild) -> Dict[str, Any]:
        """
        Process rank change confirmation workflow
        
        Args:
            change_id: Pending rank change ID
            confirmed_by: Admin confirming the change
            guild: Discord guild
            
        Returns:
            Dictionary with confirmation results
        """
        try:
            confirmation_result = {
                'success': False,
                'rank_change_confirmed': False,
                'roles_updated': False,
                'message': '',
                'confirmation_embed': None
            }
            
            # Confirm the rank change
            success, message = await self.ranking_system.confirm_rank_change(
                change_id, confirmed_by.id
            )
            
            if not success:
                confirmation_result['message'] = message
                return confirmation_result
            
            confirmation_result['rank_change_confirmed'] = True
            
            # Get the rank change details for Discord role updates
            async with self.db.get_connection() as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute(
                    'SELECT * FROM pending_rank_changes WHERE change_id = ?',
                    (change_id,)
                )
                change_data = await cursor.fetchone()
            
            if change_data:
                # Update Discord roles for both users
                role_manager = RoleManager(guild)
                roles_updated = True
                
                # Update winner's roles
                winner = guild.get_member(change_data['winner_id'])
                if winner:
                    success, _ = await role_manager.assign_rank_roles(
                        winner, 
                        change_data['winner_new_tier'], 
                        change_data['winner_new_rank']
                    )
                    if not success:
                        roles_updated = False
                
                # Update loser's roles
                loser = guild.get_member(change_data['loser_id'])
                if loser:
                    success, _ = await role_manager.assign_rank_roles(
                        loser,
                        change_data['loser_new_tier'],
                        change_data['loser_new_rank']
                    )
                    if not success:
                        roles_updated = False
                
                confirmation_result['roles_updated'] = roles_updated
                
                # Create confirmation embed
                embed = EmbedTemplates.success_embed(
                    "Rank Change Confirmed",
                    f"Rank change #{change_id} has been approved"
                )
                
                embed.add_field(
                    name="Winner Promotion",
                    value=(
                        f"{winner.mention if winner else 'Unknown'}\n"
                        f"{change_data['winner_old_tier']} {change_data['winner_old_rank']} → "
                        f"**{change_data['winner_new_tier']} {change_data['winner_new_rank']}**"
                    ),
                    inline=False
                )
                
                embed.add_field(
                    name="Loser Demotion",
                    value=(
                        f"{loser.mention if loser else 'Unknown'}\n"
                        f"{change_data['loser_old_tier']} {change_data['loser_old_rank']} → "
                        f"**{change_data['loser_new_tier']} {change_data['loser_new_rank']}**"
                    ),
                    inline=False
                )
                
                embed.add_field(
                    name="Confirmed By",
                    value=confirmed_by.mention,
                    inline=True
                )
                
                confirmation_result['confirmation_embed'] = embed
            
            confirmation_result['success'] = True
            confirmation_result['message'] = "Rank change confirmed successfully"
            
            logger.info(f'Rank change confirmation workflow completed: change {change_id} by {confirmed_by}')
            
            return confirmation_result
            
        except Exception as e:
            logger.error(f'Error in rank change confirmation workflow: {e}')
            confirmation_result['message'] = f"Error in confirmation workflow: {e}"
            return confirmation_result
    
    async def send_rank_change_notifications(self, confirmation_result: Dict[str, Any], guild: discord.Guild):
        """
        Send notifications for confirmed rank changes
        
        Args:
            confirmation_result: Result from rank change confirmation workflow
            guild: Discord guild
        """
        try:
            if confirmation_result.get('confirmation_embed'):
                # Send to rank tracker channel
                rank_tracker_channel = guild.get_channel(CHANNELS['rank_tracker'])
                if rank_tracker_channel:
                    try:
                        await rank_tracker_channel.send(embed=confirmation_result['confirmation_embed'])
                    except Exception as e:
                        logger.warning(f'Could not send to rank tracker channel: {e}')
            
        except Exception as e:
            logger.error(f'Error sending rank change notifications: {e}')
    
    async def get_duel_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive duel statistics
        
        Returns:
            Dictionary with duel statistics
        """
        try:
            stats = await self.match_system.get_match_statistics()
            
            # Add challenge statistics
            async with self.db.get_connection() as db:
                # Active challenges
                cursor = await db.execute(
                    'SELECT COUNT(*) FROM challenges WHERE status = "pending"'
                )
                stats['active_challenges'] = (await cursor.fetchone())[0]
                
                # Challenge acceptance rate
                cursor = await db.execute(
                    'SELECT COUNT(*) FROM challenges WHERE status = "accepted"'
                )
                accepted_challenges = (await cursor.fetchone())[0]
                
                cursor = await db.execute(
                    'SELECT COUNT(*) FROM challenges WHERE status IN ("accepted", "declined", "expired")'
                )
                total_resolved_challenges = (await cursor.fetchone())[0]
                
                if total_resolved_challenges > 0:
                    stats['challenge_acceptance_rate'] = (accepted_challenges / total_resolved_challenges) * 100
                else:
                    stats['challenge_acceptance_rate'] = 0
            
            return stats
            
        except Exception as e:
            logger.error(f'Error getting duel statistics: {e}')
            return {}