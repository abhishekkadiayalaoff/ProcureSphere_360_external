import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.db.models import Count, Q
from django.utils import timezone

from apps.approvals.models import ApprovalAction
from apps.audit.models import AuditLog
from apps.contracts.models import Contract, ContractAlert, ContractObligation
from apps.invoices.models import MatchException, SupplierInvoice
from apps.orders.models import PurchaseOrder
from apps.requisitions.models import PurchaseRequisition
from apps.sourcing.models import SourcingEvent, VendorBid
from apps.vendors.models import Vendor


def _actor_org_q(org):
    """Q filter restricting audit records to actors belonging to the given organization."""
    if not org:
        return None
    return Q(actor__organization=org) | Q(actor__department__organization=org)


def get_audit_logs(
    actor_id: Optional[str] = None,
    action: Optional[str] = None,
    target_model: Optional[str] = None,
    target_object_id: Optional[str] = None,
    search_term: Optional[str] = None,
    start_date: Optional[Any] = None,
    end_date: Optional[Any] = None,
    request_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    org=None,
) -> Dict[str, Any]:
    """
    Retrieves filtered and paginated immutable AuditLog records with actor prefetching.
    When ``org`` is passed, records are scoped to that organization only.
    """
    qs = AuditLog.objects.select_related("actor").all()

    org_q = _actor_org_q(org)
    if org_q:
        qs = qs.filter(org_q)

    if actor_id:
        qs = qs.filter(actor_id=actor_id)

    if action:
        qs = qs.filter(action=action)

    if target_model:
        qs = qs.filter(target_model__iexact=target_model)

    if target_object_id:
        qs = qs.filter(target_object_id__icontains=target_object_id)

    if request_id:
        qs = qs.filter(request_id=request_id)

    if start_date:
        qs = qs.filter(timestamp__gte=start_date)

    if end_date:
        qs = qs.filter(timestamp__lte=end_date)

    if search_term:
        term = search_term.strip()
        qs = qs.filter(
            Q(target_model__icontains=term)
            | Q(target_object_id__icontains=term)
            | Q(actor__email__icontains=term)
            | Q(ip_address__icontains=term)
            | Q(request_id__icontains=term)
        )

    total_count = qs.count()
    logs = list(qs.order_by("-timestamp")[offset : offset + limit])

    return {
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "logs": logs,
    }


def get_audit_metrics(period_days: int = 30, org=None) -> Dict[str, Any]:
    """
    Computes statistical and distribution metrics over AuditLog records for compliance auditing.
    When ``org`` is passed, all figures are scoped to that organization only.
    """
    now = timezone.now()
    since_date = now - timedelta(days=period_days)
    base_qs = AuditLog.objects.filter(timestamp__gte=since_date)
    all_time_qs = AuditLog.objects.all()

    org_q = _actor_org_q(org)
    if org_q:
        base_qs = base_qs.filter(org_q)
        all_time_qs = all_time_qs.filter(org_q)

    total_logs_period = base_qs.count()
    total_logs_all_time = all_time_qs.count()

    # Action counts breakdown
    action_counts_raw = base_qs.values("action").annotate(count=Count("id")).order_by("-count")
    action_distribution = {item["action"]: item["count"] for item in action_counts_raw}

    # Target model breakdown
    model_counts_raw = (
        base_qs.values("target_model").annotate(count=Count("id")).order_by("-count")[:10]
    )
    model_distribution = {item["target_model"]: item["count"] for item in model_counts_raw}

    # Top active actors
    top_actors_raw = (
        base_qs.exclude(actor__isnull=True)
        .values("actor__email")
        .annotate(count=Count("id"))
        .order_by("-count")[:8]
    )
    top_actors = [
        {"email": item["actor__email"], "count": item["count"]} for item in top_actors_raw
    ]

    # Critical security & compliance event counts from action distribution
    critical_events = {
        "approvals": action_distribution.get(AuditLog.ACTION_APPROVE, 0),
        "rejections": action_distribution.get(AuditLog.ACTION_REJECT, 0),
        "logins": action_distribution.get(AuditLog.ACTION_LOGIN, 0),
        "exports": action_distribution.get(AuditLog.ACTION_EXPORT, 0),
        "cancels": action_distribution.get(AuditLog.ACTION_CANCEL, 0),
    }

    # Daily activity trend aggregated in a single database query using TruncDate
    from django.db.models.functions import TruncDate

    daily_counts_raw = (
        base_qs.annotate(day=TruncDate("timestamp"))
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )
    daily_map = {item["day"]: item["count"] for item in daily_counts_raw if item["day"]}

    daily_trend: List[Dict[str, Any]] = []
    for day_offset in range(min(period_days, 14), -1, -1):
        day_date = (now - timedelta(days=day_offset)).date()
        daily_trend.append(
            {
                "date": day_date.strftime("%b %d"),
                "count": daily_map.get(day_date, 0),
            }
        )

    return {
        "period_days": period_days,
        "total_logs_period": total_logs_period,
        "total_logs_all_time": total_logs_all_time,
        "action_distribution": action_distribution,
        "model_distribution": model_distribution,
        "top_actors": top_actors,
        "critical_events": critical_events,
        "daily_trend": daily_trend,
    }


def _vendor_org_q(org):
    """Q filter restricting vendor records to the given organization (plus global/legacy vendors)."""
    if not org:
        return None
    return Q(
        organization=org
    ) | Q(
        organization__isnull=True
    ) | Q(
        created_by__organization=org
    ) | Q(
        created_by__department__organization=org
    )


def get_auditor_dashboard_data(period_days: int = 30, org=None) -> Dict[str, Any]:
    """
    Aggregates full data bundle for the Compliance Auditor Dashboard:
    KPI cards, compliance exceptions, recent audit feed, approval feed, and charts.
    When ``org`` is passed, everything is scoped to that organization only.
    """
    metrics = get_audit_metrics(period_days=period_days, org=org)
    org_q = _actor_org_q(org)

    # 1. High-Priority Compliance Warnings
    open_exceptions_q = MatchException.objects.filter(status="OPEN")
    suspended_vendors_q = Vendor.objects.filter(
        status__in=[Vendor.STATUS_ON_HOLD, Vendor.STATUS_SUSPENDED]
    )
    overdue_obligations_q = ContractObligation.objects.filter(
        is_fulfilled=False, due_date__lt=timezone.now().date()
    )
    active_contract_alerts_q = ContractAlert.objects.filter(is_processed=False)
    recent_logs_q = AuditLog.objects.select_related("actor")
    recent_approvals_q = ApprovalAction.objects.select_related("actor", "policy_step")
    domain_counts = {}
    total_prs_q = PurchaseRequisition.objects.all()
    total_sourcing_q = SourcingEvent.objects.all()
    total_bids_q = VendorBid.objects.all()
    total_pos_q = PurchaseOrder.objects.all()
    total_invoices_q = SupplierInvoice.objects.all()
    total_contracts_q = Contract.objects.all()
    total_vendors_q = Vendor.objects.all()

    if org:
        open_exceptions_q = open_exceptions_q.filter(
            invoice__po__requisition__department__organization=org
        )
        vendor_org_q = _vendor_org_q(org)
        suspended_vendors_q = suspended_vendors_q.filter(vendor_org_q)
        contract_org_q = (
            Q(contract__contract_owner__organization=org)
            | Q(contract__contract_owner__department__organization=org)
            | Q(contract__po__cost_center__department__organization=org)
        )
        overdue_obligations_q = overdue_obligations_q.filter(contract_org_q)
        active_contract_alerts_q = active_contract_alerts_q.filter(contract_org_q)
        if org_q:
            recent_logs_q = recent_logs_q.filter(org_q)
            recent_approvals_q = recent_approvals_q.filter(Q(actor__organization=org) | Q(actor__department__organization=org))
        total_prs_q = total_prs_q.filter(department__organization=org)
        total_sourcing_q = total_sourcing_q.filter(
            Q(requisition__department__organization=org)
            | Q(requisition__isnull=True, created_by__department__organization=org)
        )
        total_bids_q = total_bids_q.filter(
            Q(event__requisition__department__organization=org)
            | Q(
                event__requisition__isnull=True,
                event__created_by__department__organization=org,
            )
        )
        po_org_q = Q(cost_center__department__organization=org) | Q(
            requisition__department__organization=org
        )
        total_pos_q = total_pos_q.filter(po_org_q)
        total_invoices_q = total_invoices_q.filter(
            po__requisition__department__organization=org
        )
        total_contracts_q = total_contracts_q.filter(
            Q(contract_owner__organization=org)
            | Q(contract_owner__department__organization=org)
            | Q(po__cost_center__department__organization=org)
        )
        total_vendors_q = total_vendors_q.filter(vendor_org_q)

    open_exceptions = list(
        open_exceptions_q.select_related("invoice", "invoice__vendor")
        .order_by("-created_at")[:10]
    )

    suspended_vendors = list(
        suspended_vendors_q.select_related("category").order_by("-updated_at")[:10]
    )

    overdue_obligations = list(
        overdue_obligations_q.select_related("contract", "contract__vendor").order_by("due_date")[:10]
    )

    active_contract_alerts = list(
        active_contract_alerts_q.select_related("contract").order_by("-triggered_at")[:10]
    )

    # 2. Activity Feeds
    recent_logs = list(recent_logs_q.order_by("-timestamp")[:25])

    recent_approvals = list(recent_approvals_q.order_by("-created_at")[:15])

    # 3. Domain totals for auditor context
    domain_counts = {
        "total_prs": total_prs_q.count(),
        "total_sourcing_events": total_sourcing_q.count(),
        "total_bids": total_bids_q.count(),
        "total_pos": total_pos_q.count(),
        "total_invoices": total_invoices_q.count(),
        "total_contracts": total_contracts_q.count(),
        "total_vendors": total_vendors_q.count(),
        "open_exceptions_count": open_exceptions_q.count(),
        "suspended_vendors_count": suspended_vendors_q.count(),
        "overdue_obligations_count": overdue_obligations_q.count(),
    }

    return {
        "metrics": metrics,
        "domain_counts": domain_counts,
        "recent_logs": recent_logs,
        "recent_approvals": recent_approvals,
        "open_exceptions": open_exceptions,
        "suspended_vendors": suspended_vendors,
        "overdue_obligations": overdue_obligations,
        "active_contract_alerts": active_contract_alerts,
        "period_days": period_days,
        "generated_at": timezone.now(),
    }


def get_entity_audit_trail(target_model: str, target_object_id: str) -> Dict[str, Any]:
    """
    Retrieves complete chronological audit log and approval actions for a specific entity.
    """
    logs = list(
        AuditLog.objects.filter(
            target_model__iexact=target_model,
            target_object_id=str(target_object_id),
        )
        .select_related("actor")
        .order_by("timestamp")
    )

    approvals = []
    target_uuid = None
    try:
        target_uuid = uuid.UUID(str(target_object_id))
    except (ValueError, AttributeError, TypeError):
        pass

    if target_uuid:
        approvals = list(
            ApprovalAction.objects.filter(
                target_object_id=target_uuid,
            )
            .select_related("actor", "policy_step")
            .order_by("created_at")
        )

    return {
        "target_model": target_model,
        "target_object_id": target_object_id,
        "logs_count": len(logs),
        "approvals_count": len(approvals),
        "logs": logs,
        "approvals": approvals,
    }


def get_vendor_compliance_audit(
    status: Optional[str] = None,
    kyc_status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    org=None,
) -> Dict[str, Any]:
    """
    Audits vendor onboarding, verification, KYC statuses, and risk profiles.
    When ``org`` is passed, results and summary metrics are scoped to that organization.
    """
    qs = Vendor.objects.select_related("category").prefetch_related("documents", "contracts").all()

    vendor_org_q = _vendor_org_q(org)
    if vendor_org_q:
        qs = qs.filter(vendor_org_q)

    if status:
        qs = qs.filter(status=status)

    if kyc_status:
        if kyc_status == "VERIFIED":
            qs = qs.filter(documents__is_verified=True).distinct()
        elif kyc_status == "UNVERIFIED":
            qs = qs.filter(Q(documents__isnull=True) | Q(documents__is_verified=False)).distinct()

    if search:
        term = search.strip()
        qs = qs.filter(
            Q(legal_name__icontains=term)
            | Q(vendor_number__icontains=term)
            | Q(tax_identification_number__icontains=term)
            | Q(email__icontains=term)
        )

    total_count = qs.count()
    vendors_page = list(qs.order_by("-created_at")[offset : offset + limit])

    # Compute overall compliance statistics (scoped the same way as the results)
    total_vendors = qs.count()
    active_vendors = qs.filter(status=Vendor.STATUS_ACTIVE).count()
    suspended_vendors = qs.filter(
        status__in=[Vendor.STATUS_ON_HOLD, Vendor.STATUS_SUSPENDED]
    ).count()
    draft_or_pending = qs.filter(
        status__in=[Vendor.STATUS_DRAFT, Vendor.STATUS_SUBMITTED, Vendor.STATUS_KYC_REVIEW]
    ).count()

    compliance_rate = (
        round((active_vendors / total_vendors * 100), 2) if total_vendors > 0 else 100.0
    )

    items = []
    for v in vendors_page:
        docs = list(v.documents.all())
        total_docs = len(docs)
        verified_docs = sum(1 for d in docs if d.is_verified)
        active_contracts_count = v.contracts.filter(status=Contract.STATUS_ACTIVE).count()

        items.append(
            {
                "id": str(v.id),
                "vendor_number": v.vendor_number,
                "legal_name": v.legal_name,
                "category": v.category.name if v.category else None,
                "status": v.status,
                "status_display": v.get_status_display(),
                "tax_id": v.tax_identification_number,
                "email": v.email,
                "total_documents": total_docs,
                "verified_documents": verified_docs,
                "kyc_complete": total_docs > 0 and verified_docs == total_docs,
                "active_contracts_count": active_contracts_count,
                "created_at": v.created_at.isoformat(),
                "updated_at": v.updated_at.isoformat(),
            }
        )

    return {
        "summary": {
            "total_vendors": total_vendors,
            "active_vendors": active_vendors,
            "suspended_vendors": suspended_vendors,
            "draft_or_pending": draft_or_pending,
            "compliance_rate": compliance_rate,
        },
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "results": items,
    }


def get_approval_history_audit(
    target_model: Optional[str] = None,
    action: Optional[str] = None,
    actor_id: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[Any] = None,
    end_date: Optional[Any] = None,
    limit: int = 50,
    offset: int = 0,
    org=None,
) -> Dict[str, Any]:
    """
    Audits complete approval governance chain across all entities (PRs, Invoices, Contracts).
    When ``org`` is passed, results and summary metrics are scoped to that organization.
    """
    qs = ApprovalAction.objects.select_related(
        "actor", "policy_step", "policy_step__approver_role"
    ).all()

    org_q = _actor_org_q(org)
    if org_q:
        qs = qs.filter(org_q)

    if target_model:
        qs = qs.filter(target_model_name__iexact=target_model)

    if action:
        qs = qs.filter(action=action)

    if actor_id:
        qs = qs.filter(actor_id=actor_id)

    if start_date:
        qs = qs.filter(created_at__gte=start_date)

    if end_date:
        qs = qs.filter(created_at__lte=end_date)

    if search:
        term = search.strip()
        qs = qs.filter(
            Q(comments__icontains=term)
            | Q(actor__email__icontains=term)
            | Q(target_model_name__icontains=term)
        )

    total_count = qs.count()
    actions_page = list(qs.order_by("-created_at")[offset : offset + limit])

    # Summary metrics
    total_actions = qs.count()
    approved_count = qs.filter(action="APPROVED").count()
    rejected_count = qs.filter(action="REJECTED").count()
    submitted_count = qs.filter(action="SUBMITTED").count()
    delegated_count = qs.filter(action="DELEGATED").count()

    items = []
    for a in actions_page:
        items.append(
            {
                "id": str(a.id),
                "target_object_id": str(a.target_object_id),
                "target_model_name": a.target_model_name,
                "action": a.action,
                "action_display": a.get_action_display(),
                "actor_id": str(a.actor.id) if a.actor else None,
                "actor_email": a.actor.email if a.actor else "System",
                "actor_role": a.actor.role.name if a.actor and a.actor.role else "System",
                "policy_step": a.policy_step.step_number if a.policy_step else None,
                "previous_state": a.previous_state,
                "new_state": a.new_state,
                "comments": a.comments,
                "timestamp": a.created_at.isoformat(),
            }
        )

    return {
        "summary": {
            "total_actions": total_actions,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "submitted_count": submitted_count,
            "delegated_count": delegated_count,
        },
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "results": items,
    }


def get_sourcing_activity_audit(
    status: Optional[str] = None,
    event_type: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[Any] = None,
    end_date: Optional[Any] = None,
    limit: int = 50,
    offset: int = 0,
    org=None,
) -> Dict[str, Any]:
    """
    Audits competitive bidding integrity, sealed bid protection, and award distributions.
    When ``org`` is passed, results and summary metrics are scoped to that organization.
    """
    qs = (
        SourcingEvent.objects.select_related("requisition")
        .prefetch_related("bids", "invitations")
        .all()
    )

    if org:
        qs = qs.filter(
            Q(requisition__department__organization=org)
            | Q(requisition__isnull=True, created_by__department__organization=org)
        )

    if status:
        qs = qs.filter(status=status)

    if event_type:
        qs = qs.filter(event_type=event_type)

    if start_date:
        qs = qs.filter(created_at__gte=start_date)

    if end_date:
        qs = qs.filter(created_at__lte=end_date)

    if search:
        term = search.strip()
        qs = qs.filter(
            Q(event_number__icontains=term)
            | Q(title__icontains=term)
            | Q(description__icontains=term)
        )

    total_count = qs.count()
    events_page = list(qs.order_by("-created_at")[offset : offset + limit])

    now = timezone.now()
    items = []
    for e in events_page:
        bids = list(e.bids.all())
        total_bids = len(bids)
        is_window_open = e.bid_start_date <= now <= e.bid_end_date
        is_sealed_active = (
            e.is_sealed and (now < e.bid_end_date) and (e.status != SourcingEvent.STATUS_AWARDED)
        )

        awarded_bid = next((b for b in bids if b.status == "AWARDED"), None)

        items.append(
            {
                "id": str(e.id),
                "event_number": e.event_number,
                "title": e.title,
                "event_type": e.event_type,
                "event_type_display": e.get_event_type_display(),
                "status": e.status,
                "status_display": e.get_status_display(),
                "is_sealed": e.is_sealed,
                "is_sealed_active": is_sealed_active,
                "bid_start_date": e.bid_start_date.isoformat(),
                "bid_end_date": e.bid_end_date.isoformat(),
                "is_window_open": is_window_open,
                "pr_number": e.requisition.pr_number if e.requisition else None,
                "total_bids": total_bids,
                "awarded_vendor": (
                    awarded_bid.vendor.legal_name if awarded_bid and awarded_bid.vendor else None
                ),
                "awarded_amount": float(awarded_bid.total_bid_amount) if awarded_bid else None,
                "created_at": e.created_at.isoformat(),
            }
        )

    return {
        "summary": {
            "total_events": qs.count(),
            "awarded_events": qs.filter(status=SourcingEvent.STATUS_AWARDED).count(),
            "active_bidding": qs.filter(status=SourcingEvent.STATUS_BID_WINDOW).count(),
            "total_bids_submitted": VendorBid.objects.filter(
                status=VendorBid.STATUS_SUBMITTED,
                event__requisition__department__organization=org,
            ).count()
            if org
            else VendorBid.objects.filter(status=VendorBid.STATUS_SUBMITTED).count(),
        },
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "results": items,
    }


def get_po_changes_audit(
    search: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[Any] = None,
    end_date: Optional[Any] = None,
    limit: int = 50,
    offset: int = 0,
    org=None,
) -> Dict[str, Any]:
    """
    Audits purchase order amendments, change orders, status modifications, and cancellation trails.
    When ``org`` is passed, results and summary metrics are scoped to that organization.
    """
    qs = (
        PurchaseOrder.objects.select_related("vendor", "requisition", "cost_center")
        .prefetch_related("amendments")
        .all()
    )

    if org:
        qs = qs.filter(
            Q(cost_center__department__organization=org)
            | Q(requisition__department__organization=org)
        )

    if status:
        qs = qs.filter(status=status)

    if start_date:
        qs = qs.filter(created_at__gte=start_date)

    if end_date:
        qs = qs.filter(created_at__lte=end_date)

    if search:
        term = search.strip()
        qs = qs.filter(
            Q(po_number__icontains=term)
            | Q(vendor__legal_name__icontains=term)
            | Q(cost_center__name__icontains=term)
        )

    total_count = qs.count()
    pos_page = list(qs.order_by("-updated_at")[offset : offset + limit])

    items = []
    for po in pos_page:
        amendments = list(po.amendments.select_related("requested_by").all())
        items.append(
            {
                "id": str(po.id),
                "po_number": po.po_number,
                "version": po.version,
                "vendor_name": po.vendor.legal_name if po.vendor else None,
                "pr_number": po.requisition.pr_number if po.requisition else None,
                "cost_center": po.cost_center.name if po.cost_center else None,
                "status": po.status,
                "status_display": po.get_status_display(),
                "total_amount": float(po.total_amount),
                "amendments_count": len(amendments),
                "acknowledged_at": po.acknowledged_at.isoformat() if po.acknowledged_at else None,
                "created_at": po.created_at.isoformat(),
                "updated_at": po.updated_at.isoformat(),
                "amendments": [
                    {
                        "amendment_number": a.amendment_number,
                        "reason": a.reason,
                        "requested_by": a.requested_by.email if a.requested_by else "System",
                        "created_at": a.created_at.isoformat(),
                    }
                    for a in amendments
                ],
            }
        )

    return {
        "summary": {
            "total_pos": qs.count(),
            "total_amended_pos": qs.filter(version__gt=1).count(),
            "cancelled_pos": qs.filter(status=PurchaseOrder.STATUS_CANCELLED).count(),
            "completed_pos": qs.filter(status=PurchaseOrder.STATUS_COMPLETED).count(),
        },
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "results": items,
    }


def get_invoice_exceptions_audit(
    status: Optional[str] = None,
    exception_type: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[Any] = None,
    end_date: Optional[Any] = None,
    limit: int = 50,
    offset: int = 0,
    org=None,
) -> Dict[str, Any]:
    """
    Audits 3-way match discrepancies, price/qty variances, and supervisor override resolutions.
    When ``org`` is passed, results and summary metrics are scoped to that organization.
    """
    qs = MatchException.objects.select_related(
        "invoice", "invoice__vendor", "invoice__po", "resolved_by"
    ).all()

    if org:
        qs = qs.filter(invoice__po__requisition__department__organization=org)

    if status:
        qs = qs.filter(status=status)

    if exception_type:
        qs = qs.filter(exception_type=exception_type)

    if start_date:
        qs = qs.filter(created_at__gte=start_date)

    if end_date:
        qs = qs.filter(created_at__lte=end_date)

    if search:
        term = search.strip()
        qs = qs.filter(
            Q(invoice__invoice_number__icontains=term)
            | Q(invoice__vendor__legal_name__icontains=term)
            | Q(description__icontains=term)
            | Q(resolution_notes__icontains=term)
        )

    total_count = qs.count()
    exceptions_page = list(qs.order_by("-created_at")[offset : offset + limit])

    # Summary metrics
    total_exceptions = qs.count()
    open_count = qs.filter(status=MatchException.STATUS_OPEN).count()
    resolved_count = qs.filter(status=MatchException.STATUS_RESOLVED).count()
    rejected_count = qs.filter(status=MatchException.STATUS_REJECTED).count()

    items = []
    for exc in exceptions_page:
        items.append(
            {
                "id": str(exc.id),
                "invoice_number": exc.invoice.invoice_number if exc.invoice else None,
                "po_number": exc.invoice.po.po_number if exc.invoice and exc.invoice.po else None,
                "vendor_name": (
                    exc.invoice.vendor.legal_name if exc.invoice and exc.invoice.vendor else None
                ),
                "invoice_total": float(exc.invoice.total_amount) if exc.invoice else 0.0,
                "exception_type": exc.exception_type,
                "exception_type_display": exc.get_exception_type_display(),
                "status": exc.status,
                "status_display": exc.get_status_display(),
                "variance_amount": float(exc.variance_amount),
                "description": exc.description,
                "resolution_notes": exc.resolution_notes,
                "resolved_by": exc.resolved_by.email if exc.resolved_by else None,
                "created_at": exc.created_at.isoformat(),
            }
        )

    return {
        "summary": {
            "total_exceptions": total_exceptions,
            "open_exceptions": open_count,
            "resolved_exceptions": resolved_count,
            "rejected_invoices": rejected_count,
        },
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "results": items,
    }


def get_contract_changes_audit(
    search: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[Any] = None,
    end_date: Optional[Any] = None,
    limit: int = 50,
    offset: int = 0,
    org=None,
) -> Dict[str, Any]:
    """
    Audits legal contract modifications, version amendments, milestone completions, and obligation tracking.
    When ``org`` is passed, results and summary metrics are scoped to that organization.
    """
    qs = (
        Contract.objects.select_related("vendor", "contract_owner")
        .prefetch_related("versions", "milestones", "obligations", "alerts")
        .all()
    )

    if org:
        qs = qs.filter(
            Q(contract_owner__organization=org)
            | Q(contract_owner__department__organization=org)
            | Q(po__cost_center__department__organization=org)
        )

    if status:
        qs = qs.filter(status=status)

    if start_date:
        qs = qs.filter(created_at__gte=start_date)

    if end_date:
        qs = qs.filter(created_at__lte=end_date)

    if search:
        term = search.strip()
        qs = qs.filter(
            Q(contract_number__icontains=term)
            | Q(title__icontains=term)
            | Q(vendor__legal_name__icontains=term)
        )

    total_count = qs.count()
    contracts_page = list(qs.order_by("-updated_at")[offset : offset + limit])

    today = timezone.now().date()
    items = []
    for con in contracts_page:
        versions = list(con.versions.all())
        milestones = list(con.milestones.all())
        obligations = list(con.obligations.all())
        alerts = list(con.alerts.all())

        overdue_ob_count = sum(1 for o in obligations if not o.is_fulfilled and o.due_date < today)
        completed_milestones = sum(1 for m in milestones if m.is_completed)

        items.append(
            {
                "id": str(con.id),
                "contract_number": con.contract_number,
                "title": con.title,
                "version": con.version,
                "vendor_name": con.vendor.legal_name if con.vendor else None,
                "status": con.status,
                "status_display": con.get_status_display(),
                "contract_value": float(con.contract_value),
                "start_date": str(con.start_date),
                "end_date": str(con.end_date),
                "owner_email": con.contract_owner.email if con.contract_owner else None,
                "versions_count": len(versions),
                "milestones_total": len(milestones),
                "milestones_completed": completed_milestones,
                "obligations_total": len(obligations),
                "overdue_obligations": overdue_ob_count,
                "active_alerts_count": sum(1 for a in alerts if not a.is_processed),
                "created_at": con.created_at.isoformat(),
                "updated_at": con.updated_at.isoformat(),
            }
        )

    return {
        "summary": {
            "total_contracts": qs.count(),
            "active_contracts": qs.filter(status=Contract.STATUS_ACTIVE).count(),
            "amended_contracts": qs.filter(version__gt=1).count(),
            "total_overdue_obligations": ContractObligation.objects.filter(
                is_fulfilled=False,
                due_date__lt=today,
                contract__in=qs,
            ).count(),
        },
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "results": items,
    }


def get_security_events_audit(
    actor_id: Optional[str] = None,
    action: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[Any] = None,
    end_date: Optional[Any] = None,
    limit: int = 50,
    offset: int = 0,
    org=None,
) -> Dict[str, Any]:
    """
    Audits security, authentication (login/logout), export operations, and high-risk administrative overrides.
    When ``org`` is passed, results are scoped to that organization.
    """
    security_actions = [
        AuditLog.ACTION_LOGIN,
        AuditLog.ACTION_LOGOUT,
        AuditLog.ACTION_EXPORT,
        AuditLog.ACTION_OVERRIDE,
        AuditLog.ACTION_DELETE,
        AuditLog.ACTION_CANCEL,
    ]

    qs = AuditLog.objects.filter(
        Q(action__in=security_actions)
        | Q(target_model__in=["User", "Role", "ExportJob", "Session", "Permission"])
    ).select_related("actor")

    org_q = _actor_org_q(org)
    if org_q:
        qs = qs.filter(org_q)

    if action:
        qs = qs.filter(action=action)

    if actor_id:
        qs = qs.filter(actor_id=actor_id)

    if start_date:
        qs = qs.filter(timestamp__gte=start_date)

    if end_date:
        qs = qs.filter(timestamp__lte=end_date)

    if search:
        term = search.strip()
        qs = qs.filter(
            Q(actor__email__icontains=term)
            | Q(ip_address__icontains=term)
            | Q(request_id__icontains=term)
            | Q(target_model__icontains=term)
        )

    total_count = qs.count()
    events_page = list(qs.order_by("-timestamp")[offset : offset + limit])

    items = []
    for log in events_page:
        items.append(
            {
                "id": str(log.id),
                "timestamp": log.timestamp.isoformat(),
                "actor_id": str(log.actor.id) if log.actor else None,
                "actor_email": log.actor.email if log.actor else "System / Anonymous",
                "actor_role": log.actor.role.name if log.actor and log.actor.role else "System",
                "action": log.action,
                "action_display": log.get_action_display(),
                "target_model": log.target_model,
                "target_object_id": log.target_object_id,
                "ip_address": log.ip_address,
                "request_id": log.request_id,
                "user_agent": log.user_agent,
            }
        )

    return {
        "summary": {
            "total_security_events": qs.count(),
            "logins_count": qs.filter(action=AuditLog.ACTION_LOGIN).count(),
            "logouts_count": qs.filter(action=AuditLog.ACTION_LOGOUT).count(),
            "exports_count": qs.filter(action=AuditLog.ACTION_EXPORT).count(),
            "overrides_count": qs.filter(action=AuditLog.ACTION_OVERRIDE).count(),
        },
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "results": items,
    }
