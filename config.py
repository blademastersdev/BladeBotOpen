"""
BladeBot Configuration
Contains all bot settings, role IDs, channel IDs, and rank structures
"""

import os

# Bot Configuration
BOT_CONFIG = {
    'bot_token': os.getenv('DISCORD_BOT_TOKEN'),
    'command_prefix': '?',
    'owner_id': None,  # Set this to your Discord user ID if needed
}

# Channel IDs
CHANNELS = {
    'duel_logs': 1387689568207372288,
    'rank_tracker': 1387689498481000617,
    'bot_commands_public': 1388012975616688179,
    'bot_commands_bm': 1387688932766122084,
    'bmbot_logs': 1388441826859679796,
    'eval_request': 1388442021877911652,
}

# Duel Command Channel Restrictions
DUEL_COMMAND_CHANNELS = {
    'allowed_channels': [
        1390093488028254259,  # bot_commands_public
        1390093549252640888,  # bot_commands_bm  
    ],
    'allow_ticket_channels': True,  # Allow in duel ticket channels
    'admin_override': True,  # Allow admins to bypass restrictions
}

# Role IDs - Tier Roles
TIER_ROLES = {
    'Diamond': 1386495907989815367,
    'Platinum': 1386495960129208332,
    'Gold': 1386495975165526096,
    'Silver': 1386495987534528544,
    'Bronze': 1386496007566786652,
    'Evaluation': 1386495849814691961,
    'Guest': 1387950007046504610,
}

# Role IDs - Rank Roles (Tier + Numeral)
RANK_ROLES = {
    ('Diamond', 'I'): 1386495821033373702,
    ('Diamond', 'II'): 1386495823105360005,
    ('Platinum', 'I'): 1386495825777131631,
    ('Platinum', 'II'): 1386495827115118784,
    ('Platinum', 'III'): 1386495828516147330,
    ('Gold', 'I'): 1386495830189670450,
    ('Gold', 'II'): 1386495831858745495,
    ('Gold', 'III'): 1386495833419153499,
    ('Silver', 'I'): 1386495836170485923,
    ('Silver', 'II'): 1386495838024634459,
    ('Silver', 'III'): 1386495839928717332,
    ('Silver', 'IV'): 1386495841337999381,
    ('Bronze', 'I'): 1386495843359785031,
    ('Bronze', 'II'): 1386495844861214755,
    ('Bronze', 'III'): 1386495846773690419,
    ('Bronze', 'IV'): 1386495848397148191,
}

# Special Role IDs
SPECIAL_ROLES = {
    'friendly_duel_pings': 1388415078260281365,
    'official_duel_pings': 1388415102629314600,
}

# Rank Structure and Capacities
RANK_STRUCTURE = {
    'Diamond': {
        'numerals': ['I', 'II'],
        'capacities': {'I': 1, 'II': 3},
        'total_capacity': 4
    },
    'Platinum': {
        'numerals': ['I', 'II', 'III'],
        'capacities': {'I': 1, 'II': 3, 'III': 5},
        'total_capacity': 9
    },
    'Gold': {
        'numerals': ['I', 'II', 'III'],
        'capacities': {'I': 2, 'II': 6, 'III': 10},
        'total_capacity': 18
    },
    'Silver': {
        'numerals': ['I', 'II', 'III', 'IV'],
        'capacities': {'I': 2, 'II': 5, 'III': 9, 'IV': 12},
        'total_capacity': 28
    },
    'Bronze': {
        'numerals': ['I', 'II', 'III', 'IV'],
        'capacities': {'I': 3, 'II': 8, 'III': 12, 'IV': 18},
        'total_capacity': 41
    }
}

# Tier Hierarchy (for determining rank progression)
TIER_HIERARCHY = ['Bronze', 'Silver', 'Gold', 'Platinum', 'Diamond']

# Numeral Hierarchy (I is highest within each tier)
NUMERAL_HIERARCHY = {
    'Bronze': ['IV', 'III', 'II', 'I'],
    'Silver': ['IV', 'III', 'II', 'I'],
    'Gold': ['III', 'II', 'I'],
    'Platinum': ['III', 'II', 'I'],
    'Diamond': ['II', 'I']
}

# ELO Configuration
ELO_CONFIG = {
    'starting_elo': 1000,
    'k_factor_new': 32,      # For players with < 10 games
    'k_factor_established': 16,  # For players with >= 10 games
    'new_player_threshold': 10,
}

# Evaluation Ranks (only ranks evaluation can place users in)
EVALUATION_RANKS = [
    ('Bronze', 'IV'),
    ('Silver', 'IV'),
    ('Gold', 'III')
]

# Permission Levels
PERMISSION_LEVELS = {
    'everyone': 0,
    'blademasters': 1,
    'moderators': 2,
    'admins': 3,
    'owner': 4
}

# Discord Permissions Required
REQUIRED_PERMISSIONS = [
    'send_messages',
    'send_messages_in_threads',
    'embed_links',
    'add_reactions',
    'read_message_history',
    'manage_messages',
    'manage_roles',
    'view_channel',
    'create_public_threads',
    'manage_threads',
    'use_slash_commands'
]

# Embed Colors
EMBED_COLORS = {
    'success': 0x00ff00,
    'error': 0xff0000,
    'warning': 0xffff00,
    'info': 0x0099ff,
    'neutral': 0x808080,
    'duel': 0xff6b00,
    'stats': 0x9966cc,
    'rank': 0xffd700,
}

# Tier Colors (for embeds and displays)
TIER_COLORS = {
    'Diamond': 0xb9f2ff,
    'Platinum': 0xe5e4e2,
    'Gold': 0xffd700,
    'Silver': 0xc0c0c0,
    'Bronze': 0xcd7f32,
    'Evaluation': 0x808080,
    'Guest': 0x696969,
}

# Database Configuration
DATABASE_CONFIG = {
    'database_path': 'database/dueling_bot.db',
    'backup_path': 'database/backups/',
    'auto_backup': True,
    'backup_interval_hours': 24,
}

# Bot Limits and Timeouts
BOT_LIMITS = {
    'max_ticket_channels': 50,
    'challenge_timeout_minutes': 10080,
    'embed_field_limit': 25,
    'max_leaderboard_entries': 20,
    'max_duel_logs_per_page': 10,
}

CLEANUP_TIMINGS = {
    'error': 30,           # Error messages - quick cleanup  
    'confirmation': 60,    # Command confirmations
    'info': 90,           # Stats, help displays
    'admin': 120,         # Admin confirmations
    'leaderboard': 150,   # Longer viewing time
}

# Ticket Categories (for organizing ticket channels)
TICKET_CATEGORIES = {
    'friendly_duels': None,    # Set to category ID if you want to organize
    'official_duels': None,
    'bm_duels': None,
    'evaluations': None,
}

DUEL_TYPES = {
    'friendly': {
        'display_name': 'Friendly Duel',
        'emoji': '🤝',
        'description': 'Practice duel with no stakes',
        'restrictions': 'none',
        'logged': False,
        'affects_elo': False,
        'affects_rank': False,
        'ping_role': 'Friendly Duel',
        'cooldown_hours': 0,
    },
    'official': {
        'display_name': 'Official Duel',
        'emoji': '⚡',
        'description': 'Ranked duel affecting ELO ratings',
        'restrictions': 'rank-aware',
        'logged': True,
        'affects_elo': True,
        'affects_rank': False,
        'ping_role': 'Official Duel',
        'cooldown_hours': 0,
    },
    'bm': {
        'display_name': 'Blademaster Duel',
        'emoji': '👑',
        'description': 'Enhanced automatic rank progression challenges',
        'restrictions': 'rank-restricted',
        'logged': True,
        'affects_elo': True,
        'affects_rank': True,
        'ping_role': None,  # Determined automatically by system
        'cooldown_hours': 72,  # ENHANCED: Updated from 24 to 72 hours
        'auto_targeting': True,  # NEW: Auto-targeting feature flag
        'auto_ticket_creation': True,  # NEW: Auto-ticket creation flag
    }
}

# NEW: Enhanced embed colors for BM system
EMBED_COLORS.update({
    'bm_challenge': 0xFF6B00,    # Distinctive orange for BM challenges
    'bm_success': 0x00FF7F,      # Bright green for successful BM actions
    'bm_cooldown': 0xFFD700,     # Gold color for cooldown information
})

# NEW: BM admin permission configuration
BM_ADMIN_PERMISSIONS = {
    'cooldown_reset': ['Moderator', 'Admin', 'Grandmaster'],
    'subrank_config': ['Admin', 'Grandmaster'],
    'system_config': ['Grandmaster'],
    'emergency_override': ['Admin', 'Grandmaster']
}

# ENHANCED: Extended cleanup timings for BM system
CLEANUP_TIMINGS.update({
    'bm_challenge': 300,      # BM challenge embeds stay longer (5 minutes)
    'bm_admin': 180,          # Admin confirmations for BM system (3 minutes)
    'bm_notification': 120,   # BM notification messages (2 minutes)
})

# NEW: Database schema additions (to be run as migration)
BM_DATABASE_SCHEMA_ADDITIONS = """
-- Add BM system admin action logging table
CREATE TABLE IF NOT EXISTS admin_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    target_user_id INTEGER,
    action_details TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_id) REFERENCES users (discord_id),
    FOREIGN KEY (target_user_id) REFERENCES users (discord_id)
);

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_admin_actions_admin_id ON admin_actions (admin_id);
CREATE INDEX IF NOT EXISTS idx_admin_actions_timestamp ON admin_actions (timestamp);
"""

def get_rank_role_id(tier: str, numeral: str) -> int:
    """Get the Discord role ID for a specific rank"""
    return RANK_ROLES.get((tier, numeral))

def get_tier_role_id(tier: str) -> int:
    """Get the Discord role ID for a specific tier"""
    return TIER_ROLES.get(tier)

def get_next_rank(current_tier: str, current_numeral: str) -> tuple:
    """Get the next rank up from the current rank - FIXED VERSION with Unranked support"""
    
    # FIXED: Handle Guest/Evaluation users (treat as "Unranked" below Bronze IV)
    if current_tier in ['Guest', 'Evaluation']:
        return 'Bronze', 'IV'
    
    # Handle normal Blademaster ranks
    if current_tier not in TIER_HIERARCHY:
        return None, None
        
    current_tier_idx = TIER_HIERARCHY.index(current_tier)
    numerals_in_tier = NUMERAL_HIERARCHY[current_tier]
    current_numeral_idx = numerals_in_tier.index(current_numeral)
    
    # Move up within the same tier  
    if current_numeral_idx < len(numerals_in_tier) - 1:
        next_numeral = numerals_in_tier[current_numeral_idx + 1]
        return current_tier, next_numeral
    
    # At top of current tier, move to next tier
    if current_tier_idx < len(TIER_HIERARCHY) - 1:
        next_tier = TIER_HIERARCHY[current_tier_idx + 1]
        next_numeral = NUMERAL_HIERARCHY[next_tier][0]
        return next_tier, next_numeral
    
    # Already at highest rank
    return None, None

def is_rank_above(tier1: str, numeral1: str, tier2: str, numeral2: str) -> bool:
    """Check if rank1 is directly above rank2 - FIXED with Unranked support"""
    next_tier, next_numeral = get_next_rank(tier2, numeral2)
    return next_tier == tier1 and next_numeral == numeral1

def get_tier_color(tier: str) -> int:
    """Get the color associated with a tier"""
    return TIER_COLORS.get(tier, EMBED_COLORS['neutral'])

def get_bm_cooldown_hours():
    """Get current BM cooldown hours from configuration"""
    return DUEL_TYPES['bm']['cooldown_hours']

def is_bm_admin_role(role_name: str, action_type: str = 'cooldown_reset') -> bool:
    """Check if role has permission for specific BM admin action"""
    return role_name in BM_ADMIN_PERMISSIONS.get(action_type, [])

def get_bm_embed_color(message_type: str) -> int:
    """Get appropriate embed color for BM system messages"""
    bm_color_key = f'bm_{message_type}'
    return EMBED_COLORS.get(bm_color_key, EMBED_COLORS.get(message_type, EMBED_COLORS['neutral']))

# NEW: Validation function for BM cooldown
def validate_bm_cooldown(last_challenge_date: str, admin_override: bool = False) -> dict:
    """
    Validate BM challenge cooldown
    
    Args:
        last_challenge_date: ISO format date string of last challenge
        admin_override: Whether admin is overriding the cooldown
        
    Returns:
        Dict with validation result and details
    """
    if admin_override:
        return {'valid': True, 'reason': 'Admin override applied'}
    
    if not last_challenge_date:
        return {'valid': True, 'reason': 'No previous challenges'}
    
    from datetime import datetime, timedelta
    
    try:
        last_challenge = datetime.fromisoformat(last_challenge_date)
        cooldown_end = last_challenge + timedelta(hours=get_bm_cooldown_hours())
        
        if datetime.now() >= cooldown_end:
            return {'valid': True, 'reason': 'Cooldown period has expired'}
        
        remaining = cooldown_end - datetime.now()
        remaining_str = f"{remaining.days}d {remaining.seconds//3600}h {(remaining.seconds%3600)//60}m"
        
        return {
            'valid': False,
            'reason': f'BM challenge cooldown active: {remaining_str} remaining',
            'remaining_time': remaining_str,
            'cooldown_end': cooldown_end
        }
        
    except Exception as e:
        return {'valid': False, 'reason': f'Error validating cooldown: {e}'}
    
# Backward compatibility - add 'name' as alias for 'display_name'
for duel_type_key, duel_type_config in DUEL_TYPES.items():
    if 'display_name' in duel_type_config and 'name' not in duel_type_config:
        duel_type_config['name'] = duel_type_config['display_name']