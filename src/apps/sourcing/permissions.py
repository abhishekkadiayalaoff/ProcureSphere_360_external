"""
Sourcing RBAC (docs/rbac_matrix.md "Sourcing Events (RFQ/RFP)" and "Vendor Sealed Bids").

- PROC_EXEC / PROC_MGR: create, edit drafts, invite, publish, evaluate, negotiate, recommend.
- PROC_MGR: approve / reject award recommendations (PRD 3.2: "sourcing approval").
- FINANCE_AP, LEGAL_MGR, AUDITOR: read event headers; bids only for AUDITOR (post-close).
- VENDOR_USER: never uses the internal views; bid portal is under /vendor/ (invitation-scoped).
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import Role

EVENT_READ_ROLES = {
    Role.SUPER_ADMIN,
    Role.PROC_EXEC,
    Role.PROC_MGR,
    Role.FINANCE_AP,
    Role.LEGAL_MGR,
    Role.AUDITOR,
}
EVENT_MANAGE_ROLES = {Role.SUPER_ADMIN, Role.PROC_EXEC, Role.PROC_MGR}
AWARD_APPROVE_ROLES = {Role.SUPER_ADMIN, Role.PROC_MGR}
BID_READ_ROLES = {Role.SUPER_ADMIN, Role.PROC_EXEC, Role.PROC_MGR, Role.AUDITOR}


def _role(user):
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return Role.SUPER_ADMIN
    return user.role_code


def can_view_events(user) -> bool:
    return _role(user) in EVENT_READ_ROLES


def can_manage_events(user) -> bool:
    return _role(user) in EVENT_MANAGE_ROLES


def can_approve_award(user) -> bool:
    return _role(user) in AWARD_APPROVE_ROLES


def can_read_bids(user) -> bool:
    return _role(user) in BID_READ_ROLES


def sourcing_capabilities(user) -> dict:
    return {
        "can_view": can_view_events(user),
        "can_manage": can_manage_events(user),
        "can_approve_award": can_approve_award(user),
        "can_read_bids": can_read_bids(user),
    }


class SourcingEventPermission(BasePermission):
    """Internal users by role; vendor users get read access scoped to invitations."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_vendor:
            return request.method in SAFE_METHODS
        if request.method in SAFE_METHODS:
            return can_view_events(user)
        return can_manage_events(user)


class AwardApprovalPermission(BasePermission):
    def has_permission(self, request, view):
        return can_approve_award(request.user)


class BidPermission(BasePermission):
    """
    Bids are read-only over the internal API (vendors create/amend/withdraw via explicit
    actions that go through the bidding services).
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_vendor:
            return True
        return can_read_bids(user) and request.method in SAFE_METHODS
