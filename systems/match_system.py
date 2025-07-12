"""
Match System
Handles match recording, statistics, and result processing
"""

import discord
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from database.models import Database
from systems.elo_system import ELOSystem
from systems.user_system import UserSystem
from systems.ranking_system import RankingSystem
from config import DUEL_TYPES, CHANNELS

logger = logging.getLogger('BladeBot.MatchSystem')

class MatchSystem:
    def __init__(self, database: Database, elo_system: ELOSystem, 
                 user_system: UserSystem, ranking_system: RankingSystem):
        self.db = database
        self.elo_system = elo_system
        self.user_system = user_system
        self.ranking_system = ranking_system
    
    async def record_official_match(self, challenger: discord.Member, challenged: discord.Member,
                                  winner: discord.Member, loser: discord.Member,
                                  score: Optional[str] = None, notes: Optional[str] = None,
                                  recorded_by: Optional[discord.Member] = None) -> Tuple[bool, str, Optional[int]]:
        """
        Record an official duel result
        
        Args:
            challenger: Member who issued the challenge
            challenged: Member who was challenged
            winner: Member who won the match
            loser: Member who lost the match
            score: Optional score string
            notes: Optional match notes
            recorded_by: Member who recorded the match
            
        Returns:
            Tuple of (success, message, match_id)
        """
        try:
            # Get user data
            winner_data = await self.db.get_user(winner.id)
            loser_data = await self.db.get_user(loser.id)
            
            if not winner_data or not loser_data:
                return False, "User data not found", None
            
            # Calculate ELO changes
            elo_result = self.elo_system.calculate_new_ratings(
                winner_data['elo_rating'], loser_data['elo_rating'],
                winner_data['games_played'], loser_data['games_played']
            )
            
            # Create match record
            match_id = await self.db.create_match(
                challenger_id=challenger.id,
                challenged_id=challenged.id,
                winner_id=winner.id,
                match_type='official',
                score=score,
                recorded_by=recorded_by.id if recorded_by else None,
                notes=notes,
                elo_change_winner=elo_result['winner_elo_change'],
                elo_change_loser=elo_result['loser_elo_change'],
                winner_elo_before=elo_result['winner_old_elo'],
                loser_elo_before=elo_result['loser_old_elo'],
                winner_elo_after=elo_result['winner_new_elo'],
                loser_elo_after=elo_result['loser_new_elo']
            )
            
            # Update user statistics
            await self.user_system.update_user_stats(
                winner.id, won=True, elo_change=elo_result['winner_elo_change']
            )
            await self.user_system.update_user_stats(
                loser.id, won=False, elo_change=elo_result['loser_elo_change']
            )
            
            logger.info(f'Recorded official match {match_id}: {winner} beat {loser}')
            
            return True, f"Official match recorded! Match ID: {match_id}", match_id
            
        except Exception as e:
            logger.error(f'Error recording official match: {e}')
            return False, f"Error recording match: {e}", None
    
    async def record_bm_match(self, challenger: discord.Member, challenged: discord.Member,
                            winner: discord.Member, loser: discord.Member,
                            score: Optional[str] = None, notes: Optional[str] = None,
                            recorded_by: Optional[discord.Member] = None) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Record a BM duel result and initiate rank change process
        
        Args:
            challenger: Member who issued the challenge
            challenged: Member who was challenged
            winner: Member who won the match
            loser: Member who lost the match
            score: Optional score string
            notes: Optional match notes
            recorded_by: Member who recorded the match
            
        Returns:
            Tuple of (success, message, match_and_rank_data)
        """
        try:
            # Get user data
            winner_data = await self.db.get_user(winner.id)
            loser_data = await self.db.get_user(loser.id)
            
            if not winner_data or not loser_data:
                return False, "User data not found", None
            
            # Calculate ELO changes
            elo_result = self.elo_system.calculate_new_ratings(
                winner_data['elo_rating'], loser_data['elo_rating'],
                winner_data['games_played'], loser_data['games_played']
            )
            
            # Check if rank change is possible
            can_change, change_reason, rank_change_data = await self.ranking_system.can_rank_change_occur(
                winner.id, loser.id
            )
            
            # Create match record
            match_id = await self.db.create_match(
                challenger_id=challenger.id,
                challenged_id=challenged.id,
                winner_id=winner.id,
                match_type='bm',
                score=score,
                recorded_by=recorded_by.id if recorded_by else None,
                notes=notes,
                elo_change_winner=elo_result['winner_elo_change'],
                elo_change_loser=elo_result['loser_elo_change'],
                winner_elo_before=elo_result['winner_old_elo'],
                loser_elo_before=elo_result['loser_old_elo'],
                winner_elo_after=elo_result['winner_new_elo'],
                loser_elo_after=elo_result['loser_new_elo'],
                rank_change=can_change
            )
            
            # Update user statistics
            await self.user_system.update_user_stats(
                winner.id, won=True, elo_change=elo_result['winner_elo_change']
            )
            await self.user_system.update_user_stats(
                loser.id, won=False, elo_change=elo_result['loser_elo_change']
            )
            
            # Create pending rank change if applicable
            pending_change_id = None
            if can_change:
                pending_change_id = await self.ranking_system.create_pending_rank_change(
                    match_id, winner.id, loser.id, rank_change_data
                )
            
            result_data = {
                'match_id': match_id,
                'elo_changes': elo_result,
                'rank_change_possible': can_change,
                'rank_change_reason': change_reason,
                'rank_change_data': rank_change_data if can_change else None,
                'pending_change_id': pending_change_id
            }
            
            success_message = f"BM match recorded! Match ID: {match_id}"
            if can_change:
                success_message += f"\n⚠️ Rank change pending admin confirmation (ID: {pending_change_id})"
            else:
                success_message += f"\nℹ️ No rank change: {change_reason}"
            
            logger.info(f'Recorded BM match {match_id}: {winner} beat {loser}, rank change: {can_change}')
            
            return True, success_message, result_data
            
        except Exception as e:
            logger.error(f'Error recording BM match: {e}')
            return False, f"Error recording match: {e}", None

    async def get_match_summary(self, match_id: int) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive match summary
        
        Args:
            match_id: Match ID to get summary for
            
        Returns:
            Dictionary with match summary data
        """
        match_data = await self.db.get_match(match_id)
        if not match_data:
            return None
        
        # Get user data for all participants
        challenger = await self.db.get_user(match_data['challenger_id'])
        challenged = await self.db.get_user(match_data['challenged_id'])
        winner = await self.db.get_user(match_data['winner_id'])
        loser = await self.db.get_user(match_data['loser_id'])
        
        summary = {
            'match_data': match_data,
            'challenger': challenger,
            'challenged': challenged,
            'winner': winner,
            'loser': loser,
            'match_type_info': DUEL_TYPES.get(match_data['match_type'], {}),
            'elo_changes': {
                'winner_change': match_data['elo_change_winner'],
                'loser_change': match_data['elo_change_loser'],
                'winner_before': match_data['winner_elo_before'],
                'winner_after': match_data['winner_elo_after'],
                'loser_before': match_data['loser_elo_before'],
                'loser_after': match_data['loser_elo_after']
            }
        }
        
        # Add rank change info if applicable
        if match_data['rank_change']:
            # Get pending rank change details
            async with await self.db.get_connection() as db:
                db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
                cursor = await db.execute(
                    'SELECT * FROM pending_rank_changes WHERE match_id = ?',
                    (match_id,)
                )
                rank_change = await cursor.fetchone()
                if rank_change:
                    summary['rank_change'] = rank_change
        
        return summary
    
    async def get_recent_matches(self, limit: int = 10, match_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get recent matches with user information
        
        Args:
            limit: Maximum number of matches to return
            match_type: Filter by match type (optional)
            
        Returns:
            List of recent matches with enhanced data
        """
        async with await self.db.get_connection() as db:
            db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
            
            query = '''
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
            '''
            
            params = []
            if match_type:
                query += ' WHERE m.match_type = ?'
                params.append(match_type)
            
            query += ' ORDER BY m.match_date DESC LIMIT ?'
            params.append(limit)
            
            cursor = await db.execute(query, params)
            matches = await cursor.fetchall()
            
            return matches
    
    async def get_user_head_to_head(self, user1_id: int, user2_id: int) -> Dict[str, Any]:
        """
        Get head-to-head record between two users
        
        Args:
            user1_id: First user's Discord ID
            user2_id: Second user's Discord ID
            
        Returns:
            Head-to-head statistics
        """
        from database.queries import DatabaseQueries
        queries = DatabaseQueries(self.db.db_path)
        return await queries.get_head_to_head_record(user1_id, user2_id)
    
    async def get_match_statistics(self) -> Dict[str, Any]:
        """
        Get overall match statistics
        
        Returns:
            Dictionary with match statistics
        """
        async with await self.db.get_connection() as db:
            # Total matches
            cursor = await db.execute('SELECT COUNT(*) FROM matches')
            total_matches = (await cursor.fetchone())[0]
            
            # Matches by type
            cursor = await db.execute(
                'SELECT match_type, COUNT(*) FROM matches GROUP BY match_type'
            )
            matches_by_type = dict(await cursor.fetchall())
            
            # Recent activity (last 7 days)
            cursor = await db.execute(
                "SELECT COUNT(*) FROM matches WHERE match_date > datetime('now', '-7 days')"
            )
            recent_matches = (await cursor.fetchone())[0]
            
            # Rank changes
            cursor = await db.execute('SELECT COUNT(*) FROM matches WHERE rank_change = TRUE')
            total_rank_changes = (await cursor.fetchone())[0]
            
            # Average ELO changes
            cursor = await db.execute(
                'SELECT AVG(ABS(elo_change_winner)), AVG(ABS(elo_change_loser)) FROM matches WHERE elo_change_winner IS NOT NULL'
            )
            avg_elo_changes = await cursor.fetchone()
            
            return {
                'total_matches': total_matches,
                'matches_by_type': matches_by_type,
                'recent_matches_7d': recent_matches,
                'total_rank_changes': total_rank_changes,
                'avg_elo_change_winner': avg_elo_changes[0] or 0,
                'avg_elo_change_loser': avg_elo_changes[1] or 0
            }
    
    async def validate_match_participants(self, challenger: discord.Member, challenged: discord.Member,
                                        winner: discord.Member, loser: discord.Member) -> Tuple[bool, str]:
        """
        Validate that match participants are correct
        
        Args:
            challenger: Member who issued the challenge
            challenged: Member who was challenged
            winner: Member who won
            loser: Member who lost
            
        Returns:
            Tuple of (is_valid, reason)
        """
        # Check that winner and loser are among the participants
        participants = {challenger.id, challenged.id}
        match_participants = {winner.id, loser.id}
        
        if participants != match_participants:
            return False, "Winner and loser must be the original challenge participants"
        
        # Check that winner and loser are different
        if winner.id == loser.id:
            return False, "Winner and loser cannot be the same person"
        
        return True, "Match participants are valid"
    
    async def get_performance_statistics(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """
        Get performance statistics for a user over a time period
        
        Args:
            user_id: Discord user ID
            days: Number of days to analyze
            
        Returns:
            Performance statistics
        """
        async with await self.db.get_connection() as db:
            db.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
            
            since_date = datetime.now().strftime('%Y-%m-%d')
            
            # Get matches in time period
            cursor = await db.execute(
                '''SELECT * FROM matches 
                   WHERE (challenger_id = ? OR challenged_id = ?) 
                   AND match_date > datetime(?, '-{} days')
                   ORDER BY match_date DESC'''.format(days),
                (user_id, user_id, since_date)
            )
            matches = await cursor.fetchall()
            
            if not matches:
                return {
                    'matches_played': 0,
                    'wins': 0,
                    'losses': 0,
                    'win_rate': 0,
                    'elo_change': 0,
                    'avg_elo_change': 0
                }
            
            wins = sum(1 for m in matches if m['winner_id'] == user_id)
            losses = len(matches) - wins
            win_rate = (wins / len(matches)) * 100 if matches else 0
            
            # Calculate total ELO change
            total_elo_change = 0
            for match in matches:
                if match['winner_id'] == user_id:
                    total_elo_change += match['elo_change_winner'] or 0
                else:
                    total_elo_change += match['elo_change_loser'] or 0
            
            avg_elo_change = total_elo_change / len(matches) if matches else 0
            
            return {
                'matches_played': len(matches),
                'wins': wins,
                'losses': losses,
                'win_rate': win_rate,
                'total_elo_change': total_elo_change,
                'avg_elo_change': avg_elo_change,
                'recent_matches': matches[:5]  # Last 5 matches
            }