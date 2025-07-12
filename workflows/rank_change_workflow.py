"""
Rank Change Workflow
Handles the complete rank change confirmation process for BM duels
"""

import discord
from discord.ext import commands
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from database.models import Database
from systems.user_system import UserSystem
from systems.ranking_system import RankingSystem
from utils.embeds import EmbedTemplates
from utils.role_utils import RoleManager
from config import CHANNELS

logger = logging.getLogger('BladeBot.RankChangeWorkflow')

class RankChangeWorkflow:
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.user_system = UserSystem(self.db)
        self.ranking_system = RankingSystem(self.db)
    
    async def create_rank_change_request(self, match_id: int, winner_id: int, loser_id: int,
                                       rank_change_data: Dict[str, str]) -> Optional[int]:
        """
        Create a pending rank change request
        
        Args:
            match_id: ID of the match that triggered the rank change
            winner_id: Discord ID of winner
            loser_id: Discord ID of loser
            rank_change_data: Dictionary with old and new rank information
            
        Returns:
            Pending rank change ID or None if failed
        """
        try:
            pending_id = await self.ranking_system.create_pending_rank_change(
                match_id, winner_id, loser_id, rank_change_data
            )
            
            logger.info(f'Created pending rank change {pending_id} for match {match_id}')
            return pending_id
            
        except Exception as e:
            logger.error(f'Error creating rank change request: {e}')
            return None
    
    async def process_rank_change_confirmation(self, change_id: int, admin: discord.Member,
                                             guild: discord.Guild) -> Dict[str, Any]:
        """
        Process a rank change confirmation with all necessary updates
        
        Args:
            change_id: Pending rank change ID
            admin: Admin confirming the change
            guild: Discord guild
            
        Returns:
            Dictionary with confirmation results
        """
        try:
            result = {
                'success': False,
                'confirmed': False,
                'roles_updated': False,
                'notifications_sent': False,
                'change_data': None,
                'message': '',
                'error_details': []
            }
            
            # Get pending change data before confirming
            async with self.db.get_connection() as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute(
                    '''SELECT prc.*, 
                           w_user.username as winner_name,
                           l_user.username as loser_name
                       FROM pending_rank_changes prc
                       JOIN users w_user ON prc.winner_id = w_user.discord_id
                       JOIN users l_user ON prc.loser_id = l_user.discord_id
                       WHERE prc.change_id = ? AND prc.status = "pending"''',
                    (change_id,)
                )
                change_data = await cursor.fetchone()
            
            if not change_data:
                result['message'] = "Pending rank change not found or already processed"
                return result
            
            result['change_data'] = change_data
            
            # Confirm the rank change in database
            success, message = await self.ranking_system.confirm_rank_change(
                change_id, admin.id
            )
            
            if not success:
                result['message'] = message
                return result
            
            result['confirmed'] = True
            
            # Update Discord roles
            role_manager = RoleManager(guild)
            roles_success = await self._update_discord_roles(
                change_data, role_manager, guild
            )
            
            result['roles_updated'] = roles_success
            if not roles_success:
                result['error_details'].append('Failed to update some Discord roles')
            
            # Send notifications
            notifications_success = await self._send_rank_change_notifications(
                change_data, admin, guild
            )
            
            result['notifications_sent'] = notifications_success
            if not notifications_success:
                result['error_details'].append('Failed to send some notifications')
            
            result['success'] = True
            result['message'] = f"Rank change {change_id} confirmed successfully"
            
            # Log the confirmation
            await self.db.log_action(
                'rank_change_confirmed_workflow',
                admin.id,
                f'Change ID: {change_id}, Winner: {change_data["winner_name"]}, Loser: {change_data["loser_name"]}'
            )
            
            logger.info(f'Rank change workflow completed: change {change_id} confirmed by {admin}')
            
            return result
            
        except Exception as e:
            logger.error(f'Error in rank change confirmation workflow: {e}')
            result['message'] = f"Error in confirmation workflow: {e}"
            return result
    
    async def process_rank_change_rejection(self, change_id: int, admin: discord.Member,
                                          reason: str) -> Dict[str, Any]:
        """
        Process a rank change rejection
        
        Args:
            change_id: Pending rank change ID
            admin: Admin rejecting the change
            reason: Reason for rejection
            
        Returns:
            Dictionary with rejection results
        """
        try:
            result = {
                'success': False,
                'rejected': False,
                'message': '',
                'change_data': None
            }
            
            # Get change data before rejecting
            async with self.db.get_connection() as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute(
                    '''SELECT prc.*, 
                           w_user.username as winner_name,
                           l_user.username as loser_name
                       FROM pending_rank_changes prc
                       JOIN users w_user ON prc.winner_id = w_user.discord_id
                       JOIN users l_user ON prc.loser_id = l_user.discord_id
                       WHERE prc.change_id = ? AND prc.status = "pending"''',
                    (change_id,)
                )
                change_data = await cursor.fetchone()
            
            if not change_data:
                result['message'] = "Pending rank change not found or already processed"
                return result
            
            result['change_data'] = change_data
            
            # Reject the rank change
            success, message = await self.ranking_system.reject_rank_change(
                change_id, admin.id, reason
            )
            
            if not success:
                result['message'] = message
                return result
            
            result['rejected'] = True
            result['success'] = True
            result['message'] = f"Rank change {change_id} rejected"
            
            # Log the rejection
            await self.db.log_action(
                'rank_change_rejected_workflow',
                admin.id,
                f'Change ID: {change_id}, Reason: {reason}'
            )
            
            logger.info(f'Rank change rejected: change {change_id} by {admin}, reason: {reason}')
            
            return result
            
        except Exception as e:
            logger.error(f'Error in rank change rejection workflow: {e}')
            result['message'] = f"Error in rejection workflow: {e}"
            return result
    
    async def _update_discord_roles(self, change_data: Dict[str, Any], 
                                  role_manager: RoleManager, guild: discord.Guild) -> bool:
        """
        Update Discord roles for both winner and loser
        
        Args:
            change_data: Rank change data
            role_manager: Role manager instance
            guild: Discord guild
            
        Returns:
            True if all role updates successful
        """
        try:
            success_count = 0
            
            # Update winner's roles
            winner = guild.get_member(change_data['winner_id'])
            if winner:
                winner_success, winner_message = await role_manager.assign_rank_roles(
                    winner,
                    change_data['winner_new_tier'],
                    change_data['winner_new_rank']
                )
                if winner_success:
                    success_count += 1
                    logger.info(f'Updated winner roles: {winner} -> {change_data["winner_new_tier"]} {change_data["winner_new_rank"]}')
                else:
                    logger.warning(f'Failed to update winner roles for {winner}: {winner_message}')
            else:
                logger.warning(f'Winner not found in guild: {change_data["winner_id"]}')
            
            # Update loser's roles
            loser = guild.get_member(change_data['loser_id'])
            if loser:
                loser_success, loser_message = await role_manager.assign_rank_roles(
                    loser,
                    change_data['loser_new_tier'],
                    change_data['loser_new_rank']
                )
                if loser_success:
                    success_count += 1
                    logger.info(f'Updated loser roles: {loser} -> {change_data["loser_new_tier"]} {change_data["loser_new_rank"]}')
                else:
                    logger.warning(f'Failed to update loser roles for {loser}: {loser_message}')
            else:
                logger.warning(f'Loser not found in guild: {change_data["loser_id"]}')
            
            # Return True if both role updates were successful
            return success_count == 2
            
        except Exception as e:
            logger.error(f'Error updating Discord roles: {e}')
            return False
    
    async def _send_rank_change_notifications(self, change_data: Dict[str, Any],
                                            admin: discord.Member, guild: discord.Guild) -> bool:
        """
        Send notifications about confirmed rank change
        
        Args:
            change_data: Rank change data
            admin: Admin who confirmed the change
            guild: Discord guild
            
        Returns:
            True if notifications sent successfully
        """
        try:
            # Get members for mentions
            winner = guild.get_member(change_data['winner_id'])
            loser = guild.get_member(change_data['loser_id'])
            
            # Create confirmation embed
            embed = EmbedTemplates.success_embed(
                "👑 Rank Change Confirmed",
                f"Rank change #{change_data['change_id']} has been approved"
            )
            
            embed.add_field(
                name="🏆 Winner Promotion",
                value=(
                    f"{winner.mention if winner else change_data['winner_name']}\n"
                    f"{change_data['winner_old_tier']} {change_data['winner_old_rank']} → "
                    f"**{change_data['winner_new_tier']} {change_data['winner_new_rank']}**"
                ),
                inline=False
            )
            
            embed.add_field(
                name="📉 Loser Demotion",
                value=(
                    f"{loser.mention if loser else change_data['loser_name']}\n"
                    f"{change_data['loser_old_tier']} {change_data['loser_old_rank']} → "
                    f"**{change_data['loser_new_tier']} {change_data['loser_new_rank']}**"
                ),
                inline=False
            )
            
            embed.add_field(
                name="✅ Confirmed By",
                value=admin.mention,
                inline=True
            )
            
            embed.add_field(
                name="📅 Confirmed At",
                value=f"<t:{int(datetime.now().timestamp())}:F>",
                inline=True
            )
            
            # Send to rank tracker channel
            rank_tracker_channel = guild.get_channel(CHANNELS['rank_tracker'])
            if rank_tracker_channel:
                try:
                    await rank_tracker_channel.send(embed=embed)
                    logger.info(f'Sent rank change notification to rank tracker channel')
                except Exception as e:
                    logger.warning(f'Failed to send to rank tracker channel: {e}')
                    return False
            else:
                logger.warning('Rank tracker channel not found')
                return False
            
            # Send congratulatory DM to winner
            if winner:
                try:
                    dm_embed = EmbedTemplates.success_embed(
                        "🎉 Congratulations!",
                        f"You've been promoted to **{change_data['winner_new_tier']} {change_data['winner_new_rank']}**!"
                    )
                    
                    dm_embed.add_field(
                        name="Your Achievement",
                        value=(
                            f"Previous Rank: {change_data['winner_old_tier']} {change_data['winner_old_rank']}\n"
                            f"New Rank: **{change_data['winner_new_tier']} {change_data['winner_new_rank']}**\n"
                            f"Keep dueling and climbing the ranks!"
                        ),
                        inline=False
                    )
                    
                    await winner.send(embed=dm_embed)
                    logger.info(f'Sent congratulatory DM to winner: {winner}')
                    
                except discord.Forbidden:
                    logger.info(f'Could not send DM to winner {winner} (DMs disabled)')
                except Exception as e:
                    logger.warning(f'Error sending DM to winner {winner}: {e}')
            
            # Send notification DM to loser
            if loser:
                try:
                    dm_embed = EmbedTemplates.create_base_embed(
                        title="📉 Rank Update",
                        description=f"Your rank has been updated after a recent match",
                        color=0xFFA500  # Orange color
                    )
                    
                    dm_embed.add_field(
                        name="Rank Change",
                        value=(
                            f"Previous Rank: {change_data['loser_old_tier']} {change_data['loser_old_rank']}\n"
                            f"New Rank: **{change_data['loser_new_tier']} {change_data['loser_new_rank']}**\n"
                            f"Don't give up - challenge others to climb back up!"
                        ),
                        inline=False
                    )
                    
                    await loser.send(embed=dm_embed)
                    logger.info(f'Sent rank update DM to loser: {loser}')
                    
                except discord.Forbidden:
                    logger.info(f'Could not send DM to loser {loser} (DMs disabled)')
                except Exception as e:
                    logger.warning(f'Error sending DM to loser {loser}: {e}')
            
            return True
            
        except Exception as e:
            logger.error(f'Error sending rank change notifications: {e}')
            return False
    
    async def get_pending_rank_changes_summary(self) -> Dict[str, Any]:
        """
        Get summary of all pending rank changes
        
        Returns:
            Dictionary with pending changes summary
        """
        try:
            from database.queries import DatabaseQueries
            queries = DatabaseQueries(self.db.db_path)
            pending_changes = await queries.get_pending_rank_changes()
            
            summary = {
                'total_pending': len(pending_changes),
                'by_tier': {},
                'oldest_pending': None,
                'newest_pending': None,
                'changes': pending_changes
            }
            
            if pending_changes:
                # Group by tier
                for change in pending_changes:
                    winner_tier = change['winner_new_tier']
                    if winner_tier not in summary['by_tier']:
                        summary['by_tier'][winner_tier] = 0
                    summary['by_tier'][winner_tier] += 1
                
                # Find oldest and newest
                sorted_changes = sorted(pending_changes, key=lambda x: x['created_date'])
                summary['oldest_pending'] = sorted_changes[0]
                summary['newest_pending'] = sorted_changes[-1]
            
            return summary
            
        except Exception as e:
            logger.error(f'Error getting pending rank changes summary: {e}')
            return {}
    
    async def cleanup_old_rank_changes(self, days_old: int = 30) -> int:
        """
        Clean up old processed rank changes
        
        Args:
            days_old: Days old to consider for cleanup
            
        Returns:
            Number of records cleaned up
        """
        try:
            async with self.db.get_connection() as db:
                cursor = await db.execute(
                    '''DELETE FROM pending_rank_changes 
                       WHERE status IN ('confirmed', 'rejected') 
                       AND processed_date < datetime('now', '-{} days')'''.format(days_old)
                )
                await db.commit()
                
                cleaned_count = cursor.rowcount
                logger.info(f'Cleaned up {cleaned_count} old rank change records')
                
                return cleaned_count
                
        except Exception as e:
            logger.error(f'Error cleaning up old rank changes: {e}')
            return 0