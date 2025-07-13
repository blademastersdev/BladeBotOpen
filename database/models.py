"""
Database Models and Connection Handling
SQLite database schema and connection management for BladeBot
"""

import sqlite3
import aiosqlite
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from config import DATABASE_CONFIG, ELO_CONFIG

logger = logging.getLogger('BladeBot.Database')

class Database:
    def __init__(self):
        self.db_path = DATABASE_CONFIG['database_path']
        self.backup_path = DATABASE_CONFIG['backup_path']
        
        # Ensure database directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.backup_path).mkdir(parents=True, exist_ok=True)
    
    async def initialize(self):
        """Initialize the database and create tables if they don't exist"""
        logger.info('Initializing database...')
        
        async with aiosqlite.connect(self.db_path) as db:
            await self._create_tables(db)
            await db.commit()
        
        await self._migrate_add_status_column()
        logger.info('Database initialization complete')
    
    async def _create_tables(self, db: aiosqlite.Connection):
        """Create all necessary tables"""
        
        # Users table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                discord_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                roblox_username TEXT,
                tier TEXT NOT NULL DEFAULT 'Bronze',
                rank_numeral TEXT NOT NULL DEFAULT 'IV',
                elo_rating INTEGER DEFAULT 1000,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_challenge_date TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        ''')
        
        # Matches table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                match_id INTEGER PRIMARY KEY AUTOINCREMENT,
                challenger_id INTEGER,
                challenged_id INTEGER,
                winner_id INTEGER,
                loser_id INTEGER,
                match_type TEXT NOT NULL CHECK(match_type IN ('official', 'bm')),
                score TEXT,
                elo_change_winner INTEGER,
                elo_change_loser INTEGER,
                winner_elo_before INTEGER,
                loser_elo_before INTEGER,
                winner_elo_after INTEGER,
                loser_elo_after INTEGER,
                rank_change BOOLEAN DEFAULT FALSE,
                match_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT,
                recorded_by INTEGER,
                FOREIGN KEY (challenger_id) REFERENCES users (discord_id),
                FOREIGN KEY (challenged_id) REFERENCES users (discord_id),
                FOREIGN KEY (winner_id) REFERENCES users (discord_id),
                FOREIGN KEY (loser_id) REFERENCES users (discord_id),
                FOREIGN KEY (recorded_by) REFERENCES users (discord_id)
            )
        ''')
        
        # Active challenges table - UPDATED to include 'cancelled' status
        await db.execute('''
            CREATE TABLE IF NOT EXISTS challenges (
                challenge_id INTEGER PRIMARY KEY AUTOINCREMENT,
                challenger_id INTEGER,
                challenged_id INTEGER,
                challenge_type TEXT NOT NULL CHECK(challenge_type IN ('friendly', 'official', 'bm')),
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'accepted', 'declined', 'expired', 'completed', 'cancelled')),
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                accepted_date TIMESTAMP,
                ticket_channel_id INTEGER,
                expires_at TIMESTAMP,
                FOREIGN KEY (challenger_id) REFERENCES users (discord_id),
                FOREIGN KEY (challenged_id) REFERENCES users (discord_id)
            )
        ''')
        
        # Pending rank changes table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS pending_rank_changes (
                change_id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER,
                winner_id INTEGER,
                loser_id INTEGER,
                winner_old_tier TEXT,
                winner_old_rank TEXT,
                winner_new_tier TEXT,
                winner_new_rank TEXT,
                loser_old_tier TEXT,
                loser_old_rank TEXT,
                loser_new_tier TEXT,
                loser_new_rank TEXT,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'confirmed', 'rejected')),
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_date TIMESTAMP,
                processed_by INTEGER,
                FOREIGN KEY (match_id) REFERENCES matches (match_id),
                FOREIGN KEY (winner_id) REFERENCES users (discord_id),
                FOREIGN KEY (loser_id) REFERENCES users (discord_id),
                FOREIGN KEY (processed_by) REFERENCES users (discord_id)
            )
        ''')
        
        # User settings table (for future features)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                discord_id INTEGER PRIMARY KEY,
                duel_notifications BOOLEAN DEFAULT TRUE,
                rank_notifications BOOLEAN DEFAULT TRUE,
                timezone TEXT DEFAULT 'UTC',
                FOREIGN KEY (discord_id) REFERENCES users (discord_id)
            )
        ''')
        
        # Bot logs table (for tracking bot actions)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS bot_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                user_id INTEGER,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # NEW: Active tickets table for persistence
        await db.execute('''
            CREATE TABLE IF NOT EXISTS active_tickets (
                channel_id INTEGER PRIMARY KEY,
                ticket_type TEXT NOT NULL CHECK(ticket_type IN ('duel', 'evaluation')),
                challenger_id INTEGER,
                challenged_id INTEGER,
                user_id INTEGER,
                duel_type TEXT,
                challenge_id INTEGER,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data TEXT,
                FOREIGN KEY (challenger_id) REFERENCES users (discord_id),
                FOREIGN KEY (challenged_id) REFERENCES users (discord_id),
                FOREIGN KEY (user_id) REFERENCES users (discord_id),
                FOREIGN KEY (challenge_id) REFERENCES challenges (challenge_id)
            )
        ''')
        
        # Create indexes for better performance
        await db.execute('CREATE INDEX IF NOT EXISTS idx_users_tier_rank ON users (tier, rank_numeral)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_users_elo ON users (elo_rating DESC)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_matches_date ON matches (match_date DESC)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_matches_participants ON matches (challenger_id, challenged_id)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_challenges_status ON challenges (status)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_challenges_user ON challenges (challenger_id, challenged_id)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_active_tickets_channel ON active_tickets (channel_id)')

    async def _migrate_add_status_column(self):
        """Add status column for reserve system"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Check if status column exists
                cursor = await db.execute("PRAGMA table_info(users)")
                columns = [column[1] for column in await cursor.fetchall()]
                
                if 'status' not in columns:
                    # Add status column with default 'active'
                    await db.execute('ALTER TABLE users ADD COLUMN status TEXT DEFAULT "active"')
                    
                    # Update existing users to active status
                    await db.execute('UPDATE users SET status = "active" WHERE status IS NULL')
                    await db.commit()
                    
                    logger.info("Added status column for reserve system")
                    
        except Exception as e:
            logger.error(f"Error adding status column: {e}")

    async def get_connection(self) -> aiosqlite.Connection:
        """Get a database connection"""
        return await aiosqlite.connect(self.db_path)
    
    async def backup_database(self) -> str:
        """Create a backup of the database"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"backup_{timestamp}.db"
        backup_path = Path(self.backup_path) / backup_filename
        
        async with aiosqlite.connect(self.db_path) as source:
            async with aiosqlite.connect(str(backup_path)) as backup:
                await source.backup(backup)
        
        logger.info(f'Database backup created: {backup_filename}')
        return str(backup_path)
    
    async def log_action(self, action_type: str, user_id: Optional[int] = None, details: Optional[str] = None):
        """Log a bot action to the database"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'INSERT INTO bot_logs (action_type, user_id, details) VALUES (?, ?, ?)',
                (action_type, user_id, details)
            )
            await db.commit()
    
    # User management methods
    async def create_user(self, discord_id: int, username: str, roblox_username: Optional[str] = None) -> bool:
        """Create a new user in the database"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    '''INSERT INTO users (discord_id, username, roblox_username, elo_rating) 
                       VALUES (?, ?, ?, ?)''',
                    (discord_id, username, roblox_username, ELO_CONFIG['starting_elo'])
                )
                await db.commit()
                
                # Create user settings
                await db.execute(
                    'INSERT INTO user_settings (discord_id) VALUES (?)',
                    (discord_id,)
                )
                await db.commit()
                
            await self.log_action('user_created', discord_id, f'Username: {username}')
            return True
        except sqlite3.IntegrityError:
            return False  # User already exists
    
    async def get_user(self, discord_id: int) -> Optional[Dict[str, Any]]:
        """Get user data from database"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                'SELECT * FROM users WHERE discord_id = ?',
                (discord_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def update_user(self, discord_id: int, **kwargs) -> bool:
        """Update user data"""
        if not kwargs:
            return False
        
        fields = ', '.join(f'{key} = ?' for key in kwargs.keys())
        values = list(kwargs.values()) + [discord_id]
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f'UPDATE users SET {fields} WHERE discord_id = ?',
                values
            )
            await db.commit()
            
            if cursor.rowcount > 0:
                await self.log_action('user_updated', discord_id, str(kwargs))
                return True
            return False
    
    async def get_user_leaderboard_position(self, user_id: int) -> Optional[int]:
        """Get user's position in the ELO leaderboard (1-indexed)"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                '''SELECT COUNT(*) + 1 as position 
                FROM users 
                WHERE elo_rating > (
                    SELECT elo_rating FROM users 
                    WHERE discord_id = ? AND is_active = TRUE AND status = 'active'
                ) AND is_active = TRUE AND status = 'active' ''',
                (user_id,)
            )
            result = await cursor.fetchone()
            
            # Check if user exists and is active
            cursor = await db.execute(
                'SELECT discord_id FROM users WHERE discord_id = ? AND is_active = TRUE AND status = "active"',
                (user_id,)
            )
            user_exists = await cursor.fetchone()
            
            return result[0] if result and user_exists else None

    async def set_user_reserve_status(self, user_id: int, is_reserve: bool = True) -> bool:
        """Set user's reserve status (for users who left the server)"""
        status = 'reserve' if is_reserve else 'active'
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'UPDATE users SET status = ? WHERE discord_id = ?',
                (status, user_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_reserve_users(self) -> List[Dict[str, Any]]:
        """Get all users in reserve status"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                'SELECT * FROM users WHERE status = "reserve" ORDER BY username'
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_users_by_rank(self, tier: str, numeral: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all users in a specific rank"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            if numeral:
                cursor = await db.execute(
                    'SELECT * FROM users WHERE tier = ? AND rank_numeral = ? AND is_active = TRUE ORDER BY elo_rating DESC',
                    (tier, numeral)
                )
            else:
                cursor = await db.execute(
                    'SELECT * FROM users WHERE tier = ? AND is_active = TRUE ORDER BY elo_rating DESC',
                    (tier,)
                )
            
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def get_leaderboard(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get ELO leaderboard (active users only, excluding reserves)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                '''SELECT * FROM users 
                WHERE is_active = TRUE AND status = "active" 
                ORDER BY elo_rating DESC LIMIT ?''',
                (limit,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    # Challenge management methods
    async def create_challenge(self, challenger_id: int, challenged_id: Optional[int], 
                             challenge_type: str, expires_in_minutes: int = 60) -> int:
        """Create a new challenge"""
        expires_at = datetime.now() + timedelta(minutes=expires_in_minutes)
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                '''INSERT INTO challenges (challenger_id, challenged_id, challenge_type, expires_at) 
                   VALUES (?, ?, ?, ?)''',
                (challenger_id, challenged_id, challenge_type, expires_at)
            )
            await db.commit()
            
            await self.log_action('challenge_created', challenger_id, 
                                f'Type: {challenge_type}, Target: {challenged_id}')
            return cursor.lastrowid
    
    async def get_challenge(self, challenge_id: int) -> Optional[Dict[str, Any]]:
        """Get challenge by ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                'SELECT * FROM challenges WHERE challenge_id = ?',
                (challenge_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def update_challenge(self, challenge_id: int, **kwargs) -> bool:
        """Update challenge status"""
        if not kwargs:
            return False
        
        fields = ', '.join(f'{key} = ?' for key in kwargs.keys())
        values = list(kwargs.values()) + [challenge_id]
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f'UPDATE challenges SET {fields} WHERE challenge_id = ?',
                values
            )
            await db.commit()
            return cursor.rowcount > 0
    
    async def get_active_challenges(self, user_id: int) -> List[Dict[str, Any]]:
            """Get active challenges for a user"""
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    '''SELECT * FROM challenges 
                    WHERE (challenger_id = ? OR challenged_id = ?) 
                    AND status = 'pending' 
                    AND expires_at > datetime('now')
                    ORDER BY created_date DESC''',
                    (user_id, user_id)
                )
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    # Match management methods
    async def create_match(self, challenger_id: int, challenged_id: int, winner_id: int, 
                          match_type: str, score: Optional[str] = None, 
                          recorded_by: Optional[int] = None, **kwargs) -> int:
        """Create a new match record"""
        loser_id = challenged_id if winner_id == challenger_id else challenger_id
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                '''INSERT INTO matches 
                   (challenger_id, challenged_id, winner_id, loser_id, match_type, score, recorded_by,
                    elo_change_winner, elo_change_loser, winner_elo_before, loser_elo_before,
                    winner_elo_after, loser_elo_after, rank_change, notes) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (challenger_id, challenged_id, winner_id, loser_id, match_type, score, recorded_by,
                 kwargs.get('elo_change_winner', 0), kwargs.get('elo_change_loser', 0),
                 kwargs.get('winner_elo_before', 0), kwargs.get('loser_elo_before', 0),
                 kwargs.get('winner_elo_after', 0), kwargs.get('loser_elo_after', 0),
                 kwargs.get('rank_change', False), kwargs.get('notes', ''))
            )
            await db.commit()
            
            await self.log_action('match_created', winner_id, 
                                f'Match ID: {cursor.lastrowid}, Type: {match_type}')
            return cursor.lastrowid
    
    async def get_user_matches(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get match history for a user"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                '''SELECT * FROM matches 
                   WHERE challenger_id = ? OR challenged_id = ? 
                   ORDER BY match_date DESC LIMIT ?''',
                (user_id, user_id, limit)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def get_match(self, match_id: int) -> Optional[Dict[str, Any]]:
        """Get match by ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                'SELECT * FROM matches WHERE match_id = ?',
                (match_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    # NEW: Ticket persistence methods
    async def store_ticket(self, channel_id: int, ticket_info: Dict[str, Any]) -> bool:
        """Store ticket information in database"""
        try:
            import json
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    '''INSERT OR REPLACE INTO active_tickets 
                       (channel_id, ticket_type, challenger_id, challenged_id, user_id, 
                        duel_type, challenge_id, status, data)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (
                        channel_id,
                        ticket_info.get('ticket_type'),
                        ticket_info.get('challenger_id'),
                        ticket_info.get('challenged_id'),
                        ticket_info.get('user_id'),
                        ticket_info.get('duel_type'),
                        ticket_info.get('challenge_id'),
                        ticket_info.get('status', 'active'),
                        json.dumps(ticket_info)
                    )
                )
                await db.commit()
            return True
        except Exception as e:
            logger.error(f'Error storing ticket: {e}')
            return False
    
    async def get_ticket(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """Get ticket information from database"""
        try:
            import json
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    'SELECT * FROM active_tickets WHERE channel_id = ?',
                    (channel_id,)
                )
                row = await cursor.fetchone()
                if row:
                    data = json.loads(row['data']) if row['data'] else {}
                    # Ensure created_at is a datetime object
                    if 'created_at' in data and isinstance(data['created_at'], str):
                        data['created_at'] = datetime.fromisoformat(data['created_at'])
                    return data
            return None
        except Exception as e:
            logger.error(f'Error getting ticket: {e}')
            return None
    
    async def remove_ticket(self, channel_id: int) -> bool:
        """Remove ticket from database"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    'DELETE FROM active_tickets WHERE channel_id = ?',
                    (channel_id,)
                )
                await db.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f'Error removing ticket: {e}')
            return False
    
    async def get_all_tickets(self) -> List[Dict[str, Any]]:
        """Get all active tickets from database"""
        try:
            import json
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute('SELECT * FROM active_tickets')
                rows = await cursor.fetchall()
                tickets = []
                for row in rows:
                    data = json.loads(row['data']) if row['data'] else {}
                    # Ensure created_at is a datetime object
                    if 'created_at' in data and isinstance(data['created_at'], str):
                        data['created_at'] = datetime.fromisoformat(data['created_at'])
                    tickets.append((row['channel_id'], data))
                return tickets
        except Exception as e:
            logger.error(f'Error getting all tickets: {e}')
            return []