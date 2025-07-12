"""
ELO Rating System
Handles ELO calculations and rating updates for BladeBot
"""

import math
import logging
from typing import Tuple, Dict, Any
from config import ELO_CONFIG

logger = logging.getLogger('BladeBot.ELO')

class ELOSystem:
    def __init__(self):
        self.starting_elo = ELO_CONFIG['starting_elo']
        self.k_factor_new = ELO_CONFIG['k_factor_new']
        self.k_factor_established = ELO_CONFIG['k_factor_established']
        self.new_player_threshold = ELO_CONFIG['new_player_threshold']

    def calculate_elo_change(self, winner_elo: int, loser_elo: int, 
                        winner_games: int, loser_games: int) -> Tuple[int, int]:
        """
        Calculate ELO changes for both players after a match
        FIXED: Ensures mathematically consistent zero-sum ELO exchange
        
        Args:
            winner_elo: Current ELO of the winner
            loser_elo: Current ELO of the loser  
            winner_games: Number of games played by winner
            loser_games: Number of games played by loser
            
        Returns:
            Tuple of (winner_elo_change, loser_elo_change)
        """
        # Use higher K-factor (more volatile) for the exchange calculation
        # This ensures new players get faster rating adjustments
        k_winner = self.k_factor_new if winner_games < self.new_player_threshold else self.k_factor_established
        k_loser = self.k_factor_new if loser_games < self.new_player_threshold else self.k_factor_established
        
        # Use the MAXIMUM K-factor for the exchange to benefit the player who needs faster adjustment
        k_factor = max(k_winner, k_loser)
        
        # Calculate expected scores using standard ELO formula
        expected_winner = self._calculate_expected_score(winner_elo, loser_elo)
        
        # Calculate ELO change using single K-factor (ensures zero-sum)
        # Winner gets score of 1, expected was expected_winner
        winner_change = round(k_factor * (1 - expected_winner))
        
        # Loser change is EXACTLY opposite to maintain zero-sum property
        loser_change = -winner_change
        
        # Log the calculation for verification
        logger.info(f'ELO calculation: Winner {winner_elo} -> {winner_elo + winner_change} (+{winner_change})')
        logger.info(f'ELO calculation: Loser {loser_elo} -> {loser_elo + loser_change} ({loser_change})')
        logger.info(f'ELO verification: Zero-sum check: {winner_change + loser_change} (should be 0)')
        
        return winner_change, loser_change

    # MATHEMATICAL VERIFICATION:
    # Before fix: Winner +17, Loser -8 = Net +9 points created (WRONG)
    # After fix:  Winner +17, Loser -17 = Net 0 points (CORRECT)

    # This ensures ELO system maintains mathematical integrity while still
    # allowing different players to have different volatility based on experience.
    
    def _calculate_expected_score(self, player_elo: int, opponent_elo: int) -> float:
        """
        Calculate expected score for a player against an opponent
        
        Args:
            player_elo: Player's current ELO
            opponent_elo: Opponent's current ELO
            
        Returns:
            Expected score (between 0 and 1)
        """
        return 1 / (1 + math.pow(10, (opponent_elo - player_elo) / 400))
    
    def calculate_new_ratings(self, winner_elo: int, loser_elo: int,
                            winner_games: int, loser_games: int) -> Dict[str, int]:
        """
        Calculate new ELO ratings after a match
        
        Returns:
            Dictionary with winner and loser's new ratings and changes
        """
        winner_change, loser_change = self.calculate_elo_change(
            winner_elo, loser_elo, winner_games, loser_games
        )
        
        return {
            'winner_new_elo': winner_elo + winner_change,
            'loser_new_elo': loser_elo + loser_change,
            'winner_elo_change': winner_change,
            'loser_elo_change': loser_change,
            'winner_old_elo': winner_elo,
            'loser_old_elo': loser_elo
        }
    
    def get_elo_tier(self, elo: int) -> str:
        """
        Get the ELO tier name based on rating
        
        Args:
            elo: Player's ELO rating
            
        Returns:
            String representing the ELO tier
        """
        if elo >= 2000:
            return "Grandmaster"
        elif elo >= 1800:
            return "Master"
        elif elo >= 1600:
            return "Expert"
        elif elo >= 1400:
            return "Advanced"
        elif elo >= 1200:
            return "Intermediate"
        elif elo >= 1000:
            return "Novice"
        elif elo >= 800:
            return "Beginner"
        else:
            return "Rookie"
    
    def get_elo_color(self, elo: int) -> int:
        """
        Get color code based on ELO rating for embeds
        
        Args:
            elo: Player's ELO rating
            
        Returns:
            Integer color code for Discord embeds
        """
        if elo >= 2000:
            return 0xFF0000  # Red - Grandmaster
        elif elo >= 1800:
            return 0xFF6600  # Orange - Master
        elif elo >= 1600:
            return 0xFFFF00  # Yellow - Expert
        elif elo >= 1400:
            return 0x00FF00  # Green - Advanced
        elif elo >= 1200:
            return 0x0099FF  # Blue - Intermediate
        elif elo >= 1000:
            return 0x9966CC  # Purple - Novice
        elif elo >= 800:
            return 0x808080  # Gray - Beginner
        else:
            return 0x654321  # Brown - Rookie
    
    def calculate_win_probability(self, player_elo: int, opponent_elo: int) -> float:
        """
        Calculate the probability of player winning against opponent
        
        Args:
            player_elo: Player's ELO rating
            opponent_elo: Opponent's ELO rating
            
        Returns:
            Probability as a float between 0 and 1
        """
        return self._calculate_expected_score(player_elo, opponent_elo)
    
    def get_rating_change_preview(self, player_elo: int, opponent_elo: int,
                                player_games: int, opponent_games: int) -> Dict[str, Any]:
        """
        Preview what would happen to ratings if player wins or loses
        
        Args:
            player_elo: Player's current ELO
            opponent_elo: Opponent's current ELO
            player_games: Player's games played
            opponent_games: Opponent's games played
            
        Returns:
            Dictionary with win/loss scenarios
        """
        # If player wins
        win_changes = self.calculate_elo_change(player_elo, opponent_elo, player_games, opponent_games)
        
        # If player loses
        loss_changes = self.calculate_elo_change(opponent_elo, player_elo, opponent_games, player_games)
        
        return {
            'current_elo': player_elo,
            'opponent_elo': opponent_elo,
            'win_probability': self.calculate_win_probability(player_elo, opponent_elo),
            'if_win': {
                'new_elo': player_elo + win_changes[0],
                'elo_change': win_changes[0]
            },
            'if_loss': {
                'new_elo': player_elo + loss_changes[1],
                'elo_change': loss_changes[1]
            }
        }
    
    def is_elo_rating_valid(self, elo: int) -> bool:
        """
        Check if an ELO rating is within valid bounds
        
        Args:
            elo: ELO rating to validate
            
        Returns:
            True if valid, False otherwise
        """
        return 0 <= elo <= 3000  # Reasonable bounds for competitive play
    
    def get_rating_difference_description(self, elo_diff: int) -> str:
        """
        Get a human-readable description of the ELO difference
        
        Args:
            elo_diff: Absolute difference between two ELO ratings
            
        Returns:
            String description of the skill gap
        """
        if elo_diff <= 50:
            return "Very Close Match"
        elif elo_diff <= 100:
            return "Close Match"
        elif elo_diff <= 200:
            return "Moderate Difference"
        elif elo_diff <= 300:
            return "Significant Difference"
        elif elo_diff <= 400:
            return "Large Difference"
        else:
            return "Massive Difference"
    
    def calculate_performance_rating(self, wins: int, losses: int, 
                                   opponent_elos: list) -> float:
        """
        Calculate performance rating based on results against opponents
        
        Args:
            wins: Number of wins
            losses: Number of losses
            opponent_elos: List of opponent ELO ratings
            
        Returns:
            Performance rating
        """
        if not opponent_elos:
            return self.starting_elo
        
        total_games = wins + losses
        if total_games == 0:
            return self.starting_elo
        
        avg_opponent_elo = sum(opponent_elos) / len(opponent_elos)
        score_percentage = wins / total_games
        
        # Convert score percentage to rating difference
        if score_percentage == 1.0:
            rating_diff = 400  # Cap at +400
        elif score_percentage == 0.0:
            rating_diff = -400  # Cap at -400
        else:
            rating_diff = -400 * math.log10((1 / score_percentage) - 1)
        
        return avg_opponent_elo + rating_diff
    
    def get_k_factor(self, games_played: int) -> int:
        """
        Get the K-factor for a player based on games played
        
        Args:
            games_played: Number of games the player has played
            
        Returns:
            K-factor value
        """
        return self.k_factor_new if games_played < self.new_player_threshold else self.k_factor_established