from __future__ import annotations

from typing import Optional, Set, FrozenSet, Dict

# Role definitions
class Role:
    ANALYST = "analyst"
    ADMIN = "admin"

    # All available roles
    ALL: FrozenSet[str] = frozenset({"analyst", "admin"})

    # Permissions per role
    PERMISSIONS: Dict[str, Set[str]] = {
        "analyst": {
            # Case management
            "cases:view",
            "cases:update_status",
            "cases:assign",
            "cases:add_evidence",
            "cases:run_investigation",
            "cases:submit_feedback",
            "cases:view_results",
            # Evidence management
            "evidence:view",
            "evidence:add",
            # Feedback
            "feedback:submit",
            # Investigation
            "investigation:run",
        },
        "admin": {
            # All analyst permissions
            "cases:view",
            "cases:update_status",
            "cases:assign",
            "cases:add_evidence",
            "cases:run_investigation",
            "cases:submit_feedback",
            "cases:view_results",
            "evidence:view",
            "evidence:add",
            "feedback:submit",
            "investigation:run",
            # Rule management
            "rules:manage",
            # Administrative operations
            "admin:operations",
            # User management
            "users:manage",
            # System configuration
            "config:manage",
        }
    }

    # Role hierarchy (ADMIN inherits all analyst permissions)
    HIERARCHY: FrozenSet[str] = frozenset({"admin"})

    @classmethod
    def has_permission(cls, role: str, permission: str) -> bool:
        """Check if a role has a specific permission."""
        if role not in Role.ALL:
            return False
        return permission in Role.PERMISSIONS.get(role, set())

    @classmethod
    def role_has_permission(cls, user_role: str, permission: str) -> bool:
        """Check if a user with the given role has a permission."""
        # ADMIN has all permissions
        if user_role == Role.ADMIN:
            return True
        return cls.has_permission(user_role, permission)

    @classmethod
    def user_can(cls, user_role: str, permission: str) -> bool:
        """Check if a user can perform an action (alias for role_has_permission)."""
        return cls.role_has_permission(user_role, permission)