from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import Role


class IsAuditorOrSuperAdmin(BasePermission):
    """
    Grants access exclusively to Compliance Auditor or Super Admin users.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        role_code = getattr(request.user, "role_code", None) or (
            request.user.role.code if getattr(request.user, "role", None) else None
        )
        return role_code in [Role.AUDITOR, Role.SUPER_ADMIN]


class AuditorReadOnlyPermission(BasePermission):
    """
    Enforces strict read-only access (GET, HEAD, OPTIONS) for Auditor roles.
    Prevents any state mutations, guaranteeing immutable audit integrity.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        role_code = getattr(request.user, "role_code", None) or (
            request.user.role.code if getattr(request.user, "role", None) else None
        )
        if role_code == Role.SUPER_ADMIN:
            return True
        if role_code == Role.AUDITOR:
            return request.method in SAFE_METHODS
        return True
