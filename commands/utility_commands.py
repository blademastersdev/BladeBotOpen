"""
Utility Commands - Refactored
Contains the new ?stats command category with sub-commands for user statistics
Also includes other utility functionality
"""

import discord
from discord.ext import commands
import logging
import aiosqlite
import asyncio
from typing import Optional
from datetime import datetime, timedelta
from database.models import Database
from systems.user_system import UserSystem
from systems.ranking_system import RankingSystem
from systems.match_system import MatchSystem
from systems.elo_system import ELOSystem
from systems.ticket_system import TicketSystem
from database.queries import DatabaseQueries
from utils.embeds import EmbedTemplates
from utils.validators import Validators
from utils.role_utils import RoleManager
from config import BOT_LIMITS, CLEANUP_TIMINGS

logger = logging.getLogger('BladeBot.UtilityCommands')

async def setup_utility_commands(bot):
    """Setup utility commands for the bot"""
    await bot.add_cog(UtilityCommands(bot))

class UtilityCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.user_system = UserSystem(self.db)
        self.ranking_system = RankingSystem(self.db)
        self.match_system = MatchSystem(
            self.db, ELOSystem(), self.user_system, self.ranking_system
        )
        self.queries = DatabaseQueries(self.db.db_path)
        self.ticket_system = TicketSystem(bot)

    # ============================================================================
    # NEW REFACTORED ?STATS COMMAND CATEGORY
    # ============================================================================
    
    @commands.group(name='stats', aliases=['statistics'], invoke_without_subcommand=True)
    async def stats_command(self, ctx, target: Optional[discord.Member] = None):
        """
        View user statistics with interactive navigation
        Usage: ?stats [@user]
        Subcommands: logs, history
        """
        from config import CLEANUP_TIMINGS
        
        try:
            # Default to command author if no target specified
            if not target:
                target = ctx.author
            
            # Ensure user is registered
            await self.user_system.ensure_user_registered(target)
            
            # Get user data
            user_data = await self.user_system.get_user_profile(target.id)
            if not user_data:
                embed = EmbedTemplates.error_embed(
                    "User Not Found",
                    f"Could not find profile data for {target.display_name}"
                )
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                return
            
            # Quick validation check for this user (auto-fix if needed)
            correct_tier, correct_numeral = self.user_system.get_rank_from_discord_roles(target)
            # FIXED: Default to Guest with 'N/A'
            if not correct_tier:
                correct_tier, correct_numeral = 'Guest', 'N/A'
                
            # Fix if mismatch found
            if user_data['tier'] != correct_tier or user_data['rank_numeral'] != correct_numeral:
                await self.db.update_user(target.id, tier=correct_tier, rank_numeral=correct_numeral)
                # Refresh user data with corrected info
                user_data = await self.user_system.get_user_profile(target.id)
                logger.info(f"Auto-fixed rank for {target.display_name} during stats display")
            
            # Get leaderboard position
            leaderboard_rank = await self.user_system.get_user_leaderboard_rank(target.id)
            
            # Create main stats embed
            rank_display = "Unranked" if user_data['tier'] in ['Guest', 'Evaluation'] or user_data['rank_numeral'] == 'N/A' else f"{user_data['tier']} {user_data['rank_numeral']}"
            
            # Enhanced description with rank placement
            elo_text = f"ELO: **{user_data['elo_rating']}**"
            if leaderboard_rank:
                elo_text += f" • Rank **#{leaderboard_rank}**"
            
            embed = EmbedTemplates.create_base_embed( 
                title=f"📊 {target.display_name}'s Statistics",
                description=f"**{rank_display}** • {elo_text}",
                color=0x4169E1
            )
            
            # Add avatar if available
            if target.avatar:
                embed.set_thumbnail(url=target.avatar.url)
            
            # Calculate win rate
            total_games = user_data['games_played']
            wins = user_data['wins']
            losses = user_data['losses']
            win_rate = (wins / total_games * 100) if total_games > 0 else 0
            
            # Basic stats
            embed.add_field(
                name="⚔️ Combat Record",
                value=f"**Wins:** {wins}\n**Losses:** {losses}\n**Win Rate:** {win_rate:.1f}%",
                inline=True
            )
            
            # Add reserve status indicator if applicable
            if user_data.get('status') == 'reserve':
                embed.add_field(
                    name="📋 Status",
                    value="**Reserve** (Not in server)",
                    inline=True
                )
            
            # Send main embed WITHOUT cleanup timer for persistence
            message = await ctx.send(embed=embed)
            
            # Add reaction options for additional info
            await message.add_reaction('🔍')  # For match logs
            await message.add_reaction('📊')  # For extended stats
            
            def check(reaction, user):
                return (user == ctx.author and 
                    str(reaction.emoji) in ['🔍', '📊'] and
                    reaction.message.id == message.id)
            
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                
                # User interacted - clear reactions and show additional info
                try:
                    await message.clear_reactions()
                except:
                    pass
                    
                if str(reaction.emoji) == '🔍':
                    await self.stats_logs(ctx, target)
                elif str(reaction.emoji) == '📊':
                    await self._show_extended_stats(ctx, target)
                    
            except asyncio.TimeoutError:
                # Remove reactions after timeout
                try:
                    await message.clear_reactions()
                except:
                    pass
                
        except Exception as e:
            logger.error(f'Error in stats command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred while retrieving statistics: {str(e)}"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])

    @stats_command.command(name='logs', aliases=['history', 'matches'])
    async def stats_logs(self, ctx, target: Optional[discord.Member] = None, page: int = 1):
        """
        View detailed match history for a user
        Usage: ?stats logs [@user] [page]
        """
        try:
            # Default to command author if no target specified
            if not target:
                target = ctx.author
            
            # Validate page number
            if page < 1:
                page = 1
            
            # Ensure user is registered
            await self.user_system.ensure_user_registered(target)
            
            # Get user's match history
            matches = await self._get_user_match_history(target)
            
            if not matches:
                embed = EmbedTemplates.create_base_embed(
                    title=f"📋 {target.display_name}'s Match History",
                    description="No matches found for this user",
                    color=0x4169E1
                )
                await ctx.send(embed=embed)
                return
            
            # Pagination
            matches_per_page = 5
            total_pages = (len(matches) + matches_per_page - 1) // matches_per_page
            
            if page > total_pages:
                page = total_pages
            
            start_idx = (page - 1) * matches_per_page
            end_idx = min(start_idx + matches_per_page, len(matches))
            page_matches = matches[start_idx:end_idx]
            
            # Create embed
            embed = EmbedTemplates.create_base_embed(
                title=f"📋 {target.display_name}'s Match History",
                description=f"Showing matches {start_idx + 1}-{end_idx} of {len(matches)}",
                color=0x4169E1
            )
            
            # Add avatar if available
            if target.avatar:
                embed.set_thumbnail(url=target.avatar.url)
            
            for match in page_matches:
                # Determine opponent
                opponent_id = match['challenger_id'] if match['challenged_id'] == target.id else match['challenged_id']
                opponent = ctx.guild.get_member(opponent_id)
                opponent_name = opponent.display_name if opponent else f"Unknown ({opponent_id})"
                
                # Determine result and role
                is_winner = match['winner_id'] == target.id
                result_emoji = "🏆" if is_winner else "💔"
                result_text = "Victory" if is_winner else "Defeat"
                
                # Determine if user was challenger or challenged
                role = "Challenger" if match['challenger_id'] == target.id else "Challenged"
                
                # Get ELO changes
                if is_winner:
                    elo_change = match.get('elo_change_winner', 0)
                    elo_before = match.get('winner_elo_before', 'Unknown')
                    elo_after = match.get('winner_elo_after', 'Unknown')
                else:
                    elo_change = match.get('elo_change_loser', 0)
                    elo_before = match.get('loser_elo_before', 'Unknown')
                    elo_after = match.get('loser_elo_after', 'Unknown')
                
                # Format date
                match_date = datetime.fromisoformat(match['match_date']).strftime("%m/%d/%Y %H:%M")
                
                # Build field value
                field_value = f"**{result_emoji} {result_text}** vs **{opponent_name}**\n"
                field_value += f"**Type:** {match['match_type'].title()} • **Role:** {role}\n"
                
                if match.get('score'):
                    field_value += f"**Score:** {match['score']}\n"
                
                field_value += f"**ELO:** {elo_before} → {elo_after} ({elo_change:+d})\n"
                field_value += f"**Date:** {match_date}"
                
                if match.get('notes'):
                    field_value += f"\n**Notes:** {match['notes']}"
                
                embed.add_field(
                    name=f"Match #{match['match_id']}",
                    value=field_value,
                    inline=False
                )
            
            # Add pagination info
            if total_pages > 1:
                embed.set_footer(text=f"Page {page} of {total_pages} • Use ?stats logs @{target.display_name} [page] to navigate")
            else:
                embed.set_footer(text=f"Requested by {ctx.author.display_name}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f'Error in stats logs command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred while retrieving match history: {str(e)}"
            )
            await ctx.send(embed=embed)

    async def _get_recent_matches(self, user: discord.Member, limit: int = 5):
        """Get recent matches for a user"""
        try:
            async with aiosqlite.connect(self.db.db_path) as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute("""
                    SELECT * FROM matches 
                    WHERE challenger_id = ? OR challenged_id = ?
                    ORDER BY match_date DESC 
                    LIMIT ?
                """, (user.id, user.id, limit))
                return await cursor.fetchall()
        except Exception as e:
            logger.error(f'Error getting recent matches: {e}')
            return []

    async def _get_user_match_history(self, user: discord.Member):
        """Get complete match history for a user with proper database connection"""
        try:
            async with aiosqlite.connect(self.db.db_path) as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute("""
                    SELECT m.*, 
                           c.username as challenger_name,
                           ch.username as challenged_name,
                           w.username as winner_name
                    FROM matches m
                    LEFT JOIN users c ON m.challenger_id = c.discord_id
                    LEFT JOIN users ch ON m.challenged_id = ch.discord_id  
                    LEFT JOIN users w ON m.winner_id = w.discord_id
                    WHERE m.challenger_id = ? OR m.challenged_id = ?
                    ORDER BY m.match_date DESC
                """, (user.id, user.id))
                return await cursor.fetchall()
        except Exception as e:
            logger.error(f'Error getting user match history: {e}')
            return []

    async def _show_extended_stats(self, ctx, target: discord.Member):
        """Show extended statistics for a user"""
        try:
            # Get additional stats
            match_history = await self._get_user_match_history(target)
            
            if not match_history:
                embed = EmbedTemplates.create_base_embed(
                    title=f"📊 {target.display_name}'s Extended Statistics",
                    description="No match data available for extended statistics",
                    color=0x4169E1
                )
                await ctx.send(embed=embed)
                return
            
            # Calculate extended statistics
            total_matches = len(match_history)
            wins = sum(1 for match in match_history if match['winner_id'] == target.id)
            losses = total_matches - wins
            
            # Type breakdown
            friendly_matches = [m for m in match_history if m['match_type'] == 'friendly']
            official_matches = [m for m in match_history if m['match_type'] == 'official']
            bm_matches = [m for m in match_history if m['match_type'] == 'bm']
            
            # Recent performance (last 10 matches)
            recent_matches = match_history[:10]
            recent_wins = sum(1 for match in recent_matches if match['winner_id'] == target.id)
            recent_win_rate = (recent_wins / len(recent_matches) * 100) if recent_matches else 0
            
            # ELO progression
            elo_changes = []
            for match in reversed(match_history):  # Oldest first for progression
                if match['winner_id'] == target.id:
                    elo_changes.append(match.get('elo_change_winner', 0))
                else:
                    elo_changes.append(match.get('elo_change_loser', 0))
            
            total_elo_change = sum(elo_changes)
            avg_elo_change = sum(elo_changes) / len(elo_changes) if elo_changes else 0
            
            # Most faced opponents
            opponents = {}
            for match in match_history:
                opponent_id = match['challenger_id'] if match['challenged_id'] == target.id else match['challenged_id']
                opponent = ctx.guild.get_member(opponent_id)
                opponent_name = opponent.display_name if opponent else f"Unknown ({opponent_id})"
                
                if opponent_name not in opponents:
                    opponents[opponent_name] = {'wins': 0, 'losses': 0, 'total': 0}
                
                opponents[opponent_name]['total'] += 1
                if match['winner_id'] == target.id:
                    opponents[opponent_name]['wins'] += 1
                else:
                    opponents[opponent_name]['losses'] += 1
            
            # Sort by total matches
            top_opponents = sorted(opponents.items(), key=lambda x: x[1]['total'], reverse=True)[:3]
            
            # Create extended stats embed
            embed = EmbedTemplates.create_base_embed(
                title=f"📊 {target.display_name}'s Extended Statistics",
                description="Detailed performance analysis",
                color=0x4169E1
            )
            
            if target.avatar:
                embed.set_thumbnail(url=target.avatar.url)
            
            # Match type breakdown
            type_breakdown = f"**Official:** {len(official_matches)}\n"
            type_breakdown += f"**BM:** {len(bm_matches)}\n"
            type_breakdown += f"**Friendly:** {len(friendly_matches)}"
            
            embed.add_field(
                name="📈 Match Breakdown",
                value=type_breakdown,
                inline=True
            )
            
            # Recent performance
            embed.add_field(
                name="🔥 Recent Form (Last 10)",
                value=f"**Wins:** {recent_wins}/{len(recent_matches)}\n**Win Rate:** {recent_win_rate:.1f}%",
                inline=True
            )
            
            # ELO statistics
            embed.add_field(
                name="⚡ ELO Performance",
                value=f"**Total Change:** {total_elo_change:+d}\n**Average:** {avg_elo_change:+.1f}",
                inline=True
            )
            
            # Top opponents
            if top_opponents:
                opponent_text = ""
                for opponent_name, stats in top_opponents:
                    win_rate = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0
                    opponent_text += f"**{opponent_name}:** {stats['wins']}-{stats['losses']} ({win_rate:.0f}%)\n"
                
                embed.add_field(
                    name="⚔️ Most Faced Opponents",
                    value=opponent_text.strip(),
                    inline=False
                )
            
            # Activity timeline (monthly)
            monthly_activity = self._calculate_monthly_activity(match_history)
            if monthly_activity:
                activity_text = ""
                for month, count in monthly_activity[-3:]:  # Last 3 months
                    activity_text += f"**{month}:** {count} matches\n"
                
                embed.add_field(
                    name="📅 Recent Activity",
                    value=activity_text.strip(),
                    inline=True
                )
            
            embed.set_footer(text=f"Based on {total_matches} total matches • Requested by {ctx.author.display_name}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f'Error showing extended stats: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred while calculating extended statistics: {str(e)}"
            )
            await ctx.send(embed=embed)

    def _calculate_monthly_activity(self, match_history):
        """Calculate monthly match activity"""
        try:
            monthly_counts = {}
            
            for match in match_history:
                match_date = datetime.fromisoformat(match['match_date'])
                month_key = match_date.strftime("%Y-%m")
                month_name = match_date.strftime("%b %Y")
                
                if month_name not in monthly_counts:
                    monthly_counts[month_name] = 0
                monthly_counts[month_name] += 1
            
            # Sort by date
            sorted_months = sorted(monthly_counts.items(), key=lambda x: x[0])
            return sorted_months
            
        except Exception as e:
            logger.error(f'Error calculating monthly activity: {e}')
            return []

    # ============================================================================
    # OTHER UTILITY COMMANDS
    # ============================================================================
    
    @commands.command(name='recent', aliases=['activity'])
    async def recent_activity(self, ctx, days: int = 7):
        """
        View recent server activity
        Usage: ?recent [days]
        """
        try:
            if days < 1 or days > 30:
                embed = EmbedTemplates.error_embed(
                    "Invalid Range",
                    "Days must be between 1 and 30"
                )
                await ctx.send(embed=embed)
                return
            
            # Calculate date threshold
            threshold_date = datetime.now() - timedelta(days=days)
            
            # Get recent matches
            async with aiosqlite.connect(self.db.db_path) as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute("""
                    SELECT m.*, c.username as challenger_name, ch.username as challenged_name
                    FROM matches m
                    LEFT JOIN users c ON m.challenger_id = c.discord_id
                    LEFT JOIN users ch ON m.challenged_id = ch.discord_id
                    WHERE m.match_date >= ?
                    ORDER BY m.match_date DESC
                    LIMIT 20
                """, (threshold_date.isoformat(),))
                recent_matches = await cursor.fetchall()
            
            if not recent_matches:
                embed = EmbedTemplates.create_base_embed(
                    title=f"📈 Recent Activity ({days} days)",
                    description="No matches found in the specified time period",
                    color=0x4169E1
                )
                await ctx.send(embed=embed)
                return
            
            # Create activity embed
            embed = EmbedTemplates.create_base_embed(
                title=f"📈 Recent Server Activity",
                description=f"Activity from the last {days} day{'s' if days != 1 else ''} ({len(recent_matches)} matches)",
                color=0x4169E1
            )
            
            # Activity summary
            match_types = {}
            for match in recent_matches:
                match_type = match['match_type']
                if match_type not in match_types:
                    match_types[match_type] = 0
                match_types[match_type] += 1
            
            summary_text = ""
            for match_type, count in match_types.items():
                summary_text += f"**{match_type.title()}:** {count}\n"
            
            embed.add_field(
                name="📊 Match Summary",
                value=summary_text.strip(),
                inline=True
            )
            
            # Recent matches (show first 5)
            matches_text = ""
            for match in recent_matches[:5]:
                challenger = ctx.guild.get_member(match['challenger_id'])
                challenged = ctx.guild.get_member(match['challenged_id'])
                winner = ctx.guild.get_member(match['winner_id'])
                
                challenger_name = challenger.display_name if challenger else "Unknown"
                challenged_name = challenged.display_name if challenged else "Unknown"
                winner_name = winner.display_name if winner else "Unknown"
                
                match_date = datetime.fromisoformat(match['match_date']).strftime("%m/%d %H:%M")
                
                matches_text += f"**{challenger_name}** vs **{challenged_name}**\n"
                matches_text += f"Winner: {winner_name} • {match['match_type'].title()} • {match_date}\n\n"
            
            embed.add_field(
                name="⚔️ Recent Matches",
                value=matches_text.strip() or "No matches found",
                inline=False
            )
            
            if len(recent_matches) > 5:
                embed.set_footer(text=f"Showing 5 of {len(recent_matches)} recent matches")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f'Error in recent activity command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred while retrieving recent activity: {str(e)}"
            )
            await ctx.send(embed=embed)

    @commands.command(name='compare')
    async def compare_users(self, ctx, user1: discord.Member, user2: discord.Member):
        """
        Compare two users' statistics
        Usage: ?compare @user1 @user2
        """
        try:
            # Ensure both users are registered
            await self.user_system.ensure_user_registered(user1)
            await self.user_system.ensure_user_registered(user2)
            
            # Get user data
            user1_data = await self.user_system.get_user_profile(user1)
            user2_data = await self.user_system.get_user_profile(user2)
            
            if not user1_data or not user2_data:
                embed = EmbedTemplates.error_embed(
                    "Data Not Found",
                    "Could not retrieve profile data for one or both users"
                )
                await ctx.send(embed=embed)
                return
            
            # Create comparison embed
            embed = EmbedTemplates.create_base_embed(
                title="⚖️ User Comparison",
                description=f"**{user1.display_name}** vs **{user2.display_name}**",
                color=0x9C27B0
            )
            
            # Basic stats comparison
            user1_wr = (user1_data['wins'] / user1_data['games_played'] * 100) if user1_data['games_played'] > 0 else 0
            user2_wr = (user2_data['wins'] / user2_data['games_played'] * 100) if user2_data['games_played'] > 0 else 0
            
            embed.add_field(
                name=f"📊 {user1.display_name}",
                value=f"**Rank:** {user1_data['tier']} {user1_data['rank_numeral']}\n"
                      f"**ELO:** {user1_data['elo_rating']}\n"
                      f"**Record:** {user1_data['wins']}-{user1_data['losses']}\n"
                      f"**Win Rate:** {user1_wr:.1f}%\n"
                      f"**Games:** {user1_data['games_played']}",
                inline=True
            )
            
            embed.add_field(
                name=f"📊 {user2.display_name}",
                value=f"**Rank:** {user2_data['tier']} {user2_data['rank_numeral']}\n"
                      f"**ELO:** {user2_data['elo_rating']}\n"
                      f"**Record:** {user2_data['wins']}-{user2_data['losses']}\n"
                      f"**Win Rate:** {user2_wr:.1f}%\n"
                      f"**Games:** {user2_data['games_played']}",
                inline=True
            )
            
            # Head-to-head record
            h2h_record = await self._get_head_to_head_record(user1, user2)
            
            h2h_text = f"**{user1.display_name}:** {h2h_record['user1_wins']}\n"
            h2h_text += f"**{user2.display_name}:** {h2h_record['user2_wins']}\n"
            h2h_text += f"**Total Matches:** {h2h_record['total_matches']}"
            
            embed.add_field(
                name="⚔️ Head-to-Head",
                value=h2h_text,
                inline=False
            )
            
            # Comparison summary
            comparisons = []
            
            if user1_data['elo_rating'] > user2_data['elo_rating']:
                comparisons.append(f"🏆 {user1.display_name} has higher ELO (+{user1_data['elo_rating'] - user2_data['elo_rating']})")
            elif user2_data['elo_rating'] > user1_data['elo_rating']:
                comparisons.append(f"🏆 {user2.display_name} has higher ELO (+{user2_data['elo_rating'] - user1_data['elo_rating']})")
            else:
                comparisons.append("🤝 Equal ELO ratings")
            
            if user1_wr > user2_wr:
                comparisons.append(f"📈 {user1.display_name} has better win rate (+{user1_wr - user2_wr:.1f}%)")
            elif user2_wr > user1_wr:
                comparisons.append(f"📈 {user2.display_name} has better win rate (+{user2_wr - user1_wr:.1f}%)")
            
            if user1_data['games_played'] > user2_data['games_played']:
                comparisons.append(f"🎮 {user1.display_name} is more active (+{user1_data['games_played'] - user2_data['games_played']} games)")
            elif user2_data['games_played'] > user1_data['games_played']:
                comparisons.append(f"🎮 {user2.display_name} is more active (+{user2_data['games_played'] - user1_data['games_played']} games)")
            
            if comparisons:
                embed.add_field(
                    name="🔍 Analysis",
                    value="\n".join(comparisons),
                    inline=False
                )
            
            embed.set_footer(text=f"Comparison requested by {ctx.author.display_name}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f'Error in compare command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred while comparing users: {str(e)}"
            )
            await ctx.send(embed=embed)

    async def _get_head_to_head_record(self, user1: discord.Member, user2: discord.Member):
        """Get head-to-head record between two users"""
        try:
            async with aiosqlite.connect(self.db.db_path) as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute("""
                    SELECT winner_id FROM matches 
                    WHERE (challenger_id = ? AND challenged_id = ?) 
                       OR (challenger_id = ? AND challenged_id = ?)
                """, (user1.id, user2.id, user2.id, user1.id))
                matches = await cursor.fetchall()
            
            user1_wins = sum(1 for match in matches if match['winner_id'] == user1.id)
            user2_wins = sum(1 for match in matches if match['winner_id'] == user2.id)
            total_matches = len(matches)
            
            return {
                'user1_wins': user1_wins,
                'user2_wins': user2_wins,
                'total_matches': total_matches
            }
            
        except Exception as e:
            logger.error(f'Error getting head-to-head record: {e}')
            return {'user1_wins': 0, 'user2_wins': 0, 'total_matches': 0}

    @commands.command(name='search')
    async def search_users(self, ctx, *, username: str):
        """
        Search for users by username
        Usage: ?search <username>
        """
        try:
            if len(username) < 2:
                embed = EmbedTemplates.error_embed(
                    "Search Too Short",
                    "Please provide at least 2 characters to search"
                )
                await ctx.send(embed=embed)
                return
            
            # Search in database
            async with aiosqlite.connect(self.db.db_path) as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute("""
                    SELECT discord_id, username, tier, rank_numeral, elo_rating, wins, losses, games_played
                    FROM users 
                    WHERE username LIKE ? OR roblox_username LIKE ?
                    ORDER BY elo_rating DESC
                    LIMIT 10
                """, (f"%{username}%", f"%{username}%"))
                results = await cursor.fetchall()
            
            if not results:
                embed = EmbedTemplates.create_base_embed(
                    title="🔍 Search Results",
                    description=f"No users found matching '{username}'",
                    color=0x4169E1
                )
                await ctx.send(embed=embed)
                return
            
            # Create results embed
            embed = EmbedTemplates.create_base_embed(
                title="🔍 Search Results",
                description=f"Found {len(results)} user{'s' if len(results) != 1 else ''} matching '{username}'",
                color=0x4169E1
            )
            
            for result in results:
                user = ctx.guild.get_member(result['discord_id'])
                display_name = user.display_name if user else result['username']
                
                win_rate = (result['wins'] / result['games_played'] * 100) if result['games_played'] > 0 else 0
                
                user_info = f"**Rank:** {result['tier']} {result['rank_numeral']}\n"
                user_info += f"**ELO:** {result['elo_rating']}\n"
                user_info += f"**Record:** {result['wins']}-{result['losses']} ({win_rate:.1f}%)\n"
                user_info += f"**Games:** {result['games_played']}"
                
                embed.add_field(
                    name=f"👤 {display_name}",
                    value=user_info,
                    inline=True
                )
            
            embed.set_footer(text=f"Search requested by {ctx.author.display_name}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f'Error in search command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred while searching: {str(e)}"
            )
            await ctx.send(embed=embed)

    # ============================================================================
    # ADMIN UTILITY COMMANDS
    # ============================================================================
    
    @commands.command(name='tickets')
    async def view_active_tickets(self, ctx):
        """
        View all active tickets (Admin only)
        Usage: ?tickets
        """
        role_manager = RoleManager(ctx.guild)
        if not role_manager.has_admin_role(ctx.author):
            embed = EmbedTemplates.error_embed(
                "Permission Denied",
                "You need admin permissions to view active tickets"
            )
            await ctx.send(embed=embed)
            return
        
        try:
            await self.ticket_system.initialize()
            
            # Get active tickets from memory and database
            active_tickets = []
            
            # From memory
            if hasattr(self.ticket_system, 'active_tickets'):
                for channel_id, ticket_info in self.ticket_system.active_tickets.items():
                    channel = ctx.guild.get_channel(channel_id)
                    if channel:  # Only include existing channels
                        active_tickets.append((channel, ticket_info))
            
            # From database (as backup)
            async with aiosqlite.connect(self.db.db_path) as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute("""
                    SELECT * FROM active_tickets WHERE status = 'active'
                """)
                db_tickets = await cursor.fetchall()
                
                for ticket in db_tickets:
                    channel = ctx.guild.get_channel(ticket['channel_id'])
                    if channel and not any(t[0].id == channel.id for t in active_tickets):
                        active_tickets.append((channel, ticket))
            
            if not active_tickets:
                embed = EmbedTemplates.create_base_embed(
                    title="🎫 Active Tickets",
                    description="No active tickets found",
                    color=0x4169E1
                )
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['info'])
                return
            
            # Create tickets embed
            embed = EmbedTemplates.create_base_embed(
                title="🎫 Active Tickets",
                description=f"Found {len(active_tickets)} active ticket{'s' if len(active_tickets) != 1 else ''}",
                color=0x4169E1
            )
            
            for channel, ticket_info in active_tickets[:10]:  # Limit to 10 for embed size
                challenger = ctx.guild.get_member(ticket_info.get('challenger_id'))
                challenged = ctx.guild.get_member(ticket_info.get('challenged_id'))
                
                challenger_name = challenger.display_name if challenger else "Unknown"
                challenged_name = challenged.display_name if challenged else "Unknown"
                
                ticket_desc = f"**Type:** {ticket_info.get('ticket_type', 'Unknown')}\n"
                ticket_desc += f"**Duel Type:** {ticket_info.get('duel_type', 'Unknown')}\n"
                ticket_desc += f"**Participants:** {challenger_name} vs {challenged_name}\n"
                ticket_desc += f"**Created:** {ticket_info.get('created_at', 'Unknown')[:10]}"
                
                embed.add_field(
                    name=f"#{channel.name}",
                    value=ticket_desc,
                    inline=True
                )
            
            if len(active_tickets) > 10:
                embed.set_footer(text=f"Showing 10 of {len(active_tickets)} active tickets")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f'Error in tickets command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred while retrieving tickets: {str(e)}"
            )
            await ctx.send(embed=embed)

    @commands.command(name='cleanup')
    async def cleanup_expired_data(self, ctx):
        """
        Clean up expired challenges and old data (Admin only)
        Usage: ?cleanup
        """
        role_manager = RoleManager(ctx.guild)
        if not role_manager.has_admin_role(ctx.author):
            embed = EmbedTemplates.error_embed(
                "Permission Denied",
                "You need admin permissions to run cleanup"
            )
            await ctx.send(embed=embed)
            return
        
        try:
            # Clean up expired challenges
            cleanup_result = await self.challenge_system.cleanup_expired_challenges()
            
            embed = EmbedTemplates.create_base_embed(
                title="🧹 Data Cleanup Complete",
                description="Cleanup operation completed successfully",
                color=0x00FF00
            )
            
            embed.add_field(
                name="📊 Results",
                value=f"**Expired Challenges Removed:** {cleanup_result.get('expired_challenges', 0)}\n"
                      f"**Database Optimized:** Yes",
                inline=False
            )
            
            embed.set_footer(text=f"Cleanup performed by {ctx.author.display_name}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f'Error in cleanup command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred during cleanup: {str(e)}"
            )
            await ctx.send(embed=embed)