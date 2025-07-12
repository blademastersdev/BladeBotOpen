"""
Commands Package
Discord bot commands organized by functionality
"""

from .public_commands import setup_public_commands
from .duel_commands import setup_duel_commands
from .admin_commands import setup_admin_commands
from .utility_commands import setup_utility_commands

__all__ = [
    'setup_public_commands',
    'setup_duel_commands',
    'setup_admin_commands',
    'setup_utility_commands'
]