"""Read/query logic for notifications.

All querysets are scoped by recipient (IDOR protection): callers must pass
the authenticated user; no function ever returns another user's rows.
"""

from __future__ import annotations

from typing import Iterable

from .models import Notification

# Notification types that require an action (drive the "Pending Actions" widget).
ACTIONABLE_TYPES = [
    Notification.TYPE_APPROVAL_REQUIRED,
    Notification.TYPE_BID_DEADLINE,
    Notification.TYPE_EXCEPTION_RAISED,
    Notification.TYPE_CONTRACT_EXPIRATION,
    Notification.TYPE_CONTRACT_MILESTONE,
    Notification.TYPE_CONTRACT_OBLIGATION,
    Notification.TYPE_RFQ_INVITATION,
    Notification.TYPE_CLARIFICATION_RESPONSE,
    Notification.TYPE_KYC_REQUEST,
]


def get_recent_unread_notifications(user, limit: int = 10) -> Iterable[Notification]:
    """Top-N most recent unread notifications for ``user`` (newest first)."""
    return list(
        Notification.objects.filter(recipient=user, is_read=False)
        .select_related("recipient")
        .order_by("-created_at")[:limit]
    )


def get_pending_action_notifications(user, limit: int = 5) -> Iterable[Notification]:
    """Unread actionable notifications (approvals, deadlines, exceptions)."""
    return list(
        Notification.objects.filter(
            recipient=user, is_read=False, notification_type__in=ACTIONABLE_TYPES
        )
        .select_related("recipient")
        .order_by("-created_at")[:limit]
    )


def get_unread_count(user) -> int:
    """Count of unread notifications for ``user`` (badge counter)."""
    return Notification.objects.filter(recipient=user, is_read=False).count()
