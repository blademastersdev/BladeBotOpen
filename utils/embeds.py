"""
Discord Embed Templates
Provides consistent embed formatting across the bot
"""

import discord
from datetime import datetime
from typing import Optional, Dict, Any, List
from config import EMBED_COLORS, TIER_COLORS, DUEL_TYPES, get_tier_color

class EmbedTemplates:
    @staticmethod
    def create_base_embed(title: str, description: str = "", color: int = EMBED_COLORS['info'],
                         author_name: str = None, author_icon: str = None) -> discord.Embed:
        """Create a base embed with common formatting"""
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.now()
        )
        
        if author_name:
            embed.set_author(name=author_name, icon_url=author_icon)
        
        embed.set_footer(text="BladeBot • ROBLOX Linked Sword Dueling")
        return embed
    
    @staticmethod
    def error_embed(title: str = "Error", description: str = "") -> discord.Embed:
        """Create an error embed"""
        return EmbedTemplates.create_base_embed(
            title=f"❌ {title}",
            description=description,
            color=EMBED_COLORS['error']
        )
    
    @staticmethod
    def success_embed(title: str = "Success", description: str = "") -> discord.Embed:
        """Create a success embed"""
        return EmbedTemplates.create_base_embed(
            title=f"✅ {title}",
            description=description,
            color=EMBED_COLORS['success']
        )
    
    @staticmethod
    def warning_embed(title: str = "Warning", description: str = "") -> discord.Embed:
        """Create a warning embed"""
        return EmbedTemplates.create_base_embed(
            title=f"⚠️ {title}",
            description=description,
            color=EMBED_COLORS['warning']
        )
    
    @staticmethod
    def user_stats_embed(user_data: Dict[str, Any], member: discord.Member) -> discord.Embed:
        """Create a user statistics embed"""
        embed = EmbedTemplates.create_base_embed(
            title=f"📊 {member.display_name}'s Statistics",
            color=get_tier_color(user_data['tier'])
        )
        
        # Set user avatar
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
        
        # Basic info
        embed.add_field(
            name="🏆 Rank",
            value=f"**{user_data['tier']} {user_data['rank_numeral']}**",
            inline=True
        )
        
        embed.add_field(
            name="⚡ ELO Rating",
            value=f"**{user_data['elo_rating']}** ({user_data['elo_tier']})",
            inline=True
        )
        
        embed.add_field(
            name="🎮 Games Played",
            value=f"**{user_data['games_played']}**",
            inline=True
        )
        
        # Win/Loss record
        embed.add_field(
            name="📈 Record",
            value=f"**{user_data['wins']}W - {user_data['losses']}L**",
            inline=True
        )
        
        embed.add_field(
            name="📊 Win Rate",
            value=f"**{user_data['win_rate']:.1f}%**",
            inline=True
        )
        
        # Join date
        if user_data.get('joined_date'):
            join_date = datetime.fromisoformat(user_data['joined_date']).strftime('%B %d, %Y')
            embed.add_field(
                name="📅 Joined",
                value=join_date,
                inline=True
            )
        
        # ROBLOX username if available
        if user_data.get('roblox_username'):
            embed.add_field(
                name="🎮 ROBLOX Username",
                value=user_data['roblox_username'],
                inline=False
            )
        
        return embed
    
    @staticmethod
    def challenge_embed(challenge_data: Dict[str, Any], guild: discord.Guild) -> discord.Embed:
        """Create a challenge announcement embed"""
        duel_info = DUEL_TYPES[challenge_data['challenge_type']]
        
        embed = EmbedTemplates.create_base_embed(
            title=f"⚔️ {duel_info['name']} Challenge",
            description=duel_info['description'],
            color=EMBED_COLORS['duel']
        )
        
        challenger = challenge_data['challenger']
        if challenger:
            embed.add_field(
                name="🗡️ Challenger",
                value=f"{challenger.mention}\n{challenge_data['challenger_rank']}",
                inline=True
            )
        
        if challenge_data['challenged']:
            challenged = challenge_data['challenged']
            embed.add_field(
                name="🛡️ Challenged",
                value=f"{challenged.mention}\n{challenge_data['challenged_rank']}",
                inline=True
            )
        else:
            embed.add_field(
                name="🛡️ Open Challenge",
                value="Anyone can accept!",
                inline=True
            )
        
        # Add acceptance instructions
        if challenge_data['challenged']:
            embed.add_field(
                name="💬 How to Respond",
                value=f"**{challenge_data['challenged'].display_name}** can use:\n`?accept` or `?decline`",
                inline=False
            )
        else:
            embed.add_field(
                name="💬 How to Accept",
                value="Use `?accept` to accept this challenge!",
                inline=False
            )
        
        # Add expiration info
        expires_at = datetime.fromisoformat(challenge_data['expires_at'])
        embed.add_field(
            name="⏰ Expires",
            value=f"<t:{int(expires_at.timestamp())}:R>",
            inline=True
        )
        
        return embed
    
    @staticmethod
    def match_result_embed(match_data: Dict[str, Any], guild: discord.Guild) -> discord.Embed:
        """Create a match result embed"""
        match_info = match_data['match_data']
        duel_info = DUEL_TYPES[match_info['match_type']]
        
        embed = EmbedTemplates.create_base_embed(
            title=f"🏆 {duel_info['name']} Match Result",
            color=EMBED_COLORS['success']
        )
        
        winner = guild.get_member(match_info['winner_id'])
        loser = guild.get_member(match_info['loser_id'])
        
        if winner and loser:
            embed.add_field(
                name="🥇 Winner",
                value=f"{winner.mention}\n{match_data['winner']['tier']} {match_data['winner']['rank_numeral']}",
                inline=True
            )
            
            embed.add_field(
                name="🥈 Runner-up",
                value=f"{loser.mention}\n{match_data['loser']['tier']} {match_data['loser']['rank_numeral']}",
                inline=True
            )
        
        # Score if available
        if match_info.get('score'):
            embed.add_field(
                name="📊 Score",
                value=match_info['score'],
                inline=True
            )
        
        # ELO changes
        elo_changes = match_data['elo_changes']
        elo_text = (
            f"**Winner:** {elo_changes['winner_before']} → {elo_changes['winner_after']} "
            f"({elo_changes['winner_change']:+d})\n"
            f"**Runner-up:** {elo_changes['loser_before']} → {elo_changes['loser_after']} "
            f"({elo_changes['loser_change']:+d})"
        )
        embed.add_field(
            name="⚡ ELO Changes",
            value=elo_text,
            inline=False
        )
        
        # Rank change info for BM duels
        if match_info['match_type'] == 'bm' and match_data.get('rank_change'):
            rank_change = match_data['rank_change']
            if rank_change['status'] == 'pending':
                embed.add_field(
                    name="👑 Rank Change Pending",
                    value="⚠️ Awaiting admin confirmation",
                    inline=False
                )
            elif rank_change['status'] == 'confirmed':
                embed.add_field(
                    name="👑 Rank Change Confirmed",
                    value=(
                        f"**{winner.display_name}:** {rank_change['winner_old_tier']} {rank_change['winner_old_rank']} "
                        f"→ {rank_change['winner_new_tier']} {rank_change['winner_new_rank']}\n"
                        f"**{loser.display_name}:** {rank_change['loser_old_tier']} {rank_change['loser_old_rank']} "
                        f"→ {rank_change['loser_new_tier']} {rank_change['loser_new_rank']}"
                    ),
                    inline=False
                )
        
        embed.add_field(
            name="🆔 Match ID",
            value=f"`{match_info['match_id']}`",
            inline=True
        )
        
        return embed
    
    @staticmethod
    def leaderboard_embed(leaderboard_data: List[Dict[str, Any]], title: str = "ELO Leaderboard") -> discord.Embed:
        """Create a leaderboard embed"""
        embed = EmbedTemplates.create_base_embed(
            title=f"🏆 {title}",
            color=EMBED_COLORS['rank']
        )
        
        if not leaderboard_data:
            embed.description = "No data available"
            return embed
        
        # Top 3 special display
        if len(leaderboard_data) >= 3:
            top_3 = leaderboard_data[:3]
            medals = ["🥇", "🥈", "🥉"]
            
            for i, user in enumerate(top_3):
                embed.add_field(
                    name=f"{medals[i]} #{i+1}",
                    value=(
                        f"**{user['username']}**\n"
                        f"{user['tier']} {user['rank_numeral']}\n"
                        f"ELO: {user['elo_rating']}\n"
                        f"Record: {user['wins']}W-{user['losses']}L"
                    ),
                    inline=True
                )
        
        # Remaining users in a formatted list
        if len(leaderboard_data) > 3:
            remaining_text = ""
            for i, user in enumerate(leaderboard_data[3:], 4):
                if i > 15:  # Limit to prevent embed being too long
                    remaining_text += f"\n... and {len(leaderboard_data) - 15} more"
                    break
                
                remaining_text += (
                    f"**{i}.** {user['username']} - "
                    f"{user['tier']} {user['rank_numeral']} - "
                    f"{user['elo_rating']} ELO\n"
                )
            
            if remaining_text:
                embed.add_field(
                    name="📋 Rankings",
                    value=remaining_text,
                    inline=False
                )
        
        return embed
    
    @staticmethod
    def rank_distribution_embed(distribution_data: Dict[str, Any]) -> discord.Embed:
        """Create a rank distribution embed"""
        embed = EmbedTemplates.create_base_embed(
            title="👑 Rank Distribution",
            description=f"Total Users: **{distribution_data['total_users']}** / {distribution_data['total_capacity']}",
            color=EMBED_COLORS['rank']
        )
        
        for tier, tier_data in distribution_data.items():
            if tier in ['total_users', 'total_capacity']:
                continue
            
            tier_text = f"**Total: {tier_data['total']} / {tier_data['capacity']}**\n"
            
            for numeral, rank_data in tier_data['ranks'].items():
                tier_text += (
                    f"{numeral}: {rank_data['count']}/{rank_data['capacity']} "
                    f"({rank_data['percentage']:.0f}%)\n"
                )
            
            embed.add_field(
                name=f"{tier}",
                value=tier_text,
                inline=True
            )
        
        return embed
    
    @staticmethod
    def duel_history_embed(matches: List[Dict[str, Any]], user_name: str, page: int = 1) -> discord.Embed:
        """Create a duel history embed"""
        embed = EmbedTemplates.create_base_embed(
            title=f"📜 {user_name}'s Duel History",
            color=EMBED_COLORS['info']
        )
        
        if not matches:
            embed.description = "No duels found"
            return embed
        
        for i, match in enumerate(matches):
            result_emoji = "🟢" if match['user_won'] else "🔴"
            result_text = "Victory" if match['user_won'] else "Defeat"
            
            match_date = datetime.fromisoformat(match['match_date']).strftime('%m/%d/%y')
            
            field_value = (
                f"{result_emoji} **{result_text}** vs {match['opponent_name']}\n"
                f"Type: {DUEL_TYPES[match['match_type']]['name']}\n"
                f"ELO: {match['user_elo_change']:+d} | Date: {match_date}"
            )
            
            if match.get('score'):
                field_value += f"\nScore: {match['score']}"
            
            embed.add_field(
                name=f"Match #{match['match_id']}",
                value=field_value,
                inline=False
            )
        
        embed.set_footer(text=f"BladeBot • Page {page} • Showing {len(matches)} matches")
        return embed
    
    @staticmethod
    def pending_rank_changes_embed(pending_changes: List[Dict[str, Any]]) -> discord.Embed:
        """Create an embed for pending rank changes"""
        embed = EmbedTemplates.create_base_embed(
            title="⏳ Pending Rank Changes",
            description=f"**{len(pending_changes)}** rank changes awaiting confirmation",
            color=EMBED_COLORS['warning']
        )
        
        for change in pending_changes[:10]:  # Limit to 10 to prevent embed being too long
            change_date = datetime.fromisoformat(change['created_date']).strftime('%m/%d %H:%M')
            
            field_value = (
                f"**Winner:** {change['winner_name']}\n"
                f"{change['winner_old_tier']} {change['winner_old_rank']} → "
                f"{change['winner_new_tier']} {change['winner_new_rank']}\n"
                f"**Loser:** {change['loser_name']}\n"
                f"{change['loser_old_tier']} {change['loser_old_rank']} → "
                f"{change['loser_new_tier']} {change['loser_new_rank']}\n"
                f"Match: {change['score'] or 'No score'} | {change_date}"
            )
            
            embed.add_field(
                name=f"Change #{change['change_id']} (Match #{change['match_id']})",
                value=field_value,
                inline=False
            )
        
        if len(pending_changes) > 10:
            embed.add_field(
                name="...",
                value=f"And {len(pending_changes) - 10} more pending changes",
                inline=False
            )
        
        return embed
    
    @staticmethod
    def help_embed(command_prefix: str) -> discord.Embed:
        """Create the main help embed"""
        embed = EmbedTemplates.create_base_embed(
            title="🗡️ BladeBot Commands",
            description="ROBLOX Linked Sword Dueling Bot",
            color=EMBED_COLORS['info']
        )
        
        # Public commands
        public_commands = (
            f"`{command_prefix}friendly [@user]` - Challenge to friendly duel\n"
            f"`{command_prefix}official [@user]` - Challenge to official duel\n"
            f"`{command_prefix}challenge [@user]` - Challenge to BM duel (rank up)\n"
            f"`{command_prefix}accept` - Accept a challenge\n"
            f"`{command_prefix}decline` - Decline a challenge\n"
            f"`{command_prefix}cancel_challenge` - Cancel your own challenge\n"
            f"`{command_prefix}stats [@user]` - View statistics\n"
            f"`{command_prefix}leaderboard` - View ELO leaderboard\n"
            f"`{command_prefix}duellogs [@user]` - View duel history\n"
            f"`{command_prefix}mychallenges` - View your active challenges\n"
            f"`{command_prefix}about` - About the organization"
        )
        
        embed.add_field(
            name="🎮 Public Commands",
            value=public_commands,
            inline=False
        )
        
        # Moderator commands
        mod_commands = (
            f"`{command_prefix}record_duel` - Record match results (smart detection)\n"
            f"`{command_prefix}close` - Close tickets\n"
            f"`{command_prefix}ticket_info` - Show ticket information\n"
            f"`{command_prefix}tickets` - View active tickets"
        )
        
        embed.add_field(
            name="🛡️ Moderator Commands",
            value=mod_commands,
            inline=False
        )
        
        # Admin commands
        admin_commands = (
            f"`{command_prefix}evaluate @user <rank>` - Place from evaluation\n"
            f"`{command_prefix}confirm` - Confirm rank change\n"
            f"`{command_prefix}pending` - View pending rank changes\n"
            f"`{command_prefix}duel_history` - Browse all match history\n"
            f"`{command_prefix}void_duel` - Void matches (Grandmaster only)"
        )
        
        embed.add_field(
            name="👑 Admin Commands",
            value=admin_commands,
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
                f"• Use `{command_prefix}help <command>` for detailed help on specific commands\n"
                f"• Many commands have interactive modes if you don't provide parameters\n"
                f"• Reply to challenge messages to accept them quickly"
            ),
            inline=False
        )
        
        return embed