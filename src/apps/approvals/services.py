from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog

from .models import ApprovalAction, ApprovalDelegate, ApprovalPolicy, ApprovalStep


@transaction.atomic
def create_approval_policy_service(
    *,
    name: str,
    module: str,
    min_amount: Decimal = Decimal("0.00"),
    max_amount=None,
    department=None,
    cost_center=None,
    organization=None,
    currency: str = "INR",
    status: str = ApprovalPolicy.STATUS_ACTIVE,
    description: str = "",
    has_exception_routing: bool = False,
    exception_amount_threshold=None,
    exception_department=None,
    exception_cost_center=None,
    exception_trigger_on_missing_cost_center: bool = False,
    exception_trigger_on_budget_exceeded: bool = False,
    exception_approver_role=None,
    exception_specific_approver=None,
    exception_escalation_time_hours: Optional[int] = 24,
    exception_routing_behavior: str = "ADDITIONAL_APPROVER",
    exception_reason: str = "",
    exception_description: str = "",
    actor: Optional[User] = None,
) -> ApprovalPolicy:
    """
    Creates a full-featured enterprise Approval Policy configuration.
    """
    if not organization and department and getattr(department, "organization", None):
        organization = department.organization

    policy = ApprovalPolicy(
        name=name,
        module=module,
        min_amount=min_amount,
        max_amount=max_amount,
        department=department,
        cost_center=cost_center,
        organization=organization,
        currency=currency,
        status=status,
        description=description,
        is_active=(status == ApprovalPolicy.STATUS_ACTIVE),
        has_exception_routing=has_exception_routing,
        exception_amount_threshold=exception_amount_threshold,
        exception_department=exception_department,
        exception_cost_center=exception_cost_center,
        exception_trigger_on_missing_cost_center=exception_trigger_on_missing_cost_center,
        exception_trigger_on_budget_exceeded=exception_trigger_on_budget_exceeded,
        exception_approver_role=exception_approver_role,
        exception_specific_approver=exception_specific_approver,
        exception_escalation_time_hours=exception_escalation_time_hours,
        exception_routing_behavior=exception_routing_behavior,
        exception_reason=exception_reason,
        exception_description=exception_description,
    )
    policy.full_clean()
    policy.save()

    if actor:
        from apps.audit.services import create_audit_log_service
        create_audit_log_service(
            actor=actor,
            action=AuditLog.ACTION_CREATE,
            target_model="ApprovalPolicy",
            target_object_id=str(policy.id),
            previous_state=None,
            new_state={
                "name": policy.name,
                "module": policy.module,
                "status": policy.status,
                "min_amount": str(policy.min_amount),
                "max_amount": str(policy.max_amount) if policy.max_amount else None,
                "has_exception_routing": policy.has_exception_routing,
            },
        )

    return policy


@transaction.atomic
def add_approval_step_service(
    *,
    policy: ApprovalPolicy,
    step_number: int,
    approver_role: Role,
    specific_approver: User = None,
    description: str = "",
    is_mandatory: bool = True,
    approval_limit: Optional[Decimal] = None,
    step_type: str = "SEQUENTIAL",
    rejection_behavior: str = "STOP_WORKFLOW",
    escalation_hours: Optional[int] = None,
) -> ApprovalStep:
    """
    Adds an ordered step to an Approval Policy.
    """
    step = ApprovalStep.objects.create(
        policy=policy,
        step_number=step_number,
        approver_role=approver_role,
        specific_approver=specific_approver,
        description=description,
        is_mandatory=is_mandatory,
        approval_limit=approval_limit,
        step_type=step_type,
        rejection_behavior=rejection_behavior,
        escalation_hours=escalation_hours,
    )
    return step


def resolve_active_delegate(approver: User) -> User:
    """
    Resolves if an approver has an active delegate for today's date.
    If active delegate exists, returns the delegate user; otherwise returns the original approver.
    """
    today = timezone.now().date()
    delegate_record = ApprovalDelegate.objects.filter(
        approver=approver,
        is_active=True,
        start_date__lte=today,
        end_date__gte=today,
    ).first()

    if delegate_record and delegate_record.delegate:
        return delegate_record.delegate
    return approver


def evaluate_approval_chain(
    *,
    module: str,
    amount: Decimal,
    department=None,
    cost_center=None,
    organization=None,
    missing_cost_center: bool = False,
    budget_exceeded: bool = False,
) -> List[Dict[str, Any]]:
    """
    Evaluates server-side approval routing policies for a module & amount threshold.
    Supports organization-level scoping, cost-center routing, department routing,
    multi-department/multi-cost-center rules, amount slabs, and optional exception routing.

    Matching priority:
    1. Organization + Department + Cost Center + Transaction Type (Module)
    2. Organization + Department + Transaction Type
    3. Organization + Cost Center + Transaction Type
    4. Organization + Transaction Type (Organization Default / All Departments & Cost Centers)
    5. Global Fallback Policy (No Org / Global)
    """
    if not organization:
        if department and getattr(department, "organization", None):
            organization = department.organization
        elif cost_center and getattr(cost_center, "department", None) and getattr(cost_center.department, "organization", None):
            organization = cost_center.department.organization

    base_qs = ApprovalPolicy.objects.filter(
        module=module,
        is_active=True,
        min_amount__lte=amount,
    ).filter(
        models.Q(max_amount__isnull=True) | models.Q(max_amount__gte=amount)
    ).prefetch_related("departments", "cost_centers", "steps__approver_role", "steps__specific_approver")

    if organization:
        policies = base_qs.filter(
            models.Q(organization=organization) | models.Q(department__organization=organization) | models.Q(organization__isnull=True, department__isnull=True)
        )
    else:
        policies = base_qs

    selected_policy = None

    # Priority 1: Organization + Department + Cost Center + Module
    if cost_center and department:
        b1 = [
            p for p in policies
            if (p.cost_center_id == cost_center.id or cost_center in p.cost_centers.all())
            and (p.department_id == department.id or department in p.departments.all())
        ]
        if b1:
            selected_policy = sorted(b1, key=lambda x: x.min_amount, reverse=True)[0]

    # Priority 2: Organization + Department + Module
    if not selected_policy and department:
        b2 = [
            p for p in policies
            if (p.department_id == department.id or department in p.departments.all())
            and p.cost_center_id is None and not p.cost_centers.exists() and not p.all_cost_centers
        ]
        if b2:
            selected_policy = sorted(b2, key=lambda x: x.min_amount, reverse=True)[0]

    # Priority 3: Organization + Cost Center + Module
    if not selected_policy and cost_center:
        b3 = [
            p for p in policies
            if (p.cost_center_id == cost_center.id or cost_center in p.cost_centers.all())
            and p.department_id is None and not p.departments.exists() and not p.all_departments
        ]
        if b3:
            selected_policy = sorted(b3, key=lambda x: x.min_amount, reverse=True)[0]

    # Priority 4: Organization + Module (Org default / All Departments & Cost Centers)
    if not selected_policy and organization:
        b4 = [
            p for p in policies
            if p.organization_id == organization.id
            and p.department_id is None and not p.departments.exists()
            and p.cost_center_id is None and not p.cost_centers.exists()
        ]
        if b4:
            selected_policy = sorted(b4, key=lambda x: x.min_amount, reverse=True)[0]

    # Priority 5: Global Fallback Policy
    if not selected_policy:
        b5 = [
            p for p in policies
            if p.department_id is None and not p.departments.exists()
            and p.cost_center_id is None and not p.cost_centers.exists()
            and p.organization_id is None
        ]
        if b5:
            selected_policy = sorted(b5, key=lambda x: x.min_amount, reverse=True)[0]

    if not selected_policy:
        # Final fallback across matching amount
        selected_policy = policies.order_by("-min_amount").first()

    if not selected_policy:
        return []

    steps = list(
        selected_policy.steps.select_related("approver_role", "specific_approver").order_by("step_number")
    )
    if not steps:
        return []

    chain = []
    for step in steps:
        effective_user = None
        if step.specific_approver:
            effective_user = resolve_active_delegate(step.specific_approver)
        chain.append(
            {
                "step_number": step.step_number,
                "policy_step": step,
                "approver_role": step.approver_role,
                "specific_approver": step.specific_approver,
                "effective_approver": effective_user,
                "description": step.description or f"{step.approver_role.name} Approval",
                "is_mandatory": getattr(step, "is_mandatory", True),
                "approval_limit": getattr(step, "approval_limit", None),
                "step_type": getattr(step, "step_type", "SEQUENTIAL"),
                "rejection_behavior": getattr(step, "rejection_behavior", "STOP_WORKFLOW"),
                "escalation_hours": getattr(step, "escalation_hours", None),
                "is_exception_step": False,
            }
        )

    # Optional Exception Routing Check
    if selected_policy.has_exception_routing:
        exception_triggered = False
        reasons = []

        if selected_policy.exception_amount_threshold is not None and amount >= selected_policy.exception_amount_threshold:
            exception_triggered = True
            curr = selected_policy.currency or "INR"
            reasons.append(f"Amount {curr} {amount:,.2f} exceeds exception threshold ({selected_policy.exception_amount_threshold:,.2f})")

        if selected_policy.exception_trigger_on_missing_cost_center and (missing_cost_center or not cost_center):
            exception_triggered = True
            reasons.append("Missing cost center mapping")

        if selected_policy.exception_trigger_on_budget_exceeded and budget_exceeded:
            exception_triggered = True
            reasons.append("Budget overrun exception triggered")

        if selected_policy.exception_department_id and department and department.id == selected_policy.exception_department_id:
            exception_triggered = True
            reasons.append(f"Department exception rule ({department.name})")

        if selected_policy.exception_cost_center_id and cost_center and cost_center.id == selected_policy.exception_cost_center_id:
            exception_triggered = True
            reasons.append(f"Cost center exception rule ({cost_center.code})")

        if exception_triggered:
            exc_role = selected_policy.exception_approver_role
            if not exc_role and selected_policy.exception_routing_behavior == "ESCALATE_ADMIN":
                exc_role = Role.objects.filter(code=Role.SUPER_ADMIN).first()

            if exc_role:
                exc_desc = f"Exception: {selected_policy.exception_reason or ', '.join(reasons)}"
                effective_exc_user = None
                if selected_policy.exception_specific_approver:
                    effective_exc_user = resolve_active_delegate(selected_policy.exception_specific_approver)

                exc_step_dict = {
                    "step_number": len(chain) + 1,
                    "policy_step": None,
                    "approver_role": exc_role,
                    "specific_approver": selected_policy.exception_specific_approver,
                    "effective_approver": effective_exc_user,
                    "description": exc_desc,
                    "is_mandatory": True,
                    "approval_limit": None,
                    "step_type": "SEQUENTIAL",
                    "rejection_behavior": "STOP_WORKFLOW",
                    "escalation_hours": selected_policy.exception_escalation_time_hours,
                    "is_exception_step": True,
                    "exception_reasons": reasons,
                }

                if selected_policy.exception_routing_behavior == "ALTERNATE_PATH":
                    exc_step_dict["step_number"] = 1
                    chain = [exc_step_dict]
                else:
                    chain.append(exc_step_dict)

    return chain


@transaction.atomic
def duplicate_approval_policy_service(*, policy_id: Optional[str] = None, policy: Optional[ApprovalPolicy] = None, actor: Optional[User] = None) -> ApprovalPolicy:
    """
    Clones an existing approval policy into a Draft version.
    Allows easy creation of multiple amount slabs.
    """
    if policy is None:
        orig = ApprovalPolicy.objects.get(pk=policy_id)
    else:
        orig = policy
    cloned_name = f"Copy of {orig.name}"
    counter = 1
    while ApprovalPolicy.objects.filter(name=cloned_name, organization=orig.organization).exists():
        counter += 1
        cloned_name = f"Copy ({counter}) of {orig.name}"

    cloned = ApprovalPolicy.objects.create(
        name=cloned_name,
        module=orig.module,
        organization=orig.organization,
        department=orig.department,
        cost_center=orig.cost_center,
        min_amount=orig.min_amount,
        max_amount=orig.max_amount,
        currency=orig.currency,
        status=ApprovalPolicy.STATUS_DRAFT,
        is_active=False,
        description=orig.description,
        version=orig.version + 1,
        has_exception_routing=orig.has_exception_routing,
        exception_amount_threshold=orig.exception_amount_threshold,
        exception_department=orig.exception_department,
        exception_cost_center=orig.exception_cost_center,
        exception_trigger_on_missing_cost_center=orig.exception_trigger_on_missing_cost_center,
        exception_trigger_on_budget_exceeded=orig.exception_trigger_on_budget_exceeded,
        exception_approver_role=orig.exception_approver_role,
        exception_specific_approver=orig.exception_specific_approver,
        exception_escalation_time_hours=orig.exception_escalation_time_hours,
        exception_routing_behavior=orig.exception_routing_behavior,
        exception_reason=orig.exception_reason,
        exception_description=orig.exception_description,
    )

    # Clone steps
    for step in orig.steps.all().order_by("step_number"):
        ApprovalStep.objects.create(
            policy=cloned,
            step_number=step.step_number,
            approver_role=step.approver_role,
            specific_approver=step.specific_approver,
            description=step.description,
            is_mandatory=step.is_mandatory,
            approval_limit=step.approval_limit,
            step_type=step.step_type,
            rejection_behavior=step.rejection_behavior,
            escalation_hours=step.escalation_hours,
        )

    if actor:
        from apps.audit.services import create_audit_log_service
        create_audit_log_service(
            actor=actor,
            action=AuditLog.ACTION_CREATE,
            target_model="ApprovalPolicy",
            target_object_id=str(cloned.id),
            previous_state={"cloned_from": str(orig.id)},
            new_state={"name": cloned.name, "status": cloned.status},
        )

    return cloned


@transaction.atomic
def toggle_policy_status_service(*, policy_id: Optional[str] = None, policy: Optional[ApprovalPolicy] = None, actor: Optional[User] = None) -> ApprovalPolicy:
    """
    Toggles between ACTIVE and DRAFT status.
    """
    if policy is None:
        policy = ApprovalPolicy.objects.get(pk=policy_id)
    old_status = policy.status

    if policy.status == ApprovalPolicy.STATUS_ACTIVE:
        policy.status = ApprovalPolicy.STATUS_DRAFT
        policy.is_active = False
    else:
        # Activate: Validate that policy has at least one approval step
        if not policy.steps.exists():
            raise ValidationError("Cannot activate policy with zero approval steps. Add at least one approval level.")
        policy.status = ApprovalPolicy.STATUS_ACTIVE
        policy.is_active = True
        policy.full_clean()

    policy.save(update_fields=["status", "is_active", "updated_at"])

    if actor:
        from apps.audit.services import create_audit_log_service
        create_audit_log_service(
            actor=actor,
            action=AuditLog.ACTION_UPDATE,
            target_model="ApprovalPolicy",
            target_object_id=str(policy.id),
            previous_state={"status": old_status},
            new_state={"status": policy.status, "is_active": policy.is_active},
        )

    return policy


@transaction.atomic
def archive_policy_service(*, policy_id: Optional[str] = None, policy: Optional[ApprovalPolicy] = None, actor: Optional[User] = None) -> ApprovalPolicy:
    """
    Archives an approval policy.
    """
    if policy is None:
        policy = ApprovalPolicy.objects.get(pk=policy_id)
    old_status = policy.status
    policy.status = ApprovalPolicy.STATUS_ARCHIVED
    policy.is_active = False
    policy.save(update_fields=["status", "is_active", "updated_at"])

    if actor:
        from apps.audit.services import create_audit_log_service
        create_audit_log_service(
            actor=actor,
            action=AuditLog.ACTION_UPDATE,
            target_model="ApprovalPolicy",
            target_object_id=str(policy.id),
            previous_state={"status": old_status},
            new_state={"status": policy.status, "is_active": policy.is_active},
        )

    return policy


@transaction.atomic
def record_approval_action_service(
    *,
    target_object_id,
    target_model_name: str,
    actor: User,
    action: str,
    previous_state: str,
    new_state: str,
    policy_step: ApprovalStep = None,
    comments: str = "",
) -> ApprovalAction:
    """
    Records an append-only ApprovalAction and corresponding AuditLog entry inside a transaction.
    """
    approval_action = ApprovalAction.objects.create(
        policy_step=policy_step,
        target_object_id=target_object_id,
        target_model_name=target_model_name,
        actor=actor,
        action=action,
        comments=comments,
        previous_state=previous_state,
        new_state=new_state,
    )

    if action == ApprovalAction.ACTION_APPROVE:
        audit_action = AuditLog.ACTION_APPROVE
    elif action == ApprovalAction.ACTION_REJECT:
        audit_action = AuditLog.ACTION_REJECT
    elif action == ApprovalAction.ACTION_SUBMIT:
        audit_action = AuditLog.ACTION_CREATE
    else:
        audit_action = AuditLog.ACTION_UPDATE

    AuditLog.objects.create(
        actor=actor,
        action=audit_action,
        target_model=target_model_name,
        target_object_id=str(target_object_id),
        previous_state={"status": previous_state},
        new_state={"status": new_state, "comments": comments},
    )

    return approval_action


@transaction.atomic
def set_approval_delegate_service(
    *, approver: User, delegate: User, start_date, end_date, reason: str = ""
) -> ApprovalDelegate:
    """
    Sets up a temporary delegate for an approver.
    """
    delegate_record = ApprovalDelegate.objects.create(
        approver=approver,
        delegate=delegate,
        start_date=start_date,
        end_date=end_date,
        is_active=True,
        reason=reason,
    )
    return delegate_record


@transaction.atomic
def process_approval_action_service(
    *, target_object, actor: User, action: str, comments: str = ""
):
    """
    Processes an approval action (APPROVE or REJECT) on a target object (e.g. PurchaseRequisition).
    Always returns the persisted ApprovalAction record.
    """
    from apps.requisitions.models import PurchaseRequisition
    from apps.requisitions.services import (
        approve_purchase_requisition_service,
        reject_purchase_requisition_service,
    )

    act_str = str(action).upper()
    if isinstance(target_object, PurchaseRequisition):
        if act_str in ["APPROVE", "APPROVED"]:
            approve_purchase_requisition_service(
                requisition=target_object, approver=actor, comments=comments
            )
            return (
                ApprovalAction.objects.filter(
                    target_object_id=str(target_object.id),
                    target_model_name="PurchaseRequisition",
                )
                .order_by("-created_at")
                .first()
            )
        elif act_str in ["REJECT", "REJECTED"]:
            reject_purchase_requisition_service(
                requisition=target_object, approver=actor, comments=comments
            )
            return (
                ApprovalAction.objects.filter(
                    target_object_id=str(target_object.id),
                    target_model_name="PurchaseRequisition",
                )
                .order_by("-created_at")
                .first()
            )

    previous_state = getattr(target_object, "status", "UNKNOWN")
    new_state = "APPROVED" if act_str in ["APPROVE", "APPROVED"] else "REJECTED"
    if hasattr(target_object, "status"):
        target_object.status = new_state
        target_object.save()

    return record_approval_action_service(
        target_object_id=target_object.id,
        target_model_name=target_object.__class__.__name__,
        actor=actor,
        action=(
            ApprovalAction.ACTION_APPROVE
            if act_str in ["APPROVE", "APPROVED"]
            else ApprovalAction.ACTION_REJECT
        ),
        previous_state=previous_state,
        new_state=new_state,
        comments=comments,
    )
