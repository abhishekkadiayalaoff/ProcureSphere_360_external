from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from apps.accounts.models import Role


def _enforce_manager_access(request):
    """
    Enforces that the current authenticated user has Procurement Manager or Super Admin role.
    Raises PermissionDenied (HTTP 403) for any other authenticated role.
    """
    user = request.user
    role_code = getattr(user, "role_code", None) or (
        user.role.code if getattr(user, "role", None) else None
    )
    if not (
        user.is_superuser
        or role_code in [Role.PROC_MGR, Role.SUPER_ADMIN, "PROC_MGR", "SUPER_ADMIN"]
    ):
        raise PermissionDenied("Access restricted to Procurement Manager role.")


def _get_manager_context(request):
    """
    Extracts the authoritative organization/scope name from the authenticated user.
    """
    user = request.user
    org = getattr(user, "effective_organization", None) or getattr(user, "organization", None)
    if not org and getattr(user, "department_id", None) and getattr(user.department, "organization_id", None):
        org = user.department.organization
    user_org_name = org.name if org else ("Global Enterprise" if user.is_superuser else "")
    return {
        "user_org_name": user_org_name,
    }


@login_required(login_url="/login/")
def manager_dashboard_view(request):
    """
    GET /manager/
    Procurement Manager Executive Dashboard.
    """
    _enforce_manager_access(request)
    context = _get_manager_context(request)
    return render(request, "manager/dashboard.html", context)


@login_required(login_url="/login/")
def manager_pipeline_view(request):
    """
    GET /manager/pipeline/
    Procurement Pipeline Funnel Conversion View.
    """
    _enforce_manager_access(request)
    context = _get_manager_context(request)
    return render(request, "manager/pipeline.html", context)


@login_required(login_url="/login/")
def manager_pr_aging_view(request):
    """
    GET /manager/pr-aging/
    Requisition Aging and Bottlenecks Analysis.
    """
    _enforce_manager_access(request)
    context = _get_manager_context(request)
    return render(request, "manager/pr_aging.html", context)


@login_required(login_url="/login/")
def manager_sourcing_view(request):
    """
    GET /manager/sourcing/
    Sourcing Events & RFQ/RFP Directory.
    """
    _enforce_manager_access(request)
    context = _get_manager_context(request)
    return render(request, "manager/sourcing.html", context)


@login_required(login_url="/login/")
def manager_approvals_view(request):
    """
    GET /manager/approvals/
    Procurement Manager Pending Approvals Governance Desk.
    """
    _enforce_manager_access(request)
    context = _get_manager_context(request)
    return render(request, "manager/approvals.html", context)


@login_required(login_url="/login/")
def manager_awards_view(request):
    """
    GET /manager/awards/
    Pending Award Approvals Desk.
    """
    _enforce_manager_access(request)
    context = _get_manager_context(request)
    return render(request, "manager/awards.html", context)


@login_required(login_url="/login/")
def manager_purchase_orders_view(request):
    """
    GET /manager/purchase-orders/
    Purchase Orders & Commitments Directory.
    """
    _enforce_manager_access(request)
    context = _get_manager_context(request)
    return render(request, "manager/purchase_orders.html", context)


@login_required(login_url="/login/")
def manager_vendor_risk_view(request):
    """
    GET /manager/vendor-risk/
    Vendor Risk & Governance Desk.
    """
    _enforce_manager_access(request)
    context = _get_manager_context(request)
    return render(request, "manager/vendor_risk.html", context)


@login_required(login_url="/login/")
def manager_vendor_suspension_view(request):
    """
    GET /manager/vendor-risk/suspension/
    Dedicated Vendor Suspension & Governance Action Desk.
    """
    _enforce_manager_access(request)
    context = _get_manager_context(request)
    context["target_vendor_id"] = request.GET.get("vendor_id", "").strip()
    context["initial_action"] = request.GET.get("action", "").strip()
    return render(request, "manager/vendor_suspension.html", context)


@login_required(login_url="/login/")
def manager_spend_view(request):
    """
    GET /manager/spend/
    Spend Analysis & Budget Control.
    """
    _enforce_manager_access(request)
    context = _get_manager_context(request)
    return render(request, "manager/spend.html", context)


@login_required(login_url="/login/")
def manager_performance_view(request):
    """
    GET /manager/performance/
    Supplier Performance & Scorecards.
    """
    _enforce_manager_access(request)
    context = _get_manager_context(request)
    return render(request, "manager/performance.html", context)


@login_required(login_url="/login/")
def manager_notifications_view(request):
    """
    GET /manager/notifications/
    Notifications & Action Escalations.
    """
    _enforce_manager_access(request)
    context = _get_manager_context(request)
    return render(request, "manager/notifications.html", context)
