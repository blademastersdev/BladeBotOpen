"""
Ticket System - Complete Fix with Proper Initialization
Manages creation and coordination of duel ticket channels with database persistence
"""

import discord
import logging
import aiosqlite
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from config import CHANNELS, DUEL_TYPES, BOT_LIMITS, EMBED_COLORS

logger = logging.getLogger('BladeBot.TicketSystem')

class TicketSystem:
    def __init__(self, bot):
        self.bot = bot
        self.active_tickets = {}  # In-memory cache for performance
        self.db_path = 'database/dueling_bot.db'
        self._initialized = False  # Add this missing attribute
    
    async def initialize_ticket_table(self):
        """Initialize the ticket table with proper error handling and schema migration"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Create table with full schema
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS active_tickets (
                        channel_id INTEGER PRIMARY KEY,
                        challenger_id INTEGER,
                        challenged_id INTEGER,
                        user_id INTEGER,
                        ticket_type TEXT NOT NULL,
                        duel_type TEXT,
                        challenge_id INTEGER,
                        status TEXT DEFAULT 'active',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        challenger_name TEXT,
                        challenged_name TEXT,
                        match_id INTEGER,
                        pending_rank_change_id INTEGER
                    )
                """)
                
                # Schema migration: Add missing columns if they don't exist
                try:
                    await db.execute("ALTER TABLE active_tickets ADD COLUMN challenger_name TEXT")
                    logger.info("Added challenger_name column to active_tickets table")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e).lower():
                        logger.debug("challenger_name column already exists")
                    else:
                        logger.warning(f"Unexpected error adding challenger_name column: {e}")
                
                try:
                    await db.execute("ALTER TABLE active_tickets ADD COLUMN challenged_name TEXT")
                    logger.info("Added challenged_name column to active_tickets table")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e).lower():
                        logger.debug("challenged_name column already exists")
                    else:
                        logger.warning(f"Unexpected error adding challenged_name column: {e}")
                
                try:
                    await db.execute("ALTER TABLE active_tickets ADD COLUMN match_id INTEGER")
                    logger.debug("Added match_id column (if needed)")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                    
                try:
                    await db.execute("ALTER TABLE active_tickets ADD COLUMN pending_rank_change_id INTEGER")
                    logger.debug("Added pending_rank_change_id column (if needed)")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                
                await db.commit()
                logger.info("Ticket table initialized successfully with schema migration")
                
        except Exception as e:
            logger.error(f'Error initializing ticket table: {e}')
            raise

    async def load_tickets_from_database(self, guild: discord.Guild):
        """Load active tickets from database with enhanced debugging"""
        try:
            logger.info(f'LOAD DEBUG: Loading tickets from database: {self.db_path}')
            
            if not hasattr(self, 'active_tickets'):
                self.active_tickets = {}
            
            async with aiosqlite.connect(self.db_path) as db:
                # First check total ticket count
                cursor = await db.execute('SELECT COUNT(*) FROM active_tickets')
                total_count = (await cursor.fetchone())[0]
                logger.info(f'LOAD DEBUG: Total tickets in database: {total_count}')
                
                # Check active tickets
                cursor = await db.execute('SELECT COUNT(*) FROM active_tickets WHERE status = "active"')
                active_count = (await cursor.fetchone())[0]
                logger.info(f'LOAD DEBUG: Active tickets in database: {active_count}')
                
                # Get all tickets with details
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute("SELECT * FROM active_tickets WHERE status = 'active'")
                tickets = await cursor.fetchall()
                
                logger.info(f'LOAD DEBUG: Retrieved {len(tickets)} tickets from query')
                for ticket in tickets:
                    logger.info(f'LOAD DEBUG: Ticket data: {ticket}')
            
            loaded_count = 0
            for ticket in tickets:
                channel_id = ticket['channel_id']
                logger.info(f'LOAD DEBUG: Processing ticket for channel {channel_id}')
                
                # Verify channel still exists
                channel = self.bot.get_channel(channel_id)
                if channel:
                    self.active_tickets[channel_id] = ticket
                    loaded_count += 1
                    logger.info(f'LOAD DEBUG: Loaded ticket for existing channel {channel.name}')
                else:
                    logger.info(f'LOAD DEBUG: Channel {channel_id} no longer exists, cleaning up')
                    await self._remove_ticket_from_database(channel_id)
            
            logger.info(f"LOAD DEBUG: Final result - loaded {loaded_count} active tickets")
            self._initialized = True
            
        except Exception as e:
            logger.error(f'LOAD DEBUG: Error loading tickets: {e}')
            import traceback
            logger.error(f'LOAD DEBUG: Traceback: {traceback.format_exc()}')
            self._initialized = True
            if not hasattr(self, 'active_tickets'):
                self.active_tickets = {}

    async def _remove_ticket_from_database(self, channel_id):
        """Helper method to remove a ticket from database"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "DELETE FROM active_tickets WHERE channel_id = ?",
                    (channel_id,)
                )
                await db.commit()
        except Exception as e:
            logger.error(f'Error removing ticket from database: {e}')
    
    async def _save_ticket_to_database(self, channel_id: int, ticket_info: Dict[str, Any]):
        """Save ticket to database with enhanced debugging"""
        try:
            logger.info(f'SAVE DEBUG: Attempting to save ticket {channel_id} to database')
            logger.info(f'SAVE DEBUG: Ticket info: {ticket_info}')
            logger.info(f'SAVE DEBUG: Database path: {self.db_path}')
            
            async with aiosqlite.connect(self.db_path) as db:
                if ticket_info['ticket_type'] == 'duel':
                    values = (
                        channel_id,
                        ticket_info['challenger_id'],
                        ticket_info['challenged_id'],
                        ticket_info['ticket_type'],
                        ticket_info['duel_type'],
                        ticket_info['challenge_id'],
                        ticket_info['status'],
                        ticket_info['created_at'].isoformat(),
                        ticket_info['challenger_name'],
                        ticket_info['challenged_name'],
                        ticket_info.get('match_id'),
                        ticket_info.get('pending_rank_change_id')
                    )
                    logger.info(f'SAVE DEBUG: SQL values: {values}')
                    
                    await db.execute('''
                        INSERT OR REPLACE INTO active_tickets 
                        (channel_id, challenger_id, challenged_id, ticket_type, duel_type, 
                        challenge_id, status, created_at, challenger_name, challenged_name,
                        match_id, pending_rank_change_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', values)
                    
                    await db.commit()
                    logger.info(f'SAVE DEBUG: Successfully saved and committed ticket {channel_id}')
                    
                    # Verify the save worked
                    cursor = await db.execute('SELECT COUNT(*) FROM active_tickets WHERE channel_id = ?', (channel_id,))
                    count = (await cursor.fetchone())[0]
                    logger.info(f'SAVE DEBUG: Verification - found {count} tickets with channel_id {channel_id}')
                
        except Exception as e:
            logger.error(f'SAVE DEBUG: Error saving ticket to database: {e}')
            logger.error(f'SAVE DEBUG: Exception type: {type(e)}')
            import traceback
            logger.error(f'SAVE DEBUG: Traceback: {traceback.format_exc()}')
    
    async def _remove_ticket_from_database(self, channel_id: int):
        """Remove ticket from database"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('DELETE FROM active_tickets WHERE channel_id = ?', (channel_id,))
                await db.commit()
                logger.debug(f'Removed ticket {channel_id} from database')
        except Exception as e:
            logger.error(f'Error removing ticket from database: {e}')
    
    async def _update_ticket_in_database(self, channel_id: int, **updates):
        """Update ticket in database"""
        try:
            if not updates:
                return
                
            set_clauses = []
            values = []
            
            for key, value in updates.items():
                set_clauses.append(f'{key} = ?')
                values.append(value)
            
            values.append(channel_id)
            
            async with aiosqlite.connect(self.db_path) as db:
                query = f'UPDATE active_tickets SET {", ".join(set_clauses)} WHERE channel_id = ?'
                await db.execute(query, values)
                await db.commit()
                logger.debug(f'Updated ticket {channel_id} in database')
                
        except Exception as e:
            logger.error(f'Error updating ticket in database: {e}')

    async def _validate_ticket_creation(self, challenger_id: int, challenged_id: int, 
                                        duel_type: str) -> Tuple[bool, str]:
            """
            Validate ticket creation against business rules
            
            Args:
                challenger_id: Discord ID of challenger
                challenged_id: Discord ID of challenged user
                duel_type: Type of duel (friendly, official, bm)
                
            Returns:
                Tuple of (is_valid, error_message)
            """
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                    
                    # Rule 1: Check 3 official ticket maximum per person (only for official duels)
                    if duel_type == 'official':
                        # Count challenger's active official tickets
                        cursor = await db.execute(
                            '''SELECT COUNT(*) as count FROM active_tickets 
                            WHERE (challenger_id = ? OR challenged_id = ?) 
                            AND duel_type = 'official' 
                            AND status = 'active' ''',
                            (challenger_id, challenger_id)
                        )
                        challenger_count = (await cursor.fetchone())['count']
                        
                        # Count challenged user's active official tickets  
                        cursor = await db.execute(
                            '''SELECT COUNT(*) as count FROM active_tickets 
                            WHERE (challenger_id = ? OR challenged_id = ?) 
                            AND duel_type = 'official' 
                            AND status = 'active' ''',
                            (challenged_id, challenged_id)
                        )
                        challenged_count = (await cursor.fetchone())['count']
                        
                        if challenger_count >= 3:
                            return False, f"Challenger already has {challenger_count} active official tickets (maximum: 3)"
                        
                        if challenged_count >= 3:
                            return False, f"Challenged user already has {challenged_count} active official tickets (maximum: 3)"
                    
                    # Rule 2: Check for duplicate tickets between same players (any duel type)
                    cursor = await db.execute(
                        '''SELECT COUNT(*) as count FROM active_tickets 
                        WHERE ((challenger_id = ? AND challenged_id = ?) 
                                OR (challenger_id = ? AND challenged_id = ?))
                        AND status = 'active' ''',
                        (challenger_id, challenged_id, challenged_id, challenger_id)
                    )
                    duplicate_count = (await cursor.fetchone())['count']
                    
                    if duplicate_count > 0:
                        return False, "A ticket already exists between these players. Please complete the existing duel first."
                    
                    # All validation passed
                    return True, "Validation passed"
                    
            except Exception as e:
                logger.error(f'Error validating ticket creation: {e}')
                return False, f"Validation error: {str(e)}"

# MODIFY create_duel_ticket method signature in ticket_system.py:

    async def create_duel_ticket(self, guild: discord.Guild, challenger: discord.Member,
                            challenged: discord.Member, duel_type: str,
                            challenge_id: int) -> Tuple[Optional[discord.TextChannel], str]:
        """
        Create a ticket channel for a duel with database persistence
        
        Returns:
            Tuple of (channel_or_none, error_message)
        """
        try:
            # VALIDATION: Check business rules before creating ticket
            is_valid, validation_message = await self._validate_ticket_creation(
                challenger.id, challenged.id, duel_type
            )
            
            if not is_valid:
                logger.warning(f'Ticket creation validation failed: {validation_message}')
                return None, validation_message
            
            # Generate ticket name
            timestamp = datetime.now().strftime("%m%d-%H%M")
            channel_name = f"{duel_type}-{challenger.display_name[:8]}-vs-{challenged.display_name[:8]}-{timestamp}"
            channel_name = channel_name.replace(" ", "-").lower()
            
            # Check if we're at ticket limit
            if len(self.active_tickets) >= BOT_LIMITS['max_ticket_channels']:
                error_msg = 'Maximum ticket channels reached, cannot create new ticket'
                logger.warning(error_msg)
                return None, error_msg

            # Create the channel
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                challenger: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                challenged: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                self.bot.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            
            # Add moderator permissions
            for role in guild.roles:
                if any(perm_name in role.name.lower() for perm_name in ['mod', 'admin', 'staff']):
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                topic=f"{DUEL_TYPES[duel_type]['display_name']} Duel: {challenger.display_name} vs {challenged.display_name}",
                reason=f"Duel ticket created for {duel_type} challenge"
            )
            
            # Store enhanced ticket info with challenge data
            ticket_info = {
                'channel_id': channel.id,
                'challenger_id': challenger.id,
                'challenged_id': challenged.id,
                'duel_type': duel_type,
                'challenge_id': challenge_id,
                'created_at': datetime.now(),
                'status': 'active',
                'ticket_type': 'duel',
                # Store participant names for easy recording
                'challenger_name': challenger.display_name,
                'challenged_name': challenged.display_name
            }
            
            # Save to both memory and database
            self.active_tickets[channel.id] = ticket_info
            await self._save_ticket_to_database(channel.id, ticket_info)
            
            # Send enhanced initial ticket message
            await self._send_enhanced_ticket_welcome_message(channel, challenger, challenged, duel_type, challenge_id)
            
            logger.info(f'Created duel ticket: {channel.name} (ID: {channel.id})')
            return channel, "Ticket created successfully"
            
        except Exception as e:
            error_msg = f'Error creating duel ticket: {e}'
            logger.error(error_msg)
            return None, error_msg

    async def create_evaluation_ticket(self, guild: discord.Guild, user: discord.Member) -> Optional[discord.TextChannel]:
        """
        Create a ticket channel for evaluation with database persistence
        """
        try:
            timestamp = datetime.now().strftime("%m%d-%H%M")
            channel_name = f"eval-{user.display_name[:12]}-{timestamp}".replace(" ", "-").lower()
            
            # Get evaluation category
            evaluation_category_id = 1386524806316298330
            evaluation_category = guild.get_channel(evaluation_category_id)
            
            # Create overwrites
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                self.bot.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            
            # Add admin/moderator permissions
            for role in guild.roles:
                if any(perm_name in role.name.lower() for perm_name in ['admin', 'mod', 'staff', 'blademaster']):
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                category=evaluation_category,
                topic=f"Evaluation request for {user.display_name}",
                reason="Evaluation ticket created"
            )
            
            # Store ticket info
            ticket_info = {
                'channel_id': channel.id,
                'user_id': user.id,
                'ticket_type': 'evaluation',
                'created_at': datetime.now(),
                'status': 'active'
            }
            
            # Save to both memory and database
            self.active_tickets[channel.id] = ticket_info
            await self._save_ticket_to_database(channel.id, ticket_info)
            
            # Send evaluation welcome message
            await self._send_evaluation_welcome_message(channel, user)
            
            logger.info(f'Created evaluation ticket: {channel.name}')
            return channel
            
        except Exception as e:
            logger.error(f'Error creating evaluation ticket: {e}')
            return None

    async def _load_single_ticket_into_memory(self, channel_id: int):
        """Load a single ticket from database into memory cache"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute(
                    "SELECT * FROM active_tickets WHERE channel_id = ?",
                    (channel_id,)
                )
                ticket = await cursor.fetchone()
                if ticket:
                    self.active_tickets[channel_id] = ticket
                    logger.debug(f'Loaded ticket {channel_id} into memory cache')
        except Exception as e:
            logger.error(f'Error loading single ticket into memory: {e}')

    async def close_ticket(self, channel: discord.TextChannel, closed_by: discord.Member,
                          reason: str = "Ticket closed") -> bool:
        """
        Close a ticket channel with database cleanup
        """
        try:
            ticket_info = self.active_tickets.get(channel.id)
            if not ticket_info:
                logger.warning(f'Attempted to close unknown ticket: {channel.name}')
            
            # Send closing message
            embed = discord.Embed(
                title="🔒 Ticket Closing",
                description=f"This ticket is being closed by {closed_by.mention}.\n**Reason:** {reason}",
                color=EMBED_COLORS['warning'],
                timestamp=datetime.now()
            )
            
            await channel.send(embed=embed)
            
            # Remove from database and memory
            await self._remove_ticket_from_database(channel.id)
            if channel.id in self.active_tickets:
                del self.active_tickets[channel.id]
            
            # Delete the channel after a short delay
            import asyncio
            await asyncio.sleep(5)
            await channel.delete(reason=f"Ticket closed by {closed_by}: {reason}")
            
            logger.info(f'Closed ticket {channel.name} by {closed_by}')
            return True
            
        except Exception as e:
            logger.error(f'Error closing ticket {channel.name}: {e}')
            return False

    async def is_ticket_channel(self, channel: discord.TextChannel) -> bool:
        """Check if a channel is a managed ticket with database fallback"""
        if not hasattr(channel, 'id'):
            return False
        
        # Check memory cache first (fast path)
        if channel.id in self.active_tickets:
            return True
        
        # Database fallback (handles cases where memory cache is not synchronized)
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT 1 FROM active_tickets WHERE channel_id = ? AND status = 'active'",
                    (channel.id,)
                )
                result = await cursor.fetchone()
                if result:
                    # Found in database - load into memory cache for next time
                    await self._load_single_ticket_into_memory(channel.id)
                    return True
                return False
        except Exception as e:
            logger.error(f'Error checking ticket channel in database: {e}')
            return False
    
    def get_ticket_info(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """Get ticket information by channel ID"""
        return self.active_tickets.get(channel_id)
    
    async def update_ticket_info(self, channel_id: int, **updates):
        """Update ticket information in both memory and database"""
        if channel_id in self.active_tickets:
            self.active_tickets[channel_id].update(updates)
            await self._update_ticket_in_database(channel_id, **updates)

    def user_has_active_duel_ticket(self, user_id: int) -> bool:
        """Check if a user has an active duel ticket"""
        for ticket_info in self.active_tickets.values():
            if ticket_info.get('ticket_type') == 'evaluation':
                continue  # Evaluation tickets don't count as duel tickets
            else:
                # Duel ticket
                if (ticket_info.get('challenger_id') == user_id or 
                    ticket_info.get('challenged_id') == user_id):
                    return True
        return False

    async def _send_enhanced_ticket_welcome_message(self, channel: discord.TextChannel,
                                                challenger: discord.Member, 
                                                challenged: discord.Member,
                                                duel_type: str, challenge_id: int):
        """Send enhanced welcome message to duel ticket with recording shortcuts and updated information"""
        duel_info = DUEL_TYPES[duel_type]
        
        embed = discord.Embed(
            title=f"⚔️ {duel_info['display_name']} Duel Coordination",
            description=f"{challenger.mention} vs {challenged.mention}",
            color=EMBED_COLORS['duel'],
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="Duel Information",
            value=(
                f"**Type:** {duel_info['display_name']}\n"
                f"**Challenge ID:** {challenge_id}\n"
                f"**Challenger:** {challenger.display_name}\n"
                f"**Challenged:** {challenged.display_name}\n"
                f"**Description:** {duel_info['description']}"
            ),
            inline=False
        )
        
        # Add arena and rules information
        embed.add_field(
            name="🏟️ Arena & Rules",
            value=(
                f"**Arena:** [Blademasters Dueling](https://www.roblox.com/games/99964937823063/Blademasters-Dueling)\n"
                f"**Rules:** <#1390121947383468114>"
            ),
            inline=True
        )
        
        if duel_type == 'friendly':
            instructions = (
                "🎮 **Instructions:**\n"
                "• Coordinate your duel time and server\n"
                "• Have fun and good luck!\n"
                "• This match will not be recorded\n"
                "• Close this ticket when done with `?close` (moderator only)"
            )
        elif duel_type == 'official':
            instructions = (
                "📊 **Instructions:**\n"
                "• Coordinate your duel time and server\n"
                "• This match will affect your ELO rating\n"
                "• Report the winner and score when finished\n"
                "• A moderator will record the results using the quick command below"
            )
            
            # Add quick recording command for moderators  
            embed.add_field(
                name="🛠️ Quick Recording (Moderators)",
                value=(
                    f"`?log @winner [score] [notes]`\n"
                    f"This will automatically use the challenge data from this ticket"
                ),
                inline=False
            )
        else:  # bm duel
            instructions = (
                "👑 **Instructions:**\n"
                "• Coordinate your duel time and server\n"
                "• This match affects ELO AND rank progression\n"
                "• A moderator must observe or verify results\n"
                "• Rank changes require admin confirmation\n"
                "• Report the winner and score when finished"
            )
            
            # Add quick recording command for moderators
            embed.add_field(
                name="🛠️ Recording (Moderators)",
                value=(
                    f"`?log @winner [score] [notes]`\n"
                    f"This will automatically use the challenge data from this ticket"
                ),
                inline=False
            )
        
        embed.add_field(
            name="How to Proceed",
            value=instructions,
            inline=False
        )
        
        embed.add_field(
            name="Available Commands",
            value=(
                "`?close` - Close this ticket (moderator only)\n"
                "`?status` - Check duel status\n"
                "`?ticket_info` - Show detailed ticket information"
            ),
            inline=True
        )
        
        embed.set_footer(text="Good luck to both duelists!")
        
        # Create message content with participant mentions and find moderator roles to ping
        content_parts = []
        
        # Always mention the participants to ensure they get notifications
        content_parts.append(f"📋 **Participants:** {challenger.mention} {challenged.mention}")
        
        # Find and mention moderator/staff roles
        guild = channel.guild
        moderator_roles = []
        for role in guild.roles:
            if any(perm_name in role.name.lower() for perm_name in ['mod', 'admin', 'staff']):
                moderator_roles.append(role.mention)
        
        if moderator_roles:
            content_parts.append(f"🛠️ **Moderators:** {' '.join(moderator_roles)}")
        
        # Join with newlines for better formatting
        content = "\n".join(content_parts)
        
        await channel.send(content=content, embed=embed)

    async def _send_evaluation_welcome_message(self, channel: discord.TextChannel, user: discord.Member):
        """Send welcome message to evaluation ticket"""
        embed = discord.Embed(
            title="🎯 Evaluation Request",
            description=f"Evaluation ticket for {user.mention}",
            color=EMBED_COLORS['info'],
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="What happens next?",
            value=(
                "• An admin will review your request\n"
                "• You'll participate in evaluation duels\n"
                "• Your initial rank will be determined\n"
                "• You'll be placed in the Blademasters group"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Possible Starting Ranks",
            value="• Bronze IV (most common)\n• Silver IV\n• Gold III (exceptional skill)",
            inline=True
        )
        
        embed.add_field(
            name="Please provide:",
            value=(
                "• Your ROBLOX username\n"
                "• Previous dueling experience\n"
                "• Any relevant achievements"
            ),
            inline=True
        )
        
        embed.set_footer(text="An admin will be with you shortly!")
        
        await channel.send(embed=embed)

    async def get_active_tickets(self, guild: discord.Guild) -> List[Dict[str, Any]]:
        """
        Get list of all active tickets
        """
        active = []
        for channel_id, ticket_info in self.active_tickets.items():
            channel = guild.get_channel(channel_id)
            if channel:
                active.append({
                    'channel': channel,
                    'info': ticket_info
                })
            else:
                # Channel no longer exists, remove from active tickets
                await self._remove_ticket_from_database(channel_id)
                del self.active_tickets[channel_id]
        
        return active

    async def cleanup_expired_tickets(self, guild: discord.Guild, max_age_hours: int = 48) -> int:
        """
        Clean up tickets that have been inactive for too long
        """
        cleaned_up = 0
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        tickets_to_remove = []
        for channel_id, ticket_info in self.active_tickets.items():
            if ticket_info['created_at'] < cutoff_time:
                channel = guild.get_channel(channel_id)
                if channel:
                    try:
                        # Check if channel has recent activity
                        async for message in channel.history(limit=1, after=cutoff_time):
                            break  # Found recent message, don't clean up
                        else:
                            # No recent messages, clean up
                            await channel.delete(reason="Ticket cleanup - inactive")
                            tickets_to_remove.append(channel_id)
                            cleaned_up += 1
                            logger.info(f'Cleaned up inactive ticket: {channel.name}')
                    except Exception as e:
                        logger.error(f'Error cleaning up ticket {channel_id}: {e}')
                        tickets_to_remove.append(channel_id)
                else:
                    # Channel doesn't exist, remove from tracking
                    tickets_to_remove.append(channel_id)
        
        # Remove cleaned up tickets from tracking
        for channel_id in tickets_to_remove:
            if channel_id in self.active_tickets:
                await self._remove_ticket_from_database(channel_id)
                del self.active_tickets[channel_id]
        
        return cleaned_up