#!/usr/bin/env python3
"""
BM System Database Migration
Adds database tables and indexes needed for enhanced BM challenge system
"""

import asyncio
import aiosqlite
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('BM_Migration')

async def migrate_bm_database():
    """Add BM system database components"""
    db_path = 'database/dueling_bot.db'
    
    if not Path(db_path).exists():
        logger.error('Database file not found! Please ensure bot has been initialized first.')
        return False
    
    logger.info('Starting BM system database migration...')
    
    try:
        async with aiosqlite.connect(db_path) as db:
            # Check if admin_actions table already exists
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='admin_actions'"
            )
            admin_actions_exists = await cursor.fetchone()
            
            if not admin_actions_exists:
                logger.info('Creating admin_actions table...')
                await db.execute('''
                    CREATE TABLE admin_actions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        admin_id INTEGER NOT NULL,
                        action_type TEXT NOT NULL,
                        target_user_id INTEGER,
                        action_details TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (admin_id) REFERENCES users (discord_id),
                        FOREIGN KEY (target_user_id) REFERENCES users (discord_id)
                    )
                ''')
                
                # Add performance indexes
                logger.info('Creating admin_actions indexes...')
                await db.execute('CREATE INDEX idx_admin_actions_admin_id ON admin_actions (admin_id)')
                await db.execute('CREATE INDEX idx_admin_actions_timestamp ON admin_actions (timestamp)')
                await db.execute('CREATE INDEX idx_admin_actions_type ON admin_actions (action_type)')
                
                logger.info('✅ Created admin_actions table with indexes')
            else:
                logger.info('Admin_actions table already exists - skipping creation')
            
            # Verify the table structure
            cursor = await db.execute("PRAGMA table_info(admin_actions)")
            columns = await cursor.fetchall()
            expected_columns = ['id', 'admin_id', 'action_type', 'target_user_id', 'action_details', 'timestamp']
            actual_columns = [col[1] for col in columns]
            
            if all(col in actual_columns for col in expected_columns):
                logger.info('✅ Admin_actions table structure verified')
            else:
                logger.warning(f'⚠️  Table structure mismatch. Expected: {expected_columns}, Found: {actual_columns}')
            
            # Verify indexes exist
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='admin_actions'")
            indexes = await cursor.fetchall()
            index_names = [idx[0] for idx in indexes]
            
            expected_indexes = ['idx_admin_actions_admin_id', 'idx_admin_actions_timestamp', 'idx_admin_actions_type']
            missing_indexes = [idx for idx in expected_indexes if idx not in index_names]
            
            if missing_indexes:
                logger.info(f'Creating missing indexes: {missing_indexes}')
                for idx in missing_indexes:
                    if 'admin_id' in idx:
                        await db.execute('CREATE INDEX IF NOT EXISTS idx_admin_actions_admin_id ON admin_actions (admin_id)')
                    elif 'timestamp' in idx:
                        await db.execute('CREATE INDEX IF NOT EXISTS idx_admin_actions_timestamp ON admin_actions (timestamp)')
                    elif 'type' in idx:
                        await db.execute('CREATE INDEX IF NOT EXISTS idx_admin_actions_type ON admin_actions (action_type)')
            else:
                logger.info('✅ All admin_actions indexes verified')
            
            # Commit all changes
            await db.commit()
            
            # Final verification - test insertion and retrieval
            logger.info('Testing admin_actions table functionality...')
            test_admin_id = 123456789  # Dummy ID for testing
            
            await db.execute('''
                INSERT INTO admin_actions (admin_id, action_type, action_details)
                VALUES (?, ?, ?)
            ''', (test_admin_id, 'migration_test', 'BM system migration test'))
            
            cursor = await db.execute('SELECT * FROM admin_actions WHERE admin_id = ?', (test_admin_id,))
            test_record = await cursor.fetchone()
            
            if test_record:
                logger.info('✅ Admin_actions table functionality test passed')
                # Clean up test record
                await db.execute('DELETE FROM admin_actions WHERE admin_id = ?', (test_admin_id,))
            else:
                logger.error('❌ Admin_actions table functionality test failed')
                return False
            
            await db.commit()
            
        logger.info('🎉 BM system database migration completed successfully!')
        return True
        
    except Exception as e:
        logger.error(f'❌ BM database migration failed: {e}')
        return False

async def rollback_bm_migration():
    """Rollback BM system database changes if needed"""
    db_path = 'database/dueling_bot.db'
    
    logger.warning('Rolling back BM system database changes...')
    
    try:
        async with aiosqlite.connect(db_path) as db:
            # Drop admin_actions table and its indexes
            await db.execute('DROP TABLE IF EXISTS admin_actions')
            logger.info('Dropped admin_actions table')
            
            # Indexes are automatically dropped with the table
            await db.commit()
            
        logger.info('✅ BM system rollback completed')
        return True
        
    except Exception as e:
        logger.error(f'❌ BM system rollback failed: {e}')
        return False

def main():
    """Main migration function with options"""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--rollback':
        asyncio.run(rollback_bm_migration())
    else:
        success = asyncio.run(migrate_bm_database())
        if not success:
            print("\n❌ Migration failed! Check logs above.")
            sys.exit(1)
        else:
            print("\n✅ Migration completed successfully!")
            print("The BM system database components are now ready.")

if __name__ == '__main__':
    main()