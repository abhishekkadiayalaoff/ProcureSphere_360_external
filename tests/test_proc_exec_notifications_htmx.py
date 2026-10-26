"""Notification & Escalation HTMX module (Procurement Executive dashboard).

Verifies the DB-backed feed behind ``proc_exec.html`` /
``procurement_dashboard.html``: service-layer top-10 fetch, recipient-scoped
HTMX feed + pending-actions fragments, mark-as-read mutation with RBAC
(positive and negative), and sealed visibility (no cross-user leakage).
"""

import pytest

from apps.accounts.models import Role
from apps.notifications.models import Notification
from apps.notifications.selectors import (
    get_pending_action_notifications,
    get_recent_unread_notifications,
    get_unread_count,
)
from apps.notifications.services import (
    get_top_unread_for_user,
    mark_notification_as_read,
    notify_users,
)

pytestmark = [pytest.mark.django_db, pytest.mark.regression]


@pytest.fixture(autouse=True)
def _fast_password_hashes(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def _make_notification(recipient, ntype=Notification.TYPE_BID_DEADLINE, title="Bid closing"):
    return Notification.objects.create(
        recipient=recipient,
        notification_type=ntype,
        title=title,
        message="Bid window closes soon",
        target_url="/sourcing-events/",
    )


# --- service / selector layer ------------------------------------------------


def test_service_returns_top10_newest_unread(procurement_world):
    user = procurement_world["exec"]
    for i in range(12):
        _make_notification(user, title=f"N-{i:02d}")
    top = get_top_unread_for_user(user=user, limit=10)
    assert len(top) == 10
    titles = [n.title for n in top]
    assert titles == sorted(titles, reverse=True)  # newest first
    assert "N-00" not in titles and "N-01" not in titles  # oldest excluded


def test_read_notifications_excluded_from_feed(procurement_world):
    user = procurement_world["exec"]
    n = _make_notification(user)
    mark_notification_as_read(user=user, notification_id=n.id)
    assert get_recent_unread_notifications(user) == []
    assert get_unread_count(user) == 0


def test_pending_actions_only_actionable_types(procurement_world):
    user = procurement_world["exec"]
    _make_notification(user, ntype=Notification.TYPE_BID_SUBMITTED, title="FYI only")
    _make_notification(user, ntype=Notification.TYPE_BID_DEADLINE, title="Deadline")
    pending = get_pending_action_notifications(user)
    assert [n.title for n in pending] == ["Deadline"]


def test_notify_users_helper_persists_to_db(procurement_world):
    user = procurement_world["exec"]
    created = notify_users(
        users=[user],
        notification_type=Notification.TYPE_APPROVAL_REQUIRED,
        title="Approval needed",
        message="Please review",
        target_url="/approvals/inbox/",
    )
    assert len(created) == 1
    assert Notification.objects.filter(recipient=user).count() == 1


# --- HTMX views: positive RBAC -----------------------------------------------


def test_feed_returns_partial_with_own_notifications(client, procurement_world):
    user = procurement_world["exec"]
    _make_notification(user, title="Bid closing soon")
    client.force_login(user)
    resp = client.get("/notifications/htmx/feed/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Bid closing soon" in html
    assert "hx-post" in html  # mark-as-read buttons present
    assert "<html" not in html.lower()  # partial, not a full page


def test_pending_actions_fragment_renders(client, procurement_world):
    user = procurement_world["exec"]
    _make_notification(user, ntype=Notification.TYPE_APPROVAL_REQUIRED, title="Approve PR")
    client.force_login(user)
    resp = client.get("/notifications/htmx/pending-actions/")
    assert resp.status_code == 200
    assert "Approve PR" in resp.content.decode()


def test_mark_read_post_updates_db_and_returns_empty_fragment(client, procurement_world):
    user = procurement_world["exec"]
    n = _make_notification(user)
    client.force_login(user)
    resp = client.post(f"/notifications/htmx/{n.id}/mark-read/")
    assert resp.status_code == 200
    assert resp["HX-Trigger"]  # polling widgets refresh
    n.refresh_from_db()
    assert n.is_read is True
    # item disappears from the next feed poll
    resp2 = client.get("/notifications/htmx/feed/")
    assert "caught up" in resp2.content.decode().lower()


def test_proc_exec_dashboard_shell_contains_htmx_widgets(client, procurement_world):
    client.force_login(procurement_world["exec"])
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'hx-get="/notifications/htmx/feed/"' in html
    assert 'hx-trigger="load, every 60s' in html


# --- HTMX views: negative RBAC -----------------------------------------------


def test_anonymous_feed_redirects_to_login(client, procurement_world):
    resp = client.get("/notifications/htmx/feed/")
    assert resp.status_code == 302
    assert "/login/" in resp["Location"]


def test_user_cannot_read_another_users_notification(client, procurement_world):
    victim = procurement_world["exec"]
    attacker = procurement_world["exec2"]
    n = _make_notification(victim, title="Victim secret")
    client.force_login(attacker)
    # attacker's feed must not leak the victim's row
    resp = client.get("/notifications/htmx/feed/")
    assert resp.status_code == 200
    assert "Victim secret" not in resp.content.decode()
    # direct mark-read on someone else's id → 404 (no ID enumeration)
    resp = client.post(f"/notifications/htmx/{n.id}/mark-read/")
    assert resp.status_code == 404
    n.refresh_from_db()
    assert n.is_read is False


def test_requester_cannot_mutate_exec_notification(client, procurement_world):
    n = _make_notification(procurement_world["exec"])
    client.force_login(procurement_world["requester"])
    resp = client.post(f"/notifications/htmx/{n.id}/mark-read/")
    assert resp.status_code == 404


def test_mark_read_requires_post(client, procurement_world):
    user = procurement_world["exec"]
    n = _make_notification(user)
    client.force_login(user)
    resp = client.get(f"/notifications/htmx/{n.id}/mark-read/")
    assert resp.status_code == 405
    n.refresh_from_db()
    assert n.is_read is False


def test_role_dashboard_matrix_smoke(client, procurement_world):
    """Every internal role's home page still renders (no URL/template breakage)."""
    for key in ["exec", "requester", "finance", "auditor", "stores"]:
        client.force_login(procurement_world[key])
        assert client.get("/").status_code == 200, key
    assert Role.objects.count() >= 10
