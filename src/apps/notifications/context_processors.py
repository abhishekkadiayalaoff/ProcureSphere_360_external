from apps.accounts.models import Role
from apps.notifications.models import Notification
from apps.requisitions.models import PurchaseRequisition


def notifications_processor(request):
    """
    Global context processor supplying unread notifications and pending approval counts to all templates.
    """
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {
            "unread_notifications_count": 0,
            "pending_approvals_count": 0,
            "notifications_list": [],
        }

    user = request.user
    role_code = getattr(user, "role_code", None)

    # 1. Calculate unread notifications count for recipient
    unread_count = Notification.objects.filter(recipient=user, is_read=False).count()

    # 2. Calculate pending approvals count for DEPT_APPROVER, PROC_MGR, or SUPER_ADMIN
    pending_count = 0
    statuses = [
        PurchaseRequisition.STATUS_SUBMITTED,
        PurchaseRequisition.STATUS_MANAGER_REVIEW,
        PurchaseRequisition.STATUS_BUDGET_REVIEW,
    ]
    if role_code == Role.DEPT_APPROVER:
        from django.db.models import Q
        user_dept = getattr(user, "department", None)
        if not user_dept:
            from apps.organization.models import CostCenter, Department

            managed_cc = (
                CostCenter.objects.filter(manager=user)
                .select_related("department")
                .first()
            )
            if managed_cc and managed_cc.department:
                user_dept = managed_cc.department
            elif getattr(user, "organization", None):
                user_dept = Department.objects.filter(
                    organization=user.organization
                ).first()

        from apps.approvals.models import ApprovalAction
        user_approved_pr_ids = ApprovalAction.objects.filter(
            actor=user,
            target_model_name="PurchaseRequisition",
            action=ApprovalAction.ACTION_APPROVE,
        ).values_list("target_object_id", flat=True)

        if user_dept:
            pending_count = (
                PurchaseRequisition.objects.filter(
                    Q(department=user_dept) | Q(cost_center__manager=user),
                    status__in=statuses,
                )
                .exclude(id__in=user_approved_pr_ids)
                .distinct()
                .count()
            )
        elif getattr(user, "organization", None):
            pending_count = (
                PurchaseRequisition.objects.filter(
                    Q(department__organization=user.organization) | Q(cost_center__manager=user),
                    status__in=statuses,
                )
                .exclude(id__in=user_approved_pr_ids)
                .distinct()
                .count()
            )
        else:
            pending_count = (
                PurchaseRequisition.objects.filter(status__in=statuses)
                .exclude(id__in=user_approved_pr_ids)
                .count()
            )
    elif role_code == Role.PROC_MGR:
        scoped_org = getattr(user, "effective_organization", None) or getattr(user, "organization", None)
        if scoped_org:
            pending_count = PurchaseRequisition.objects.filter(
                department__organization=scoped_org,
                status__in=statuses,
            ).count()
        else:
            pending_count = PurchaseRequisition.objects.filter(status__in=statuses).count()
    elif role_code == Role.SUPER_ADMIN:
        scoped_org = getattr(user, "effective_organization", None) if not (user.is_superuser and not getattr(user, "organization_id", None)) else None
        if scoped_org:
            pending_count = PurchaseRequisition.objects.filter(
                department__organization=scoped_org,
                status__in=statuses,
            ).count()
        else:
            pending_count = PurchaseRequisition.objects.filter(status__in=statuses).count()
    elif role_code == Role.LEGAL_MGR:
        from apps.contracts.models import Contract

        pending_count = Contract.objects.filter(status=Contract.STATUS_LEGAL_REVIEW).count()

    recent_notifications = Notification.objects.filter(recipient=user).order_by("-created_at")[:5]

    return {
        "unread_notifications_count": unread_count,
        "pending_approvals_count": pending_count,
        "notifications_list": recent_notifications,
    }
