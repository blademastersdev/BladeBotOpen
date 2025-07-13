"""
Public Commands - Fixed for Refactoring
Commands available to all users: leaderboard, about, help
REMOVED: stats, friendly, official, challenge (now in other command files)
"""

import discord
from discord.ext import commands
import logging
from typing import Optional
from database.models import Database
from systems.user_system import UserSystem
from systems.challenge_system import ChallengeSystem
from systems.ranking_system import RankingSystem
from systems.elo_system import ELOSystem
from utils.embeds import EmbedTemplates
from utils.validators import Validators
from utils.role_utils import RoleManager
from config import DUEL_TYPES, TIER_HIERARCHY, RANK_STRUCTURE

logger = logging.getLogger('BladeBot.PublicCommands')

async def setup_public_commands(bot):
    """Setup public commands for the bot"""
    await bot.add_cog(PublicCommands(bot))

class PublicCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.user_system = UserSystem(self.db)
        self.ranking_system = RankingSystem(self.db)
        self.elo_system = ELOSystem()
        self.challenge_system = ChallengeSystem(
            self.db, self.user_system, self.ranking_system
        )
    
    # NOTE: Removed ?friendly, ?official, ?challenge, ?stats commands
    # These are now handled by the refactored duel_commands.py and utility_commands.py
    
    @commands.command(name='leaderboard', aliases=['lb', 'top', 'leaderboards'])
    async def leaderboard(self, ctx, count: int = 20):
        """
        View ELO leaderboard
        Usage: ?leaderboard [count]
        """
        from config import CLEANUP_TIMINGS
        
        try:
            # Validate count
            if count < 1 or count > 50:
                embed = EmbedTemplates.error_embed(
                    "Invalid Count",
                    "Leaderboard count must be between 1 and 50"
                )
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])  
                return
            
            # Get leaderboard data
            leaderboard_data = await self.db.get_leaderboard(limit=count)
            
            if not leaderboard_data:
                embed = EmbedTemplates.error_embed(
                    "No Data",
                    "No users found for leaderboard"
                )
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])  
                return
            
            # Create and send leaderboard embed
            embed = EmbedTemplates.leaderboard_embed(leaderboard_data, f"Top {count} ELO Leaderboard")
            await ctx.send(embed=embed)  
            
        except Exception as e:
            logger.error(f'Error in leaderboard command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error", 
                "An error occurred while retrieving leaderboard"
            )
            await ctx.send(embed=embed)  
    
    @commands.command(name='ranks', aliases=['distribution'])
    async def rank_distribution(self, ctx):
        """
        View current rank distribution
        Usage: ?ranks
        """
        try:
            # Get rank distribution
            distribution_data = await self.ranking_system.get_rank_distribution()
            
            # Create and send distribution embed
            embed = EmbedTemplates.rank_distribution_embed(distribution_data)
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f'Error in ranks command: {e}')
            await ctx.send("❌ An error occurred while retrieving rank distribution")
    
    @commands.command(name='about', aliases=['info'])
    async def about_organization(self, ctx):
        """
        Information about the ROBLOX Linked Sword Dueling organization
        Usage: ?about
        """
        try:
            embed = EmbedTemplates.create_base_embed(
                title="🗡️ ROBLOX Linked Sword Dueling Organization",
                description="Competitive dueling community with structured ranking system",
                color=0x4169E1
            )
            
            embed.add_field(
                name="🏆 Ranking System",
                value=(
                    "**Diamond** (I-II) - Elite Tier\n"
                    "**Platinum** (I-III) - Expert Tier\n"
                    "**Gold** (I-III) - Advanced Tier\n"
                    "**Silver** (I-IV) - Intermediate Tier\n"
                    "**Bronze** (I-IV) - Beginner Tier"
                ),
                inline=False
            )
            
            embed.add_field(
                name="⚔️ Duel Types",
                value=(
                    "**Friendly** - Practice matches (no stakes)\n"
                    "**Official** - Competitive matches (affects ELO)\n"
                    "**BM (Blademaster)** - Rank progression matches"
                ),
                inline=False
            )
            
            embed.add_field(
                name="📈 Progression",
                value=(
                    "• Start with evaluation duels to determine initial rank\n"
                    "• Challenge users in the rank directly above you\n"
                    "• Win BM duels to advance, lose to drop rank\n"
                    "• Build ELO through official duels"
                ),
                inline=False
            )
            
            embed.add_field(
                name="🎯 Getting Started",
                value=(
                    f"• Use `?duel friendly` for practice\n"
                    f"• Use `?duel official` for ELO matches\n"
                    f"• Use `?stats` to view your progress\n"
                    f"• Complete evaluation to join Blademasters"
                ),
                inline=False
            )
            
            embed.set_footer(text="Good luck in your dueling journey!")
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f'Error in about command: {e}')
            await ctx.send("❌ An error occurred while retrieving information")
    
    @commands.command(name='help', aliases=['h', 'cmds']) 
    async def help_command(self, ctx, *, command_name: str = None):
        """
        Show help information
        Usage: ?help [command_name]
        """
        from config import CLEANUP_TIMINGS
        
        try:
            if command_name:
                # Show help for specific command
                command = self.bot.get_command(command_name)
                if command:
                    embed = EmbedTemplates.create_base_embed(
                        title=f"📖 Help: {command.name}",
                        description=command.help or "No description available",
                        color=0x00BFFF
                    )
                    
                    # Add aliases if any
                    if command.aliases:
                        embed.add_field(
                            name="Aliases",
                            value=", ".join(f"`{alias}`" for alias in command.aliases),
                            inline=False
                        )
                    
                    # Add usage info
                    embed.add_field(
                        name="Usage",
                        value=f"`{self.bot.command_prefix}{command.name} {command.signature}`",
                        inline=False
                    )
                    
                    await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['info'])  # ADD THIS
                else:
                    embed = EmbedTemplates.error_embed(
                        "Command Not Found",
                        f"No command named `{command_name}` found"
                    )
                    await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])  # ADD THIS
            else:
                # Show general help
                embed = EmbedTemplates.create_base_embed(
                    title="🗡️ BladeBot Commands",
                    description="ROBLOX Linked Sword Dueling Bot",
                    color=0x4169E1
                )
                
                # Duel commands
                duel_commands = (
                    "`?duel` - Interactive duel menu\n"
                    "`?duel friendly [@user]` - Challenge to friendly duel\n"
                    "`?duel official [@user]` - Challenge to official duel\n"
                    "`?duel bm [@user]` - Challenge to BM duel (rank up)\n"
                    "`?duel cancel` - Cancel your challenges\n"
                    "`?accept` - Accept a challenge\n"
                    "`?decline` - Decline a challenge\n"
                    "`?preview @user` - Preview ELO changes"
                )
                
                embed.add_field(
                    name="⚔️ Duel Commands",
                    value=duel_commands,
                    inline=False
                )
                
                # Statistics commands
                stats_commands = (
                    "`?stats [@user]` - View user statistics\n"
                    "`?stats logs [@user]` - View detailed match history\n"
                    "`?leaderboard [count]` - View ELO leaderboard\n"
                    "`?ranks` - View rank distribution\n"
                    "`?recent [days]` - View recent activity\n"
                    "`?compare @user1 @user2` - Compare two users\n"
                    "`?search <username>` - Search for users"
                )
                
                embed.add_field(
                    name="📊 Statistics Commands",
                    value=stats_commands,
                    inline=False
                )
                
                # Moderator commands
                mod_commands = (
                    "`?log` - Interactive admin menu\n"
                    "`?log duel` - Record match results\n"
                    "`?log edit [match_id]` - Edit match data\n"
                    "`?log void [match_id]` - Void matches (Grandmaster)\n"
                    "`?log history` - Browse all match history\n"
                    "`?close [reason]` - Close tickets\n"
                    "`?tickets` - View active tickets (Admin)"
                )
                
                embed.add_field(
                    name="🛡️ Moderator Commands",
                    value=mod_commands,
                    inline=False
                )
                
                # Admin commands
                admin_commands = (
                    "`?evaluate @user <rank>` - Place from evaluation\n"
                    "`?confirm <change_id>` - Confirm rank change\n"
                    "`?pending` - View pending rank changes\n"
                    "`?cleanup` - Clean expired data"
                )
                
                embed.add_field(
                    name="👑 Admin Commands",
                    value=admin_commands,
                    inline=False
                )
                
                # General commands
                general_commands = (
                    "`?about` - About the organization\n"
                    "`?help [command]` - Show help information"
                )
                
                embed.add_field(
                    name="ℹ️ General Commands",
                    value=general_commands,
                    inline=False
                )
                
                # Duel types explanation
                duel_types = (
                    "**Friendly:** No stakes, not logged\n"
                    "**Official:** Logged, affects ELO\n"
                    "**BM (Blademaster):** Logged, affects ELO and rank"
                )
                
                embed.add_field(
                    name="⚔️ Duel Types",
                    value=duel_types,
                    inline=False
                )
                
                embed.add_field(
                    name="💡 Tips",
                    value=(
                        f"• Use `?help <command>` for detailed help on specific commands\n"
                        f"• Many commands have interactive modes with emoji reactions\n"
                        f"• Reply to challenge messages to accept them quickly\n"
                        f"• Use commands in ticket channels for auto-detection"
                    ),
                    inline=False
                )
                
                embed.set_footer(text="Use ?help <command> for specific command details")
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['info'])  # ADD THIS
                
        except Exception as e:
            logger.error(f'Error in help command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                "An error occurred while generating help information"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])  # ADD THIS