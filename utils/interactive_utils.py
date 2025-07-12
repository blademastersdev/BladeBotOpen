"""
Interactive Utilities
Provides reusable interactive prompt and pagination functionality
"""

import discord
import asyncio
import logging
from typing import Optional, List, Dict, Any, Callable, Union
from utils.embeds import EmbedTemplates
from datetime import datetime

logger = logging.getLogger('BladeBot.InteractiveUtils')

class InteractivePrompts:
    """Handles interactive prompts and user input collection"""
    
    @staticmethod
    async def numbered_selection(ctx, options: List[Dict[str, Any]], 
                               title: str = "Select Option",
                               description: str = "Choose an option by typing its number",
                               timeout: int = 30,
                               cancel_option: bool = True) -> Optional[int]:
        """
        Present a numbered list for user selection
        
        Args:
            ctx: Command context
            options: List of option dictionaries with 'name' and 'value' keys
            title: Embed title
            description: Embed description
            timeout: Timeout in seconds
            cancel_option: Whether to allow cancellation
            
        Returns:
            Selected index (0-based) or None if cancelled/timed out
        """
        try:
            embed = EmbedTemplates.create_base_embed(
                title=title,
                description=description,
                color=0xFF6600
            )
            
            # Add numbered options
            options_text = ""
            for i, option in enumerate(options[:20], 1):  # Limit to 20 options
                options_text += f"**{i}.** {option['name']}\n"
                if 'description' in option:
                    options_text += f"    {option['description']}\n"
                options_text += "\n"
            
            embed.add_field(
                name="Options",
                value=options_text,
                inline=False
            )
            
            instructions = f"Type the number (1-{len(options)})"
            if cancel_option:
                instructions += " or 'cancel' to cancel"
            
            embed.add_field(
                name="Instructions",
                value=instructions,
                inline=False
            )
            
            await ctx.send(embed=embed)
            
            def check(message):
                if message.author != ctx.author or message.channel != ctx.channel:
                    return False
                    
                content = message.content.strip().lower()
                if cancel_option and content == 'cancel':
                    return True
                    
                if content.isdigit():
                    num = int(content)
                    return 1 <= num <= len(options)
                    
                return False
            
            response = await ctx.bot.wait_for('message', check=check, timeout=timeout)
            
            if response.content.lower() == 'cancel':
                embed = EmbedTemplates.warning_embed("Selection Cancelled", "Operation was cancelled")
                await ctx.send(embed=embed)
                return None
            
            selection_num = int(response.content)
            return selection_num - 1  # Convert to 0-based index
            
        except asyncio.TimeoutError:
            embed = EmbedTemplates.warning_embed(
                "Selection Timed Out", 
                f"No response received within {timeout} seconds"
            )
            await ctx.send(embed=embed)
            return None
        except Exception as e:
            logger.error(f'Error in numbered selection: {e}')
            return None
    
    @staticmethod
    async def text_input(ctx, prompt: str, 
                        title: str = "Input Required",
                        timeout: int = 60,
                        validator: Optional[Callable[[str], tuple]] = None,
                        max_length: int = 2000) -> Optional[str]:
        """
        Get text input from user with optional validation
        
        Args:
            ctx: Command context
            prompt: Prompt message for user
            title: Embed title
            timeout: Timeout in seconds
            validator: Optional validation function that returns (is_valid, error_message)
            max_length: Maximum input length
            
        Returns:
            User input string or None if cancelled/timed out
        """
        try:
            embed = EmbedTemplates.create_base_embed(
                title=title,
                description=prompt,
                color=0x00BFFF
            )
            
            embed.add_field(
                name="Instructions",
                value=f"Type your response (max {max_length} characters) or 'cancel' to cancel",
                inline=False
            )
            
            await ctx.send(embed=embed)
            
            def check(message):
                return (message.author == ctx.author and 
                       message.channel == ctx.channel)
            
            while True:
                response = await ctx.bot.wait_for('message', check=check, timeout=timeout)
                
                if response.content.lower() == 'cancel':
                    embed = EmbedTemplates.warning_embed("Input Cancelled", "Operation was cancelled")
                    await ctx.send(embed=embed)
                    return None
                
                input_text = response.content.strip()
                
                # Check length
                if len(input_text) > max_length:
                    embed = EmbedTemplates.error_embed(
                        "Input Too Long",
                        f"Input must be {max_length} characters or less"
                    )
                    await ctx.send(embed=embed)
                    continue
                
                # Run validator if provided
                if validator:
                    is_valid, error_message = validator(input_text)
                    if not is_valid:
                        embed = EmbedTemplates.error_embed("Invalid Input", error_message)
                        await ctx.send(embed=embed)
                        continue
                
                return input_text
                
        except asyncio.TimeoutError:
            embed = EmbedTemplates.warning_embed(
                "Input Timed Out",
                f"No response received within {timeout} seconds"
            )
            await ctx.send(embed=embed)
            return None
        except Exception as e:
            logger.error(f'Error in text input: {e}')
            return None
    
    @staticmethod
    async def yes_no_prompt(ctx, question: str,
                           title: str = "Confirmation Required",
                           timeout: int = 30) -> Optional[bool]:
        """
        Get yes/no confirmation from user
        
        Args:
            ctx: Command context
            question: Question to ask
            title: Embed title
            timeout: Timeout in seconds
            
        Returns:
            True for yes, False for no, None for timeout/cancel
        """
        try:
            embed = EmbedTemplates.create_base_embed(
                title=title,
                description=question,
                color=0xFFFF00
            )
            
            embed.add_field(
                name="Instructions",
                value="Type 'yes' or 'no' (or 'y'/'n')",
                inline=False
            )
            
            await ctx.send(embed=embed)
            
            def check(message):
                if message.author != ctx.author or message.channel != ctx.channel:
                    return False
                content = message.content.lower().strip()
                return content in ['yes', 'no', 'y', 'n']
            
            response = await ctx.bot.wait_for('message', check=check, timeout=timeout)
            content = response.content.lower().strip()
            
            return content in ['yes', 'y']
            
        except asyncio.TimeoutError:
            embed = EmbedTemplates.warning_embed(
                "Prompt Timed Out",
                f"No response received within {timeout} seconds"
            )
            await ctx.send(embed=embed)
            return None
        except Exception as e:
            logger.error(f'Error in yes/no prompt: {e}')
            return None


class PaginatedView(discord.ui.View):
    """Discord UI View for paginated content"""
    
    def __init__(self, embeds: List[discord.Embed], timeout: int = 180):
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.current_page = 0
        
    @discord.ui.button(label='⬅️ Previous', style=discord.ButtonStyle.gray)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label='➡️ Next', style=discord.ButtonStyle.gray)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label='🗑️ Close', style=discord.ButtonStyle.red)
    async def close_pagination(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=None)
        self.stop()


class Paginator:
    """Handles pagination for long lists of data"""
    
    @staticmethod
    def paginate_embeds(data: List[Any], 
                       items_per_page: int = 10,
                       embed_creator: Callable[[List[Any], int, int], discord.Embed] = None) -> List[discord.Embed]:
        """
        Create paginated embeds from data
        
        Args:
            data: List of items to paginate
            items_per_page: Number of items per page
            embed_creator: Function that creates embed for a page of data
            
        Returns:
            List of Discord embeds
        """
        if not data:
            return [EmbedTemplates.warning_embed("No Data", "No items to display")]
        
        embeds = []
        total_pages = (len(data) + items_per_page - 1) // items_per_page
        
        for page in range(total_pages):
            start_idx = page * items_per_page
            end_idx = min(start_idx + items_per_page, len(data))
            page_data = data[start_idx:end_idx]
            
            if embed_creator:
                embed = embed_creator(page_data, page + 1, total_pages)
            else:
                # Default embed creation
                embed = EmbedTemplates.create_base_embed(
                    title=f"Page {page + 1} of {total_pages}",
                    description=f"Items {start_idx + 1}-{end_idx} of {len(data)}",
                    color=0x00BFFF
                )
                
                items_text = ""
                for i, item in enumerate(page_data):
                    items_text += f"{start_idx + i + 1}. {str(item)}\n"
                
                embed.add_field(
                    name="Items",
                    value=items_text or "No items",
                    inline=False
                )
            
            embeds.append(embed)
        
        return embeds
    
    @staticmethod
    async def send_paginated(ctx, embeds: List[discord.Embed], timeout: int = 180):
        """
        Send paginated embeds with navigation buttons
        
        Args:
            ctx: Command context
            embeds: List of embeds to paginate
            timeout: View timeout in seconds
        """
        if not embeds:
            embed = EmbedTemplates.warning_embed("No Data", "No content to display")
            await ctx.send(embed=embed)
            return
        
        if len(embeds) == 1:
            # Single page, no pagination needed
            await ctx.send(embed=embeds[0])
            return
        
        # Multiple pages, use pagination view
        view = PaginatedView(embeds, timeout=timeout)
        await ctx.send(embed=embeds[0], view=view)

class MatchQueryBuilder:
    """Builds database queries for match filtering and sorting"""
    
    @staticmethod
    def build_match_query(filter_user=None, filter_type=None, sort_by='date'):
        query = """
            SELECT m.*, c_user.username as challenger_name, ch_user.username as challenged_name, w_user.username as winner_name
            FROM matches m
            LEFT JOIN users c_user ON m.challenger_id = c_user.discord_id
            LEFT JOIN users ch_user ON m.challenged_id = ch_user.discord_id
            LEFT JOIN users w_user ON m.winner_id = w_user.discord_id
        """
        conditions, params = [], []
        
        if filter_user:
            conditions.append("(m.challenger_id = ? OR m.challenged_id = ?)")
            params.extend([filter_user.id, filter_user.id])
        if filter_type:
            conditions.append("m.match_type = ?")
            params.append(filter_type)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        sort_options = {
            'date': 'ORDER BY m.match_date DESC',
            'user': 'ORDER BY c_user.username ASC, ch_user.username ASC', 
            'id': 'ORDER BY m.match_id ASC',
            'type': 'ORDER BY m.match_type ASC, m.match_date DESC'
        }
        query += ' ' + sort_options.get(sort_by, sort_options['date'])
        return query, params

class MatchEmbedFormatter:
    """Formats match data into Discord embeds"""
    
    @staticmethod
    def create_history_embed(matches, page, total_pages, sort_by='date', filter_info=None):
        title = f"📚 Match History (Page {page}/{total_pages})"
        if filter_info:
            title += f" - {filter_info}"
        
        embed = EmbedTemplates.create_base_embed(
            title=title,
            description=f"Sorted by: **{sort_by.title()}** | Total matches: **{len(matches)}**",
            color=0x4169E1
        )
        
        for match in matches:
            challenger_name = match.get('challenger_name', 'Unknown')
            challenged_name = match.get('challenged_name', 'Unknown') 
            winner_name = match.get('winner_name', 'Unknown')
            
            try:
                match_date = datetime.fromisoformat(match['match_date']).strftime("%m/%d/%Y %H:%M")
            except:
                match_date = match.get('match_date', 'Unknown')
            
            field_value = f"**{challenger_name}** vs **{challenged_name}**\n**Winner:** {winner_name}\n**Type:** {match['match_type'].title()}"
            if match.get('score'):
                field_value += f" | **Score:** {match['score']}"
            field_value += f"\n**Date:** {match_date}"
            if match.get('notes'):
                field_value += f"\n**Notes:** {match['notes'][:50]}{'...' if len(match.get('notes', '')) > 50 else ''}"
            
            embed.add_field(name=f"Match #{match['match_id']}", value=field_value, inline=True)
        
        return embed

class CommandOptionsParser:
    """Parses command options from strings"""
    
    @staticmethod
    def parse_history_options(options_str, ctx):
        options = {}
        if not options_str:
            return options
        
        for part in options_str.split():
            if ':' not in part:
                continue
            key, value = part.split(':', 1)
            
            if key == 'sort' and value in ['date', 'user', 'id', 'type']:
                options['sort'] = value
            elif key == 'type' and value in ['official', 'bm', 'friendly']:
                options['type'] = value
            elif key == 'page':
                try:
                    options['page'] = max(1, int(value))
                except ValueError:
                    pass
            elif key == 'user' and value.startswith('<@'):
                user_id = value.strip('<@!>')
                try:
                    user = ctx.guild.get_member(int(user_id))
                    if user:
                        options['user'] = user
                except ValueError:
                    pass
        return options

