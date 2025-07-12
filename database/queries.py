"""
Database Query Utilities
Common database operations and complex queries for BladeBot
"""

import aiosqlite
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from config import RANK_STRUCTURE, TIER_HIERARCHY, NUMERAL_HIERARCHY

class DatabaseQueries:
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    async def get_connection(self) -> aiosqlite.Connection:
        """Get database connection"""
        return await aiosqlite.connect(self.db_path)
    
    async def can_user_challenge(self, challenger_id: int, challenged_id: int, challenge_type: str) -> Tuple[bool, str]:
            """Check if a user can challenge another user"""
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                # Get both users
                challenger = await self._get_user_by_id(db, challenger_id)
                challenged = await self._get_user_by_id(db, challenged_id)
                
                if not challenger:
                    return False, "Challenger not found in database"
                if not challenged:
                    return False, "Challenged user not found in database"
                
                # Check for BM duel restrictions
                if challenge_type == 'bm':
                    # Check if challenger can challenge the target rank
                    can_challenge, reason = self._can_challenge_rank(
                        challenger['tier'], challenger['rank_numeral'],
                        challenged['tier'], challenged['rank_numeral']
                    )
                    if not can_challenge:
                        return False, reason
                    
                    # Check cooldown
                    if challenger['last_challenge_date']:
                        last_challenge = datetime.fromisoformat(challenger['last_challenge_date'])
                        if datetime.now() - last_challenge < timedelta(hours=24):
                            remaining = 24 - (datetime.now() - last_challenge).total_seconds() / 3600
                            return False, f"Challenge cooldown active. {remaining:.1f} hours remaining."
                
                # CLEANUP: First, find and clean up stale challenges (pending but no active ticket)
                cursor = await db.execute(
                    '''SELECT challenge_id, ticket_channel_id FROM challenges 
                    WHERE ((challenger_id = ? AND challenged_id = ?) OR 
                            (challenger_id = ? AND challenged_id = ?))
                    AND status = 'pending' AND expires_at > datetime('now')''',
                    (challenger_id, challenged_id, challenged_id, challenger_id)
                )
                existing_challenges = await cursor.fetchall()
                
                # Check if any of these challenges have orphaned tickets
                stale_challenge_ids = []
                for challenge in existing_challenges:
                    challenge_id = challenge[0]
                    ticket_channel_id = challenge[1]
                    
                    # If challenge has no ticket channel, it's stale
                    if not ticket_channel_id:
                        stale_challenge_ids.append(challenge_id)
                        continue
                    
                    # Check if ticket channel still exists in active_tickets table
                    cursor = await db.execute(
                        'SELECT COUNT(*) FROM active_tickets WHERE channel_id = ? AND status = "active"',
                        (ticket_channel_id,)
                    )
                    ticket_exists = (await cursor.fetchone())[0] > 0
                    
                    if not ticket_exists:
                        stale_challenge_ids.append(challenge_id)
                
                # Clean up stale challenges
                if stale_challenge_ids:
                    placeholders = ','.join('?' * len(stale_challenge_ids))
                    await db.execute(
                        f'UPDATE challenges SET status = "cancelled" WHERE challenge_id IN ({placeholders})',
                        stale_challenge_ids
                    )
                    await db.commit()
                    
                    # Log cleanup
                    import logging
                    logger = logging.getLogger('BladeBot.DatabaseQueries')
                    logger.info(f'Cleaned up {len(stale_challenge_ids)} stale challenges as cancelled: {stale_challenge_ids}')
                
                # Now check for ACTUAL active challenges (after cleanup)
                cursor = await db.execute(
                    '''SELECT COUNT(*) FROM challenges 
                    WHERE ((challenger_id = ? AND challenged_id = ?) OR 
                            (challenger_id = ? AND challenged_id = ?))
                    AND status = 'pending' AND expires_at > datetime('now')''',
                    (challenger_id, challenged_id, challenged_id, challenger_id)
                )
                remaining_challenges = (await cursor.fetchone())[0]
                
                if remaining_challenges > 0:
                    return False, "An active challenge already exists between these users"
                
                return True, "Challenge allowed"
    
    def _can_challenge_rank(self, challenger_tier: str, challenger_numeral: str, 
                           challenged_tier: str, challenged_numeral: str) -> Tuple[bool, str]:
        """Check if challenger can challenge the target rank"""
        from config import get_next_rank
        
        next_tier, next_numeral = get_next_rank(challenger_tier, challenger_numeral)
        
        if not next_tier:
            return False, "You are already at the highest rank"
        
        if challenged_tier != next_tier or challenged_numeral != next_numeral:
            return False, f"You can only challenge users in {next_tier} {next_numeral}"
        
        return True, "Valid challenge target"
    
    async def _get_user_by_id(self, db: aiosqlite.Connection, user_id: int) -> Optional[Dict[str, Any]]:
        """Helper to get user by ID"""
        cursor = await db.execute('SELECT * FROM users WHERE discord_id = ?', (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None
    
    async def get_rank_statistics(self) -> Dict[str, Any]:
        """Get comprehensive rank statistics"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            stats = {
                'total_users': 0,
                'by_tier': {},
                'by_rank': {},
                'capacity_usage': {}
            }
            
            # Get total active users
            cursor = await db.execute('SELECT COUNT(*) FROM users WHERE is_active = TRUE')
            stats['total_users'] = (await cursor.fetchone())[0]
            
            # Get users by tier and rank
            for tier in TIER_HIERARCHY:
                cursor = await db.execute(
                    'SELECT rank_numeral, COUNT(*) FROM users WHERE tier = ? AND is_active = TRUE GROUP BY rank_numeral',
                    (tier,)
                )
                tier_data = await cursor.fetchall()
                
                stats['by_tier'][tier] = sum(row[1] for row in tier_data)
                
                for numeral, count in tier_data:
                    rank_key = f"{tier} {numeral}"
                    stats['by_rank'][rank_key] = count
                    
                    # Calculate capacity usage
                    capacity = RANK_STRUCTURE[tier]['capacities'].get(numeral, 0)
                    usage_percent = (count / capacity * 100) if capacity > 0 else 0
                    stats['capacity_usage'][rank_key] = {
                        'current': count,
                        'capacity': capacity,
                        'usage_percent': usage_percent
                    }
            
            return stats
    
    async def get_user_duel_history(self, user_id: int, duel_type: Optional[str] = None, 
                                   limit: int = 50) -> List[Dict[str, Any]]:
        """Get detailed duel history for a user"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            base_query = '''
                SELECT m.*, 
                       c_user.username as challenger_name,
                       ch_user.username as challenged_name,
                       w_user.username as winner_name,
                       l_user.username as loser_name
                FROM matches m
                JOIN users c_user ON m.challenger_id = c_user.discord_id
                JOIN users ch_user ON m.challenged_id = ch_user.discord_id
                JOIN users w_user ON m.winner_id = w_user.discord_id
                JOIN users l_user ON m.loser_id = l_user.discord_id
                WHERE (m.challenger_id = ? OR m.challenged_id = ?)
            '''
            
            params = [user_id, user_id]
            
            if duel_type:
                base_query += ' AND m.match_type = ?'
                params.append(duel_type)
            
            base_query += ' ORDER BY m.match_date DESC LIMIT ?'
            params.append(limit)
            
            cursor = await db.execute(base_query, params)
            rows = await cursor.fetchall()
            
            return [dict(row) for row in rows]
    
    async def get_head_to_head_record(self, user1_id: int, user2_id: int) -> Dict[str, Any]:
        """Get head-to-head record between two users"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Get all matches between these users
            cursor = await db.execute(
                '''SELECT * FROM matches 
                   WHERE (challenger_id = ? AND challenged_id = ?) OR 
                         (challenger_id = ? AND challenged_id = ?)
                   ORDER BY match_date DESC''',
                (user1_id, user2_id, user2_id, user1_id)
            )
            matches = await cursor.fetchall()
            
            record = {
                'total_matches': len(matches),
                'user1_wins': 0,
                'user2_wins': 0,
                'matches': [dict(match) for match in matches]
            }
            
            for match in matches:
                if match['winner_id'] == user1_id:
                    record['user1_wins'] += 1
                else:
                    record['user2_wins'] += 1
            
            return record
    
    async def get_recent_activity(self, days: int = 7) -> Dict[str, Any]:
        """Get recent activity statistics"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            since_date = datetime.now() - timedelta(days=days)
            
            # Recent matches
            cursor = await db.execute(
                'SELECT COUNT(*) FROM matches WHERE match_date > ?',
                (since_date.isoformat(),)
            )
            recent_matches = (await cursor.fetchone())[0]
            
            # Recent users joined
            cursor = await db.execute(
                'SELECT COUNT(*) FROM users WHERE joined_date > ?',
                (since_date.isoformat(),)
            )
            recent_users = (await cursor.fetchone())[0]
            
            # Recent rank changes
            cursor = await db.execute(
                'SELECT COUNT(*) FROM matches WHERE match_date > ? AND rank_change = TRUE',
                (since_date.isoformat(),)
            )
            recent_rank_changes = (await cursor.fetchone())[0]
            
            # Most active users
            cursor = await db.execute(
                '''SELECT u.username, COUNT(*) as match_count
                   FROM matches m
                   JOIN users u ON (m.challenger_id = u.discord_id OR m.challenged_id = u.discord_id)
                   WHERE m.match_date > ?
                   GROUP BY u.discord_id
                   ORDER BY match_count DESC
                   LIMIT 5''',
                (since_date.isoformat(),)
            )
            most_active = [dict(row) for row in await cursor.fetchall()]
            
            return {
                'days': days,
                'recent_matches': recent_matches,
                'recent_users': recent_users,
                'recent_rank_changes': recent_rank_changes,
                'most_active_users': most_active
            }
    
    async def cleanup_expired_challenges(self) -> int:
        """Clean up expired challenges and return count of cleaned up challenges"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                '''UPDATE challenges 
                   SET status = 'expired' 
                   WHERE status = 'pending' AND expires_at <= datetime('now')'''
            )
            await db.commit()
            return cursor.rowcount
    
    async def get_pending_rank_changes(self) -> List[Dict[str, Any]]:
        """Get all pending rank changes awaiting admin confirmation"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            cursor = await db.execute(
                '''SELECT prc.*, 
                       w_user.username as winner_name,
                       l_user.username as loser_name,
                       m.match_type, m.score, m.match_date
                   FROM pending_rank_changes prc
                   JOIN users w_user ON prc.winner_id = w_user.discord_id
                   JOIN users l_user ON prc.loser_id = l_user.discord_id
                   JOIN matches m ON prc.match_id = m.match_id
                   WHERE prc.status = 'pending'
                   ORDER BY prc.created_date ASC'''
            )
            
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def get_rank_capacity_info(self, tier: str, numeral: str) -> Dict[str, Any]:
        """Get capacity information for a specific rank"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'SELECT COUNT(*) FROM users WHERE tier = ? AND rank_numeral = ? AND is_active = TRUE',
                (tier, numeral)
            )
            current_count = (await cursor.fetchone())[0]
            
            capacity = RANK_STRUCTURE[tier]['capacities'].get(numeral, 0)
            
            return {
                'tier': tier,
                'numeral': numeral,
                'current_count': current_count,
                'capacity': capacity,
                'available_spots': max(0, capacity - current_count),
                'is_full': current_count >= capacity,
                'usage_percent': (current_count / capacity * 100) if capacity > 0 else 0
            }
    
    async def find_available_spot_in_rank(self, tier: str, numeral: str) -> bool:
        """Check if there's an available spot in the specified rank"""
        capacity_info = await self.get_rank_capacity_info(tier, numeral)
        return not capacity_info['is_full']
    
    async def get_elo_distribution(self) -> Dict[str, Any]:
        """Get ELO distribution statistics"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Basic stats
            cursor = await db.execute(
                '''SELECT AVG(elo_rating) as avg_elo, 
                          MIN(elo_rating) as min_elo, 
                          MAX(elo_rating) as max_elo,
                          COUNT(*) as total_players
                   FROM users WHERE is_active = TRUE'''
            )
            basic_stats = dict(await cursor.fetchone())
            
            # ELO ranges
            ranges = [
                (0, 800),
                (800, 900),
                (900, 1000),
                (1000, 1100),
                (1100, 1200),
                (1200, 1300),
                (1300, 1400),
                (1400, 1500),
                (1500, float('inf'))
            ]
            
            distribution = {}
            for min_elo, max_elo in ranges:
                if max_elo == float('inf'):
                    cursor = await db.execute(
                        'SELECT COUNT(*) FROM users WHERE elo_rating >= ? AND is_active = TRUE',
                        (min_elo,)
                    )
                    range_name = f"{min_elo}+"
                else:
                    cursor = await db.execute(
                        'SELECT COUNT(*) FROM users WHERE elo_rating >= ? AND elo_rating < ? AND is_active = TRUE',
                        (min_elo, max_elo)
                    )
                    range_name = f"{min_elo}-{max_elo}"
                
                count = (await cursor.fetchone())[0]
                distribution[range_name] = count
            
            return {
                'basic_stats': basic_stats,
                'distribution': distribution
            }