#!/usr/bin/env python3
"""
Database Migration Script
Updates existing database schema to support new features
"""

import sqlite3
import asyncio
import aiosqlite
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('Migration')

async def migrate_database():
    """Migrate existing database to new schema"""
    db_path = 'database/dueling_bot.db'
    
    if not Path(db_path).exists():
        logger.info('No existing database found, skipping migration')
        return
    
    logger.info('Starting database migration...')
    
    async with aiosqlite.connect(db_path) as db:
        # Check if we need to update the challenges table
        cursor = await db.execute("PRAGMA table_info(challenges)")
        columns = await cursor.fetchall()
        
        # Check if active_tickets table exists
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='active_tickets'"
        )
        tickets_table_exists = await cursor.fetchone()
        
        if not tickets_table_exists:
            logger.info('Creating active_tickets table...')
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
            await db.execute('CREATE INDEX IF NOT EXISTS idx_active_tickets_channel ON active_tickets (channel_id)')
            logger.info('Created active_tickets table')
        
        # Update challenges table constraint
        try:
            # First, check current schema
            cursor = await db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='challenges'")
            current_schema = await cursor.fetchone()
            
            if current_schema and 'cancelled' not in current_schema[0]:
                logger.info('Updating challenges table to support cancelled status...')
                
                # SQLite doesn't support modifying CHECK constraints directly
                # We need to recreate the table
                
                # 1. Create new table with updated constraint
                await db.execute('''
                    CREATE TABLE challenges_new (
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
                
                # 2. Copy data from old table
                await db.execute('''
                    INSERT INTO challenges_new 
                    SELECT * FROM challenges
                ''')
                
                # 3. Drop old table
                await db.execute('DROP TABLE challenges')
                
                # 4. Rename new table
                await db.execute('ALTER TABLE challenges_new RENAME TO challenges')
                
                # 5. Recreate indexes
                await db.execute('CREATE INDEX IF NOT EXISTS idx_challenges_status ON challenges (status)')
                await db.execute('CREATE INDEX IF NOT EXISTS idx_challenges_user ON challenges (challenger_id, challenged_id)')
                
                logger.info('Updated challenges table successfully')
            else:
                logger.info('Challenges table already supports cancelled status')
        
        except Exception as e:
            logger.error(f'Error updating challenges table: {e}')
            raise
        
        await db.commit()
        logger.info('Database migration completed successfully')

if __name__ == '__main__':
    asyncio.run(migrate_database())