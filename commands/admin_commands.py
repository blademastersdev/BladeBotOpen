"""
Administrative Commands - Refactored with Message Cleanup
Contains the new ?log command category with sub-commands for match management
"""

import discord
import asyncio
import aiosqlite
from discord.ext import commands
import logging
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime
from database.models import Database
from systems.user_system import UserSystem
from systems.ranking_system import RankingSystem
from systems.match_system import MatchSystem
from systems.elo_system import ELOSystem
from systems.ticket_system import TicketSystem
from utils.embeds import EmbedTemplates
from utils.validators import Validators
from utils.role_utils import RoleManager
from utils.interactive_utils import InteractivePrompts, MatchQueryBuilder, MatchEmbedFormatter, CommandOptionsParser, Paginator
from config import CHANNELS, EVALUATION_RANKS, CLEANUP_TIMINGS

logger = logging.getLogger('BladeBot.AdminCommands')

async def setup_admin_commands(bot):
    """Setup admin commands for the bot"""
    await bot.add_cog(AdminCommands(bot))

class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.user_system = UserSystem(self.db)
        self.ranking_system = RankingSystem(self.db)
        self.elo_system = ELOSystem()
        self.match_system = MatchSystem(
            self.db, self.elo_system, self.user_system, self.ranking_system
        )
        self.ticket_system = TicketSystem(bot)
    
    def has_moderator_permissions(self, member: discord.Member) -> bool:
        """Check if member has moderator permissions"""
        role_manager = RoleManager(member.guild)
        return role_manager.has_moderator_role(member) or role_manager.has_admin_role(member)
    
    def has_admin_permissions(self, member: discord.Member) -> bool:
        """Check if member has admin permissions"""
        role_manager = RoleManager(member.guild)
        return role_manager.has_admin_role(member)

    # ============================================================================
    # NEW REFACTORED ?LOG COMMAND CATEGORY
    # ============================================================================
    
    @commands.group(name='log', aliases=['logging'], invoke_without_subcommand=True)
    async def log_command(self, ctx):
        """
        Administrative logging commands with interactive menu
        Usage: ?log [subcommand]
        Subcommands: duel, edit, void, history
        """
        if ctx.invoked_subcommand is None:
            if not self.has_moderator_permissions(ctx.author):
                embed = EmbedTemplates.error_embed(
                    "Permission Denied",
                    "You need moderator permissions to use logging commands"
                )
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                return
            
            # Interactive menu for log commands
            embed = EmbedTemplates.create_base_embed(
                title="📝 Administrative Logging Menu",
                description="Select an action using the emoji reactions below:",
                color=0x4169E1
            )
            
            embed.add_field(
                name="📝 1️⃣ Record Duel Result",
                value="Log match results (auto-detects from ticket)",
                inline=False
            )
            
            embed.add_field(
                name="✏️ 2️⃣ Edit Match Data", 
                value="Comprehensive match editing",
                inline=False
            )
            
            embed.add_field(
                name="🗑️ 3️⃣ Void Match",
                value="Void matches (Grandmaster only)",
                inline=False
            )
            
            embed.add_field(
                name="📚 4️⃣ Browse Match History",
                value="Browse all match history",
                inline=False
            )
            
            embed.set_footer(text="React with the corresponding emoji or ❌ to cancel")
            
            message = await ctx.send(embed=embed)
            
            # Add reactions
            reactions = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '❌']
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
                    await self.log_duel(ctx)
                elif str(reaction.emoji) == '2️⃣':
                    await self.log_edit(ctx)
                elif str(reaction.emoji) == '3️⃣':
                    await self.log_void(ctx)
                elif str(reaction.emoji) == '4️⃣':
                    await self.log_history(ctx)
                elif str(reaction.emoji) == '❌':
                    embed = EmbedTemplates.create_base_embed(
                        title="❌ Cancelled",
                        description="Administrative action cancelled",
                        color=0x808080
                    )
                    await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['confirmation'])
                    
            except asyncio.TimeoutError:
                await message.delete()
                embed = EmbedTemplates.error_embed(
                    "Timeout",
                    "Menu selection timed out after 60 seconds"
                )
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])

    def _validate_score_format(self, score_input: str) -> bool:
        """
        Validate score format as #-# (e.g., 3-2, 10-7, etc.)
        Returns True if valid format, False otherwise
        """
        import re
        if not score_input:
            return False
        # Pattern: one or more digits, dash, one or more digits
        pattern = r'^\d+-\d+$'
        return bool(re.match(pattern, score_input.strip()))

    async def _get_score_with_validation(self, ctx):
        """
        Get score input with format validation and exit option
        Returns: (score, should_exit)
        """
        from config import CLEANUP_TIMINGS
        
        embed = EmbedTemplates.create_base_embed(
            title="📊 Match Score",
            description="What was the score?\n\n" +
                    "**Format:** Use format like `3-2` or `10-7`\n" +
                    "**Options:** Type `skip` for no score, or `exit` to cancel",
            color=0x4169E1
        )
        await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['confirmation'])
        
        def score_check(message):
            return (message.author == ctx.author and 
                    message.channel == ctx.channel)
        
        while True:  # Loop until valid input or exit
            try:
                score_msg = await self.bot.wait_for('message', timeout=60.0, check=score_check)
                score_input = score_msg.content.strip().lower()
                
                # Handle exit commands
                if score_input in ['exit', 'cancel', 'quit']:
                    embed = EmbedTemplates.create_base_embed(
                        title="❌ Recording Cancelled",
                        description="Match recording has been cancelled.",
                        color=0xFF0000
                    )
                    await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                    return None, True  # Signal to exit
                
                # Handle skip
                if score_input == 'skip':
                    return None, False  # No score, but continue
                
                # Validate score format
                if self._validate_score_format(score_msg.content.strip()):
                    return score_msg.content.strip(), False  # Valid score, continue
                else:
                    # Invalid format - show error and ask again
                    embed = EmbedTemplates.error_embed(
                        "Invalid Format",
                        "Score must be in format `#-#` (e.g., `3-2`, `10-7`)\n" +
                        "Type `skip` for no score, or `exit` to cancel"
                    )
                    await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                    # Loop continues for another attempt
                    
            except asyncio.TimeoutError:
                embed = EmbedTemplates.error_embed(
                    "Timeout", 
                    "Score input timed out. Recording cancelled."
                )
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                return None, True  # Signal to exit

    @log_command.command(name='duel', aliases=['record', 'rd'])
    async def log_duel(self, ctx, winner: Optional[discord.Member] = None, *, score_and_notes: str = ""):
        """
        Record a duel result with smart ticket detection
        Usage: ?log duel [@winner] [score] [notes]
        """
        try:
            # Initialize ticket system
            await self.ticket_system.initialize_ticket_table()
            
            # Check if we're in a ticket channel and get info
            ticket_info = None
            if await self.ticket_system.is_ticket_channel(ctx.channel):
                ticket_info = await self._get_ticket_info_from_channel(ctx.channel)
            
            # If we have ticket info, use it for auto-detection
            if ticket_info:
                return await self._record_from_ticket(ctx, ticket_info, winner, score_and_notes)
            else:
                return await self._record_manual(ctx, winner, score_and_notes)
                
        except Exception as e:
            logger.error(f'Error in log duel command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred while recording the duel: {str(e)}"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])

    async def _get_ticket_info_from_channel(self, channel):
        """Get ticket information from channel with database fallback"""
        try:
            # Try memory first
            if hasattr(self.ticket_system, 'active_tickets'):
                memory_info = self.ticket_system.active_tickets.get(channel.id)
                if memory_info:
                    return memory_info
            
            # Fallback to database
            async with aiosqlite.connect(self.db.db_path) as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute(
                    "SELECT * FROM active_tickets WHERE channel_id = ?",
                    (channel.id,)
                )
                return await cursor.fetchone()
                
        except Exception as e:
            logger.error(f'Error getting ticket info: {e}')
            return None

    async def _record_from_ticket(self, ctx, ticket_info, winner, score_and_notes):
        """Record duel from ticket with auto-detection and interactive prompts"""
        try:
            challenger_id = ticket_info.get('challenger_id')
            challenged_id = ticket_info.get('challenged_id')
            duel_type = ticket_info.get('duel_type', 'official')
            
            # Get participant members
            challenger = ctx.guild.get_member(challenger_id) if challenger_id else None
            challenged = ctx.guild.get_member(challenged_id) if challenged_id else None
            
            if not challenger or not challenged:
                return await self._record_manual(ctx, winner, score_and_notes)
            
            participants = [challenger, challenged]
            
            # If winner not specified, prompt for selection
            if not winner:
                embed = EmbedTemplates.create_base_embed(
                    title="⚔️ Select Winner",
                    description=f"Who won this {duel_type} duel?\n\n" +
                            f"1️⃣ {challenger.display_name}\n" +
                            f"2️⃣ {challenged.display_name}\n\n" +
                            "Or type `exit` to cancel recording",
                    color=0x4169E1
                )
                
                message = await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['confirmation'])
                await message.add_reaction("1️⃣")
                await message.add_reaction("2️⃣")
                
                def check(reaction, user):
                    return (user == ctx.author and 
                        str(reaction.emoji) in ["1️⃣", "2️⃣"] and 
                        reaction.message.id == message.id)
                
                # Also check for exit message
                def exit_check(message):
                    return (message.author == ctx.author and 
                            message.channel == ctx.channel and
                            message.content.strip().lower() in ['exit', 'cancel', 'quit'])
                
                try:
                    # Wait for either reaction or exit message
                    done, pending = await asyncio.wait([
                        asyncio.create_task(self.bot.wait_for('reaction_add', timeout=60.0, check=check)),
                        asyncio.create_task(self.bot.wait_for('message', timeout=60.0, check=exit_check))
                    ], return_when=asyncio.FIRST_COMPLETED)
                    
                    # Cancel remaining tasks
                    for task in pending:
                        task.cancel()
                    
                    result = done.pop().result()
                    
                    # Check if it was an exit message
                    if isinstance(result, discord.Message):
                        embed = EmbedTemplates.create_base_embed(
                            title="❌ Recording Cancelled",
                            description="Match recording has been cancelled.",
                            color=0xFF0000
                        )
                        await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                        return
                    
                    # It was a reaction
                    reaction, user = result
                    if str(reaction.emoji) == "1️⃣":
                        winner = challenger
                    else:
                        winner = challenged
                        
                except asyncio.TimeoutError:
                    embed = EmbedTemplates.error_embed("Timeout", "Winner selection timed out")
                    await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                    return
            
            # Parse score from score_and_notes parameter first
            score = None
            notes = ""
            
            if score_and_notes:
                parts = score_and_notes.split()
                if parts:
                    # Look for note indicators
                    note_indicators = ['note:', 'notes:', 'note', 'notes']
                    score_parts = []
                    notes_parts = []
                    found_note_indicator = False
                    
                    for part in parts:
                        if not found_note_indicator and part.lower() in note_indicators:
                            found_note_indicator = True
                            continue
                        
                        if found_note_indicator:
                            notes_parts.append(part)
                        else:
                            score_parts.append(part)
                    
                    if score_parts:
                        potential_score = ' '.join(score_parts)
                        # Validate format if provided via parameter
                        if self._validate_score_format(potential_score):
                            score = potential_score
                    if notes_parts:
                        notes = ' '.join(notes_parts)
            
            # If no valid score from parameters, prompt for it
            if not score:
                score, should_exit = await self._get_score_with_validation(ctx)
                if should_exit:
                    return
            
            # Get notes if not provided
            if not notes:
                embed = EmbedTemplates.create_base_embed(
                    title="📝 Additional Notes",
                    description="Any additional notes for this match?\n\nType `none` for no notes, or `exit` to cancel",
                    color=0x4169E1
                )
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['confirmation'])
                
                def notes_check(message):
                    return (message.author == ctx.author and 
                        message.channel == ctx.channel)
                
                try:
                    notes_msg = await self.bot.wait_for('message', timeout=60.0, check=notes_check)
                    notes_input = notes_msg.content.strip()
                    
                    # Check for exit
                    if notes_input.lower() in ['exit', 'cancel', 'quit']:
                        embed = EmbedTemplates.create_base_embed(
                            title="❌ Recording Cancelled",
                            description="Match recording has been cancelled.",
                            color=0xFF0000
                        )
                        await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                        return
                    
                    if notes_input.lower() != 'none':
                        notes = notes_input
                        
                except asyncio.TimeoutError:
                    notes = ""  # Continue with no notes
            
            # Ensure both users are registered
            await self.user_system.ensure_user_registered(challenger)
            await self.user_system.ensure_user_registered(challenged)
            
            # Import and create DuelWorkflows instance
            from workflows.duel_workflows import DuelWorkflows
            duel_workflows = DuelWorkflows(self.bot)
            
            # Use duel_workflows for proper recording
            recording_result = await duel_workflows.process_match_recording_workflow(
                match_type=duel_type,
                challenger=challenger,
                challenged=challenged,
                winner=winner,
                score=score,
                notes=notes,
                recorded_by=ctx.author,
                guild=ctx.guild
            )
            
            if recording_result and recording_result.get('success'):
                # Send success confirmation
                embed = EmbedTemplates.create_base_embed(
                    title="✅ Match Recorded Successfully",
                    description=f"**{duel_type.title()} Duel** recorded between {challenger.mention} and {challenged.mention}",
                    color=0x00FF00
                )
                
                embed.add_field(
                    name="🏆 Winner",
                    value=winner.mention,
                    inline=True
                )
                
                if score:
                    embed.add_field(
                        name="📊 Score",
                        value=score,
                        inline=True
                    )
                
                if 'match_id' in recording_result:
                    embed.add_field(
                        name="🔍 Match ID",
                        value=f"`{recording_result['match_id']}`",
                        inline=True
                    )
                
                if notes:
                    embed.add_field(
                        name="📝 Notes",
                        value=notes,
                        inline=False
                    )
                
                embed.set_footer(text=f"Recorded by {ctx.author.display_name}")
                
                await ctx.send(embed=embed)
            else:
                # Handle recording failure
                error_msg = recording_result.get('error', 'Unknown error occurred') if recording_result else 'Recording failed'
                embed = EmbedTemplates.error_embed(
                    "Recording Failed",
                    f"Failed to record match: {error_msg}"
                )
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
            
        except Exception as e:
            logger.error(f'Error in _record_from_ticket: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred while recording the duel: {str(e)}"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])

    async def _record_manual(self, ctx, winner, score_and_notes):
        """Manual duel recording with full interactive workflow"""
        from config import CLEANUP_TIMINGS
        
        try:
            # Step 1: Get challenger
            embed = EmbedTemplates.create_base_embed(
                title="👤 Select Challenger",
                description="**Step 1:** Who was the challenger? (mention user or type name)\nType `exit` to cancel",
                color=0x4169E1
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['confirmation'])
            
            def user_check(message):
                return (message.author == ctx.author and 
                    message.channel == ctx.channel)
            
            try:
                challenger_msg = await self.bot.wait_for('message', timeout=60.0, check=user_check)
                challenger_input = challenger_msg.content.strip()
                
                # Check for exit
                if challenger_input.lower() in ['exit', 'cancel', 'quit']:
                    embed = EmbedTemplates.create_base_embed(
                        title="❌ Recording Cancelled",
                        description="Match recording has been cancelled.",
                        color=0xFF0000
                    )
                    await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                    return
                
                # Parse challenger
                challenger = None

                # Try Discord ID first if input is all digits
                if challenger_input.isdigit():
                    try:
                        user_id = int(challenger_input)
                        challenger = ctx.guild.get_member(user_id)
                        
                        # If not in guild, check database for reserve users
                        if not challenger:
                            user_data = await self.db.get_user(user_id)
                            if user_data:
                                # Create a mock member object for database users
                                challenger = type('MockMember', (), {
                                    'id': user_id,
                                    'display_name': user_data['username'],
                                    'mention': f"<@{user_id}>",
                                    'name': user_data['username']
                                })()
                    except ValueError:
                        pass

                # If not found, try existing methods
                if not challenger:
                    result = Validators.validate_mention(challenger_input, ctx.guild)
                    # Handle tuple return from validator
                    if isinstance(result, tuple):
                        challenger = None  # Validation failed
                    else:
                        challenger = result
                        
                    if not challenger:
                        # Try username search as fallback
                        challenger = discord.utils.find(
                            lambda m: challenger_input.lower() in m.display_name.lower(),
                            ctx.guild.members
                        )
                
                if not challenger:
                    embed = EmbedTemplates.error_embed(
                        "User Not Found",
                        f"Could not find user: {challenger_input}"
                    )
                    await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                    return
                    
            except asyncio.TimeoutError:
                embed = EmbedTemplates.error_embed("Timeout", "Challenger selection timed out")
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                return
            
            # Step 2: Get challenged
            embed = EmbedTemplates.create_base_embed(
                title="🎯 Select Challenged",
                description="**Step 2:** Who was challenged? (mention user or type name)\nType `exit` to cancel",
                color=0x4169E1
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['confirmation'])
            
            try:
                challenged_msg = await self.bot.wait_for('message', timeout=60.0, check=user_check)
                challenged_input = challenged_msg.content.strip()
                
                # Check for exit
                if challenged_input.lower() in ['exit', 'cancel', 'quit']:
                    embed = EmbedTemplates.create_base_embed(
                        title="❌ Recording Cancelled",
                        description="Match recording has been cancelled.",
                        color=0xFF0000
                    )
                    await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                    return
                
                # Parse challenged
                challenged = None

                # Try Discord ID first if input is all digits
                if challenged_input.isdigit():
                    try:
                        user_id = int(challenged_input)
                        challenged = ctx.guild.get_member(user_id)
                        
                        # If not in guild, check database for reserve users
                        if not challenged:
                            user_data = await self.db.get_user(user_id)
                            if user_data:
                                # Create a mock member object for database users
                                challenged = type('MockMember', (), {
                                    'id': user_id,
                                    'display_name': user_data['username'],
                                    'mention': f"<@{user_id}>",
                                    'name': user_data['username']
                                })()
                    except ValueError:
                        pass

                # If not found, try existing methods
                if not challenged:
                    result = Validators.validate_mention(challenged_input, ctx.guild)
                    # Handle tuple return from validator
                    if isinstance(result, tuple):
                        challenged = None  # Validation failed
                    else:
                        challenged = result
                        
                    if not challenged:
                        # Try username search as fallback
                        challenged = discord.utils.find(
                            lambda m: challenged_input.lower() in m.display_name.lower(),
                            ctx.guild.members
                        )
                
                if not challenged:
                    embed = EmbedTemplates.error_embed(
                        "User Not Found",
                        f"Could not find user: {challenged_input}"
                    )
                    await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                    return
                    
            except asyncio.TimeoutError:
                embed = EmbedTemplates.error_embed("Timeout", "Challenged selection timed out")
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                return
            
            # Step 3: Get duel type
            embed = EmbedTemplates.create_base_embed(
                title="⚔️ Duel Type",
                description="**Step 3:** What type of duel was this?\n\n1️⃣ Official Duel\n2️⃣ Blademaster Duel",
                color=0x4169E1
            )
            
            type_msg = await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['confirmation'])
            await type_msg.add_reaction("1️⃣")
            await type_msg.add_reaction("2️⃣")
            
            def type_reaction_check(reaction, user):
                return (user == ctx.author and 
                    str(reaction.emoji) in ["1️⃣", "2️⃣"] and 
                    reaction.message.id == type_msg.id)
            
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=type_reaction_check)
                if str(reaction.emoji) == "1️⃣":
                    duel_type = "official"
                else:
                    duel_type = "bm"
                    
            except asyncio.TimeoutError:
                embed = EmbedTemplates.error_embed("Timeout", "Duel type selection timed out")
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                return

            # Right after the duel type selection, add:
            logger.error(f"DEBUG EARLY: challenger={type(challenger)}, challenged={type(challenged)}")
            logger.error(f"DEBUG VALUES: challenger={challenger}, challenged={challenged}")

            # Step 4: Get winner (if not provided)
            if not winner:
                embed = EmbedTemplates.create_base_embed(
                    title="🏆 Select Winner",
                    description=f"**Step 4:** Who won the duel?\n\n1️⃣ {challenger.display_name}\n2️⃣ {challenged.display_name}",
                    color=0x4169E1
                )
                
                winner_msg = await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['confirmation'])
                await winner_msg.add_reaction("1️⃣")
                await winner_msg.add_reaction("2️⃣")
                
                def winner_reaction_check(reaction, user):
                    return (user == ctx.author and 
                        str(reaction.emoji) in ["1️⃣", "2️⃣"] and 
                        reaction.message.id == winner_msg.id)
                
                try:
                    reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=winner_reaction_check)
                    if str(reaction.emoji) == "1️⃣":
                        winner = challenger
                    else:
                        winner = challenged
                        
                except asyncio.TimeoutError:
                    embed = EmbedTemplates.error_embed("Timeout", "Winner selection timed out")
                    await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                    return
            
            # Parse score from score_and_notes parameter first
            score = None
            notes = ""
            
            if score_and_notes:
                parts = score_and_notes.split()
                if parts:
                    # Look for note indicators
                    note_indicators = ['note:', 'notes:', 'note', 'notes']
                    score_parts = []
                    notes_parts = []
                    found_note_indicator = False
                    
                    for part in parts:
                        if not found_note_indicator and part.lower() in note_indicators:
                            found_note_indicator = True
                            continue
                        
                        if found_note_indicator:
                            notes_parts.append(part)
                        else:
                            score_parts.append(part)
                    
                    if score_parts:
                        potential_score = ' '.join(score_parts)
                        # Validate format if provided via parameter
                        if self._validate_score_format(potential_score):
                            score = potential_score
                    if notes_parts:
                        notes = ' '.join(notes_parts)
            
            # Step 5: Get score if not provided
            if not score:
                score, should_exit = await self._get_score_with_validation(ctx)
                if should_exit:
                    return
            
            # Step 6: Get notes if not provided
            if not notes:
                embed = EmbedTemplates.create_base_embed(
                    title="📝 Additional Notes",
                    description="**Step 5:** Any additional notes? (type 'none' for no notes or 'exit' to cancel)",
                    color=0x4169E1
                )
                
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['confirmation'])
                
                def notes_check(message):
                    return (message.author == ctx.author and 
                        message.channel == ctx.channel)
                
                try:
                    notes_msg = await self.bot.wait_for('message', timeout=60.0, check=notes_check)
                    notes_input = notes_msg.content.strip()
                    
                    # Check for exit
                    if notes_input.lower() in ['exit', 'cancel', 'quit']:
                        embed = EmbedTemplates.create_base_embed(
                            title="❌ Recording Cancelled",
                            description="Match recording has been cancelled.",
                            color=0xFF0000
                        )
                        await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                        return
                    
                    if notes_input.lower() != 'none':
                        notes = notes_input
                    else:
                        notes = ""
                        
                except asyncio.TimeoutError:
                    notes = ""
            
            # Ensure both users are registered before recording
            await self.user_system.ensure_user_registered(challenger)
            await self.user_system.ensure_user_registered(challenged)

            # Right before the DuelWorkflows call, add:
            logger.error(f"DEBUG: challenger={type(challenger)}, challenged={type(challenged)}, winner={type(winner)}")
            
            # Now record the match using the proper workflow system
            from workflows.duel_workflows import DuelWorkflows
            duel_workflows = DuelWorkflows(self.bot)
            
            recording_result = await duel_workflows.process_match_recording_workflow(
                match_type=duel_type,
                challenger=challenger,
                challenged=challenged,
                winner=winner,
                score=score,
                notes=notes,
                recorded_by=ctx.author,
                guild=ctx.guild
            )
            
            if recording_result and recording_result.get('success'):
                # Send success confirmation
                embed = EmbedTemplates.create_base_embed(
                    title="✅ Match Recorded Successfully",
                    description=f"**{duel_type.title()} Duel** recorded between {challenger.mention} and {challenged.mention}",
                    color=0x00FF00
                )
                
                embed.add_field(
                    name="🏆 Winner",
                    value=winner.mention,
                    inline=True
                )
                
                if score:
                    embed.add_field(
                        name="📊 Score",
                        value=score,
                        inline=True
                    )
                
                if 'match_id' in recording_result:
                    embed.add_field(
                        name="🔍 Match ID",
                        value=f"`{recording_result['match_id']}`",
                        inline=True
                    )
                
                if notes:
                    embed.add_field(
                        name="📝 Notes",
                        value=notes,
                        inline=False
                    )
                
                embed.set_footer(text=f"Recorded by {ctx.author.display_name}")
                
                await ctx.send(embed=embed)
                
            else:
                # Handle recording failure
                error_msg = recording_result.get('error', 'Unknown error occurred') if recording_result else 'Recording failed'
                embed = EmbedTemplates.error_embed(
                    "Recording Failed",
                    f"Failed to record match: {error_msg}"
                )
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
            
        except Exception as e:
            logger.error(f'Error in _record_manual: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred while recording the duel: {str(e)}"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])

    @commands.command(name='close')
    async def close_ticket(self, ctx, *, reason: str = "Ticket closed"):
        """
        Close a ticket channel (Moderator only)
        Usage: ?close [reason]
        """
        # Check moderator permissions
        role_manager = RoleManager(ctx.guild)
        if not (role_manager.has_moderator_role(ctx.author) or role_manager.has_admin_role(ctx.author)):
            embed = EmbedTemplates.error_embed(
                "Permission Denied",
                "You need moderator permissions to close tickets"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
            return
        
        # Check if we're in a ticket channel
        if not await self.ticket_system.is_ticket_channel(ctx.channel):
            embed = EmbedTemplates.error_embed(
                "Not a Ticket",
                "This command can only be used in ticket channels"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
            return
        
        try:
            # Close the ticket
            success = await self.ticket_system.close_ticket(ctx.channel, ctx.author, reason)
            
            if success:
                logger.info(f'Ticket {ctx.channel.name} closed by {ctx.author.display_name}')
            else:
                embed = EmbedTemplates.error_embed(
                    "Close Failed",
                    "Failed to close ticket - please try again or contact an admin"
                )
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                
        except Exception as e:
            logger.error(f'Error in close command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred while closing the ticket: {str(e)}"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])

    @log_command.command(name='edit', aliases=['modify'])
    async def log_edit(self, ctx, match_id: Optional[int] = None):
        """
        Edit match data comprehensively with enhanced interface
        Usage: ?log edit [match_id]
        """
        if not self.has_admin_permissions(ctx.author):
            embed = EmbedTemplates.error_embed("Permission Denied", "You need admin permissions to edit matches")
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
            return
        
        # Enhanced match selection if no ID provided
        if match_id is None:
            match_id = await self._select_match_interactively(ctx)
            if match_id is None:
                return
        
        try:
            async with aiosqlite.connect(self.db.db_path) as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute("""
                    SELECT m.*, 
                           c_user.username as challenger_name,
                           ch_user.username as challenged_name,
                           w_user.username as winner_name
                    FROM matches m
                    LEFT JOIN users c_user ON m.challenger_id = c_user.discord_id
                    LEFT JOIN users ch_user ON m.challenged_id = ch_user.discord_id
                    LEFT JOIN users w_user ON m.winner_id = w_user.discord_id
                    WHERE m.match_id = ?
                """, (match_id,))
                match_data = await cursor.fetchone()
            
            if not match_data:
                embed = EmbedTemplates.error_embed("Match Not Found", f"No match found with ID #{match_id}")
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                return
            
            # Interactive editing interface
            await self._interactive_match_editing(ctx, match_data)
            
        except Exception as e:
            logger.error(f'Error in log edit command: {e}')
            embed = EmbedTemplates.error_embed("Error", f"An error occurred: {str(e)}")
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])

    @log_command.command(name='void', aliases=['delete'])
    async def log_void(self, ctx, match_id: Optional[int] = None, *, reason: str = ""):
        """
        Void a match (Grandmaster only)
        Usage: ?log void [match_id] [reason]
        """
        # Check Grandmaster permissions
        grandmaster_role_id = 1386495816952446977
        grandmaster_role = ctx.guild.get_role(grandmaster_role_id)
        
        if not grandmaster_role or grandmaster_role not in ctx.author.roles:
            embed = EmbedTemplates.error_embed(
                "Permission Denied",
                "Only the Grandmaster can void matches"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
            return
        
        # Interactive match selection if no ID provided
        if match_id is None:
            match_id = await self._interactive_match_selection(ctx)
            if match_id is None:
                return
        
        # Void the match
        try:
            success = await self._void_match_operation(match_id, reason, ctx.author)
            
            if success:
                embed = EmbedTemplates.create_base_embed(
                    title="✅ Match Voided",
                    description=f"Match #{match_id} has been voided successfully",
                    color=0x00FF00
                )
                
                if reason:
                    embed.add_field(
                        name="📝 Reason",
                        value=reason,
                        inline=False
                    )
                
                embed.set_footer(text=f"Voided by {ctx.author.display_name}")
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['admin'])
            else:
                embed = EmbedTemplates.error_embed(
                    "Void Failed",
                    f"Failed to void match #{match_id}"
                )
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                
        except Exception as e:
            logger.error(f'Error voiding match: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred while voiding the match: {str(e)}"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])

    async def _interactive_match_selection(self, ctx):
        """Interactive match selection with fixed database access"""
        try:
            # Get recent matches using proper database connection
            async with aiosqlite.connect(self.db.db_path) as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute("""
                    SELECT m.match_id, m.challenger_id, m.challenged_id, m.winner_id, 
                           m.match_type, m.score, m.match_date
                    FROM matches m 
                    ORDER BY m.match_date DESC 
                    LIMIT 10
                """)
                matches = await cursor.fetchall()
            
            if not matches:
                embed = EmbedTemplates.error_embed(
                    "No Matches Found",
                    "No matches found in the database"
                )
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                return None
            
            # Create selection embed
            embed = EmbedTemplates.create_base_embed(
                title="🔍 Select Match to Process",
                description="Choose a match by reacting with the corresponding number:",
                color=0x4169E1
            )
            
            reactions = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
            
            for i, match in enumerate(matches[:10]):
                if i >= len(reactions):
                    break
                    
                challenger = ctx.guild.get_member(match['challenger_id'])
                challenged = ctx.guild.get_member(match['challenged_id'])
                winner = ctx.guild.get_member(match['winner_id'])
                
                challenger_name = challenger.display_name if challenger else "Unknown"
                challenged_name = challenged.display_name if challenged else "Unknown"
                winner_name = winner.display_name if winner else "Unknown"
                
                match_date = datetime.fromisoformat(match['match_date']).strftime("%m/%d/%Y")
                
                embed.add_field(
                    name=f"{reactions[i]} Match #{match['match_id']}",
                    value=f"**{challenger_name}** vs **{challenged_name}**\nWinner: {winner_name}\nType: {match['match_type'].title()}\nDate: {match_date}",
                    inline=False
                )
            
            embed.add_field(
                name="❌ Cancel",
                value="Cancel selection",
                inline=False
            )
            
            message = await ctx.send(embed=embed)
            
            # Add reactions
            valid_reactions = reactions[:len(matches)] + ['❌']
            for reaction in valid_reactions:
                await message.add_reaction(reaction)
            
            def check(reaction, user):
                return (user == ctx.author and 
                       str(reaction.emoji) in valid_reactions and
                       reaction.message.id == message.id)
            
            try:
                reaction, _ = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                await message.delete()
                
                if str(reaction.emoji) == '❌':
                    embed = EmbedTemplates.create_base_embed(
                        title="❌ Cancelled",
                        description="Match selection cancelled",
                        color=0x808080
                    )
                    await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['confirmation'])
                    return None
                
                # Find selected match
                reaction_index = reactions.index(str(reaction.emoji))
                if reaction_index < len(matches):
                    return matches[reaction_index]['match_id']
                
                return None
                
            except asyncio.TimeoutError:
                await message.delete()
                embed = EmbedTemplates.error_embed(
                    "Timeout",
                    "Match selection timed out"
                )
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                return None
                
        except Exception as e:
            logger.error(f'Error in interactive match selection: {e}')
            embed = EmbedTemplates.error_embed(
                "Selection Error",
                f"An error occurred during match selection: {str(e)}"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
            return None

    async def _void_match_operation(self, match_id, reason, voided_by):
        """Void match operation with ELO/stats reversal"""
        try:
            async with aiosqlite.connect(self.db.db_path) as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                
                # Get match data first
                cursor = await db.execute(
                    "SELECT * FROM matches WHERE match_id = ?",
                    (match_id,)
                )
                match_data = await cursor.fetchone()
                
                if not match_data:
                    return False
                
                # Reverse ELO changes
                winner_id = match_data['winner_id']
                loser_id = match_data['loser_id']
                winner_elo_change = match_data.get('elo_change_winner', 0)
                loser_elo_change = match_data.get('elo_change_loser', 0)
                
                # Reverse ELO for winner (subtract the gain)
                await db.execute("""
                    UPDATE users 
                    SET elo_rating = elo_rating - ?,
                        wins = wins - 1,
                        games_played = games_played - 1
                    WHERE discord_id = ?
                """, (winner_elo_change, winner_id))
                
                # Reverse ELO for loser (subtract the loss, which is negative, so it adds back)
                await db.execute("""
                    UPDATE users 
                    SET elo_rating = elo_rating - ?,
                        losses = losses - 1,
                        games_played = games_played - 1
                    WHERE discord_id = ?
                """, (loser_elo_change, loser_id))
                
                # Delete the match record
                await db.execute(
                    "DELETE FROM matches WHERE match_id = ?",
                    (match_id,)
                )
                
                # Log the void operation with correct column name
                await db.execute("""
                    INSERT INTO bot_logs (action_type, user_id, details, timestamp)
                    VALUES (?, ?, ?, ?)
                """, (
                    'match_voided',
                    voided_by.id,
                    f"Voided match #{match_id}. Reason: {reason}. ELO and stats reversed.",
                    datetime.now().isoformat()
                ))
                
                await db.commit()
                return True
                
        except Exception as e:
            logger.error(f'Error in void operation: {e}')
            return False

    @log_command.command(name='history', aliases=['browse'])
    async def log_history(self, ctx, *, options: str = ""):
        """
        Browse all match history with advanced sorting and pagination
        Usage: ?log history [sort:date|user|id|type] [user:@mention] [type:official|bm|friendly]
        """
        if not self.has_admin_permissions(ctx.author):
            embed = EmbedTemplates.error_embed("Permission Denied", "You need admin permissions to browse full match history")
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
            return
        
        try:
            parsed_options = CommandOptionsParser.parse_history_options(options, ctx)
            sort_by = parsed_options.get('sort', 'date')
            filter_user = parsed_options.get('user')
            filter_type = parsed_options.get('type')
            
            query, params = MatchQueryBuilder.build_match_query(filter_user, filter_type, sort_by)
            
            async with aiosqlite.connect(self.db.db_path) as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute(query, params)
                matches = await cursor.fetchall()
            
            if not matches:
                embed = EmbedTemplates.error_embed("No Matches Found", "No matches found matching your criteria")
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                return
            
            filter_info = None
            if filter_user or filter_type:
                filters = []
                if filter_user:
                    filters.append(f"User: {filter_user.display_name}")
                if filter_type:
                    filters.append(f"Type: {filter_type.title()}")
                filter_info = ', '.join(filters)
            
            def embed_creator(page_matches, page, total_pages):
                return MatchEmbedFormatter.create_history_embed(page_matches, page, total_pages, sort_by, filter_info)
            
            embeds = Paginator.paginate_embeds(matches, items_per_page=6, embed_creator=embed_creator)
            
            # Add sorting help to first embed
            embeds[0].set_footer(text="💡 Try: ?log history sort:user, ?log history type:bm, ?log history user:@mention")
            
            await Paginator.send_paginated(ctx, embeds, timeout=300)
            
        except Exception as e:
            logger.error(f'Error in log history command: {e}')
            embed = EmbedTemplates.error_embed("Error", f"An error occurred: {str(e)}")
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])

    # ============================================================================
    # EXISTING ADMIN COMMANDS (With Cleanup)
    # ============================================================================
    
    @commands.command(name='evaluate')
    async def evaluate_user(self, ctx, target: discord.Member, tier: str, rank_numeral: str):
        """
        Place user from evaluation into Blademasters
        Usage: ?evaluate @user <tier> <rank>
        Valid placements: Bronze IV, Silver IV, Gold III
        """
        if not self.has_admin_permissions(ctx.author):
            embed = EmbedTemplates.error_embed(
                "Permission Denied",
                "You need admin permissions to evaluate users"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
            return
        
        # Validate rank
        rank_key = (tier.title(), rank_numeral.upper())
        if rank_key not in EVALUATION_RANKS:
            valid_ranks = ', '.join([f"{t} {r}" for t, r in EVALUATION_RANKS])
            embed = EmbedTemplates.error_embed(
                "Invalid Rank",
                f"Valid evaluation ranks are: {valid_ranks}"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
            return
        
        try:
            # Process evaluation
            result = await self.user_system.evaluate_user(target, tier.title(), rank_numeral.upper())
            
            if result['success']:
                embed = EmbedTemplates.create_base_embed(
                    title="✅ User Evaluated Successfully",
                    description=f"{target.display_name} has been placed in **{tier.title()} {rank_numeral.upper()}**",
                    color=0x00FF00
                )
                
                embed.set_footer(text=f"Evaluated by {ctx.author.display_name}")
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['admin'])
                
                # Log to bmbot-logs if configured (persistent)
                logs_channel = self.bot.get_channel(CHANNELS.get('bmbot_logs'))
                if logs_channel:
                    await logs_channel.send(embed=embed)
            else:
                embed = EmbedTemplates.error_embed(
                    "Evaluation Failed",
                    result.get('error', 'Unknown error occurred')
                )
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                
        except Exception as e:
            logger.error(f'Error in evaluate command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred during evaluation: {str(e)}"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])

    @commands.command(name='confirm')
    async def confirm_rank_change(self, ctx, change_id: int):
        """
        Confirm a pending rank change
        Usage: ?confirm <change_id>
        """
        if not self.has_admin_permissions(ctx.author):
            embed = EmbedTemplates.error_embed(
                "Permission Denied",
                "You need admin permissions to confirm rank changes"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
            return
        
        try:
            result = await self.ranking_system.confirm_rank_change(change_id, ctx.author)
            
            if result['success']:
                embed = EmbedTemplates.create_base_embed(
                    title="✅ Rank Change Confirmed",
                    description=f"Rank change #{change_id} has been confirmed and applied",
                    color=0x00FF00
                )
                
                embed.set_footer(text=f"Confirmed by {ctx.author.display_name}")
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['admin'])
                
                # Post to rank tracker if configured (persistent)
                tracker_channel = self.bot.get_channel(CHANNELS.get('rank_tracker'))
                if tracker_channel:
                    await tracker_channel.send(embed=embed)
            else:
                embed = EmbedTemplates.error_embed(
                    "Confirmation Failed",
                    result.get('error', 'Unknown error occurred')
                )
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                
        except Exception as e:
            logger.error(f'Error in confirm command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred during confirmation: {str(e)}"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])

    @commands.command(name='pending')
    async def view_pending_changes(self, ctx):
        """
        View all pending rank changes
        Usage: ?pending
        """
        if not self.has_admin_permissions(ctx.author):
            embed = EmbedTemplates.error_embed(
                "Permission Denied",
                "You need admin permissions to view pending changes"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
            return
        
        try:
            pending_changes = await self.ranking_system.get_pending_rank_changes()
            
            if not pending_changes:
                embed = EmbedTemplates.create_base_embed(
                    title="📋 Pending Rank Changes",
                    description="No pending rank changes found",
                    color=0x4169E1
                )
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['admin'])
                return
            
            embed = EmbedTemplates.create_base_embed(
                title="📋 Pending Rank Changes",
                description=f"Found {len(pending_changes)} pending change(s)",
                color=0x4169E1
            )
            
            for change in pending_changes[:5]:  # Limit to 5 for embed size
                winner = ctx.guild.get_member(change['winner_id'])
                loser = ctx.guild.get_member(change['loser_id'])
                
                winner_name = winner.display_name if winner else f"Unknown ({change['winner_id']})"
                loser_name = loser.display_name if loser else f"Unknown ({change['loser_id']})"
                
                change_desc = f"**Winner:** {winner_name}\n"
                change_desc += f"**Loser:** {loser_name}\n"
                change_desc += f"**Match:** #{change['match_id']}\n"
                change_desc += f"**Date:** {change['created_date'][:10]}"
                
                embed.add_field(
                    name=f"Change #{change['change_id']}",
                    value=change_desc,
                    inline=True
                )
            
            if len(pending_changes) > 5:
                embed.set_footer(text=f"Showing 5 of {len(pending_changes)} pending changes")
            
            # Pending changes is administrative data - keep persistent for reference
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f'Error in pending command: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred while retrieving pending changes: {str(e)}"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])

    async def _select_match_interactively(self, ctx) -> Optional[int]:
        """Select match using comprehensive interface"""
        selection_options = [
            {"name": "🆔 Enter Match ID", "value": "id"},
            {"name": "📅 Browse Recent Matches", "value": "recent"},
            {"name": "👤 Search by User", "value": "user"}
        ]
        
        selection = await InteractivePrompts.numbered_selection(
            ctx, selection_options, title="🔍 Match Selection", 
            description="How would you like to select a match to edit?", timeout=60
        )
        
        if selection is None:
            return None
        
        method = selection_options[selection]["value"]
        
        if method == "id":
            return await self._get_match_id_input(ctx)
        elif method == "recent":
            return await self._select_from_recent_matches(ctx)
        elif method == "user":
            return await self._search_matches_by_user(ctx)
        
        return None

    async def _get_match_id_input(self, ctx) -> Optional[int]:
        """Get match ID from user input"""
        embed = EmbedTemplates.create_base_embed(
            title="🆔 Enter Match ID", description="Please enter the match ID number:", color=0x9966cc
        )
        await ctx.send(embed=embed, delete_after=30)
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        
        try:
            message = await self.bot.wait_for('message', timeout=30.0, check=check)
            return int(message.content)
        except ValueError:
            embed = EmbedTemplates.error_embed("Invalid Input", "Please enter a valid match ID number")
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
            return None
        except asyncio.TimeoutError:
            embed = EmbedTemplates.error_embed("Timeout", "Input timed out")
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
            return None

    async def _select_from_recent_matches(self, ctx) -> Optional[int]:
        """Select from recent matches"""
        try:
            async with aiosqlite.connect(self.db.db_path) as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute("""
                    SELECT m.match_id, m.challenger_id, m.challenged_id, m.winner_id,
                           m.match_type, m.score, m.match_date,
                           c_user.username as challenger_name,
                           ch_user.username as challenged_name,
                           w_user.username as winner_name
                    FROM matches m
                    LEFT JOIN users c_user ON m.challenger_id = c_user.discord_id
                    LEFT JOIN users ch_user ON m.challenged_id = ch_user.discord_id
                    LEFT JOIN users w_user ON m.winner_id = w_user.discord_id
                    ORDER BY m.match_date DESC LIMIT 10
                """)
                matches = await cursor.fetchall()
            
            if not matches:
                embed = EmbedTemplates.error_embed("No Matches", "No recent matches found")
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                return None
            
            match_options = []
            for match in matches:
                try:
                    match_date = datetime.fromisoformat(match['match_date']).strftime("%m/%d %H:%M")
                except:
                    match_date = "Unknown"
                
                name = f"Match #{match['match_id']} - {match.get('challenger_name', 'Unknown')} vs {match.get('challenged_name', 'Unknown')}"
                value = f"Winner: {match.get('winner_name', 'Unknown')} | {match['match_type'].title()} | {match_date}"
                match_options.append({"name": name, "value": value, "match_id": match['match_id']})
            
            selection = await InteractivePrompts.numbered_selection(
                ctx, match_options, title="📅 Select Recent Match", 
                description="Choose a match to edit:", timeout=60
            )
            
            return match_options[selection]["match_id"] if selection is not None else None
            
        except Exception as e:
            logger.error(f'Error in recent match selection: {e}')
            return None

    async def _search_matches_by_user(self, ctx) -> Optional[int]:
        """Search matches by user"""
        embed = EmbedTemplates.create_base_embed(
            title="👤 Search by User", description="Please mention the user to search matches for:", color=0x9966cc
        )
        await ctx.send(embed=embed, delete_after=30)
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        
        try:
            message = await self.bot.wait_for('message', timeout=30.0, check=check)
            
            if not message.mentions:
                embed = EmbedTemplates.error_embed("No User", "Please mention a user to search for")
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                return None
            
            target_user = message.mentions[0]
            query, params = MatchQueryBuilder.build_match_query(filter_user=target_user, sort_by='date')
            
            async with aiosqlite.connect(self.db.db_path) as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute(query + " LIMIT 10", params)
                matches = await cursor.fetchall()
            
            if not matches:
                embed = EmbedTemplates.error_embed("No Matches", f"No matches found for {target_user.display_name}")
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                return None
            
            match_options = []
            for match in matches:
                try:
                    match_date = datetime.fromisoformat(match['match_date']).strftime("%m/%d %H:%M")
                except:
                    match_date = "Unknown"
                
                name = f"Match #{match['match_id']} - {match.get('challenger_name', 'Unknown')} vs {match.get('challenged_name', 'Unknown')}"
                value = f"Winner: {match.get('winner_name', 'Unknown')} | {match['match_type'].title()} | {match_date}"
                match_options.append({"name": name, "value": value, "match_id": match['match_id']})
            
            selection = await InteractivePrompts.numbered_selection(
                ctx, match_options, title=f"🔍 Matches for {target_user.display_name}",
                description="Choose a match to edit:", timeout=60
            )
            
            return match_options[selection]["match_id"] if selection is not None else None
            
        except asyncio.TimeoutError:
            embed = EmbedTemplates.error_embed("Timeout", "User search timed out")
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
            return None

    async def _interactive_match_editing(self, ctx, match_data: Dict[str, Any]):
        """Complete interactive match editing interface"""
        edit_options = [
            {"name": "🏆 Change Winner", "value": "winner"},
            {"name": "📊 Edit Score", "value": "score"},
            {"name": "📝 Edit Notes", "value": "notes"},
            {"name": "⚔️ Change Match Type", "value": "type"},
            {"name": "👁️ View Full Details", "value": "details"}
        ]
        
        changes_made = {}
        
        while True:
            # Show current status with pending changes
            embed = self._create_edit_status_embed(match_data, changes_made)
            status_msg = await ctx.send(embed=embed, delete_after=120)
            
            # Get user selection
            all_options = edit_options + [
                {"name": "✅ Save Changes", "value": "save"}, 
                {"name": "❌ Cancel", "value": "cancel"}
            ]
            
            selection = await InteractivePrompts.numbered_selection(
                ctx, all_options, title="✏️ Match Editing",
                description="What would you like to edit?", timeout=120, cancel_option=False
            )
            
            try:
                await status_msg.delete()
            except:
                pass
            
            if selection is None:
                continue
            
            if selection == len(edit_options):  # Save
                if changes_made:
                    success = await self._apply_match_changes(ctx, match_data['match_id'], changes_made)
                    if success:
                        embed = EmbedTemplates.create_base_embed(
                            title="✅ Match Updated", 
                            description=f"Match #{match_data['match_id']} updated successfully.\nChanges: {', '.join(changes_made.keys())}",
                            color=0x51cf66
                        )
                    else:
                        embed = EmbedTemplates.error_embed("Update Failed", "Failed to update match.")
                    await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['confirmation'])
                else:
                    embed = EmbedTemplates.error_embed("No Changes", "No changes were made to save.")
                    await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                return
            
            elif selection == len(edit_options) + 1:  # Cancel
                embed = EmbedTemplates.create_base_embed(
                    title="❌ Edit Cancelled", description="No changes were made.", color=0xff6b6b
                )
                await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['confirmation'])
                return
            
            # Handle specific editing actions
            action = edit_options[selection]["value"]
            
            if action == "winner":
                new_winner = await self._edit_winner(ctx, match_data)
                if new_winner:
                    changes_made['winner_id'] = new_winner
            elif action == "score":
                new_score = await self._edit_score(ctx)
                if new_score is not None:
                    changes_made['score'] = new_score
            elif action == "notes":
                new_notes = await self._edit_notes(ctx)
                if new_notes is not None:
                    changes_made['notes'] = new_notes
            elif action == "type":
                new_type = await self._edit_match_type(ctx)
                if new_type:
                    changes_made['match_type'] = new_type
            elif action == "details":
                await self._show_full_match_details(ctx, match_data)

    def _create_edit_status_embed(self, match_data: Dict[str, Any], changes: Dict[str, Any]) -> discord.Embed:
        """Create status embed showing current values and pending changes"""
        embed = EmbedTemplates.create_base_embed(
            title=f"✏️ Edit Match #{match_data['match_id']}" + (" - Changes Pending" if changes else ""),
            description="Current values and pending changes:", color=0xffd43b if changes else 0x9966cc
        )
        
        challenger_name = match_data.get('challenger_name', 'Unknown')
        challenged_name = match_data.get('challenged_name', 'Unknown')
        
        # Winner with change indicator
        current_winner = match_data.get('winner_name', 'Unknown')
        if 'winner_id' in changes:
            if changes['winner_id'] == match_data['challenger_id']:
                winner_display = f"~~{current_winner}~~ → **{challenger_name}** 🔄"
            elif changes['winner_id'] == match_data['challenged_id']:
                winner_display = f"~~{current_winner}~~ → **{challenged_name}** 🔄"
            else:
                winner_display = f"~~{current_winner}~~ → **Updated** 🔄"
        else:
            winner_display = current_winner
        
        # Other fields with change indicators
        score_display = f"~~{match_data.get('score', 'No score')}~~ → **{changes['score']}** 🔄" if 'score' in changes else match_data.get('score', 'No score')
        notes_display = f"~~Notes~~ → **Updated** 🔄" if 'notes' in changes else (match_data.get('notes', 'No notes')[:30] + '...' if len(match_data.get('notes', '')) > 30 else match_data.get('notes', 'No notes'))
        type_display = f"~~{match_data['match_type'].title()}~~ → **{changes['match_type'].title()}** 🔄" if 'match_type' in changes else match_data['match_type'].title()
        
        embed.add_field(
            name="📊 Match Details",
            value=f"**Challenger:** {challenger_name}\n**Challenged:** {challenged_name}\n**Winner:** {winner_display}\n**Type:** {type_display}\n**Score:** {score_display}\n**Notes:** {notes_display}",
            inline=False
        )
        
        if changes:
            embed.add_field(name="⚠️ Pending Changes", value=f"**{len(changes)}** field(s) will be updated", inline=False)
        
        return embed

    async def _edit_winner(self, ctx, match_data) -> Optional[int]:
        """Edit winner using interactive selection"""
        options = [
            {"name": f"🥇 {match_data.get('challenger_name', 'Unknown')} (Challenger)", "value": match_data['challenger_id']},
            {"name": f"🥇 {match_data.get('challenged_name', 'Unknown')} (Challenged)", "value": match_data['challenged_id']}
        ]
        
        selection = await InteractivePrompts.numbered_selection(
            ctx, options, title="🏆 Select New Winner", timeout=30
        )
        
        return options[selection]["value"] if selection is not None else None

    async def _edit_score(self, ctx) -> Optional[str]:
        """Edit score through text input"""
        embed = EmbedTemplates.create_base_embed(
            title="📊 Edit Score", description="Enter the new score (or 'none' to remove):", color=0x9966cc
        )
        await ctx.send(embed=embed, delete_after=30)
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        
        try:
            message = await self.bot.wait_for('message', timeout=30.0, check=check)
            return None if message.content.lower() == 'none' else message.content
        except asyncio.TimeoutError:
            return None

    async def _edit_notes(self, ctx) -> Optional[str]:
        """Edit notes through text input"""
        embed = EmbedTemplates.create_base_embed(
            title="📝 Edit Notes", description="Enter the new notes (or 'none' to remove):", color=0x9966cc
        )
        await ctx.send(embed=embed, delete_after=30)
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        
        try:
            message = await self.bot.wait_for('message', timeout=60.0, check=check)
            return None if message.content.lower() == 'none' else message.content
        except asyncio.TimeoutError:
            return None

    async def _edit_match_type(self, ctx) -> Optional[str]:
        """Edit match type using interactive selection"""
        options = [
            {"name": "⚔️ Official Match", "value": "official"},
            {"name": "🏆 Blademaster Match", "value": "bm"},
            {"name": "😄 Friendly Match", "value": "friendly"}
        ]
        
        selection = await InteractivePrompts.numbered_selection(
            ctx, options, title="⚔️ Select Match Type", timeout=30
        )
        
        return options[selection]["value"] if selection is not None else None

    async def _apply_match_changes(self, ctx, match_id: int, changes: Dict[str, Any]) -> bool:
        """Apply changes to database with audit logging"""
        try:
            async with aiosqlite.connect(self.db.db_path) as db:
                # Build update query
                set_clauses = [f"{field} = ?" for field in changes.keys()]
                params = list(changes.values()) + [match_id]
                query = f"UPDATE matches SET {', '.join(set_clauses)} WHERE match_id = ?"
                
                await db.execute(query, params)
                await db.commit()
                
                # Log the edit
                await db.execute("""
                    INSERT INTO bot_logs (action_type, user_id, details, timestamp)
                    VALUES (?, ?, ?, ?)
                """, (
                    'match_edited', ctx.author.id,
                    f"Edited match #{match_id}. Fields: {', '.join(changes.keys())}",
                    datetime.now().isoformat()
                ))
                await db.commit()
                
                return True
                
        except Exception as e:
            logger.error(f'Error applying match changes: {e}')
            return False

    async def _show_full_match_details(self, ctx, match_data: Dict[str, Any]):
        """Show comprehensive match details"""
        embed = EmbedTemplates.create_base_embed(
            title=f"📋 Full Details - Match #{match_data['match_id']}", 
            description="Complete match information:", color=0x4169E1
        )
        
        try:
            match_date = datetime.fromisoformat(match_data['match_date']).strftime("%B %d, %Y at %H:%M")
        except:
            match_date = match_data.get('match_date', 'Unknown')
        
        embed.add_field(
            name="👥 Participants",
            value=f"**Challenger:** {match_data.get('challenger_name', 'Unknown')} (ID: {match_data['challenger_id']})\n**Challenged:** {match_data.get('challenged_name', 'Unknown')} (ID: {match_data['challenged_id']})",
            inline=False
        )
        
        embed.add_field(
            name="🏆 Outcome",
            value=f"**Winner:** {match_data.get('winner_name', 'Unknown')} (ID: {match_data['winner_id']})\n**Score:** {match_data.get('score', 'No score recorded')}",
            inline=False
        )
        
        embed.add_field(
            name="📊 Match Info",
            value=f"**Type:** {match_data['match_type'].title()}\n**Date:** {match_date}",
            inline=False
        )
        
        if match_data.get('notes'):
            embed.add_field(name="📝 Notes", value=match_data['notes'], inline=False)
        
        await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['info'])

    @commands.command(name='reserve')
    async def manage_reserves(self, ctx, action: str = None, target: discord.Member = None):
        """
        Manage reserve users (Admin only)
        Usage: ?reserve [list|move|restore] [@user]
        """
        from config import CLEANUP_TIMINGS
        
        if not self.has_admin_permissions(ctx.author):
            embed = EmbedTemplates.error_embed(
                "Permission Denied",
                "You need admin permissions to manage reserves"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
            return
        
        if not action:
            embed = EmbedTemplates.create_base_embed(
                title="🗃️ Reserve Management",
                description="**Available Actions:**\n" +
                        "`?reserve list` - View all reserve users\n" +
                        "`?reserve move @user` - Move user to reserve\n" +
                        "`?reserve restore @user` - Restore user from reserve\n" +
                        "`?reserve sync` - Sync with server membership",
                color=0x4169E1
            )
            await ctx.send(embed=embed)
            return
        
        try:
            if action.lower() == 'list':
                reserve_users = await self.db.get_reserve_users()
                
                if not reserve_users:
                    embed = EmbedTemplates.create_base_embed(
                        title="🗃️ Reserve Users",
                        description="No users currently in reserve",
                        color=0x4169E1
                    )
                else:
                    embed = EmbedTemplates.create_base_embed(
                        title="🗃️ Reserve Users",
                        description=f"Found {len(reserve_users)} users in reserve:",
                        color=0x4169E1
                    )
                    
                    reserve_text = ""
                    for user in reserve_users[:20]:  # Limit for embed size
                        reserve_text += f"**{user['username']}** - {user['tier']} {user['rank_numeral']} ({user['elo_rating']} ELO)\n"
                    
                    if len(reserve_users) > 20:
                        reserve_text += f"\n... and {len(reserve_users) - 20} more"
                    
                    embed.add_field(
                        name="📋 Users",
                        value=reserve_text,
                        inline=False
                    )
                
                await ctx.send(embed=embed)
                
            elif action.lower() == 'move':
                if not target:
                    embed = EmbedTemplates.error_embed(
                        "Missing Target",
                        "Please specify a user to move to reserve"
                    )
                    await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                    return
                
                success = await self.user_system.move_user_to_reserve(
                    target.id, f"Manual reserve by {ctx.author.display_name}"
                )
                
                if success:
                    embed = EmbedTemplates.create_base_embed(
                        title="✅ User Moved to Reserve",
                        description=f"**{target.display_name}** has been moved to reserve status",
                        color=0x00FF00
                    )
                    await ctx.send(embed=embed)
                    
                    # Log to BMBot Logs
                    try:
                        from config import CHANNELS
                        from datetime import datetime
                        
                        logs_channel = self.bot.get_channel(CHANNELS.get('bmbot_logs'))
                        if logs_channel:
                            log_embed = EmbedTemplates.create_base_embed(
                                title="📋 User Moved to Reserve",
                                description=f"**{target.display_name}** ({target.mention}) moved to reserve status",
                                color=0xFFAA00
                            )
                            
                            log_embed.add_field(
                                name="👤 Action Details",
                                value=f"**Admin:** {ctx.author.mention}\n" +
                                    f"**Reason:** Manual admin action\n" +
                                    f"**Guild:** {ctx.guild.name}",
                                inline=False
                            )
                            
                            log_embed.set_footer(text=f"Reserve action • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                            
                            await logs_channel.send(embed=log_embed)
                            
                    except Exception as e:
                        logger.error(f"Error logging reserve move to BMBot Logs: {e}")
                else:
                    embed = EmbedTemplates.error_embed(
                        "Failed",
                        f"Failed to move {target.display_name} to reserve"
                    )
                    await ctx.send(embed=embed)
                
            elif action.lower() == 'restore':
                if not target:
                    embed = EmbedTemplates.error_embed(
                        "Missing Target",
                        "Please specify a user to restore from reserve"
                    )
                    await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])
                    return
                
                success = await self.user_system.restore_user_from_reserve(
                    target.id, f"Manual restore by {ctx.author.display_name}"
                )
                
                if success:
                    embed = EmbedTemplates.create_base_embed(
                        title="✅ User Restored from Reserve",
                        description=f"**{target.display_name}** has been restored to active status",
                        color=0x00FF00
                    )
                    await ctx.send(embed=embed)
                    
                    # Log to BMBot Logs
                    try:
                        from config import CHANNELS
                        from datetime import datetime
                        
                        logs_channel = self.bot.get_channel(CHANNELS.get('bmbot_logs'))
                        if logs_channel:
                            log_embed = EmbedTemplates.create_base_embed(
                                title="📋 User Restored from Reserve",
                                description=f"**{target.display_name}** ({target.mention}) restored to active status",
                                color=0x00FF00
                            )
                            
                            log_embed.add_field(
                                name="👤 Action Details",
                                value=f"**Admin:** {ctx.author.mention}\n" +
                                    f"**Reason:** Manual admin action\n" +
                                    f"**Guild:** {ctx.guild.name}",
                                inline=False
                            )
                            
                            log_embed.set_footer(text=f"Restore action • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                            
                            await logs_channel.send(embed=log_embed)
                            
                    except Exception as e:
                        logger.error(f"Error logging reserve restore to BMBot Logs: {e}")
                else:
                    embed = EmbedTemplates.error_embed(
                        "Failed",
                        f"Failed to restore {target.display_name} from reserve"
                    )
                    await ctx.send(embed=embed)
                
            elif action.lower() == 'sync':
                stats = await self.user_system.sync_server_membership(ctx.guild)
                
                embed = EmbedTemplates.create_base_embed(
                    title="🔄 Server Membership Sync Complete",
                    description="Reserve status synchronized with server membership",
                    color=0x00FF00
                )
                
                embed.add_field(
                    name="📊 Results",
                    value=f"**Moved to Reserve:** {stats['moved_to_reserve']}\n" +
                        f"**Restored from Reserve:** {stats['restored_from_reserve']}\n" +
                        f"**Errors:** {stats['errors']}",
                    inline=False
                )
                
                await ctx.send(embed=embed)
                
                # Also log to BMBot Logs channel if there were changes
                if stats['moved_to_reserve'] > 0 or stats['restored_from_reserve'] > 0 or stats['errors'] > 0:
                    try:
                        from config import CHANNELS
                        from datetime import datetime
                        
                        logs_channel = self.bot.get_channel(CHANNELS.get('bmbot_logs'))
                        if logs_channel:
                            log_embed = EmbedTemplates.create_base_embed(
                                title="🔄 Manual Server Sync",
                                description=f"Server membership sync triggered by {ctx.author.mention}",
                                color=0x4169E1
                            )
                            
                            log_embed.add_field(
                                name="📊 Results",
                                value=f"**Guild:** {ctx.guild.name}\n" +
                                    f"**Moved to Reserve:** {stats['moved_to_reserve']}\n" +
                                    f"**Restored from Reserve:** {stats['restored_from_reserve']}\n" +
                                    f"**Errors:** {stats['errors']}",
                                inline=False
                            )
                            
                            log_embed.set_footer(text=f"Manual sync • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                            
                            await logs_channel.send(embed=log_embed)
                            
                    except Exception as e:
                        logger.error(f"Error logging manual sync to BMBot Logs: {e}")
                
        except Exception as e:
            logger.error(f'Error in reserve management: {e}')
            embed = EmbedTemplates.error_embed(
                "Error",
                f"An error occurred: {str(e)}"
            )
            await ctx.send(embed=embed, delete_after=CLEANUP_TIMINGS['error'])