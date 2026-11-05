from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.models import Avg, Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from redis import Redis
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.accounts.models import Role, User
from apps.orders.models import PurchaseOrder
from apps.requisitions.models import PurchaseRequisition
from apps.scorecards.models import VendorScorecard
from apps.sourcing.models import Clarification, SourcingEvent
from apps.vendors.models import Vendor


def health_check_view(request):
    """
    Health check endpoint returning DB and Redis status.
    """
    health_status = {
        "status": "healthy",
        "service": "ProcureSphere 360",
        "database": "unknown",
        "redis": "unknown",
    }

    # Check Database connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            health_status["database"] = "ok"
    except Exception as e:
        health_status["database"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    # Check Redis connection
    try:
        redis_client = Redis.from_url(settings.REDIS_URL, socket_timeout=2)
        if redis_client.ping():
            health_status["redis"] = "ok"
    except Exception as e:
        health_status["redis"] = f"offline (local mode): {str(e)}"

    http_status = 200 if health_status["status"] == "healthy" else 503
    return JsonResponse(health_status, status=http_status)


class HealthAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return health_check_view(request)


def get_dashboard_url_for_user(user):
    """
    Returns the canonical URL slug for the user's role-specific dashboard.
    """
    if not user or not user.is_authenticated:
        return "/login/"

    role_code = getattr(user, "role_code", None) or (
        user.role.code if hasattr(user, "role") and user.role else None
    )

    # Platform Admin (Django Admin superuser with no organization) -> /admin/
    if user.is_superuser and not getattr(user, "organization_id", None):
        return "/admin/"

    role_url_map = {
        Role.SUPER_ADMIN: "/superadmin/",
        Role.REQUESTER: "/requester/",
        Role.DEPT_APPROVER: "/approver/",
        Role.PROC_EXEC: "/procurement/",
        Role.PROC_MGR: "/manager/",
        Role.FINANCE_AP: "/finance/",
        Role.STORES_RECEIVER: "/stores/",
        Role.LEGAL_MGR: "/legal/",
        Role.AUDITOR: "/audit/dashboard/",
        Role.VENDOR_USER: "/vendor/",
    }
    return role_url_map.get(role_code, "/requester/")


@login_required(login_url="/login/")
def dashboard_redirect_view(request):
    """
    GET /dashboard/
    Redirects authenticated user to their role's canonical dashboard slug.
    """
    return redirect(get_dashboard_url_for_user(request.user))


@login_required(login_url="/login/")
def requester_dashboard_view(request):
    user = request.user
    my_prs = PurchaseRequisition.objects.filter(requester=user).prefetch_related(
        "purchase_orders", "sourcing_events"
    )
    context = {
        "metrics": {
            "total_my_prs": my_prs.count(),
            "pending_prs": my_prs.filter(
                status__in=["SUBMITTED", "MANAGER_REVIEW", "BUDGET_REVIEW"]
            ).count(),
            "approved_prs": my_prs.filter(status="APPROVED").count(),
        },
        "my_recent_prs": my_prs.order_by("-created_at")[:10],
    }
    return render(request, "pages/dashboards/requester_dashboard.html", context)


@login_required(login_url="/login/")
def manager_dashboard_view(request):
    from apps.core.manager_views import manager_dashboard_view as mgr_view

    return mgr_view(request)


@login_required(login_url="/login/")
def stores_dashboard_view(request):
    user = request.user
    from apps.receipts.views import get_stores_dashboard_data

    data = get_stores_dashboard_data(user)
    return render(
        request,
        "pages/dashboards/stores_dashboard.html",
        {
            "metrics": data["metrics"],
            "recent_grns": data["recent_grns"],
            "pending_deliveries": data.get("pending_deliveries", []),
            "pending_inspections": data.get("pending_inspections", []),
            "pending_handoffs": data.get("pending_handoffs", []),
            "pending_rejections": data.get("pending_rejections", []),
        },
    )


@login_required(login_url="/login/")
def vendor_dashboard_view(request):
    from apps.vendors.vendor_dashboard_views import vendor_dashboard_overview_view

    return vendor_dashboard_overview_view(request)


@login_required(login_url="/login/")
def finance_dashboard_view(request):
    from apps.budgets.models import SpendLedger
    from apps.invoices.models import MatchException, SupplierInvoice
    from apps.notifications.models import Notification
    from apps.organization.models import CostCenter, Department

    selected_dept_id = request.GET.get("dept") or ""
    selected_cc_id = request.GET.get("cost_center") or ""

    scoped_org = getattr(request.user, "effective_organization", None) if not (request.user.is_superuser and not request.user.organization_id) else None

    departments = Department.objects.all().order_by("name")
    cost_centers = CostCenter.objects.select_related("department").all().order_by("code")

    open_match_exceptions = (
        MatchException.objects.filter(status=MatchException.STATUS_OPEN)
        .select_related(
            "invoice__vendor",
            "invoice__po__requisition__department",
            "invoice__po__requisition__cost_center",
        )
        .order_by("-created_at")
    )
    open_budget_exceptions = (
        PurchaseRequisition.objects.filter(status=PurchaseRequisition.STATUS_BUDGET_REVIEW)
        .select_related("department", "cost_center", "requester")
        .order_by("-updated_at")
    )
    from apps.approvals.models import ApprovalAction
    user_approved_pr_ids = ApprovalAction.objects.filter(
        actor=request.user,
        target_model_name="PurchaseRequisition",
        action=ApprovalAction.ACTION_APPROVE,
    ).values_list("target_object_id", flat=True)

    pending_finance_prs = (
        PurchaseRequisition.objects.filter(
            status__in=[
                PurchaseRequisition.STATUS_MANAGER_REVIEW,
                PurchaseRequisition.STATUS_SUBMITTED,
            ]
        )
        .exclude(id__in=user_approved_pr_ids)
        .select_related("department", "cost_center", "requester")
        .order_by("-updated_at")
    )

    ready_for_payment_qs = SupplierInvoice.objects.filter(
        status=SupplierInvoice.STATUS_READY_FOR_PAYMENT
    )
    committed_spend_qs = SpendLedger.objects.filter(entry_type=SpendLedger.ENTRY_COMMITMENT)
    actual_spend_qs = SpendLedger.objects.filter(entry_type=SpendLedger.ENTRY_ACTUAL)

    if scoped_org:
        departments = departments.filter(organization=scoped_org)
        cost_centers = cost_centers.filter(department__organization=scoped_org)
        open_match_exceptions = open_match_exceptions.filter(
            Q(invoice__po__cost_center__department__organization=scoped_org)
            | Q(invoice__po__requisition__department__organization=scoped_org)
            | Q(invoice__vendor__organization=scoped_org)
        ).distinct()
        open_budget_exceptions = open_budget_exceptions.filter(
            Q(department__organization=scoped_org)
            | Q(cost_center__department__organization=scoped_org)
        ).distinct()
        pending_finance_prs = pending_finance_prs.filter(
            Q(department__organization=scoped_org)
            | Q(cost_center__department__organization=scoped_org)
        ).distinct()
        ready_for_payment_qs = ready_for_payment_qs.filter(
            Q(po__cost_center__department__organization=scoped_org)
            | Q(po__requisition__department__organization=scoped_org)
            | Q(vendor__organization=scoped_org)
        ).distinct()
        committed_spend_qs = committed_spend_qs.filter(
            budget__cost_center__department__organization=scoped_org
        )
        actual_spend_qs = actual_spend_qs.filter(
            budget__cost_center__department__organization=scoped_org
        )

    all_cost_centers = list(cost_centers)
    if selected_dept_id:
        filtered_cost_centers = [cc for cc in all_cost_centers if str(cc.department_id) == str(selected_dept_id)]
    else:
        filtered_cost_centers = all_cost_centers

    if selected_dept_id:
        open_budget_exceptions = open_budget_exceptions.filter(department_id=selected_dept_id)
        pending_finance_prs = pending_finance_prs.filter(department_id=selected_dept_id)
        open_match_exceptions = open_match_exceptions.filter(
            invoice__po__requisition__department_id=selected_dept_id
        )
        ready_for_payment_qs = ready_for_payment_qs.filter(
            po__requisition__department_id=selected_dept_id
        )
        committed_spend_qs = committed_spend_qs.filter(
            budget__cost_center__department_id=selected_dept_id
        )
        actual_spend_qs = actual_spend_qs.filter(
            budget__cost_center__department_id=selected_dept_id
        )

    if selected_cc_id:
        open_budget_exceptions = open_budget_exceptions.filter(cost_center_id=selected_cc_id)
        pending_finance_prs = pending_finance_prs.filter(cost_center_id=selected_cc_id)
        open_match_exceptions = open_match_exceptions.filter(
            invoice__po__requisition__cost_center_id=selected_cc_id
        )
        ready_for_payment_qs = ready_for_payment_qs.filter(
            po__requisition__cost_center_id=selected_cc_id
        )
        committed_spend_qs = committed_spend_qs.filter(
            budget__cost_center_id=selected_cc_id
        )
        actual_spend_qs = actual_spend_qs.filter(
            budget__cost_center_id=selected_cc_id
        )

    committed_spend = (
        committed_spend_qs.aggregate(total=Sum("amount"))["total"] or 0
    )
    actual_spend = (
        actual_spend_qs.aggregate(total=Sum("amount"))["total"] or 0
    )

    selected_dept_obj = None
    if selected_dept_id:
        selected_dept_obj = next((d for d in departments if str(d.id) == str(selected_dept_id)), None)

    selected_cc_obj = None
    if selected_cc_id:
        selected_cc_obj = next((c for c in all_cost_centers if str(c.id) == str(selected_cc_id)), None)

    user_org_name = scoped_org.name if scoped_org else ("Global Enterprise" if request.user.is_superuser else "")

    context = {
        "metrics": {
            "pending_match_exceptions": open_match_exceptions.count(),
            "pending_budget_exceptions": open_budget_exceptions.count(),
            "pending_pr_approvals": pending_finance_prs.count(),
            "ready_for_payment": ready_for_payment_qs.count(),
            "committed_spend": float(committed_spend),
            "actual_spend": float(actual_spend),
        },
        "open_match_exceptions": open_match_exceptions[:10],
        "open_budget_exceptions": open_budget_exceptions[:10],
        "pending_finance_prs": pending_finance_prs[:10],
        "departments": departments,
        "cost_centers": filtered_cost_centers,
        "all_cost_centers": all_cost_centers,
        "selected_dept_id": selected_dept_id,
        "selected_cc_id": selected_cc_id,
        "selected_dept_obj": selected_dept_obj,
        "selected_cc_obj": selected_cc_obj,
        "user_org_name": user_org_name,
        "unread_notifications_count": Notification.objects.filter(recipient=request.user, is_read=False).count(),
    }
    return render(request, "pages/dashboards/finance_dashboard.html", context)


@login_required(login_url="/login/")
def procurement_dashboard_view(request):
    user = request.user
    from apps.notifications.models import Notification
    from apps.sourcing.selectors import get_sourcing_dashboard_metrics
    from apps.sourcing.services import sync_all_event_windows
    from apps.vendors.selectors import get_governance_metrics, get_governance_vendor_queryset

    sync_all_event_windows()
    now = timezone.now()
    _proc_org = getattr(user, "effective_organization", None)
    _event_org_filter = (
        Q(requisition__department__organization=_proc_org)
        | Q(requisition__isnull=True, created_by__organization=_proc_org)
    ) if _proc_org and not getattr(user, "is_superuser", False) else Q()
    closing_soon = (
        SourcingEvent.objects.filter(
            _event_org_filter,
            status=SourcingEvent.STATUS_BID_WINDOW,
            bid_end_date__gt=now,
            bid_end_date__lte=now + timezone.timedelta(days=3),
        )
        .annotate(invite_count=Count("invitations"))
        .order_by("bid_end_date")[:8]
    )
    action_queue = SourcingEvent.objects.filter(
        _event_org_filter,
        status__in=[
            SourcingEvent.STATUS_DRAFT,
            SourcingEvent.STATUS_TECHNICAL_REVIEW,
            SourcingEvent.STATUS_COMMERCIAL_REVIEW,
            SourcingEvent.STATUS_AWARD_APPROVAL,
        ]
    ).order_by("-updated_at")[:10]
    attention_vendors = (
        get_governance_vendor_queryset(user=request.user)
        .filter(
            Q(status=Vendor.STATUS_ON_HOLD)
            | Q(latest_risk_level="HIGH")
            | Q(latest_composite_score__lt=70)
        )
        .order_by("-updated_at")[:8]
    )
    awarded_without_po = (
        SourcingEvent.objects.filter(_event_org_filter, status=SourcingEvent.STATUS_AWARDED)
        .exclude(
            purchase_orders__status__in=[
                PurchaseOrder.STATUS_DRAFT,
                PurchaseOrder.STATUS_APPROVAL,
                PurchaseOrder.STATUS_ISSUED,
                PurchaseOrder.STATUS_ACKNOWLEDGED,
                PurchaseOrder.STATUS_PARTIAL_RECEIPT,
                PurchaseOrder.STATUS_COMPLETED,
            ]
        )
        .order_by("-updated_at")[:8]
    )
    avg_scorecard = VendorScorecard.objects.aggregate(avg=Avg("composite_score"))["avg"]
    _prs_org_filter = (
        Q(department__organization=_proc_org)
        | Q(cost_center__department__organization=_proc_org)
        | Q(requester__organization=_proc_org)
    ) if _proc_org and not getattr(user, "is_superuser", False) else Q()
    ready_prs_count = PurchaseRequisition.objects.filter(
        _prs_org_filter,
        status=PurchaseRequisition.STATUS_APPROVED,
    ).count()
    context = {
        "sourcing": get_sourcing_dashboard_metrics(user=user),
        "governance": get_governance_metrics(),
        "ready_prs_count": ready_prs_count,
        "open_pos": PurchaseOrder.objects.filter(
            status__in=[
                PurchaseOrder.STATUS_ISSUED,
                PurchaseOrder.STATUS_ACKNOWLEDGED,
                PurchaseOrder.STATUS_PARTIAL_RECEIPT,
            ]
        ).count(),
        "pending_clarifications": Clarification.objects.filter(status="PENDING")
        .exclude(event__status__in=["AWARDED", "CANCELLED"])
        .count(),
        "avg_scorecard": round(float(avg_scorecard), 1) if avg_scorecard is not None else None,
        "unread_notifications": Notification.objects.filter(
            recipient=user, is_read=False
        ).count(),
        "closing_soon": closing_soon,
        "action_queue": action_queue,
        "attention_vendors": attention_vendors,
        "awarded_without_po": awarded_without_po,
    }
    return render(request, "pages/dashboards/procurement_dashboard.html", context)


@login_required(login_url="/login/")
def legal_dashboard_view(request):
    from apps.contracts.views import dashboard_view as contract_dashboard_view

    return contract_dashboard_view(request)


@login_required(login_url="/login/")
def approver_dashboard_view(request):
    user = request.user
    user_department = getattr(user, "department", None)
    from apps.budgets.models import Budget
    from apps.organization.models import CostCenter, Department, FiscalPeriod

    if not user_department:
        managed_cc = (
            CostCenter.objects.filter(manager=user)
            .select_related("department")
            .first()
        )
        if managed_cc and managed_cc.department:
            user_department = managed_cc.department
        elif getattr(user, "organization", None):
            user_department = Department.objects.filter(
                organization=user.organization
            ).first()

    if not user_department:
        messages.warning(
            request,
            "Your account is not linked to a department or organization. "
            "Dashboard figures are limited until an administrator assigns your scope.",
        )

    if user_department:
        dept_prs = PurchaseRequisition.objects.filter(
            Q(department=user_department) | Q(cost_center__manager=user)
        ).distinct()
    elif getattr(user, "organization", None):
        dept_prs = PurchaseRequisition.objects.filter(
            Q(department__organization=user.organization) | Q(cost_center__manager=user)
        ).distinct()
    else:
        dept_prs = PurchaseRequisition.objects.none()

    from apps.approvals.models import ApprovalAction
    user_approved_pr_ids = ApprovalAction.objects.filter(
        actor=user,
        target_model_name="PurchaseRequisition",
        action=ApprovalAction.ACTION_APPROVE,
    ).values_list("target_object_id", flat=True)

    pending_prs_qs = (
        dept_prs.filter(status__in=["SUBMITTED", "MANAGER_REVIEW", "BUDGET_REVIEW"])
        .exclude(id__in=user_approved_pr_ids)
        .order_by("-updated_at")
        .prefetch_related("attachments")
    )
    budget_overrun_qs = pending_prs_qs.filter(status=PurchaseRequisition.STATUS_BUDGET_REVIEW)
    has_budget_overrun = budget_overrun_qs.exists()
    budget_overrun_count = budget_overrun_qs.count()

    now = timezone.now()
    user_org = getattr(user, "organization", None) or (
        user_department.organization if user_department else None
    )
    period_filter = Q(start_date__lte=now, end_date__gte=now, is_closed=False)
    if user_org:
        current_period = FiscalPeriod.objects.filter(
            period_filter, organization=user_org
        ).first()
    else:
        current_period = FiscalPeriod.objects.filter(period_filter).first()

    available_budget = 0
    if current_period:
        if user_department:
            dept_ccs = CostCenter.objects.filter(
                Q(department=user_department) | Q(manager=user)
            ).distinct()
        elif getattr(user, "organization", None):
            dept_ccs = CostCenter.objects.filter(department__organization=user.organization)
        else:
            dept_ccs = CostCenter.objects.filter(manager=user)
        budgets = Budget.objects.filter(
            cost_center__in=dept_ccs, fiscal_period=current_period
        )
        available_budget = sum([b.available_amount for b in budgets])

    context = {
        "user_department": user_department,
        "has_budget_overrun": has_budget_overrun,
        "budget_overrun_count": budget_overrun_count,
        "metrics": {
            "total_prs_count": dept_prs.count(),
            "pending_count": pending_prs_qs.count(),
            "approved_count": dept_prs.filter(status="APPROVED").count(),
            "available_budget": float(available_budget),
            "budget_overrun_count": budget_overrun_count,
        },
        "pending_prs": pending_prs_qs[:10],
    }
    return render(request, "pages/dashboards/approver_dashboard.html", context)


@login_required(login_url="/login/")
def superadmin_dashboard_view(request):
    user = request.user
    from apps.audit.models import AuditLog
    from apps.budgets.models import Budget
    from apps.invoices.models import MatchException
    from apps.organization.models import Organization

    from apps.core.superadmin_views import get_user_scoped_org

    scoped_org = get_user_scoped_org(user)
    is_global_superadmin = bool(not scoped_org and user.is_superuser)
    can_add_organization = is_global_superadmin

    today = timezone.now().date()
    users_qs = User.objects.all()
    budgets_qs = Budget.objects.all()
    prs_qs = PurchaseRequisition.objects.filter(
        status__in=[
            PurchaseRequisition.STATUS_SUBMITTED,
            PurchaseRequisition.STATUS_MANAGER_REVIEW,
            PurchaseRequisition.STATUS_BUDGET_REVIEW,
        ]
    )
    exceptions_qs = MatchException.objects.filter(status=MatchException.STATUS_OPEN)
    audits_qs = AuditLog.objects.filter(timestamp__date=today)
    orgs_qs = Organization.objects.select_related("admin_user").order_by("code")

    if scoped_org:
        users_qs = users_qs.filter(Q(organization=scoped_org) | Q(department__organization=scoped_org))
        budgets_qs = budgets_qs.filter(cost_center__department__organization=scoped_org)
        prs_qs = prs_qs.filter(department__organization=scoped_org)
        exceptions_qs = exceptions_qs.filter(invoice__po__requisition__department__organization=scoped_org)
        audits_qs = audits_qs.filter(
            Q(actor__organization=scoped_org) | Q(actor__department__organization=scoped_org)
        )
        orgs_qs = orgs_qs.filter(id=scoped_org.id)

    total_users = users_qs.count()
    budget_agg = budgets_qs.aggregate(total=Sum("allocated_amount"))["total"]
    allocated_budget = budget_agg if budget_agg is not None else Decimal("0.00")
    pending_pr_count = prs_qs.count()
    pending_exceptions = exceptions_qs.count()
    audits_today = audits_qs.count()

    # is_global_superadmin and can_add_organization are computed above based on get_user_scoped_org and user.is_superuser

    context = {
        "organizations": orgs_qs,
        "scoped_org": scoped_org,
        "is_global_superadmin": is_global_superadmin,
        "can_add_organization": is_global_superadmin,
        "total_organizations": Organization.objects.count() if is_global_superadmin else (1 if scoped_org else 0),
        "active_organizations": (
            Organization.objects.filter(is_active=True).count()
            if is_global_superadmin
            else (1 if (scoped_org and scoped_org.is_active) else 0)
        ),
        "provisioned_admins": (
            Organization.objects.filter(admin_user__isnull=False).count()
            if is_global_superadmin
            else (1 if (scoped_org and scoped_org.admin_user) else 0)
        ),
        "metrics": {
            "total_users": total_users,
            "allocated_budget": allocated_budget,
            "pending_pr_count": pending_pr_count,
            "pending_exceptions": pending_exceptions,
            "audits_today": audits_today,
        },
        "kpi_total_users": total_users,
        "kpi_total_budget": allocated_budget,
        "kpi_pending_transactions": pending_pr_count + pending_exceptions,
        "kpi_audit_logs_today": audits_today,
    }
    return render(request, "pages/dashboards/superadmin_dashboard.html", context)


@login_required(login_url="/login/")
def auditor_dashboard_view(request):
    from apps.audit.views import auditor_dashboard_view as aud_view

    return aud_view(request)


@login_required(login_url="/login/")
def home_view(request):  # noqa: C901
    """
    Role-tailored Dashboard page view with live aggregated ERP metrics.
    Dispatches to custom workspace per user role (Requester, Approver, Procurement, Finance, Vendor, Legal, Auditor, Admin).
    """
    user = request.user
    role_code = getattr(user, "role_code", None) or (
        user.role.code if hasattr(user, "role") and user.role else None
    )

    # Platform Admin landing on home view redirects directly to Django Admin
    if user.is_superuser and not getattr(user, "organization_id", None):
        return redirect("/admin/")

    if role_code is None and not user.is_superuser:
        return render(request, "pages/dashboards/no_role.html", status=403)

    dispatch_map = {
        Role.REQUESTER: requester_dashboard_view,
        Role.PROC_MGR: manager_dashboard_view,
        Role.STORES_RECEIVER: stores_dashboard_view,
        Role.VENDOR_USER: vendor_dashboard_view,
        Role.FINANCE_AP: finance_dashboard_view,
        Role.PROC_EXEC: procurement_dashboard_view,
        Role.LEGAL_MGR: legal_dashboard_view,
        Role.DEPT_APPROVER: approver_dashboard_view,
        Role.SUPER_ADMIN: superadmin_dashboard_view,
        Role.AUDITOR: auditor_dashboard_view,
    }

    handler = dispatch_map.get(role_code)
    if handler:
        return handler(request)

    # Fallback for all other unknown roles
    return requester_dashboard_view(request)


def _is_api_request(request):
    accept = request.headers.get("Accept", "").lower()
    return request.path.startswith("/api/") or "application/json" in accept or "json" in accept


def custom_404_view(request, exception=None):
    if request.path == "/favicon.ico":
        from django.shortcuts import redirect
        return redirect("/static/icons/favicon.ico")

    # Auto-redirect non-slash URLs if the slashed path resolves (replaces default CommonMiddleware behavior bypassed by catch-all)
    if not request.path.endswith("/") and not _is_api_request(request):
        slash_path = request.path + "/"
        from django.shortcuts import redirect
        from django.urls import Resolver404, resolve
        try:
            match = resolve(slash_path)
            if match.url_name != "custom_404_fallback":
                query = request.META.get("QUERY_STRING", "")
                return redirect(slash_path + ("?" + query if query else ""), permanent=False)
        except Resolver404:
            pass

    if _is_api_request(request):
        return JsonResponse(
            {
                "error": {
                    "code": "NOT_FOUND",
                    "message": "The requested resource was not found.",
                    "details": {"path": request.path},
                }
            },
            status=404,
        )
    return render(request, "404.html", status=404)


def custom_500_view(request):
    if _is_api_request(request):
        return JsonResponse(
            {
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected server error occurred.",
                    "details": {},
                }
            },
            status=500,
        )
    return render(request, "500.html", status=500)


def custom_403_view(request, exception=None):
    if _is_api_request(request):
        return JsonResponse(
            {
                "error": {
                    "code": "PERMISSION_DENIED",
                    "message": "You do not have permission to access this resource.",
                    "details": {"detail": str(exception) if exception else "Permission denied."},
                }
            },
            status=403,
        )
    return render(request, "403.html", status=403)


def protected_media_view(request, file_path):
    """
    Secure media delivery endpoint enforcing authentication, directory traversal
    protection, and object-level/role-based access control (DEF-002).
    """
    import mimetypes
    import os

    from django.conf import settings
    from django.http import FileResponse, Http404, HttpResponseForbidden

    if not request.user or not request.user.is_authenticated:
        if _is_api_request(request):
            return JsonResponse(
                {
                    "error": {
                        "code": "AUTHENTICATION_REQUIRED",
                        "message": "Authentication required to access media documents.",
                    }
                },
                status=401,
            )
        return HttpResponseForbidden("Authentication required to access media documents.")

    user = request.user
    role_code = getattr(user, "role_code", None) or (
        user.role.code if hasattr(user, "role") and user.role else None
    )

    # 1. Path traversal hardening
    normalized_path = os.path.normpath(file_path).lstrip("/\\")
    if normalized_path.startswith("..") or ".." in normalized_path.split(os.path.sep):
        return HttpResponseForbidden("Access denied: Invalid file path.")

    full_path = os.path.join(settings.MEDIA_ROOT, normalized_path)
    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        raise Http404("Document not found.")

    # 2. RBAC and Ownership Enforcement
    if user.is_superuser or role_code == Role.SUPER_ADMIN:
        pass  # Super Admin has full administrative access
    elif role_code == Role.VENDOR_USER:
        vendor = getattr(user, "vendor", None)
        if not vendor:
            return HttpResponseForbidden("Access denied: No linked vendor profile.")

        from apps.sourcing.models import BidAttachment
        from apps.vendors.models import VendorDocument

        is_vendor_doc = VendorDocument.objects.filter(
            vendor=vendor, file__endswith=os.path.basename(normalized_path)
        ).exists()
        is_bid_att = BidAttachment.objects.filter(
            bid__vendor=vendor, file__endswith=os.path.basename(normalized_path)
        ).exists()

        if not (is_vendor_doc or is_bid_att or str(vendor.id) in normalized_path):
            return HttpResponseForbidden("Access denied: Vendors may only access their own documents.")
    elif role_code in [Role.REQUESTER, Role.DEPT_APPROVER, Role.STORES_RECEIVER]:
        norm_lower = normalized_path.lower()
        if "contracts" in norm_lower:
            return HttpResponseForbidden("Access denied: Legal contracts are restricted to Legal and Procurement.")
        if "vendor_docs" in norm_lower or "kyc" in norm_lower:
            return HttpResponseForbidden("Access denied: Vendor KYC records are restricted to Procurement and Legal.")
    elif role_code in [Role.PROC_EXEC, Role.PROC_MGR, Role.LEGAL_MGR, Role.FINANCE_AP, Role.AUDITOR]:
        pass

    content_type, _ = mimetypes.guess_type(full_path)
    filename = os.path.basename(full_path)
    response = FileResponse(open(full_path, "rb"), content_type=content_type or "application/octet-stream")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def protected_vendor_document_view(request, file_path):
    """Alias for backwards compatibility with vendor_documents specific route."""
    import os
    if not file_path.startswith("vendor_documents"):
        file_path = os.path.join("vendor_documents", file_path)
    return protected_media_view(request, file_path)

