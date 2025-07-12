#!/usr/bin/env python3
"""
BladeBot - ROBLOX Linked Sword Dueling Bot
Main entry point and bot initialization
"""
from dotenv import load_dotenv
load_dotenv()
import discord
from discord.ext import commands
import logging
import sys
import os
from pathlib import Path
from systems.user_system import UserSystem
from config import TIER_ROLES, RANK_ROLES
from datetime import datetime, timedelta

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import our modules
from config import BOT_CONFIG
from database.models import Database
from commands.public_commands import setup_public_commands
from commands.duel_commands import setup_duel_commands
from commands.admin_commands import setup_admin_commands
from commands.utility_commands import setup_utility_commands
from systems.ticket_system import TicketSystem
from utils.embeds import EmbedTemplates

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bladebot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('BladeBot')

class BladeBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.reactions = True
        
        super().__init__(
            command_prefix=BOT_CONFIG['command_prefix'],
            intents=intents,
            help_command=None  # We'll create a custom help command
        )
        
        # Initialize systems
        self.db = Database()
        self.ticket_system = TicketSystem(self)
        
    async def on_ready(self):
        """Called when the bot is ready and connected to Discord"""
        logger.info(f'{self.user} has connected to Discord!')
        logger.info(f'Bot is in {len(self.guilds)} guilds')
        
        # Initialize database
        await self.db.initialize()
        logger.info('Database initialized')
        
        # Initialize ticket system and load existing tickets
        await self.ticket_system.initialize_ticket_table()
        
        # Load tickets from database for each guild
        for guild in self.guilds:
            await self.ticket_system.load_tickets_from_database(guild)
        
        logger.info('Ticket system initialized')

        logger.info('Running startup rank validation...')
        for guild in self.guilds:
            from systems.user_system import UserSystem
            user_system = UserSystem(self.db)
            if await user_system.should_run_rank_validation():
                stats = await user_system.validate_and_fix_user_ranks(guild)
                if stats['fixed'] > 0:
                    logger.info(f"Startup validation: Fixed {stats['fixed']} user ranks")

        # Set bot status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, 
                name="blade duels | ?help"
            )
        )

    async def on_command_error(self, ctx, error):
        """Global error handler"""
        from config import CLEANUP_TIMINGS
        
        if isinstance(error, commands.CommandNotFound):
            await ctx.send(
                f"❌ Command not found. Use `{self.command_prefix}help` for available commands.",
                delete_after=CLEANUP_TIMINGS['error']
            )
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send(
                "❌ You don't have permission to use this command.",
                delete_after=CLEANUP_TIMINGS['error']
            )
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                f"❌ Missing required argument. Use `{self.command_prefix}help {ctx.command}` for usage.",
                delete_after=CLEANUP_TIMINGS['error']
            )
        elif isinstance(error, commands.BadArgument):
            await ctx.send(
                f"❌ Invalid argument. Use `{self.command_prefix}help {ctx.command}` for usage.",
                delete_after=CLEANUP_TIMINGS['error']
            )
        elif isinstance(error, commands.CheckFailure):
            # Handle channel restrictions from DuelCommands
            if hasattr(ctx.cog, '_check_duel_channel_permissions'):
                _, channel_error = await ctx.cog._check_duel_channel_permissions(ctx)
                embed = EmbedTemplates.error_embed("Channel Restricted", channel_error)
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
            else:
                # Some other check failure - handle generically
                await ctx.send(
                    "❌ You cannot use this command here.",
                    delete_after=CLEANUP_TIMINGS['error']
                )
        else:
            logger.error(f'Unhandled error in command {ctx.command}: {error}', exc_info=True)
            await ctx.send(
                "❌ An unexpected error occurred. Please try again later.",
                delete_after=CLEANUP_TIMINGS['error']
            )
    
    async def on_message(self, message):
        """Process messages for commands and other functionality"""
        # Ignore bot messages
        if message.author.bot:
            return
            
        # Process commands
        await self.process_commands(message)
    
    async def setup_commands(self):
        """Load all command modules"""
        logger.info('Loading command modules...')
        
        # Load command groups
        await setup_public_commands(self)
        await setup_duel_commands(self)
        await setup_admin_commands(self)
        await setup_utility_commands(self)
        
        logger.info('All command modules loaded')

    async def on_reaction_add(self, reaction, user):
        """Handle reactions to messages, including challenge embeds"""
        
        # Ignore bot reactions
        if user.bot:
            return
        
        # Only handle sword reactions
        if str(reaction.emoji) != '⚔️':
            return
        
        message = reaction.message
        
        # Check if this is a challenge embed by looking for challenge ID in embed
        if not message.embeds:
            return
        
        embed = message.embeds[0]
        challenge_id = None
        
        # Look for challenge ID in embed fields
        for field in embed.fields:
            if field.name == "📝 Challenge ID" and field.value.startswith("#"):
                try:
                    challenge_id = int(field.value.replace("#", ""))
                    break
                except ValueError:
                    continue
        
        # If no challenge ID found, this isn't a challenge embed
        if challenge_id is None:
            return
        
        # Handle the challenge reaction
        await self._handle_challenge_reaction(reaction, user, challenge_id)

    async def _handle_challenge_reaction(self, reaction, user, challenge_id):
        """Handle a reaction to a challenge embed"""
        try:
            # Get challenge data
            challenge = await self.db.get_challenge(challenge_id)
            if not challenge:
                await reaction.remove(user)
                return
            
            # Check if challenge is still pending
            if challenge['status'] != 'pending':
                await reaction.remove(user)
                return
            
            # Check if user can accept this challenge
            if challenge['challenger_id'] == user.id:
                # Can't accept your own challenge
                await reaction.remove(user)
                return
            
            if challenge['challenged_id'] and challenge['challenged_id'] != user.id:
                # This challenge is for someone specific, not this user
                await reaction.remove(user)
                return
            
            # Use the proper workflow system for acceptance
            from workflows.duel_workflows import DuelWorkflows
            duel_workflows = DuelWorkflows(self)
            
            acceptance_result = await duel_workflows.process_challenge_acceptance(
                accepter=user,
                challenge_id=challenge_id,
                guild=reaction.message.guild
            )
            
            if acceptance_result['success']:
                challenger = reaction.message.guild.get_member(challenge['challenger_id'])
                challenger_name = challenger.display_name if challenger else "Unknown"
                
                # Edit the original message to show it was accepted
                accepted_embed = EmbedTemplates.create_base_embed(
                    title="✅ Challenge Accepted!",
                    description=f"**{user.display_name}** has accepted **{challenger_name}**'s {challenge['challenge_type']} duel challenge!",
                    color=0x00FF00
                )
                
                if acceptance_result.get('ticket_channel'):
                    accepted_embed.add_field(
                        name="🎫 Duel Ticket",
                        value=f"{acceptance_result['ticket_channel'].mention}",
                        inline=True
                    )
                
                accepted_embed.add_field(
                    name="📝 Challenge ID",
                    value=f"#{challenge_id}",
                    inline=True
                )
                
                accepted_embed.set_footer(text=f"Accepted by {user.display_name} via reaction")
                
                try:
                    await reaction.message.edit(embed=accepted_embed)
                    # Clear reactions since challenge is now accepted
                    await reaction.message.clear_reactions()
                except:
                    # Fallback: send new message if edit fails
                    await reaction.message.channel.send(embed=accepted_embed)
                    
            else:
                # Challenge acceptance failed
                await reaction.remove(user)
                error_embed = EmbedTemplates.error_embed(
                    "Accept Failed",
                    acceptance_result.get('message', 'Unknown error occurred')
                )
                await reaction.message.channel.send(embed=error_embed, delete_after=10)
                
        except Exception as e:
            logger.error(f'Error handling challenge reaction: {e}')
            # Remove the reaction on error
            try:
                await reaction.remove(user)
            except:
                pass

    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Auto-validate rank when Discord roles change"""
        if before.roles != after.roles:
            # Check if rank-related roles changed
            rank_roles_before = set()
            rank_roles_after = set()
            
            for role in before.roles:
                if role.id in TIER_ROLES.values() or role.id in RANK_ROLES.values():
                    rank_roles_before.add(role.id)
            
            for role in after.roles:
                if role.id in TIER_ROLES.values() or role.id in RANK_ROLES.values():
                    rank_roles_after.add(role.id)
            
            if rank_roles_before != rank_roles_after:
                # Rank-related roles changed, validate this user
                try:
                    user_system = UserSystem(self.db)
                    
                    # Get correct rank from new Discord roles
                    correct_tier, correct_numeral = user_system.get_rank_from_discord_roles(after)
                    # FIXED: Default to Guest with 'N/A'
                    if not correct_tier:
                        correct_tier, correct_numeral = 'Guest', 'N/A'
                    
                    # Get current database rank
                    user_data = await user_system.db.get_user(after.id)
                    if user_data:
                        db_tier = user_data['tier']
                        db_numeral = user_data['rank_numeral']
                        
                        # Fix if mismatch
                        if db_tier != correct_tier or db_numeral != correct_numeral:
                            success = await user_system.db.update_user(
                                after.id,
                                tier=correct_tier,
                                rank_numeral=correct_numeral  # Now 'N/A' instead of None
                            )
                            
                            if success:
                                logger.info(f"Auto-updated {after.display_name}: {db_tier} {db_numeral} → {correct_tier} {correct_numeral}")
                                await user_system.db.log_action(
                                    'role_change_validation',
                                    after.id,
                                    f"Role change: {db_tier} {db_numeral} → {correct_tier} {correct_numeral}"
                                )
                    
                except Exception as e:
                    logger.error(f'Error in role change validation for {after.display_name}: {e}')

async def main():
    """Main function to start the bot"""
    bot = BladeBot()
    
    try:
        # Setup commands
        await bot.setup_commands()
        
        # Start the bot
        logger.info('Starting BladeBot...')
        await bot.start(BOT_CONFIG['bot_token'])
        
    except discord.LoginFailure:
        logger.error('Invalid bot token')
    except KeyboardInterrupt:
        logger.info('Bot shutdown requested')
    except Exception as e:
        logger.error(f'Unexpected error: {e}', exc_info=True)
    finally:
        if not bot.is_closed():
            await bot.close()
        logger.info('BladeBot shutdown complete')

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())