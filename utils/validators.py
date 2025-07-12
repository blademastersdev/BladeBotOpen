"""
Input Validation Helpers
Provides validation functions for user inputs and bot operations
"""

import re
import discord
from typing import Optional, Tuple, List
from config import RANK_STRUCTURE, TIER_HIERARCHY, EVALUATION_RANKS, DUEL_TYPES

class Validators:
    @staticmethod
    def validate_rank(tier: str, numeral: str) -> Tuple[bool, str]:
        """
        Validate if a tier and numeral combination is valid
        
        Args:
            tier: Tier name (Bronze, Silver, Gold, Platinum, Diamond)
            numeral: Numeral (I, II, III, IV)
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if tier not in RANK_STRUCTURE:
            valid_tiers = ", ".join(RANK_STRUCTURE.keys())
            return False, f"Invalid tier. Valid tiers: {valid_tiers}"
        
        if numeral not in RANK_STRUCTURE[tier]['numerals']:
            valid_numerals = ", ".join(RANK_STRUCTURE[tier]['numerals'])
            return False, f"Invalid numeral for {tier}. Valid numerals: {valid_numerals}"
        
        return True, ""
    
    @staticmethod
    def validate_evaluation_rank(tier: str, numeral: str) -> Tuple[bool, str]:
        """
        Validate if a rank is valid for evaluation placement
        
        Args:
            tier: Tier name
            numeral: Numeral
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if (tier, numeral) not in EVALUATION_RANKS:
            valid_ranks = ", ".join([f"{t} {n}" for t, n in EVALUATION_RANKS])
            return False, f"Invalid evaluation rank. Valid ranks: {valid_ranks}"
        
        return True, ""
    
    @staticmethod
    def validate_duel_type(duel_type: str) -> Tuple[bool, str]:
        """
        Validate if a duel type is valid
        
        Args:
            duel_type: Type of duel
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if duel_type not in DUEL_TYPES:
            valid_types = ", ".join(DUEL_TYPES.keys())
            return False, f"Invalid duel type. Valid types: {valid_types}"
        
        return True, ""
    
    @staticmethod
    def validate_score_format(score: str) -> Tuple[bool, str]:
        """
        Validate score format (e.g., "3-1", "5-2", etc.)
        
        Args:
            score: Score string
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not score:
            return True, ""  # Score is optional
        
        # Pattern for score like "3-1", "10-5", etc.
        pattern = r'^\d{1,2}-\d{1,2}$'
        if not re.match(pattern, score):
            return False, "Score must be in format 'X-Y' (e.g., '3-1', '5-2')"
        
        # Extract winner and loser scores
        try:
            winner_score, loser_score = map(int, score.split('-'))
            
            if winner_score <= loser_score:
                return False, "Winner's score must be higher than loser's score"
            
            if winner_score > 20 or loser_score > 20:
                return False, "Scores must be 20 or less"
            
            if winner_score < 1 or loser_score < 0:
                return False, "Scores must be non-negative (winner must have at least 1)"
            
        except ValueError:
            return False, "Invalid score format"
        
        return True, ""
    
    @staticmethod
    def validate_roblox_username(username: str) -> Tuple[bool, str]:
        """
        Validate ROBLOX username format
        
        Args:
            username: ROBLOX username
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not username:
            return True, ""  # Username is optional
        
        # ROBLOX username rules:
        # - 3-20 characters
        # - Letters, numbers, and underscores only
        # - Cannot start or end with underscore
        # - Cannot have consecutive underscores
        
        if len(username) < 3 or len(username) > 20:
            return False, "ROBLOX username must be 3-20 characters long"
        
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            return False, "ROBLOX username can only contain letters, numbers, and underscores"
        
        if username.startswith('_') or username.endswith('_'):
            return False, "ROBLOX username cannot start or end with an underscore"
        
        if '__' in username:
            return False, "ROBLOX username cannot have consecutive underscores"
        
        return True, ""
    
    @staticmethod
    def validate_mention(mention_text: str, guild: discord.Guild) -> Tuple[bool, Optional[discord.Member], str]:
        """
        Validate and extract member from mention
        
        Args:
            mention_text: Text that should contain a mention
            guild: Discord guild
            
        Returns:
            Tuple of (is_valid, member, error_message)
        """
        if not mention_text:
            return False, None, "No user mentioned"
        
        # Extract user ID from mention
        user_id_match = re.search(r'<@!?(\d+)>', mention_text)
        if not user_id_match:
            return False, None, "Invalid user mention format"
        
        try:
            user_id = int(user_id_match.group(1))
            member = guild.get_member(user_id)
            
            if not member:
                return False, None, "User not found in this server"
            
            if member.bot:
                return False, None, "Cannot target bot users"
            
            return True, member, ""
            
        except ValueError:
            return False, None, "Invalid user ID in mention"
    
    @staticmethod
    def validate_command_permissions(member: discord.Member, required_permissions: List[str]) -> Tuple[bool, str]:
        """
        Validate if member has required permissions
        
        Args:
            member: Discord member
            required_permissions: List of required permission names
            
        Returns:
            Tuple of (has_permissions, error_message)
        """
        member_permissions = member.guild_permissions
        
        missing_permissions = []
        for perm_name in required_permissions:
            if not hasattr(member_permissions, perm_name):
                missing_permissions.append(perm_name)
                continue
                
            if not getattr(member_permissions, perm_name):
                missing_permissions.append(perm_name)
        
        if missing_permissions:
            missing_str = ", ".join(missing_permissions)
            return False, f"Missing permissions: {missing_str}"
        
        return True, ""
    
    @staticmethod
    def validate_channel_permissions(channel: discord.TextChannel, bot_user: discord.Member,
                                   required_permissions: List[str]) -> Tuple[bool, str]:
        """
        Validate if bot has required permissions in channel
        
        Args:
            channel: Discord text channel
            bot_user: Bot's member object
            required_permissions: List of required permission names
            
        Returns:
            Tuple of (has_permissions, error_message)
        """
        bot_permissions = channel.permissions_for(bot_user)
        
        missing_permissions = []
        for perm_name in required_permissions:
            if not hasattr(bot_permissions, perm_name):
                missing_permissions.append(perm_name)
                continue
                
            if not getattr(bot_permissions, perm_name):
                missing_permissions.append(perm_name)
        
        if missing_permissions:
            missing_str = ", ".join(missing_permissions)
            return False, f"Bot missing permissions in #{channel.name}: {missing_str}"
        
        return True, ""
    
    @staticmethod
    def validate_integer_input(value: str, min_value: int = None, max_value: int = None) -> Tuple[bool, Optional[int], str]:
        """
        Validate integer input with optional bounds
        
        Args:
            value: String value to validate
            min_value: Minimum allowed value (optional)
            max_value: Maximum allowed value (optional)
            
        Returns:
            Tuple of (is_valid, parsed_value, error_message)
        """
        try:
            parsed_value = int(value)
            
            if min_value is not None and parsed_value < min_value:
                return False, None, f"Value must be at least {min_value}"
            
            if max_value is not None and parsed_value > max_value:
                return False, None, f"Value must be at most {max_value}"
            
            return True, parsed_value, ""
            
        except ValueError:
            return False, None, "Invalid number format"
    
    @staticmethod
    def validate_text_length(text: str, min_length: int = 0, max_length: int = 2000) -> Tuple[bool, str]:
        """
        Validate text length
        
        Args:
            text: Text to validate
            min_length: Minimum length
            max_length: Maximum length
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(text) < min_length:
            return False, f"Text must be at least {min_length} characters long"
        
        if len(text) > max_length:
            return False, f"Text must be at most {max_length} characters long"
        
        return True, ""
    
    @staticmethod
    def sanitize_input(text: str) -> str:
        """
        Sanitize user input by removing dangerous characters
        
        Args:
            text: Input text to sanitize
            
        Returns:
            Sanitized text
        """
        if not text:
            return ""
        
        # Remove or escape potentially dangerous characters
        sanitized = text.strip()
        
        # Remove excessive whitespace
        sanitized = re.sub(r'\s+', ' ', sanitized)
        
        # Remove Discord formatting that could cause issues
        sanitized = re.sub(r'[`*_~|]', '', sanitized)
        
        return sanitized
    
    @staticmethod
    def validate_challenge_target(challenger: discord.Member, target: discord.Member) -> Tuple[bool, str]:
        """
        Validate challenge target
        
        Args:
            challenger: Member issuing the challenge
            target: Target member
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if challenger.id == target.id:
            return False, "You cannot challenge yourself"
        
        if target.bot:
            return False, "You cannot challenge bots"
        
        # Check if target is in the server
        if not challenger.guild.get_member(target.id):
            return False, "Target user is not in this server"
        
        return True, ""
    
    @staticmethod
    def parse_rank_from_string(rank_string: str) -> Tuple[bool, Optional[str], Optional[str], str]:
        """
        Parse tier and numeral from a rank string like "Gold III" or "silver 2"
        
        Args:
            rank_string: String containing rank information
            
        Returns:
            Tuple of (is_valid, tier, numeral, error_message)
        """
        if not rank_string:
            return False, None, None, "No rank provided"
        
        # Clean and split the input
        parts = rank_string.strip().split()
        if len(parts) != 2:
            return False, None, None, "Rank must be in format 'Tier Numeral' (e.g., 'Gold III')"
        
        tier_part, numeral_part = parts
        
        # Normalize tier name
        tier = tier_part.capitalize()
        
        # Normalize numeral (convert numbers to roman numerals if needed)
        numeral_map = {
            '1': 'I', '2': 'II', '3': 'III', '4': 'IV',
            'i': 'I', 'ii': 'II', 'iii': 'III', 'iv': 'IV'
        }
        
        numeral = numeral_map.get(numeral_part.lower(), numeral_part.upper())
        
        # Validate the rank
        is_valid, error = Validators.validate_rank(tier, numeral)
        if not is_valid:
            return False, None, None, error
        
        return True, tier, numeral, ""
    
    @staticmethod
    def validate_embed_field_count(field_count: int) -> Tuple[bool, str]:
        """
        Validate Discord embed field count
        
        Args:
            field_count: Number of fields
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if field_count > 25:
            return False, "Discord embeds cannot have more than 25 fields"
        
        return True, ""
    
    @staticmethod
    def validate_discord_message_length(message: str) -> Tuple[bool, str]:
        """
        Validate Discord message length
        
        Args:
            message: Message content
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(message) > 2000:
            return False, "Discord messages cannot exceed 2000 characters"
        
        return True, ""