from django.urls import path

from .views import (
    notification_list_view,
    notification_mark_all_read_view,
    notification_mark_read_htmx_view,
    notification_open_view,
    proc_exec_notifications_view,
    proc_exec_pending_actions_view,
)

urlpatterns = [
    # Procurement Executive dashboard HTMX fragments (polled feed + mark-read)
    path(
        "notifications/htmx/feed/",
        proc_exec_notifications_view,
        name="proc_exec_notifications_feed",
    ),
    path(
        "notifications/htmx/pending-actions/",
        proc_exec_pending_actions_view,
        name="proc_exec_pending_actions",
    ),
    path(
        "notifications/htmx/<uuid:notification_id>/mark-read/",
        notification_mark_read_htmx_view,
        name="notification_mark_read_htmx",
    ),
    path("notifications/", notification_list_view, name="notification_list"),
    path(
        "notifications/<uuid:notification_id>/open/",
        notification_open_view,
        name="notification_open",
    ),
    path(
        "notifications/mark-all-read/",
        notification_mark_all_read_view,
        name="notification_mark_all_read",
    ),
]
