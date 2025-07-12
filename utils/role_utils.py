"""
Role Management Utilities
Provides functions for managing Discord roles related to ranks and permissions
"""

import discord
import logging
from typing import Optional, List, Dict, Any, Tuple
from config import TIER_ROLES, RANK_ROLES, SPECIAL_ROLES

logger = logging.getLogger('BladeBot.RoleUtils')

class RoleManager:
    def __init__(self, guild: discord.Guild):
        self.guild = guild
    
    async def assign_rank_roles(self, member: discord.Member, tier: str, numeral: str,
                              remove_old_roles: bool = True) -> Tuple[bool, str]:
        """
        Assign rank and tier roles to a member
        
        Args:
            member: Discord member
            tier: Tier name (Bronze, Silver, Gold, Platinum, Diamond)
            numeral: Numeral (I, II, III, IV)
            remove_old_roles: Whether to remove old rank/tier roles
            
        Returns:
            Tuple of (success, message)
        """
        try:
            roles_to_add = []
            roles_to_remove = []
            
            # Get new tier role
            tier_role_id = TIER_ROLES.get(tier)
            if tier_role_id:
                tier_role = self.guild.get_role(tier_role_id)
                if tier_role:
                    roles_to_add.append(tier_role)
                else:
                    logger.warning(f'Tier role {tier} not found in guild (ID: {tier_role_id})')
            
            # Get new rank role
            rank_role_id = RANK_ROLES.get((tier, numeral))
            if rank_role_id:
                rank_role = self.guild.get_role(rank_role_id)
                if rank_role:
                    roles_to_add.append(rank_role)
                else:
                    logger.warning(f'Rank role {tier} {numeral} not found in guild (ID: {rank_role_id})')
            
            # Remove old roles if requested
            if remove_old_roles:
                for role in member.roles:
                    # Remove old tier roles
                    if role.id in TIER_ROLES.values() and role not in roles_to_add:
                        roles_to_remove.append(role)
                    # Remove old rank roles
                    elif role.id in RANK_ROLES.values() and role not in roles_to_add:
                        roles_to_remove.append(role)
            
            # Remove old roles first
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=f'Rank update: {tier} {numeral}')
                logger.info(f'Removed roles from {member}: {[r.name for r in roles_to_remove]}')
            
            # Add new roles
            if roles_to_add:
                await member.add_roles(*roles_to_add, reason=f'Rank assignment: {tier} {numeral}')
                logger.info(f'Added roles to {member}: {[r.name for r in roles_to_add]}')
            
            return True, f"Successfully assigned {tier} {numeral} roles"
            
        except discord.Forbidden:
            return False, "Bot lacks permission to manage roles"
        except discord.HTTPException as e:
            return False, f"Discord error: {e}"
        except Exception as e:
            logger.error(f'Error assigning roles to {member}: {e}')
            return False, f"Unexpected error: {e}"
    
    async def remove_evaluation_role(self, member: discord.Member) -> bool:
        """
        Remove evaluation role from member
        
        Args:
            member: Discord member
            
        Returns:
            True if successful
        """
        try:
            evaluation_role_id = TIER_ROLES.get('Evaluation')
            if evaluation_role_id:
                evaluation_role = self.guild.get_role(evaluation_role_id)
                if evaluation_role and evaluation_role in member.roles:
                    await member.remove_roles(evaluation_role, reason='Evaluation completed')
                    logger.info(f'Removed evaluation role from {member}')
                    return True
            return True  # Role not found or member doesn't have it
            
        except Exception as e:
            logger.error(f'Error removing evaluation role from {member}: {e}')
            return False
    
    async def assign_guest_role(self, member: discord.Member) -> bool:
        """
        Assign guest role to member
        
        Args:
            member: Discord member
            
        Returns:
            True if successful
        """
        try:
            guest_role_id = TIER_ROLES.get('Guest')
            if guest_role_id:
                guest_role = self.guild.get_role(guest_role_id)
                if guest_role and guest_role not in member.roles:
                    await member.add_roles(guest_role, reason='New member')
                    logger.info(f'Assigned guest role to {member}')
                    return True
            return True  # Role not found or member already has it
            
        except Exception as e:
            logger.error(f'Error assigning guest role to {member}: {e}')
            return False
    
    def get_member_rank_from_roles(self, member: discord.Member) -> Tuple[Optional[str], Optional[str]]:
        """
        Get member's rank from their Discord roles
        
        Args:
            member: Discord member
            
        Returns:
            Tuple of (tier, numeral) or (None, None) if not found
        """
        for role in member.roles:
            # Check rank roles first (more specific)
            for (tier, numeral), role_id in RANK_ROLES.items():
                if role.id == role_id:
                    return tier, numeral
        
        # If no rank role found, check tier roles
        for role in member.roles:
            for tier, role_id in TIER_ROLES.items():
                if role.id == role_id:
                    # Return tier with default numeral
                    if tier == 'Evaluation':
                        return 'Evaluation', 'N/A'
                    elif tier == 'Guest':
                        return 'Guest', 'N/A'
                    # For other tiers without specific rank, return None
        
        return None, None
    
    def get_member_tier_from_roles(self, member: discord.Member) -> Optional[str]:
        """
        Get member's tier from their Discord roles
        
        Args:
            member: Discord member
            
        Returns:
            Tier name or None if not found
        """
        for role in member.roles:
            for tier, role_id in TIER_ROLES.items():
                if role.id == role_id:
                    return tier
        return None
    
    def has_blademaster_role(self, member: discord.Member) -> bool:
        """
        Check if member has any Blademaster tier role
        
        Args:
            member: Discord member
            
        Returns:
            True if member is a Blademaster
        """
        blademaster_tiers = ['Bronze', 'Silver', 'Gold', 'Platinum', 'Diamond']
        member_tier = self.get_member_tier_from_roles(member)
        return member_tier in blademaster_tiers
    
    def has_admin_role(self, member: discord.Member) -> bool:
        """
        Check if member has admin permissions
        
        Args:
            member: Discord member
            
        Returns:
            True if member has admin permissions
        """
        return member.guild_permissions.administrator or any(
            role.name.lower() in ['admin', 'administrator', 'owner']
            for role in member.roles
        )
    
    def has_moderator_role(self, member: discord.Member) -> bool:
        """
        Check if member has moderator permissions
        
        Args:
            member: Discord member
            
        Returns:
            True if member has moderator permissions
        """
        return (
            member.guild_permissions.manage_messages or
            member.guild_permissions.kick_members or
            any(role.name.lower() in ['mod', 'moderator', 'staff'] for role in member.roles)
        )
    
    def get_permission_level(self, member: discord.Member) -> int:
        """
        Get numeric permission level for member
        
        Args:
            member: Discord member
            
        Returns:
            Permission level (0=everyone, 1=blademasters, 2=moderators, 3=admins, 4=owner)
        """
        if member.id == self.guild.owner_id:
            return 4  # Owner
        elif self.has_admin_role(member):
            return 3  # Admin
        elif self.has_moderator_role(member):
            return 2  # Moderator
        elif self.has_blademaster_role(member):
            return 1  # Blademaster
        else:
            return 0  # Everyone
    
    async def sync_user_roles_with_database(self, member: discord.Member, user_data: Dict[str, Any]) -> bool:
        """
        Sync member's Discord roles with database rank information
        
        Args:
            member: Discord member
            user_data: User data from database
            
        Returns:
            True if successful
        """
        db_tier = user_data.get('tier')
        db_numeral = user_data.get('rank_numeral')
        
        if not db_tier:
            return False
        
        # Special handling for Evaluation and Guest
        if db_tier in ['Evaluation', 'Guest']:
            role_id = TIER_ROLES.get(db_tier)
            if role_id:
                role = self.guild.get_role(role_id)
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role, reason='Database sync')
                        return True
                    except Exception as e:
                        logger.error(f'Error syncing {db_tier} role for {member}: {e}')
                        return False
            return True
        
        # For Blademaster ranks
        if db_numeral:
            success, message = await self.assign_rank_roles(member, db_tier, db_numeral)
            if not success:
                logger.warning(f'Failed to sync roles for {member}: {message}')
            return success
        
        return False
    
    def get_role_hierarchy_position(self, role: discord.Role) -> int:
        """
        Get role's position in hierarchy for rank roles
        
        Args:
            role: Discord role
            
        Returns:
            Hierarchy position (higher number = higher rank)
        """
        # Check if it's a rank role
        for (tier, numeral), role_id in RANK_ROLES.items():
            if role.id == role_id:
                tier_value = ['Bronze', 'Silver', 'Gold', 'Platinum', 'Diamond'].index(tier)
                numeral_value = ['IV', 'III', 'II', 'I'].index(numeral)
                return tier_value * 10 + numeral_value
        
        # Check if it's a tier role
        for tier, role_id in TIER_ROLES.items():
            if role.id == role_id:
                if tier in ['Bronze', 'Silver', 'Gold', 'Platinum', 'Diamond']:
                    return ['Bronze', 'Silver', 'Gold', 'Platinum', 'Diamond'].index(tier) * 10
                elif tier == 'Evaluation':
                    return -1
                elif tier == 'Guest':
                    return -2
        
        return 0  # Unknown role
    
    async def cleanup_orphaned_roles(self, member: discord.Member) -> int:
        """
        Remove orphaned rank/tier roles from member
        
        Args:
            member: Discord member
            
        Returns:
            Number of roles removed
        """
        removed_count = 0
        roles_to_remove = []
        
        # Find multiple tier roles (should only have one)
        tier_roles = [role for role in member.roles if role.id in TIER_ROLES.values()]
        if len(tier_roles) > 1:
            # Keep highest tier role, remove others
            highest_tier_role = max(tier_roles, key=self.get_role_hierarchy_position)
            roles_to_remove.extend([role for role in tier_roles if role != highest_tier_role])
        
        # Find multiple rank roles (should only have one)
        rank_roles = [role for role in member.roles if role.id in RANK_ROLES.values()]
        if len(rank_roles) > 1:
            # Keep highest rank role, remove others
            highest_rank_role = max(rank_roles, key=self.get_role_hierarchy_position)
            roles_to_remove.extend([role for role in rank_roles if role != highest_rank_role])
        
        # Remove orphaned roles
        if roles_to_remove:
            try:
                await member.remove_roles(*roles_to_remove, reason='Cleanup orphaned roles')
                removed_count = len(roles_to_remove)
                logger.info(f'Removed {removed_count} orphaned roles from {member}')
            except Exception as e:
                logger.error(f'Error removing orphaned roles from {member}: {e}')
        
        return removed_count
    
    def validate_role_configuration(self) -> List[str]:
        """
        Validate that all configured roles exist in the guild
        
        Returns:
            List of missing role configurations
        """
        missing_roles = []
        
        # Check tier roles
        for tier, role_id in TIER_ROLES.items():
            if not self.guild.get_role(role_id):
                missing_roles.append(f"Tier role '{tier}' (ID: {role_id})")
        
        # Check rank roles
        for (tier, numeral), role_id in RANK_ROLES.items():
            if not self.guild.get_role(role_id):
                missing_roles.append(f"Rank role '{tier} {numeral}' (ID: {role_id})")
        
        # Check special roles
        for role_name, role_id in SPECIAL_ROLES.items():
            if not self.guild.get_role(role_id):
                missing_roles.append(f"Special role '{role_name}' (ID: {role_id})")
        
        return missing_roles