from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import Notification
from .selectors import (
    get_pending_action_notifications,
    get_recent_unread_notifications,
    get_unread_count,
)
from .services import mark_notification_as_read


@login_required(login_url="/login/")
def notification_list_view(request):
    """Internal users' in-app notifications (vendors use /vendor/notifications/)."""
    if request.user.is_vendor:
        return redirect("vendor_notifications")
    qs = Notification.objects.filter(recipient=request.user).order_by("-created_at")
    if request.GET.get("filter") == "unread":
        qs = qs.filter(is_read=False)
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "notifications/notification_list.html",
        {
            "page_obj": page,
            "notifications": page.object_list,
            "unread_count": Notification.objects.filter(
                recipient=request.user, is_read=False
            ).count(),
            "only_unread": request.GET.get("filter") == "unread",
            "querystring": "filter=unread" if request.GET.get("filter") == "unread" else "",
        },
    )


@login_required(login_url="/login/")
@require_POST
def notification_open_view(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id, recipient=request.user)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read", "updated_at"])
    target = notification.target_url
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect("notification_list")


@login_required(login_url="/login/")
@require_POST
def notification_mark_all_read_view(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return redirect("notification_list")


# ---------------------------------------------------------------------------
# Procurement Executive dashboard HTMX fragments (RBAC: own rows only)
# ---------------------------------------------------------------------------


@login_required(login_url="/login/")
def proc_exec_notifications_view(request):
    """HTMX partial: top-10 recent unread notifications for the logged-in user.

    Scoped strictly to ``request.user`` (IDOR-safe). Polled by the dashboard
    via ``hx-get`` + ``hx-trigger="load, every 60s"``.
    """
    notifications = get_recent_unread_notifications(request.user, limit=10)
    return render(
        request,
        "notifications/partials/htmx_feed.html",
        {
            "notifications": notifications,
            "unread_count": get_unread_count(request.user),
        },
    )


@login_required(login_url="/login/")
def proc_exec_pending_actions_view(request):
    """HTMX partial: unread actionable items (approvals, deadlines, exceptions)."""
    pending = get_pending_action_notifications(request.user, limit=5)
    return render(
        request,
        "notifications/partials/htmx_pending_actions.html",
        {
            "pending": pending,
            "unread_count": get_unread_count(request.user),
        },
    )


@login_required(login_url="/login/")
@require_POST
def notification_mark_read_htmx_view(request, notification_id):
    """HTMX endpoint: mark one notification read, remove it from the list.

    RBAC enforced in ``mark_notification_as_read`` (recipient-only; other
    users' ids raise 404 to avoid ID enumeration). Returns an empty body so
    HTMX ``outerHTML`` swap removes the ``<li id="notif-...">`` seamlessly,
    plus an ``HX-Trigger`` so polling feeds refresh their counters.
    """
    try:
        mark_notification_as_read(user=request.user, notification_id=notification_id)
    except Notification.DoesNotExist:
        raise Http404("Notification not found.")
    remaining = get_unread_count(request.user)
    response = HttpResponse("", content_type="text/html")
    response["HX-Trigger"] = f'{{"notification-read": {{"remaining": {remaining}}}}}'
    return response
