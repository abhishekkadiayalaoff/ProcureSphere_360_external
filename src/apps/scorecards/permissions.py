"""Supplier scorecard RBAC (docs/rbac_matrix.md "Supplier Scorecards")."""

from apps.accounts.models import Role

SCORECARD_READ_ROLES = {
    Role.SUPER_ADMIN,
    Role.PROC_EXEC,
    Role.PROC_MGR,
    Role.FINANCE_AP,
    Role.STORES_RECEIVER,
    Role.LEGAL_MGR,
    Role.AUDITOR,
}
SCORECARD_CALCULATE_ROLES = {Role.SUPER_ADMIN, Role.PROC_EXEC, Role.PROC_MGR}


def _role(user):
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return Role.SUPER_ADMIN
    return user.role_code


def can_view_scorecards(user) -> bool:
    return _role(user) in SCORECARD_READ_ROLES


def can_calculate_scorecards(user) -> bool:
    return _role(user) in SCORECARD_CALCULATE_ROLES
