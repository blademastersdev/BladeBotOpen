"""
Evaluation Workflow
Handles the complete evaluation process for new users joining Blademasters
"""

import discord
from discord.ext import commands
import logging
from typing import Optional, Dict, Any
from database.models import Database
from systems.user_system import UserSystem
from systems.ranking_system import RankingSystem
from systems.ticket_system import TicketSystem
from utils.embeds import EmbedTemplates
from utils.role_utils import RoleManager
from config import CHANNELS, EVALUATION_RANKS

logger = logging.getLogger('BladeBot.EvaluationWorkflow')

class EvaluationWorkflow:
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.user_system = UserSystem(self.db)
        self.ranking_system = RankingSystem(self.db)
        self.ticket_system = TicketSystem(bot)
    
    async def start_evaluation_request(self, user: discord.Member, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """
        Start the evaluation process for a user
        
        Args:
            user: Discord member requesting evaluation
            guild: Discord guild
            
        Returns:
            Created evaluation ticket channel or None if failed
        """
        try:
            # Check if user is already a Blademaster
            role_manager = RoleManager(guild)
            if role_manager.has_blademaster_role(user):
                logger.info(f'User {user} is already a Blademaster, cannot request evaluation')
                return None
            
            # Register user if not already registered
            await self.user_system.ensure_user_registered(user)
            
            # Assign evaluation role if not already assigned
            evaluation_role_id = role_manager.get_tier_role_id('Evaluation')
            if evaluation_role_id:
                evaluation_role = guild.get_role(evaluation_role_id)
                if evaluation_role and evaluation_role not in user.roles:
                    try:
                        await user.add_roles(evaluation_role, reason='Evaluation request')
                        logger.info(f'Assigned evaluation role to {user}')
                    except Exception as e:
                        logger.warning(f'Could not assign evaluation role to {user}: {e}')
            
            # Create evaluation ticket
            ticket_channel = await self.ticket_system.create_evaluation_ticket(guild, user)
            
            if ticket_channel:
                logger.info(f'Created evaluation ticket for {user}: {ticket_channel.name}')
                
                # Log the evaluation request
                await self.db.log_action('evaluation_requested', user.id, f'Ticket: {ticket_channel.name}')
                
                return ticket_channel
            else:
                logger.error(f'Failed to create evaluation ticket for {user}')
                return None
            
        except Exception as e:
            logger.error(f'Error starting evaluation for {user}: {e}')
            return None
    
    async def complete_evaluation(self, user: discord.Member, tier: str, numeral: str,
                                admin: discord.Member, guild: discord.Guild) -> Dict[str, Any]:
        """
        Complete the evaluation process and place user in rank
        
        Args:
            user: Discord member being evaluated
            tier: Target tier for placement
            numeral: Target numeral for placement
            admin: Admin completing the evaluation
            guild: Discord guild
            
        Returns:
            Dictionary with completion results
        """
        try:
            result = {
                'success': False,
                'message': '',
                'placed_rank': None,
                'errors': []
            }
            
            # Validate evaluation rank
            if (tier, numeral) not in EVALUATION_RANKS:
                result['message'] = f"{tier} {numeral} is not a valid evaluation placement rank"
                return result
            
            # Check rank capacity
            capacity_info = await self.ranking_system.ranking_system.get_rank_capacity_info(tier, numeral)
            if capacity_info['is_full']:
                result['message'] = f"{tier} {numeral} is currently full"
                return result
            
            # Place user in database
            success, message = await self.ranking_system.place_user_from_evaluation(
                user.id, tier, numeral
            )
            
            if not success:
                result['message'] = message
                return result
            
            # Update Discord roles
            role_manager = RoleManager(guild)
            
            # Remove evaluation role
            removal_success = await role_manager.remove_evaluation_role(user)
            if not removal_success:
                result['errors'].append('Failed to remove evaluation role')
            
            # Assign new rank roles
            role_success, role_message = await role_manager.assign_rank_roles(
                user, tier, numeral
            )
            
            if not role_success:
                result['errors'].append(f'Failed to assign rank roles: {role_message}')
                logger.warning(f'Failed to assign Discord roles to {user}: {role_message}')
            
            # Update user profile to reflect completion
            await self.user_system.update_user_stats(user.id, won=False, elo_change=0)  # No ELO change for evaluation
            
            result['success'] = True
            result['message'] = f"Successfully placed {user.display_name} in {tier} {numeral}"
            result['placed_rank'] = f"{tier} {numeral}"
            
            # Log the completion
            await self.db.log_action(
                'evaluation_completed',
                user.id,
                f'Placed in {tier} {numeral} by {admin.display_name}'
            )
            
            logger.info(f'Evaluation completed for {user}: placed in {tier} {numeral} by {admin}')
            
            return result
            
        except Exception as e:
            logger.error(f'Error completing evaluation for {user}: {e}')
            result['message'] = f"Error completing evaluation: {e}"
            return result
    
    async def cancel_evaluation(self, user: discord.Member, reason: str, guild: discord.Guild) -> bool:
        """
        Cancel an ongoing evaluation
        
        Args:
            user: Discord member whose evaluation is being cancelled
            reason: Reason for cancellation
            guild: Discord guild
            
        Returns:
            True if cancellation successful
        """
        try:
            # Remove evaluation role
            role_manager = RoleManager(guild)
            removal_success = await role_manager.remove_evaluation_role(user)
            
            # Assign guest role instead
            guest_success = await role_manager.assign_guest_role(user)
            
            # Log the cancellation
            await self.db.log_action(
                'evaluation_cancelled',
                user.id,
                f'Reason: {reason}'
            )
            
            logger.info(f'Evaluation cancelled for {user}: {reason}')
            
            return removal_success and guest_success
            
        except Exception as e:
            logger.error(f'Error cancelling evaluation for {user}: {e}')
            return False
    
    async def get_evaluation_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about evaluations
        
        Returns:
            Dictionary with evaluation statistics
        """
        try:
            stats = {
                'total_evaluations': 0,
                'placement_distribution': {},
                'recent_evaluations': [],
                'current_evaluation_users': 0
            }
            
            # Get users currently in evaluation
            evaluation_users = await self.db.get_users_by_rank('Evaluation')
            stats['current_evaluation_users'] = len(evaluation_users)
            
            # Get evaluation completion logs
            async with self.db.get_connection() as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                
                # Total evaluations completed
                cursor = await db.execute(
                    'SELECT COUNT(*) FROM bot_logs WHERE action_type = "evaluation_completed"'
                )
                stats['total_evaluations'] = (await cursor.fetchone())[0]
                
                # Recent evaluations
                cursor = await db.execute(
                    '''SELECT bl.*, u.username 
                       FROM bot_logs bl
                       JOIN users u ON bl.user_id = u.discord_id
                       WHERE bl.action_type = "evaluation_completed"
                       ORDER BY bl.timestamp DESC
                       LIMIT 10'''
                )
                recent_evals = await cursor.fetchall()
                
                for eval_log in recent_evals:
                    # Parse placement from details
                    details = eval_log.get('details', '')
                    if 'Placed in' in details:
                        placement = details.split('Placed in')[1].split(' by')[0].strip()
                        stats['recent_evaluations'].append({
                            'username': eval_log['username'],
                            'placement': placement,
                            'timestamp': eval_log['timestamp']
                        })
                
                # Placement distribution
                for tier, numeral in EVALUATION_RANKS:
                    rank_key = f"{tier} {numeral}"
                    cursor = await db.execute(
                        'SELECT COUNT(*) FROM users WHERE tier = ? AND rank_numeral = ?',
                        (tier, numeral)
                    )
                    count = (await cursor.fetchone())[0]
                    stats['placement_distribution'][rank_key] = count
            
            return stats
            
        except Exception as e:
            logger.error(f'Error getting evaluation statistics: {e}')
            return {}
    
    async def send_evaluation_notifications(self, user: discord.Member, tier: str, numeral: str,
                                          admin: discord.Member, guild: discord.Guild):
        """
        Send notifications about completed evaluation
        
        Args:
            user: User who was evaluated
            tier: Placement tier
            numeral: Placement numeral
            admin: Admin who completed the evaluation
            guild: Discord guild
        """
        try:
            # Create notification embed
            embed = EmbedTemplates.create_base_embed(
                title="🎉 New Blademaster!",
                description=f"{user.mention} has joined the Blademasters!",
                color=0x00FF00
            )
            
            embed.add_field(
                name="Initial Rank",
                value=f"**{tier} {numeral}**",
                inline=True
            )
            
            embed.add_field(
                name="Evaluated By",
                value=admin.mention,
                inline=True
            )
            
            embed.add_field(
                name="Welcome Message",
                value=(
                    f"Welcome to the Blademasters, {user.mention}! "
                    f"You've been placed in {tier} {numeral}. "
                    f"Good luck in your dueling journey!"
                ),
                inline=False
            )
            
            # Send to rank tracker channel
            rank_tracker_channel = guild.get_channel(CHANNELS['rank_tracker'])
            if rank_tracker_channel:
                try:
                    await rank_tracker_channel.send(embed=embed)
                except Exception as e:
                    logger.warning(f'Could not send to rank tracker channel: {e}')
            
            # Send welcome DM to user
            try:
                dm_embed = EmbedTemplates.create_base_embed(
                    title="🎉 Welcome to the Blademasters!",
                    description=f"You've been placed in **{tier} {numeral}**",
                    color=0x00FF00
                )
                
                dm_embed.add_field(
                    name="Next Steps",
                    value=(
                        "• Explore the Blademaster channels\n"
                        "• Challenge others to friendly duels\n"
                        "• Work your way up the ranks!\n"
                        "• Use `?help` to see all commands"
                    ),
                    inline=False
                )
                
                await user.send(embed=dm_embed)
                
            except discord.Forbidden:
                logger.info(f'Could not send welcome DM to {user} (DMs disabled)')
            except Exception as e:
                logger.warning(f'Error sending welcome DM to {user}: {e}')
            
        except Exception as e:
            logger.error(f'Error sending evaluation notifications: {e}')
    
    async def handle_evaluation_button_click(self, interaction: discord.Interaction):
        """
        Handle evaluation request button clicks
        
        Args:
            interaction: Discord button interaction
        """
        try:
            user = interaction.user
            guild = interaction.guild
            
            # Check if user is already in evaluation or is a Blademaster
            role_manager = RoleManager(guild)
            user_tier = role_manager.get_member_tier_from_roles(user)
            
            if user_tier in ['Bronze', 'Silver', 'Gold', 'Platinum', 'Diamond']:
                await interaction.response.send_message(
                    "❌ You are already a Blademaster!", ephemeral=True
                )
                return
            
            if user_tier == 'Evaluation':
                await interaction.response.send_message(
                    "⚠️ You already have an active evaluation request!", ephemeral=True
                )
                return
            
            # Start evaluation process
            ticket_channel = await self.start_evaluation_request(user, guild)
            
            if ticket_channel:
                await interaction.response.send_message(
                    f"✅ Evaluation ticket created: {ticket_channel.mention}\n"
                    f"An admin will be with you shortly!",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ Failed to create evaluation ticket. Please try again later.",
                    ephemeral=True
                )
            
        except Exception as e:
            logger.error(f'Error handling evaluation button click: {e}')
            try:
                await interaction.response.send_message(
                    "❌ An error occurred while processing your request.",
                    ephemeral=True
                )
            except:
                pass