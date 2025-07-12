"""
Duel Commands - Refactored
Contains the new ?duel command category with sub-commands for challenging
Also includes existing accept/decline functionality
"""

import discord
from discord.ext import commands
import asyncio
import aiosqlite
import logging
from datetime import datetime, timedelta
from typing import Optional
from database.models import Database
from systems.user_system import UserSystem
from systems.challenge_system import ChallengeSystem
from systems.ranking_system import RankingSystem
from systems.ticket_system import TicketSystem
from utils.embeds import EmbedTemplates
from utils.validators import Validators
from utils.role_utils import RoleManager
from config import TIER_ROLES, RANK_ROLES, CHANNELS, DUEL_COMMAND_CHANNELS, get_next_rank

logger = logging.getLogger('BladeBot.DuelCommands')

async def setup_duel_commands(bot):
    """Setup duel commands for the bot"""
    await bot.add_cog(DuelCommands(bot))

def duel_channel_required():
    """Standard check decorator for channel restrictions"""
    async def predicate(ctx):
        cog = ctx.cog
        if hasattr(cog, '_check_duel_channel_permissions'):
            channel_allowed, _ = await cog._check_duel_channel_permissions(ctx)
            return channel_allowed
        return True
    return commands.check(predicate)

class DuelCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.user_system = UserSystem(self.db)
        self.ranking_system = RankingSystem(self.db)
        self.challenge_system = ChallengeSystem(
            self.db, self.user_system, self.ranking_system
        )
        self.ticket_system = TicketSystem(bot)

    async def _check_duel_channel_permissions(self, ctx) -> tuple[bool, str]:
        """
        Check if duel commands are allowed in current channel
        
        Returns:
            Tuple of (allowed, error_message)
        """
        logger.info(f"Checking channel permissions for channel {ctx.channel.id} ({ctx.channel.name})")
        
        # Check if user has admin permissions (bypass restriction)
        if DUEL_COMMAND_CHANNELS.get('admin_override', True):
            if ctx.author.guild_permissions.administrator:
                logger.info(f"User {ctx.author} has admin permissions - bypassing restriction")
                return True, ""
        
        # Check if in allowed channels
        allowed_channels = DUEL_COMMAND_CHANNELS.get('allowed_channels', [])
        logger.info(f"Allowed channels: {allowed_channels}")
        
        if ctx.channel.id in allowed_channels:
            logger.info(f"Channel {ctx.channel.id} is in allowed channels")
            return True, ""
        
        # Check if it's a ticket channel (if allowed)
        if DUEL_COMMAND_CHANNELS.get('allow_ticket_channels', True):
            if hasattr(self.ticket_system, 'is_duel_ticket_channel'):
                is_ticket = self.ticket_system.is_duel_ticket_channel(ctx.channel.id)
                logger.info(f"Is ticket channel: {is_ticket}")
                if is_ticket:
                    return True, ""
            else:
                logger.warning("ticket_system.is_duel_ticket_channel method not found")
        
        # Not allowed - build error message
        allowed_channel_mentions = []
        for channel_id in allowed_channels:
            channel = ctx.guild.get_channel(channel_id)
            if channel:
                allowed_channel_mentions.append(channel.mention)
        
        error_msg = f"Duel commands are only allowed in: {', '.join(allowed_channel_mentions)}"
        if DUEL_COMMAND_CHANNELS.get('allow_ticket_channels', True):
            error_msg += " or in duel ticket channels"
        
        logger.info(f"Channel restriction failed: {error_msg}")
        return False, error_msg

    # ============================================================================
    # NEW REFACTORED ?DUEL COMMAND CATEGORY
    # ============================================================================

    @duel_channel_required()
    @commands.group(name='duel', aliases=['challenge'], invoke_without_subcommand=True)
    async def duel_command(self, ctx):
        """
        Duel challenge commands with interactive menu
        """
        logger.info(f"Duel command called in channel {ctx.channel.id} ({ctx.channel.name}) by {ctx.author}")
        
        # RESTRICTION CHECK - applies to ALL subcommands automatically
        channel_allowed, channel_error = await self._check_duel_channel_permissions(ctx)
        logger.info(f"Channel check result: allowed={channel_allowed}, error='{channel_error}'")
        
        if not channel_allowed:
            embed = EmbedTemplates.error_embed(
                "Channel Restricted",
                channel_error
            )
            await ctx.send(embed=embed)
            return
        
        if ctx.invoked_subcommand is None:
            # Interactive menu for duel types
            embed = EmbedTemplates.create_base_embed(
                title="⚔️ Duel Challenge Menu",
                description="Select the type of duel you want to request:",
                color=0xFF6B6B
            )
            
            embed.add_field(
                name="🤝 1️⃣ Friendly Duel",
                value="No stakes, not logged - Pure practice",
                inline=False
            )
            
            embed.add_field(
                name="⚡ 2️⃣ Official Duel",
                value="Affects ELO rating - Competitive match",
                inline=False
            )
            
            embed.add_field(
                name="👑 3️⃣ BM Duel",
                value="Affects ELO and rank - Advancement match",
                inline=False
            )
            
            embed.set_footer(text="React with the corresponding emoji or ❌ to cancel")
            
            message = await ctx.send(embed=embed)
            
            # Add reactions
            reactions = ['1️⃣', '2️⃣', '3️⃣', '❌']
            for reaction in reactions:
                await message.add_reaction(reaction)
            
            try:
                def check(reaction, user):
                    return (user == ctx.author and 
                        str(reaction.emoji) in reactions and 
                        reaction.message.id == message.id)
                
                reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                
                await message.delete()
                
                if str(reaction.emoji) == '1️⃣':
                    await self.duel_friendly(ctx, None)
                elif str(reaction.emoji) == '2️⃣':
                    await self.duel_official(ctx, None)
                elif str(reaction.emoji) == '3️⃣':
                    await self.duel_bm(ctx, None)
                elif str(reaction.emoji) == '❌':
                    embed = EmbedTemplates.create_base_embed(
                        title="❌ Cancelled",
                        description="Duel request cancelled",
                        color=0x808080
                    )
                    await ctx.send(embed=embed, delete_after=5)
                    
            except asyncio.TimeoutError:
                await message.delete()
                embed = EmbedTemplates.error_embed(
                    "Timeout",
                    "Duel type selection timed out after 60 seconds"
                )
                await ctx.send(embed=embed, delete_after=5)
            except Exception as e:
                logger.error(f'Error in duel command interaction: {e}')
                await message.delete()
                embed = EmbedTemplates.error_embed(
                    "Error",
                    f"An error occurred: {str(e)}"
                )
                await ctx.send(embed=embed)

    @duel_command.command(name='official', aliases=['o'])
    async def duel_official(self, ctx, target: Optional[discord.Member] = None):
        """
        Challenge to an official duel (affects ELO)
        Usage: ?duel official [@user]
        """
        try:
            # Check if user already has an active duel ticket
            if self.ticket_system.user_has_active_duel_ticket(ctx.author.id):
                embed = EmbedTemplates.error_embed(
                    "Active Duel Found",
                    "You already have an active duel ticket! Complete your current duel before starting a new one."
                )
                await ctx.send(embed=embed)
                return
            
            # Ensure user is registered
            await self.user_system.ensure_user_registered(ctx.author)
            
            if target:
                # Specific user challenge
                if target == ctx.author:
                    embed = EmbedTemplates.error_embed(
                        "Invalid Target",
                        "You cannot challenge yourself to a duel!"
                    )
                    await ctx.send(embed=embed)
                    return
                
                if target.bot:
                    embed = EmbedTemplates.error_embed(
                        "Invalid Target",
                        "You cannot challenge a bot to a duel!"
                    )
                    await ctx.send(embed=embed)
                    return
                
                # Ensure target is registered
                await self.user_system.ensure_user_registered(target)
                
                # Use proper workflow system
                from workflows.duel_workflows import DuelWorkflows
                duel_workflows = DuelWorkflows(self.bot)
                
                workflow_result = await duel_workflows.process_complete_duel_workflow(
                    challenge_type='official',
                    challenger=ctx.author,
                    challenged=target,
                    guild=ctx.guild
                )
                
                if workflow_result['success']:
                    embed = EmbedTemplates.create_base_embed(
                        title="⚡ Official Duel Challenge Sent!",
                        description=f"{target.mention}, you have been challenged to an **official duel** by {ctx.author.mention}!",
                        color=0xFF9800
                    )
                    
                    embed.add_field(
                        name="⚔️ Duel Type",
                        value="**Official** - Affects ELO rating",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="📝 Challenge ID",
                        value=f"#{workflow_result['challenge_id']}",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="🎯 How to Respond",
                        value=f"Use `?accept` or `?decline` to respond",
                        inline=False
                    )
                    
                    embed.set_footer(text="This challenge will expire in 1 week.")
                    await ctx.send(embed=embed)
                    
                else:
                    embed = EmbedTemplates.error_embed(
                        "Challenge Failed",
                        workflow_result.get('message', 'Unknown error occurred')
                    )
                    await ctx.send(embed=embed)
            
            else:
                # General challenge - Use proper workflow system
                from workflows.duel_workflows import DuelWorkflows
                duel_workflows = DuelWorkflows(self.bot)
                
                workflow_result = await duel_workflows.process_complete_duel_workflow(
                    challenge_type='official',
                    challenger=ctx.author,
                    challenged=None,  # General challenge
                    guild=ctx.guild
                )
                
                if workflow_result['success']:
                    # Create general challenge embed
                    embed = EmbedTemplates.create_base_embed(
                        title="⚡ Official Duel Request",
                        description=f"{ctx.author.mention} is looking for an **official duel**!",
                        color=0xFF9800
                    )
                    
                    embed.add_field(
                        name="⚔️ Duel Type",
                        value="**Official** - Affects ELO rating",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="📝 Challenge ID",
                        value=f"#{workflow_result['challenge_id']}",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="🎯 How to Accept",
                        value="React with ⚔️ or use `?accept` to join!",
                        inline=False
                    )
                    
                    embed.set_footer(text="This challenge will expire in 1 week.")
                    
                    # Send with ping role if available
                    content = ""
                    if workflow_result.get('ping_role'):
                        content = workflow_result['ping_role'].mention
                    
                    message = await ctx.send(content=content, embed=embed)
                    await message.add_reaction('⚔️')
                    
                else:
                    embed = EmbedTemplates.error_embed(
                        "Challenge Failed",
                        workflow_result.get('message', 'Unknown error occurred')
                    )
                    await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f'Error in official duel command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred while creating the official duel: {str(e)}"
            )
            await ctx.send(embed=embed)

    @duel_command.command(name='friendly', aliases=['f'])
    async def duel_friendly(self, ctx, target: Optional[discord.Member] = None):
        """
        Challenge to a friendly duel (no stakes)
        Usage: ?duel friendly [@user]
        """
        try:
            # Check if user already has an active duel ticket
            if self.ticket_system.user_has_active_duel_ticket(ctx.author.id):
                embed = EmbedTemplates.error_embed(
                    "Active Duel Found",
                    "You already have an active duel ticket! Complete your current duel before starting a new one."
                )
                await ctx.send(embed=embed)
                return
            
            # Ensure user is registered
            await self.user_system.ensure_user_registered(ctx.author)
            
            if target:
                # Specific user challenge
                if target == ctx.author:
                    embed = EmbedTemplates.error_embed(
                        "Invalid Target",
                        "You cannot challenge yourself to a duel!"
                    )
                    await ctx.send(embed=embed)
                    return
                
                if target.bot:
                    embed = EmbedTemplates.error_embed(
                        "Invalid Target",
                        "You cannot challenge a bot to a duel!"
                    )
                    await ctx.send(embed=embed)
                    return
                
                # Ensure target is registered
                await self.user_system.ensure_user_registered(target)
                
                # Use proper workflow system
                from workflows.duel_workflows import DuelWorkflows
                duel_workflows = DuelWorkflows(self.bot)
                
                workflow_result = await duel_workflows.process_complete_duel_workflow(
                    challenge_type='friendly',
                    challenger=ctx.author,
                    challenged=target,
                    guild=ctx.guild
                )
                
                if workflow_result['success']:
                    embed = EmbedTemplates.create_base_embed(
                        title="🤝 Friendly Duel Challenge Sent!",
                        description=f"{target.mention}, you have been challenged to a **friendly duel** by {ctx.author.mention}!",
                        color=0x4CAF50
                    )
                    
                    embed.add_field(
                        name="⚔️ Duel Type",
                        value="**Friendly** - No stakes, not logged",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="📝 Challenge ID",
                        value=f"#{workflow_result['challenge_id']}",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="🎯 How to Respond",
                        value=f"Use `?accept` or `?decline` to respond",
                        inline=False
                    )
                    
                    embed.set_footer(text="This challenge will expire in 1 week.")
                    await ctx.send(embed=embed)
                    
                else:
                    embed = EmbedTemplates.error_embed(
                        "Challenge Failed",
                        workflow_result.get('message', 'Unknown error occurred')
                    )
                    await ctx.send(embed=embed)
            
            else:
                # General challenge
                from workflows.duel_workflows import DuelWorkflows
                duel_workflows = DuelWorkflows(self.bot)
                
                workflow_result = await duel_workflows.process_complete_duel_workflow(
                    challenge_type='friendly',
                    challenger=ctx.author,
                    challenged=None,  # General challenge
                    guild=ctx.guild
                )
                
                if workflow_result['success']:
                    embed = EmbedTemplates.create_base_embed(
                        title="🤝 Friendly Duel Request",
                        description=f"{ctx.author.mention} is looking for a **friendly duel**!",
                        color=0x4CAF50
                    )
                    
                    embed.add_field(
                        name="⚔️ Duel Type",
                        value="**Friendly** - No stakes, not logged",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="📝 Challenge ID",
                        value=f"#{workflow_result['challenge_id']}",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="🎯 How to Accept",
                        value="React with ⚔️ or use `?accept` to join!",
                        inline=False
                    )
                    
                    # Send with ping role if available
                    content = ""
                    if workflow_result.get('ping_role'):
                        content = workflow_result['ping_role'].mention
                    
                    message = await ctx.send(content=content, embed=embed)
                    await message.add_reaction('⚔️')
                    
                else:
                    embed = EmbedTemplates.error_embed(
                        "Challenge Failed",
                        workflow_result.get('message', 'Unknown error occurred')
                    )
                    await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f'Error in friendly duel command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred while creating the friendly duel: {str(e)}"
            )
            await ctx.send(embed=embed)

    @duel_command.command(name='bm', aliases=['blademaster'])
    async def duel_bm(self, ctx, target: Optional[discord.Member] = None):
        """
        Create a BM duel challenge
        Usage: ?duel bm [@user]
        """
        try:
            # Check if user is in evaluation
            user_data = await self.user_system.get_user_profile(ctx.author.id)
            if user_data and user_data.get('tier') == 'Evaluation':
                embed = EmbedTemplates.error_embed(
                    "Evaluation Status",
                    "You cannot participate in BM duels while in evaluation. Complete evaluation first!"
                )
                await ctx.send(embed=embed)
                return
            
            # Check if user already has an active duel ticket
            if self.ticket_system.user_has_active_duel_ticket(ctx.author.id):
                embed = EmbedTemplates.error_embed(
                    "Active Duel Found",
                    "You already have an active duel ticket! Complete your current duel before starting a new one."
                )
                await ctx.send(embed=embed)
                return
            
            # Check cooldown
            user_data = await self.user_system.get_user_profile(ctx.author.id)
            if user_data and user_data.get('last_challenge_date'):
                from datetime import datetime, timedelta
                last_challenge = datetime.fromisoformat(user_data['last_challenge_date'])
                time_since = datetime.now() - last_challenge
                
                if time_since < timedelta(hours=24):
                    remaining_hours = 24 - (time_since.total_seconds() / 3600)
                    embed = EmbedTemplates.error_embed(
                        "Cooldown Active",
                        f"You can challenge again in {remaining_hours:.1f} hours"
                    )
                    await ctx.send(embed=embed)
                    return
            
            # Ensure user is registered
            await self.user_system.ensure_user_registered(ctx.author)
            
            if target:
                # Specific user challenge - validate rank restrictions
                if target == ctx.author:
                    embed = EmbedTemplates.error_embed(
                        "Invalid Target",
                        "You cannot challenge yourself to a duel!"
                    )
                    await ctx.send(embed=embed)
                    return
                
                if target.bot:
                    embed = EmbedTemplates.error_embed(
                        "Invalid Target",
                        "You cannot challenge a bot to a duel!"
                    )
                    await ctx.send(embed=embed)
                    return
                
                # Check if target is a Blademaster - FIXED: Use correct method name
                role_manager = RoleManager(ctx.guild)
                if not role_manager.has_blademaster_role(target):
                    embed = EmbedTemplates.error_embed(
                        "Invalid Target",
                        f"{target.display_name} is not a Blademaster and cannot participate in BM duels"
                    )
                    await ctx.send(embed=embed)
                    return
                
                # Ensure target is registered
                await self.user_system.ensure_user_registered(target)
                
                # Validate rank progression rules
                rank_validation = await self.ranking_system.validate_bm_challenge(ctx.author, target)
                if not rank_validation['valid']:
                    embed = EmbedTemplates.error_embed(
                        "Invalid Challenge",
                        rank_validation.get('error', 'You can only challenge users in the rank directly above you')
                    )
                    await ctx.send(embed=embed)
                    return
                
                # Create challenge
                success, message, challenge_id = await self.challenge_system.create_challenge(
                    challenger=ctx.author,
                    challenged=target,
                    challenge_type='bm',
                    guild=ctx.guild  # ADDED: Missing guild parameter
                )
                
                if success:
                    embed = EmbedTemplates.create_base_embed(
                        title="👑 BM Duel Challenge Sent!",
                        description=f"{target.mention}, you have been challenged to a **BM duel** by {ctx.author.mention}!",
                        color=0x9C27B0
                    )
                    
                    embed.add_field(
                        name="⚔️ Duel Type",
                        value="**Blademaster** - Affects ELO and rank",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="📝 Challenge ID",
                        value=f"#{challenge_id}",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="🏆 Stakes",
                        value="Winner advances, loser drops rank",
                        inline=False
                    )
                    
                    embed.add_field(
                        name="🎯 How to Respond",
                        value=f"Use `?accept` or `?decline` to respond",
                        inline=False
                    )
                    
                    embed.set_footer(text="This challenge will expire in 1 week.")
                    
                    await ctx.send(embed=embed)
                    
                else:
                    embed = EmbedTemplates.error_embed(
                        "Challenge Failed",
                        message
                    )
                    await ctx.send(embed=embed)
            
            else:
                # General challenge - ping rank above
                challenger_data = await self.db.get_user(ctx.author.id)
                if not challenger_data:
                    embed = EmbedTemplates.error_embed(
                        "Rank Error",
                        "Could not determine your current rank"
                    )
                    await ctx.send(embed=embed)
                    return
                
                # Get rank above using the FIXED get_next_rank function
                from config import get_next_rank
                rank_above = get_next_rank(
                    challenger_data['tier'], 
                    challenger_data['rank_numeral']
                )
                
                if not rank_above or not rank_above[0]:
                    embed = EmbedTemplates.error_embed(
                        "No Valid Targets",
                        "You are already at the highest rank!"
                    )
                    await ctx.send(embed=embed)
                    return
                
                # Create general BM challenge - ensure it's detectable by ?accept
                success, message, challenge_id = await self.challenge_system.create_challenge(
                    challenger=ctx.author,
                    challenged=None,  # General challenge
                    challenge_type='bm',
                    guild=ctx.guild  # ADDED: Missing guild parameter
                )
                
                if not success:
                    embed = EmbedTemplates.error_embed(
                        "Challenge Failed",
                        message
                    )
                    await ctx.send(embed=embed)
                    return
                
                # Get role for rank above
                rank_role_id = RANK_ROLES.get(rank_above)
                rank_role = ctx.guild.get_role(rank_role_id) if rank_role_id else None
                
                embed = EmbedTemplates.create_base_embed(
                    title="👑 BM Duel Request",
                    description=f"{ctx.author.mention} ({challenger_data['tier']} {challenger_data['rank_numeral']}) is looking for a **BM duel**!",
                    color=0x9C27B0
                )
                
                embed.add_field(
                    name="⚔️ Duel Type",
                    value="**Blademaster** - Affects ELO and rank",
                    inline=True
                )
                
                embed.add_field(
                    name="🎯 Target Rank",
                    value=f"{rank_above[0]} {rank_above[1]}",
                    inline=True
                )
                
                embed.add_field(
                    name="📝 Challenge ID",
                    value=f"#{challenge_id}",
                    inline=True
                )
                
                embed.add_field(
                    name="🏆 Stakes",
                    value="Winner advances, loser drops rank",
                    inline=False
                )
                
                embed.add_field(
                    name="🎯 How to Accept",
                    value="React with ⚔️ or use `?accept` to join!",
                    inline=False
                )
                
                # Ping appropriate rank role
                content = ""
                if rank_role:
                    content = rank_role.mention
                
                message = await ctx.send(content=content, embed=embed)
                await message.add_reaction('⚔️')
                
        except Exception as e:
            logger.error(f'Error in BM duel command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred while creating the BM duel: {str(e)}"
            )
            await ctx.send(embed=embed)

    @duel_command.command(name='cancel', aliases=['c'])
    async def duel_cancel(self, ctx):
        """
        Cancel your active challenges
        Usage: ?duel cancel
        """
        try:
            # Ensure user is registered
            await self.user_system.ensure_user_registered(ctx.author)
            
            # Get user's active challenges
            user_challenges = await self.challenge_system.get_active_challenges_for_user(ctx.author.id)
            
            # Filter to only challenges created by this user
            user_created_challenges = [
                c for c in user_challenges 
                if c['challenger_id'] == ctx.author.id and c['status'] == 'pending'
            ]
            
            if not user_created_challenges:
                embed = EmbedTemplates.error_embed(
                    "No Active Challenges",
                    "You have no active challenges to cancel."
                )
                await ctx.send(embed=embed)
                return
            
            if len(user_created_challenges) == 1:
                # Single challenge - cancel it directly
                challenge = user_created_challenges[0]
                
                # Update challenge status to cancelled
                success = await self.db.update_challenge(
                    challenge['challenge_id'], 
                    status='cancelled'
                )
                
                if success:
                    # FIXED: Try to find and update the original challenge embed with fallback channel
                    await self._update_challenge_embed_cancelled(challenge, ctx.channel)
                    
                    target_info = "general challenge"
                    if challenge['challenged_id']:
                        target_member = ctx.guild.get_member(challenge['challenged_id'])
                        target_info = f"challenge to {target_member.display_name if target_member else 'Unknown'}"
                    
                    embed = EmbedTemplates.create_base_embed(
                        title="❌ Challenge Cancelled",
                        description=f"Your **{challenge['challenge_type']}** {target_info} has been cancelled.",
                        color=0xFF5722
                    )
                    
                    embed.add_field(
                        name="📝 Challenge ID",
                        value=f"#{challenge['challenge_id']}",
                        inline=True
                    )
                    
                    await ctx.send(embed=embed)
                else:
                    embed = EmbedTemplates.error_embed(
                        "Error",
                        "Failed to cancel the challenge."
                    )
                    await ctx.send(embed=embed)
            else:
                # Multiple challenges - show interactive menu with "cancel all" option
                embed = EmbedTemplates.create_base_embed(
                    title="🗂️ Your Active Challenges",
                    description="React with the number to cancel a specific challenge:",
                    color=0xFF6B6B
                )
                
                emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']
                
                for i, challenge in enumerate(user_created_challenges[:5]):
                    target_info = "General Challenge"
                    if challenge['challenged_id']:
                        target_member = ctx.guild.get_member(challenge['challenged_id'])
                        target_info = f"vs {target_member.display_name if target_member else 'Unknown'}"
                    
                    field_value = (
                        f"**Target:** {target_info}\n"
                        f"**Type:** {challenge['challenge_type'].title()}\n"
                        f"**Created:** {challenge['created_date'][:16]}"
                    )
                    
                    embed.add_field(
                        name=f"{emojis[i]} Challenge #{challenge['challenge_id']}",
                        value=field_value,
                        inline=False
                    )
                
                # Add "Cancel All" option
                embed.add_field(
                    name="❌ Cancel All Challenges",
                    value="React with ❌ to cancel all your pending challenges",
                    inline=False
                )
                
                message = await ctx.send(embed=embed)
                
                # Add reactions
                for i in range(min(len(user_created_challenges), 5)):
                    await message.add_reaction(emojis[i])
                await message.add_reaction("❌")
                
                # Wait for reaction
                def check(reaction, user):
                    return (user == ctx.author and 
                        str(reaction.emoji) in emojis[:len(user_created_challenges)] + ["❌"] and 
                        reaction.message.id == message.id)
                
                try:
                    reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
                    
                    if str(reaction.emoji) == "❌":
                        # Handle "Cancel All" functionality
                        cancelled_count = 0
                        failed_cancellations = []
                        
                        for challenge in user_created_challenges:
                            success = await self.db.update_challenge(
                                challenge['challenge_id'], 
                                status='cancelled'
                            )
                            if success:
                                cancelled_count += 1
                                # FIXED: Try to update original embed for each cancelled challenge with fallback channel
                                await self._update_challenge_embed_cancelled(challenge, ctx.channel)
                            else:
                                failed_cancellations.append(f"#{challenge['challenge_id']}")
                        
                        # Build result message
                        if cancelled_count > 0:
                            embed = EmbedTemplates.create_base_embed(
                                title="✅ Bulk Cancellation Complete",
                                description=f"Successfully cancelled {cancelled_count} challenge(s).",
                                color=0x00FF00
                            )
                            
                            if failed_cancellations:
                                embed.add_field(
                                    name="⚠️ Failed Cancellations",
                                    value=", ".join(failed_cancellations),
                                    inline=False
                                )
                        else:
                            embed = EmbedTemplates.error_embed(
                                "Cancellation Failed",
                                "No challenges could be cancelled."
                            )
                        
                        await message.edit(embed=embed)
                        await message.clear_reactions()
                    else:
                        # Cancel specific challenge
                        selected_index = emojis.index(str(reaction.emoji))
                        selected_challenge = user_created_challenges[selected_index]
                        
                        success = await self.db.update_challenge(
                            selected_challenge['challenge_id'], 
                            status='cancelled'
                        )
                        
                        if success:
                            # FIXED: Try to find and update the original challenge embed with fallback channel
                            await self._update_challenge_embed_cancelled(selected_challenge, ctx.channel)
                            
                            target_info = "general challenge"
                            if selected_challenge['challenged_id']:
                                target_member = ctx.guild.get_member(selected_challenge['challenged_id'])
                                target_info = f"challenge to {target_member.display_name if target_member else 'Unknown'}"
                            
                            embed = EmbedTemplates.create_base_embed(
                                title="❌ Challenge Cancelled",
                                description=f"Your **{selected_challenge['challenge_type']}** {target_info} has been cancelled.",
                                color=0xFF5722
                            )
                            
                            embed.add_field(
                                name="📝 Challenge ID",
                                value=f"#{selected_challenge['challenge_id']}",
                                inline=True
                            )
                            
                            await message.edit(embed=embed)
                            await message.clear_reactions()
                        else:
                            embed = EmbedTemplates.error_embed(
                                "Error",
                                "Failed to cancel the challenge."
                            )
                            await message.edit(embed=embed)
                            await message.clear_reactions()
                            
                except asyncio.TimeoutError:
                    timeout_embed = EmbedTemplates.error_embed(
                        "Timeout",
                        "Challenge cancellation timed out."
                    )
                    await message.edit(embed=timeout_embed)
                    await message.clear_reactions()
                
        except Exception as e:
            logger.error(f'Error in duel cancel command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred while cancelling the challenge: {str(e)}"
            )
            await ctx.send(embed=embed)

    async def _update_challenge_embed_cancelled(self, challenge, fallback_channel=None):
        """
        Try to find and update the original challenge embed to show it was cancelled
        
        Args:
            challenge: Challenge data dictionary
            fallback_channel: Optional fallback channel to search if no channel_id stored
        """
        try:
            channel = None
            
            # Try to get the stored channel first (if it exists)
            if challenge.get('channel_id'):
                channel = self.bot.get_channel(challenge['channel_id'])
            
            # If no stored channel or channel not found, use fallback
            if not channel and fallback_channel:
                channel = fallback_channel
            
            # If still no channel, exit gracefully
            if not channel:
                logger.warning(f'No channel found for updating cancelled challenge embed: {challenge["challenge_id"]}')
                return
            
            # Look through recent messages for the challenge embed
            search_limit = 100
            async for message in channel.history(limit=search_limit):
                if (message.embeds and 
                    message.author == self.bot.user and
                    any(field.name == "📝 Challenge ID" and 
                        field.value == f"#{challenge['challenge_id']}" 
                        for field in message.embeds[0].fields)):
                    
                    # Found the original challenge embed - update it
                    cancelled_embed = EmbedTemplates.create_base_embed(
                        title="❌ Challenge Cancelled",
                        description=f"This **{challenge['challenge_type']}** challenge has been cancelled by the challenger.",
                        color=0x607D8B
                    )
                    
                    cancelled_embed.add_field(
                        name="📝 Challenge ID",
                        value=f"#{challenge['challenge_id']}",
                        inline=True
                    )
                    
                    cancelled_embed.add_field(
                        name="⏰ Cancelled At",
                        value=f"<t:{int(datetime.now().timestamp())}:R>",
                        inline=True
                    )
                    
                    cancelled_embed.set_footer(text="This challenge is no longer available")
                    
                    try:
                        await message.edit(embed=cancelled_embed)
                        await message.clear_reactions()
                        logger.info(f'Successfully updated cancelled challenge embed for challenge {challenge["challenge_id"]}')
                        return
                    except Exception as edit_error:
                        logger.warning(f'Could not edit challenge embed {challenge["challenge_id"]}: {edit_error}')
                    
            logger.info(f'Challenge embed not found in recent {search_limit} messages for challenge {challenge["challenge_id"]}')
                    
        except Exception as e:
            logger.error(f'Error updating cancelled challenge embed: {e}')

    # ============================================================================
    # EXISTING ACCEPT/DECLINE COMMANDS (Enhanced)
    # ============================================================================
    
    @duel_channel_required()
    @commands.command(name='accept', aliases=['acc', 'a'])
    async def accept_challenge(self, ctx, target_user: Optional[discord.Member] = None, challenge_type: Optional[str] = None):
        """
        Accept a challenge or show menu of available challenges
        Usage: ?accept [@user] [official/friendly]
        """
        try:
            logger.info(f"Accept command called by {ctx.author} with target={target_user}, type={challenge_type}")
            
            # Check if user has an active duel ticket already
            if self.ticket_system.user_has_active_duel_ticket(ctx.author.id):
                embed = EmbedTemplates.warning_embed(
                    "Active Duel in Progress",
                    "Complete your current duel before accepting new challenges."
                )
                await ctx.send(embed=embed)
                return
            
            # Ensure user is registered
            await self.user_system.ensure_user_registered(ctx.author)
            
            # Check if this is a reply to a challenge embed
            if ctx.message.reference and ctx.message.reference.message_id:
                try:
                    replied_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                    
                    if (replied_message.embeds and 
                        replied_message.author == self.bot.user):
                        
                        embed = replied_message.embeds[0]
                        
                        # Extract challenge ID from embed fields
                        challenge_id = None
                        for field in embed.fields:
                            if field.name == "📝 Challenge ID":
                                challenge_id = int(field.value.replace("#", ""))
                                break
                        
                        if challenge_id:
                            # Get challenge details
                            challenge_data = await self.challenge_system.db.get_challenge(challenge_id)
                            
                            if challenge_data and challenge_data['status'] == 'pending':
                                # Check if user can accept this challenge
                                if (challenge_data['challenger_id'] != ctx.author.id and
                                    (challenge_data['challenged_id'] is None or challenge_data['challenged_id'] == ctx.author.id)):
                                    
                                    # Process the challenge acceptance directly
                                    from workflows.duel_workflows import DuelWorkflows
                                    duel_workflows = DuelWorkflows(self.bot)
                                    
                                    acceptance_result = await duel_workflows.process_challenge_acceptance(
                                        accepter=ctx.author,
                                        challenge_id=challenge_id,
                                        guild=ctx.guild
                                    )
                                    
                                    if acceptance_result['success']:
                                        challenger = ctx.guild.get_member(challenge_data['challenger_id'])
                                        challenger_name = challenger.display_name if challenger else "Unknown"
                                        
                                        # Send success message
                                        feedback_embed = EmbedTemplates.create_base_embed(
                                            title="✅ Challenge Accepted!",
                                            description=f"You have accepted {challenger_name}'s **{challenge_data['challenge_type']}** duel challenge!",
                                            color=0x00FF00
                                        )
                                        
                                        feedback_embed.add_field(
                                            name="📝 Challenge ID",
                                            value=f"#{challenge_id}",
                                            inline=True
                                        )
                                        
                                        if acceptance_result.get('ticket_channel'):
                                            feedback_embed.add_field(
                                                name="🎫 Ticket Channel",
                                                value=f"{acceptance_result['ticket_channel'].mention}",
                                                inline=True
                                            )
                                        
                                        await ctx.send(embed=feedback_embed)
                                        
                                        # Update the original challenge embed
                                        accepted_embed = EmbedTemplates.create_base_embed(
                                            title="✅ Challenge Accepted!",
                                            description=f"**{ctx.author.display_name}** has accepted this **{challenge_data['challenge_type']}** duel challenge!",
                                            color=0x00FF00
                                        )
                                        
                                        accepted_embed.add_field(
                                            name="📝 Challenge ID",
                                            value=f"#{challenge_id}",
                                            inline=True
                                        )
                                        
                                        accepted_embed.add_field(
                                            name="⏰ Accepted At",
                                            value=f"<t:{int(datetime.now().timestamp())}:R>",
                                            inline=True
                                        )
                                        
                                        if acceptance_result.get('ticket_channel'):
                                            accepted_embed.add_field(
                                                name="🎫 Ticket Channel",
                                                value=f"{acceptance_result['ticket_channel'].mention}",
                                                inline=True
                                            )
                                        
                                        accepted_embed.set_footer(text="This challenge has been accepted")
                                        
                                        try:
                                            await replied_message.edit(embed=accepted_embed)
                                            await replied_message.clear_reactions()
                                        except Exception as edit_error:
                                            logger.warning(f'Could not edit original challenge embed: {edit_error}')
                                        
                                        return  # Exit early since we handled the reply
                                    else:
                                        # Send the error embed from the workflow
                                        if acceptance_result.get('embed'):
                                            await ctx.send(embed=acceptance_result['embed'])
                                        else:
                                            embed = EmbedTemplates.error_embed(
                                                "Acceptance Failed",
                                                acceptance_result.get('message', 'Failed to accept challenge')
                                            )
                                            await ctx.send(embed=embed)
                                        return
                                else:
                                    embed = EmbedTemplates.error_embed(
                                        "Cannot Accept",
                                        "You cannot accept your own challenge or this challenge is not for you."
                                    )
                                    await ctx.send(embed=embed)
                                    return
                            else:
                                embed = EmbedTemplates.error_embed(
                                    "Challenge Not Found",
                                    "This challenge is no longer active or doesn't exist."
                                )
                                await ctx.send(embed=embed)
                                return
                        
                except Exception as e:
                    logger.error(f'Error processing replied message: {e}')

            # Find challenges this user can accept
            all_challenges = await self.challenge_system.get_active_challenges_for_user(ctx.author.id)
            
            # Filter to challenges this user can accept (not their own challenges)
            acceptable_challenges = []
            for c in all_challenges:
                if (c['challenger_id'] != ctx.author.id and 
                    (c['challenged_id'] is None or c['challenged_id'] == ctx.author.id) and
                    c['status'] == 'pending' and
                    c['challenge_type'] != 'bm'):  # Exclude BM challenges
                    
                    # If target_user specified, only include challenges from that user
                    if target_user:
                        if c['challenger_id'] == target_user.id:
                            acceptable_challenges.append(c)
                    else:
                        acceptable_challenges.append(c)
            
            if not acceptable_challenges:
                if target_user:
                    embed = EmbedTemplates.error_embed(
                        "No Challenge Found",
                        f"No pending challenge found from {target_user.display_name}."
                    )
                else:
                    embed = EmbedTemplates.error_embed(
                        "No Challenges Available",
                        "No pending challenges found that you can accept. Use `?accept @user` to accept a specific challenge."
                    )
                await ctx.send(embed=embed)
                return
            
            # Validate challenge_type argument if provided
            if challenge_type:
                challenge_type = challenge_type.lower()
                if challenge_type not in ['official', 'friendly']:
                    embed = EmbedTemplates.error_embed(
                        "Invalid Challenge Type",
                        "Valid types: `official`, `friendly`, `bm`"
                    )
                    await ctx.send(embed=embed)
                    return
            
            # Check what types of challenges are available
            available_types = set(c['challenge_type'] for c in acceptable_challenges)
            
            # If challenge_type specified, filter by that type
            if challenge_type:
                filtered_challenges = [c for c in acceptable_challenges if c['challenge_type'] == challenge_type]
                if not filtered_challenges:
                    embed = EmbedTemplates.error_embed(
                        "No Matching Challenges",
                        f"No {challenge_type} challenges found that you can accept."
                    )
                    await ctx.send(embed=embed)
                    return
                acceptable_challenges = filtered_challenges
            # If multiple types available and no type specified, ask user to choose
            elif len(available_types) > 1:
                selected_type = await self._show_challenge_type_menu(ctx, available_types)
                if not selected_type:
                    return  # User cancelled or timeout
                
                # Filter by selected type
                acceptable_challenges = [c for c in acceptable_challenges if c['challenge_type'] == selected_type]
            
            # Sort challenges by time (newest first)
            acceptable_challenges = sorted(acceptable_challenges, 
                                         key=lambda chall: chall['created_date'], 
                                         reverse=True)
            
            # If only one challenge, accept it directly
            if len(acceptable_challenges) == 1:
                challenge = acceptable_challenges[0]
            else:
                # Multiple challenges - show selection menu
                challenge = await self._show_challenge_selection_menu(ctx, acceptable_challenges)
                if not challenge:
                    return  # User cancelled or timeout
            
            # Process the challenge acceptance
            from workflows.duel_workflows import DuelWorkflows
            duel_workflows = DuelWorkflows(self.bot)
            
            acceptance_result = await duel_workflows.process_challenge_acceptance(
                accepter=ctx.author,
                challenge_id=challenge['challenge_id'],
                guild=ctx.guild
            )
            
            if acceptance_result['success']:
                challenger = ctx.guild.get_member(challenge['challenger_id'])
                challenger_name = challenger.display_name if challenger else "Unknown"
                
                # Send success embed
                embed = EmbedTemplates.create_base_embed(
                    title="✅ Challenge Accepted!",
                    description=f"You have accepted {challenger_name}'s **{challenge['challenge_type']}** duel challenge!",
                    color=0x00FF00
                )
                
                embed.add_field(
                    name="📝 Challenge ID",
                    value=f"#{challenge['challenge_id']}",
                    inline=True
                )
                
                embed.add_field(
                    name="🎯 Challenge Type", 
                    value=challenge['challenge_type'].title(),
                    inline=True
                )
                
                if acceptance_result.get('ticket_channel'):
                    embed.add_field(
                        name="🎫 Ticket Channel",
                        value=f"{acceptance_result['ticket_channel'].mention}",
                        inline=True
                    )
                
                embed.set_footer(text="Good luck in your duel!")
                await ctx.send(embed=embed)
                
            else:
                # Send the error embed from the workflow
                if acceptance_result.get('embed'):
                    await ctx.send(embed=acceptance_result['embed'])
                else:
                    embed = EmbedTemplates.error_embed(
                        "Acceptance Failed",
                        acceptance_result.get('message', 'Failed to accept challenge')
                    )
                    await ctx.send(embed=embed)
                
        except Exception as e:
            logger.error(f"Error in accept_challenge: {e}")
            embed = EmbedTemplates.error_embed(
                "System Error",
                "An error occurred while processing your acceptance. Please try again."
            )
            await ctx.send(embed=embed)

    async def _show_challenge_type_menu(self, ctx, available_types):
        """Show menu to select challenge type"""
        try:
            type_emojis = {
                'friendly': '🤝',
                'official': '⚡'
            }
            
            embed = EmbedTemplates.create_base_embed(
                title="🎯 Challenge Type Selection",
                description="What kind of duel are you looking to accept?",
                color=0x3498DB
            )
            
            emoji_list = []
            type_list = list(available_types)
            
            for i, challenge_type in enumerate(type_list):
                emoji = ['1️⃣', '2️⃣', '3️⃣'][i]
                emoji_list.append(emoji)
                
                type_name = challenge_type.title()
                type_icon = type_emojis.get(challenge_type, '⚔️')
                
                embed.add_field(
                    name=f"{emoji} {type_icon} {type_name}",
                    value=f"Accept {challenge_type} duels",
                    inline=False
                )
            
            embed.add_field(
                name="❌ Cancel",
                value="Cancel challenge acceptance",
                inline=False
            )
            
            embed.set_footer(text="Select a challenge type • Menu expires in 30 seconds")
            
            message = await ctx.send(embed=embed)
            
            # Add reactions
            for emoji in emoji_list:
                await message.add_reaction(emoji)
            await message.add_reaction("❌")
            
            # Wait for reaction
            def check(reaction, user):
                return (user == ctx.author and 
                    str(reaction.emoji) in emoji_list + ["❌"] and 
                    reaction.message.id == message.id)
            
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
                
                if str(reaction.emoji) == "❌":
                    embed = EmbedTemplates.create_base_embed(
                        title="❌ Selection Cancelled",
                        description="Challenge type selection cancelled.",
                        color=0x808080
                    )
                    await message.edit(embed=embed)
                    await message.clear_reactions()
                    return None
                else:
                    selected_index = emoji_list.index(str(reaction.emoji))
                    selected_type = type_list[selected_index]
                    await message.delete()
                    return selected_type
                    
            except asyncio.TimeoutError:
                timeout_embed = EmbedTemplates.error_embed(
                    "Timeout",
                    "Challenge type selection timed out after 30 seconds."
                )
                await message.edit(embed=timeout_embed)
                await message.clear_reactions()
                return None
                
        except Exception as e:
            logger.error(f"Error in challenge type menu: {e}")
            return None

    async def _show_challenge_selection_menu(self, ctx, challenges):
        """Show menu to select specific challenge"""
        try:
            embed = EmbedTemplates.create_base_embed(
                title="⚔️ Available Challenges",
                description="React with the number to accept a challenge:",
                color=0x00FF00
            )
            
            emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']
            
            # Take up to 5 challenges (already sorted by time)
            display_challenges = challenges[:5]
            
            for i, chall in enumerate(display_challenges):
                challenger_member = ctx.guild.get_member(chall['challenger_id'])
                challenger_name = challenger_member.display_name if challenger_member else "Unknown"
                
                # Format challenge type with appropriate emoji
                type_emoji = {
                    'friendly': '🤝',
                    'official': '⚡',
                    'bm': '👑'
                }
                
                field_value = (
                    f"**From:** {challenger_name}\n"
                    f"**Type:** {type_emoji.get(chall['challenge_type'], '⚔️')} {chall['challenge_type'].title()}\n"
                    f"**Created:** <t:{int(datetime.fromisoformat(chall['created_date'].replace('Z', '+00:00')).timestamp())}:R>"
                )
                
                embed.add_field(
                    name=f"{emojis[i]} Challenge #{chall['challenge_id']}",
                    value=field_value,
                    inline=False
                )
            
            # Add cancel option
            embed.add_field(
                name="❌ Cancel",
                value="React with ❌ to cancel selection",
                inline=False
            )
            
            embed.set_footer(text="Select a challenge to accept • Menu expires in 60 seconds")
            
            message = await ctx.send(embed=embed)
            
            # Add reactions
            for i in range(len(display_challenges)):
                await message.add_reaction(emojis[i])
            await message.add_reaction("❌")
            
            # Wait for reaction
            def check(reaction, user):
                return (user == ctx.author and 
                    str(reaction.emoji) in emojis[:len(display_challenges)] + ["❌"] and 
                    reaction.message.id == message.id)
            
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                
                if str(reaction.emoji) == "❌":
                    embed = EmbedTemplates.create_base_embed(
                        title="❌ Selection Cancelled",
                        description="Challenge acceptance cancelled.",
                        color=0x808080
                    )
                    await message.edit(embed=embed)
                    await message.clear_reactions()
                    return None
                else:
                    selected_index = emojis.index(str(reaction.emoji))
                    selected_challenge = display_challenges[selected_index]
                    await message.delete()
                    return selected_challenge
                    
            except asyncio.TimeoutError:
                timeout_embed = EmbedTemplates.error_embed(
                    "Timeout",
                    "Challenge selection timed out after 60 seconds."
                )
                await message.edit(embed=timeout_embed)
                await message.clear_reactions()
                return None
                
        except Exception as e:
            logger.error(f"Error in challenge selection menu: {e}")
            return None

    @duel_channel_required()
    @commands.command(name='decline', aliases=['dec', 'd'])
    async def decline_challenge(self, ctx, target_user: Optional[discord.Member] = None):
        """
        Decline a challenge
        Usage: 
        - ?decline @user: Decline specific challenge from user
        - ?decline (reply to embed): Decline challenge or cancel own challenge
        - ?decline: Decline pending challenges (menu if multiple)
        """
        try:
            # Ensure user is registered
            await self.user_system.ensure_user_registered(ctx.author)
            
            challenge = None
            is_own_challenge_cancel = False
            
            # Check if this is a reply to a challenge embed
            if ctx.message.reference and ctx.message.reference.message_id:
                try:
                    replied_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                    
                    if (replied_message.embeds and 
                        replied_message.author == self.bot.user):
                        
                        embed = replied_message.embeds[0]
                        
                        # Extract challenge ID from embed fields
                        challenge_id = None
                        for field in embed.fields:
                            if field.name == "📝 Challenge ID":
                                challenge_id = int(field.value.replace("#", ""))
                                break
                        
                        if challenge_id:
                            # Get challenge details
                            challenge_data = await self.challenge_system.db.get_challenge(challenge_id)
                            
                            if challenge_data and challenge_data['status'] == 'pending':
                                # Check if this is user's own challenge (cancel scenario)
                                if challenge_data['challenger_id'] == ctx.author.id:
                                    is_own_challenge_cancel = True
                                    challenge = challenge_data
                                    
                                    # Cancel the challenge
                                    result = await self.challenge_system.cancel_challenge(challenge['challenge_id'], ctx.author)
                                    
                                    if result['success']:
                                        # Send feedback message
                                        feedback_embed = EmbedTemplates.create_base_embed(
                                            title="🚫 Challenge Cancelled",
                                            description=f"You have cancelled your **{challenge['challenge_type']}** duel challenge.",
                                            color=0xFF5722
                                        )
                                        feedback_embed.add_field(
                                            name="📝 Challenge ID",
                                            value=f"#{challenge['challenge_id']}",
                                            inline=True
                                        )
                                        await ctx.send(embed=feedback_embed)
                                        
                                        # FIXED: Edit the original replied message directly
                                        cancelled_embed = EmbedTemplates.create_base_embed(
                                            title="❌ Challenge Cancelled",
                                            description=f"This **{challenge['challenge_type']}** challenge has been cancelled by the challenger.",
                                            color=0x607D8B
                                        )
                                        cancelled_embed.add_field(
                                            name="📝 Challenge ID",
                                            value=f"#{challenge['challenge_id']}",
                                            inline=True
                                        )
                                        cancelled_embed.add_field(
                                            name="⏰ Cancelled At",
                                            value=f"<t:{int(datetime.now().timestamp())}:R>",
                                            inline=True
                                        )
                                        cancelled_embed.set_footer(text="This challenge is no longer available")
                                        
                                        try:
                                            await replied_message.edit(embed=cancelled_embed)
                                            await replied_message.clear_reactions()
                                        except Exception as edit_error:
                                            logger.warning(f'Could not edit original challenge embed: {edit_error}')
                                    else:
                                        embed = EmbedTemplates.error_embed("Cancel Failed", result['message'])
                                        await ctx.send(embed=embed)
                                    return  # Exit early since we handled it
                                    
                                # Check if user can decline this challenge
                                elif (challenge_data['challenged_id'] == ctx.author.id or 
                                    (challenge_data['challenged_id'] is None)):
                                    if challenge_data['challenged_id'] is not None:
                                        challenge = challenge_data
                                        
                                        # Decline the challenge
                                        result = await self.challenge_system.decline_challenge(ctx.author, challenge['challenge_id'])
                                        
                                        if result[0]:  # Success
                                            challenger = ctx.guild.get_member(challenge['challenger_id'])
                                            challenger_name = challenger.display_name if challenger else "Unknown"
                                            
                                            # Send feedback message
                                            feedback_embed = EmbedTemplates.create_base_embed(
                                                title="❌ Challenge Declined",
                                                description=f"You have declined {challenger_name}'s **{challenge['challenge_type']}** duel challenge.",
                                                color=0xFF6B6B
                                            )
                                            feedback_embed.add_field(
                                                name="📝 Challenge ID",
                                                value=f"#{challenge['challenge_id']}",
                                                inline=True
                                            )
                                            await ctx.send(embed=feedback_embed)
                                            
                                            # FIXED: Edit the original replied message directly
                                            declined_embed = EmbedTemplates.create_base_embed(
                                                title="❌ Challenge Declined",
                                                description=f"This **{challenge['challenge_type']}** challenge has been declined.",
                                                color=0x607D8B
                                            )
                                            declined_embed.add_field(
                                                name="📝 Challenge ID",
                                                value=f"#{challenge['challenge_id']}",
                                                inline=True
                                            )
                                            declined_embed.add_field(
                                                name="⏰ Declined At",
                                                value=f"<t:{int(datetime.now().timestamp())}:R>",
                                                inline=True
                                            )
                                            declined_embed.set_footer(text="This challenge is no longer available")
                                            
                                            try:
                                                await replied_message.edit(embed=declined_embed)
                                                await replied_message.clear_reactions()
                                            except Exception as edit_error:
                                                logger.warning(f'Could not edit original challenge embed: {edit_error}')
                                        else:
                                            embed = EmbedTemplates.error_embed("Decline Failed", result[1])
                                            await ctx.send(embed=embed)
                                        return  # Exit early since we handled it
                                    else:
                                        embed = EmbedTemplates.error_embed(
                                            "Cannot Decline",
                                            "You cannot decline public challenges. Only specific challenges directed at you can be declined."
                                        )
                                        await ctx.send(embed=embed)
                                        return
                        
                except Exception as e:
                    logger.error(f'Error fetching replied message: {e}')
            
            # If no challenge found from reply, use parameter or search logic
            if not challenge:
                if target_user:
                    # Decline specific challenge from target_user
                    user_challenges = await self.challenge_system.get_active_challenges_for_user(target_user.id)
                    # Find challenges where target_user challenged this user specifically
                    for c in user_challenges:
                        if (c['challenger_id'] == target_user.id and 
                            c['challenged_id'] == ctx.author.id and  # Must be specifically challenged
                            c['status'] == 'pending'):
                            challenge = c
                            break
                else:
                    # Find challenges this user can decline (NO public challenges)
                    all_challenges = await self.challenge_system.get_active_challenges_for_user(ctx.author.id)
                    declined_challenges = []
                    
                    for c in all_challenges:
                        if (c['challenger_id'] != ctx.author.id and 
                            c['challenged_id'] == ctx.author.id and  # Must be specifically challenged
                            c['status'] == 'pending'):
                            declined_challenges.append(c)
                    
                    if len(declined_challenges) == 0:
                        embed = EmbedTemplates.error_embed(
                            "No Challenges Found",
                            "No pending challenges directed at you. Use `?decline @user` to decline a specific challenge."
                        )
                        await ctx.send(embed=embed)
                        return
                    elif len(declined_challenges) == 1:
                        challenge = declined_challenges[0]
                    else:
                        # Multiple challenges - show selection menu
                        embed = EmbedTemplates.create_base_embed(
                            title="📋 Pending Challenges for You",
                            description="React with the number to decline a challenge:",
                            color=0xFF6B6B
                        )
                        
                        emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']
                        
                        for i, chall in enumerate(declined_challenges[:5]):
                            challenger_member = ctx.guild.get_member(chall['challenger_id'])
                            challenger_name = challenger_member.display_name if challenger_member else "Unknown"
                            
                            field_value = (
                                f"**From:** {challenger_name}\n"
                                f"**Type:** {chall['challenge_type'].title()}\n"
                                f"**Created:** {chall['created_date'][:16]}"
                            )
                            
                            embed.add_field(
                                name=f"{emojis[i]} Challenge #{chall['challenge_id']}",
                                value=field_value,
                                inline=False
                            )
                        
                        # Add option to decline all
                        embed.add_field(
                            name="❌ Decline All",
                            value="React with ❌ to decline all pending challenges",
                            inline=False
                        )
                        
                        message = await ctx.send(embed=embed)
                        
                        # Add reactions
                        for i in range(min(len(declined_challenges), 5)):
                            await message.add_reaction(emojis[i])
                        await message.add_reaction("❌")
                        
                        # Wait for reaction
                        def check(reaction, user):
                            return (user == ctx.author and 
                                str(reaction.emoji) in emojis[:len(declined_challenges)] + ["❌"] and 
                                reaction.message.id == message.id)
                        
                        try:
                            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
                            
                            if str(reaction.emoji) == "❌":
                                # Decline all challenges
                                declined_count = 0
                                failed_declines = []
                                
                                for chall in declined_challenges:
                                    result = await self.challenge_system.decline_challenge(ctx.author, chall['challenge_id'])
                                    if result[0]:  # Success
                                        declined_count += 1
                                        # FIXED: Update each declined challenge embed with fallback channel
                                        await self._update_challenge_embed_cancelled(chall, ctx.channel)
                                    else:
                                        failed_declines.append(f"#{chall['challenge_id']}: {result[1]}")
                                
                                # Build result message
                                if declined_count > 0:
                                    embed = EmbedTemplates.create_base_embed(
                                        title="✅ Challenges Declined",
                                        description=f"Successfully declined {declined_count} challenge(s).",
                                        color=0x00FF00
                                    )
                                    
                                    if failed_declines:
                                        embed.add_field(
                                            name="⚠️ Failed Declines",
                                            value="\n".join(failed_declines[:5]),
                                            inline=False
                                        )
                                else:
                                    embed = EmbedTemplates.error_embed(
                                        "Decline Failed",
                                        "No challenges could be declined. " + 
                                        ("\n".join(failed_declines[:3]) if failed_declines else "")
                                    )
                                
                                await message.edit(embed=embed)
                                await message.clear_reactions()
                            else:
                                # Decline specific challenge
                                selected_index = emojis.index(str(reaction.emoji))
                                selected_challenge = declined_challenges[selected_index]
                                
                                result = await self.challenge_system.decline_challenge(ctx.author, selected_challenge['challenge_id'])
                                
                                if result[0]:  # Success
                                    challenger = ctx.guild.get_member(selected_challenge['challenger_id'])
                                    challenger_name = challenger.display_name if challenger else "Unknown"
                                    
                                    embed = EmbedTemplates.create_base_embed(
                                        title="❌ Challenge Declined",
                                        description=f"You have declined {challenger_name}'s **{selected_challenge['challenge_type']}** duel challenge.",
                                        color=0xFF6B6B
                                    )
                                    
                                    embed.add_field(
                                        name="📝 Challenge ID",
                                        value=f"#{selected_challenge['challenge_id']}",
                                        inline=True
                                    )
                                    
                                    await message.edit(embed=embed)
                                    await message.clear_reactions()
                                    
                                    # FIXED: Update original challenge embed with fallback channel
                                    await self._update_challenge_embed_cancelled(selected_challenge, ctx.channel)
                                    
                                else:
                                    embed = EmbedTemplates.error_embed(
                                        "Decline Failed",
                                        result[1]
                                    )
                                    await message.edit(embed=embed)
                                    await message.clear_reactions()
                                
                        except asyncio.TimeoutError:
                            timeout_embed = EmbedTemplates.error_embed(
                                "Timeout",
                                "Challenge decline timed out."
                            )
                            await message.edit(embed=timeout_embed)
                            await message.clear_reactions()
                            return
            
            if not challenge:
                embed = EmbedTemplates.error_embed(
                    "No Challenge Found",
                    "No pending challenge found that you can decline."
                )
                await ctx.send(embed=embed)
                return
            
            # Handle canceling own challenge vs declining others
            if is_own_challenge_cancel:
                # Cancel own challenge (like ?duel cancel) - correct parameter order
                result = await self.challenge_system.cancel_challenge(challenge['challenge_id'], ctx.author)
                
                if result['success']:  # Dictionary response
                    embed = EmbedTemplates.create_base_embed(
                        title="🚫 Challenge Cancelled",
                        description=f"You have cancelled your **{challenge['challenge_type']}** duel challenge.",
                        color=0xFF5722
                    )
                    
                    embed.add_field(
                        name="📝 Challenge ID",
                        value=f"#{challenge['challenge_id']}",
                        inline=True
                    )
                    
                    await ctx.send(embed=embed)
                    
                    # FIXED: Update original challenge embed with fallback channel
                    await self._update_challenge_embed_cancelled(challenge, ctx.channel)
                    
                else:
                    embed = EmbedTemplates.error_embed(
                        "Cancel Failed",
                        result['message']  # Dictionary has 'message' key
                    )
                    await ctx.send(embed=embed)
            else:
                # Decline someone else's challenge
                result = await self.challenge_system.decline_challenge(ctx.author, challenge['challenge_id'])
                
                if result[0]:  # Success
                    challenger = ctx.guild.get_member(challenge['challenger_id'])
                    challenger_name = challenger.display_name if challenger else "Unknown"
                    
                    embed = EmbedTemplates.create_base_embed(
                        title="❌ Challenge Declined",
                        description=f"You have declined {challenger_name}'s **{challenge['challenge_type']}** duel challenge.",
                        color=0xFF6B6B
                    )
                    
                    embed.add_field(
                        name="📝 Challenge ID",
                        value=f"#{challenge['challenge_id']}",
                        inline=True
                    )
                    
                    await ctx.send(embed=embed)
                    
                    # FIXED: Update original challenge embed with fallback channel
                    await self._update_challenge_embed_cancelled(challenge, ctx.channel)
                    
                else:
                    embed = EmbedTemplates.error_embed(
                        "Decline Failed",
                        result[1]  # Error message
                    )
                    await ctx.send(embed=embed)
                    
        except Exception as e:
            logger.error(f'Error in decline command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred while declining the challenge: {str(e)}"
            )
            await ctx.send(embed=embed)

    # ============================================================================
    # UTILITY COMMANDS
    # ============================================================================
    
    @commands.command(name='preview')
    async def preview_elo_changes(self, ctx, target: discord.Member):
        """
        Preview ELO changes for a potential match
        Usage: ?preview @user
        """
        try:
            await self.user_system.ensure_user_registered(ctx.author)
            await self.user_system.ensure_user_registered(target)
            
            user_elo = await self.user_system.get_user_elo(ctx.author)
            target_elo = await self.user_system.get_user_elo(target)
            
            # Calculate potential ELO changes
            from systems.elo_system import ELOSystem
            elo_system = ELOSystem()
            
            if_you_win = elo_system.calculate_elo_change(user_elo, target_elo, won=True)
            if_you_lose = elo_system.calculate_elo_change(user_elo, target_elo, won=False)
            
            embed = EmbedTemplates.create_base_embed(
                title="📊 ELO Preview",
                description=f"Potential ELO changes for **{ctx.author.display_name}** vs **{target.display_name}**",
                color=0x4169E1
            )
            
            embed.add_field(
                name="Current ELO",
                value=f"**You:** {user_elo}\n**{target.display_name}:** {target_elo}",
                inline=False
            )
            
            embed.add_field(
                name="If You Win",
                value=f"**+{if_you_win}** ELO (New: {user_elo + if_you_win})",
                inline=True
            )
            
            embed.add_field(
                name="If You Lose",
                value=f"**{if_you_lose}** ELO (New: {user_elo + if_you_lose})",
                inline=True
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f'Error in preview command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred while calculating ELO preview: {str(e)}"
            )
            await ctx.send(embed=embed)