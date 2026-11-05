from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsProcurementManager
from apps.budgets.models import Budget, SpendLedger
from apps.invoices.models import MatchException, SupplierInvoice
from apps.notifications.models import Notification
from apps.orders.models import POAmendment, PurchaseOrder
from apps.organization.models import Department, FiscalPeriod
from apps.receipts.models import GoodsReceipt, InspectionRecord, RejectionRecord
from apps.requisitions.models import PurchaseRequisition
from apps.scorecards.models import VendorScorecard
from apps.sourcing.models import SourcingEvent
from apps.vendors.models import Vendor, VendorRiskRecord


def get_user_org(user):
    if not user or not user.is_authenticated or user.is_superuser:
        return None
    return getattr(user, "effective_organization", None) or getattr(user, "organization", None)


class ManagerKPIsAPIView(APIView):
    """
    Returns real database-backed high-level KPIs for the Procurement Manager governance desk.
    """

    permission_classes = [IsAuthenticated, IsProcurementManager]

    def get(self, request):
        now = timezone.now()
        org = get_user_org(request.user)

        # 1. Pending Award Approvals
        pending_awards_qs = SourcingEvent.objects.filter(
            status__in=[
                SourcingEvent.STATUS_AWARD_APPROVAL,
                SourcingEvent.STATUS_COMMERCIAL_REVIEW,
                SourcingEvent.STATUS_TECHNICAL_REVIEW,
            ]
        )
        if org:
            is_hpe_org = org.code in ["ORG-HPE-01", "HPE-GLOBAL"] or "Hewlett Packard" in org.name
            org_filter = (
                Q(requisition__department__organization=org)
                | Q(requisition__requester__organization=org)
                | Q(created_by__organization=org)
                | Q(created_by__department__organization=org)
            )
            if is_hpe_org:
                org_filter |= Q(requisition__isnull=True, created_by__isnull=True)
            pending_awards_qs = pending_awards_qs.filter(org_filter)
        elif not request.user.is_superuser:
            pending_awards_qs = pending_awards_qs.none()
        pending_awards_count = pending_awards_qs.count()

        # 2. PR Bottlenecks & Aging (>3 days or pending review)
        pending_prs_qs = PurchaseRequisition.objects.filter(
            status__in=[
                PurchaseRequisition.STATUS_SUBMITTED,
                PurchaseRequisition.STATUS_MANAGER_REVIEW,
                PurchaseRequisition.STATUS_BUDGET_REVIEW,
            ]
        )
        if org:
            pending_prs_qs = pending_prs_qs.filter(department__organization=org)
        pr_bottlenecks_count = pending_prs_qs.count()
        pr_bottlenecks_value = pending_prs_qs.aggregate(total=Sum("total_amount"))[
            "total"
        ] or Decimal("0.00")

        # 3. Active Purchase Orders
        active_pos_qs = PurchaseOrder.objects.filter(
            status__in=[
                PurchaseOrder.STATUS_ISSUED,
                PurchaseOrder.STATUS_ACKNOWLEDGED,
                PurchaseOrder.STATUS_PARTIAL_RECEIPT,
            ]
        )
        if org:
            active_pos_qs = active_pos_qs.filter(cost_center__department__organization=org)
        active_pos_count = active_pos_qs.count()
        active_pos_value = active_pos_qs.aggregate(total=Sum("total_amount"))["total"] or Decimal(
            "0.00"
        )

        # 4. High-Risk & Suspended Vendors
        # High risk records or vendors currently on hold/suspended
        high_risk_qs = VendorRiskRecord.objects.filter(
            risk_level=VendorRiskRecord.RISK_LEVEL_HIGH
        )
        held_vendor_qs = Vendor.objects.filter(
            status__in=[Vendor.STATUS_ON_HOLD, Vendor.STATUS_SUSPENDED]
        )
        if org:
            high_risk_qs = high_risk_qs.filter(vendor__organization=org)
            held_vendor_qs = held_vendor_qs.filter(organization=org)
        elif not request.user.is_superuser:
            high_risk_qs = high_risk_qs.none()
            held_vendor_qs = held_vendor_qs.none()
        high_risk_vendor_ids = set(high_risk_qs.values_list("vendor_id", flat=True))
        held_vendor_ids = set(held_vendor_qs.values_list("id", flat=True))
        high_risk_vendors_count = len(high_risk_vendor_ids.union(held_vendor_ids))

        # 5. Pending KYC Reviews
        kyc_reviews_qs = Vendor.objects.filter(
            status__in=[Vendor.STATUS_SUBMITTED, Vendor.STATUS_KYC_REVIEW]
        )
        if org:
            kyc_reviews_qs = kyc_reviews_qs.filter(organization=org)
        elif not request.user.is_superuser:
            kyc_reviews_qs = kyc_reviews_qs.none()
        kyc_reviews_count = kyc_reviews_qs.count()

        # 6. Spend & Budgets
        budget_qs = Budget.objects.all()
        spend_qs = SpendLedger.objects.all()
        if org:
            budget_qs = budget_qs.filter(cost_center__department__organization=org)
            spend_qs = spend_qs.filter(budget__cost_center__department__organization=org)

        allocated_budget = budget_qs.aggregate(total=Sum("allocated_amount"))["total"] or Decimal(
            "0.00"
        )
        committed_spend = spend_qs.filter(entry_type=SpendLedger.ENTRY_COMMITMENT).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")
        actual_spend = spend_qs.filter(entry_type=SpendLedger.ENTRY_ACTUAL).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")

        # 7. Sourcing Events & Supplier Performance
        open_sourcing_qs = SourcingEvent.objects.filter(
            status__in=[SourcingEvent.STATUS_PUBLISHED, SourcingEvent.STATUS_BID_WINDOW]
        )
        if org:
            open_sourcing_qs = open_sourcing_qs.filter(requisition__department__organization=org)
        open_sourcing_count = open_sourcing_qs.count()
        sc_qs = VendorScorecard.objects.all()
        if org:
            sc_qs = sc_qs.filter(vendor__organization=org)
        elif not request.user.is_superuser:
            sc_qs = sc_qs.none()
        avg_scorecard = sc_qs.aggregate(avg=Avg("composite_score"))["avg"] or Decimal("0.00")

        # 8. Unread Governance Notifications
        unread_notifications = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count()

        # 9. Invoice Exceptions Pending
        exceptions_qs = MatchException.objects.filter(status=MatchException.STATUS_OPEN)
        if org:
            exceptions_qs = exceptions_qs.filter(
                invoice__po__cost_center__department__organization=org
            )
        open_invoice_exceptions = exceptions_qs.count()

        # 10. Core 4-Pillar Governance Metrics (HPE-PRD-2026-PRD001 Section 3.2)
        # Pillar 1: Approval Oversight
        pending_approvals_qs = PurchaseRequisition.objects.filter(
            status__in=[
                PurchaseRequisition.STATUS_SUBMITTED,
                PurchaseRequisition.STATUS_MANAGER_REVIEW,
            ]
        )
        if org:
            pending_approvals_qs = pending_approvals_qs.filter(department__organization=org)
        pending_approvals_count = pending_approvals_qs.count()

        # Pillar 2: Policy Exceptions (Budget overruns + 3-way invoice match exceptions)
        budget_review_prs_qs = PurchaseRequisition.objects.filter(
            status=PurchaseRequisition.STATUS_BUDGET_REVIEW
        )
        if org:
            budget_review_prs_qs = budget_review_prs_qs.filter(department__organization=org)
        budget_overruns_count = budget_review_prs_qs.count()
        policy_exceptions_count = budget_overruns_count + open_invoice_exceptions

        data = {
            "timestamp": now.isoformat(),
            "pending_approvals_count": pending_approvals_count,
            "policy_exceptions_count": policy_exceptions_count,
            "budget_overruns_count": budget_overruns_count,
            "pending_awards_count": pending_awards_count,
            "pr_bottlenecks_count": pr_bottlenecks_count,
            "pr_bottlenecks_value": float(pr_bottlenecks_value),
            "active_pos_count": active_pos_count,
            "active_pos_value": float(active_pos_value),
            "high_risk_vendors_count": high_risk_vendors_count,
            "kyc_reviews_count": kyc_reviews_count,
            "open_sourcing_events_count": open_sourcing_count,
            "allocated_budget_total": float(allocated_budget),
            "committed_spend_total": float(committed_spend),
            "actual_spend_total": float(actual_spend),
            "avg_supplier_performance": round(float(avg_scorecard), 1),
            "unread_notifications_count": unread_notifications,
            "open_invoice_exceptions": open_invoice_exceptions,
        }

        return Response(data, status=status.HTTP_200_OK)


class ManagerPipelineAPIView(APIView):
    """
    Returns real procurement lifecycle distribution across all core stages:
    PR -> Sourcing -> Evaluation/Award -> PO -> Receipt/Inspection -> Invoice.
    Also supports item-level listing, multi-dimensional filtering, searching,
    and server-side pagination for the manager pipeline governance desk.
    """

    permission_classes = [IsAuthenticated, IsProcurementManager]

    def get(self, request):
        now = timezone.now()
        org = get_user_org(request.user)

        # 1. Requisitions (PR) Funnel Aggregations
        prs = (
            PurchaseRequisition.objects.filter(department__organization=org)
            if org
            else PurchaseRequisition.objects.all()
        )
        pr_submitted_qs = prs.filter(status=PurchaseRequisition.STATUS_SUBMITTED)
        pr_mgr_review_qs = prs.filter(status=PurchaseRequisition.STATUS_MANAGER_REVIEW)
        pr_budget_review_qs = prs.filter(status=PurchaseRequisition.STATUS_BUDGET_REVIEW)
        pr_approved_qs = prs.filter(status=PurchaseRequisition.STATUS_APPROVED)
        pr_rejected_qs = prs.filter(status=PurchaseRequisition.STATUS_REJECTED)
        pr_sourcing_qs = prs.filter(status=PurchaseRequisition.STATUS_SOURCING)

        requisitions_data = {
            "submitted": {
                "count": pr_submitted_qs.count(),
                "amount": float(pr_submitted_qs.aggregate(total=Sum("total_amount"))["total"] or 0),
            },
            "manager_review": {
                "count": pr_mgr_review_qs.count(),
                "amount": float(
                    pr_mgr_review_qs.aggregate(total=Sum("total_amount"))["total"] or 0
                ),
            },
            "budget_review": {
                "count": pr_budget_review_qs.count(),
                "amount": float(
                    pr_budget_review_qs.aggregate(total=Sum("total_amount"))["total"] or 0
                ),
            },
            "approved": {
                "count": pr_approved_qs.count(),
                "amount": float(pr_approved_qs.aggregate(total=Sum("total_amount"))["total"] or 0),
            },
            "in_sourcing": {
                "count": pr_sourcing_qs.count(),
                "amount": float(pr_sourcing_qs.aggregate(total=Sum("total_amount"))["total"] or 0),
            },
            "rejected": {
                "count": pr_rejected_qs.count(),
                "amount": float(pr_rejected_qs.aggregate(total=Sum("total_amount"))["total"] or 0),
            },
            "total_count": prs.count(),
            "total_amount": float(prs.aggregate(total=Sum("total_amount"))["total"] or 0),
        }

        # 2. Sourcing Events (RFQ/RFP)
        if org:
            is_hpe_org = org.code in ["ORG-HPE-01", "HPE-GLOBAL"] or "Hewlett Packard" in org.name
            org_filter = (
                Q(requisition__department__organization=org)
                | Q(requisition__requester__organization=org)
                | Q(created_by__organization=org)
                | Q(created_by__department__organization=org)
            )
            if is_hpe_org:
                org_filter |= Q(requisition__isnull=True, created_by__isnull=True)
            events = SourcingEvent.objects.filter(org_filter)
        elif not request.user.is_superuser:
            events = SourcingEvent.objects.none()
        else:
            events = SourcingEvent.objects.all()
        sourcing_data = {
            "draft": events.filter(status=SourcingEvent.STATUS_DRAFT).count(),
            "published": events.filter(status=SourcingEvent.STATUS_PUBLISHED).count(),
            "bid_window_open": events.filter(status=SourcingEvent.STATUS_BID_WINDOW).count(),
            "technical_review": events.filter(status=SourcingEvent.STATUS_TECHNICAL_REVIEW).count(),
            "commercial_review": events.filter(
                status=SourcingEvent.STATUS_COMMERCIAL_REVIEW
            ).count(),
            "award_approval": events.filter(status=SourcingEvent.STATUS_AWARD_APPROVAL).count(),
            "awarded": events.filter(status=SourcingEvent.STATUS_AWARDED).count(),
            "cancelled": events.filter(status=SourcingEvent.STATUS_CANCELLED).count(),
            "total_events": events.count(),
        }

        # 3. Purchase Orders (PO)
        pos = (
            PurchaseOrder.objects.filter(cost_center__department__organization=org)
            if org
            else PurchaseOrder.objects.all()
        )
        orders_data = {
            "draft": {
                "count": pos.filter(status=PurchaseOrder.STATUS_DRAFT).count(),
                "amount": float(
                    pos.filter(status=PurchaseOrder.STATUS_DRAFT).aggregate(
                        total=Sum("total_amount")
                    )["total"]
                    or 0
                ),
            },
            "in_approval": {
                "count": pos.filter(status=PurchaseOrder.STATUS_APPROVAL).count(),
                "amount": float(
                    pos.filter(status=PurchaseOrder.STATUS_APPROVAL).aggregate(
                        total=Sum("total_amount")
                    )["total"]
                    or 0
                ),
            },
            "issued": {
                "count": pos.filter(status=PurchaseOrder.STATUS_ISSUED).count(),
                "amount": float(
                    pos.filter(status=PurchaseOrder.STATUS_ISSUED).aggregate(
                        total=Sum("total_amount")
                    )["total"]
                    or 0
                ),
            },
            "acknowledged": {
                "count": pos.filter(status=PurchaseOrder.STATUS_ACKNOWLEDGED).count(),
                "amount": float(
                    pos.filter(status=PurchaseOrder.STATUS_ACKNOWLEDGED).aggregate(
                        total=Sum("total_amount")
                    )["total"]
                    or 0
                ),
            },
            "partial_receipt": {
                "count": pos.filter(status=PurchaseOrder.STATUS_PARTIAL_RECEIPT).count(),
                "amount": float(
                    pos.filter(status=PurchaseOrder.STATUS_PARTIAL_RECEIPT).aggregate(
                        total=Sum("total_amount")
                    )["total"]
                    or 0
                ),
            },
            "completed": {
                "count": pos.filter(status=PurchaseOrder.STATUS_COMPLETED).count(),
                "amount": float(
                    pos.filter(status=PurchaseOrder.STATUS_COMPLETED).aggregate(
                        total=Sum("total_amount")
                    )["total"]
                    or 0
                ),
            },
            "cancelled": {
                "count": pos.filter(status=PurchaseOrder.STATUS_CANCELLED).count(),
                "amount": float(
                    pos.filter(status=PurchaseOrder.STATUS_CANCELLED).aggregate(
                        total=Sum("total_amount")
                    )["total"]
                    or 0
                ),
            },
            "total_pos": pos.count(),
            "total_po_value": float(pos.aggregate(total=Sum("total_amount"))["total"] or 0),
        }

        # 4. Receipts & Inspection
        grns_qs = (
            GoodsReceipt.objects.filter(po__cost_center__department__organization=org)
            if org
            else GoodsReceipt.objects.all()
        )
        total_grns = grns_qs.count()
        inspections = (
            InspectionRecord.objects.filter(
                receipt_line__receipt__po__cost_center__department__organization=org
            )
            if org
            else InspectionRecord.objects.all()
        )
        inspections_passed = inspections.filter(passed=True).count()
        inspections_failed = inspections.filter(passed=False).count()
        rejections_qs = (
            RejectionRecord.objects.filter(
                receipt_line__receipt__po__cost_center__department__organization=org
            )
            if org
            else RejectionRecord.objects.all()
        )
        total_rejections = rejections_qs.count()

        receipts_data = {
            "total_grns": total_grns,
            "inspections_passed": inspections_passed,
            "inspections_failed": inspections_failed,
            "total_rejections": total_rejections,
        }

        # 5. Invoices & 3-Way Match
        invoices = (
            SupplierInvoice.objects.filter(po__cost_center__department__organization=org)
            if org
            else SupplierInvoice.objects.all()
        )
        exceptions_open_qs = MatchException.objects.filter(status=MatchException.STATUS_OPEN)
        if org:
            exceptions_open_qs = exceptions_open_qs.filter(
                invoice__po__cost_center__department__organization=org
            )
        invoices_data = {
            "received": invoices.filter(status=SupplierInvoice.STATUS_RECEIVED).count(),
            "matching": invoices.filter(status=SupplierInvoice.STATUS_MATCHING).count(),
            "exceptions_open": {
                "count": exceptions_open_qs.count(),
                "variance_amount": float(
                    exceptions_open_qs.aggregate(total=Sum("variance_amount"))["total"] or 0
                ),
            },
            "ready_for_payment": {
                "count": invoices.filter(status=SupplierInvoice.STATUS_READY_FOR_PAYMENT).count(),
                "amount": float(
                    invoices.filter(status=SupplierInvoice.STATUS_READY_FOR_PAYMENT).aggregate(
                        total=Sum("total_amount")
                    )["total"]
                    or 0
                ),
            },
            "paid": {
                "count": invoices.filter(status=SupplierInvoice.STATUS_PAID).count(),
                "amount": float(
                    invoices.filter(status=SupplierInvoice.STATUS_PAID).aggregate(
                        total=Sum("total_amount")
                    )["total"]
                    or 0
                ),
            },
            "total_invoices": invoices.count(),
        }

        # 6. Overall Pipeline Summary Metrics
        active_pr_statuses = [
            PurchaseRequisition.STATUS_SUBMITTED,
            PurchaseRequisition.STATUS_MANAGER_REVIEW,
            PurchaseRequisition.STATUS_BUDGET_REVIEW,
            PurchaseRequisition.STATUS_APPROVED,
            PurchaseRequisition.STATUS_SOURCING,
        ]
        active_prs_qs = prs.filter(status__in=active_pr_statuses)
        active_prs_count = active_prs_qs.count()
        active_prs_amount = float(active_prs_qs.aggregate(total=Sum("total_amount"))["total"] or 0)

        approval_pending_statuses = [
            PurchaseRequisition.STATUS_SUBMITTED,
            PurchaseRequisition.STATUS_MANAGER_REVIEW,
            PurchaseRequisition.STATUS_BUDGET_REVIEW,
        ]
        approval_pending_qs = prs.filter(status__in=approval_pending_statuses)
        approval_pending_count = approval_pending_qs.count()
        approval_pending_amount = float(
            approval_pending_qs.aggregate(total=Sum("total_amount"))["total"] or 0
        )

        sourcing_in_progress_count = events.filter(
            status__in=[
                SourcingEvent.STATUS_PUBLISHED,
                SourcingEvent.STATUS_BID_WINDOW,
                SourcingEvent.STATUS_TECHNICAL_REVIEW,
                SourcingEvent.STATUS_COMMERCIAL_REVIEW,
                SourcingEvent.STATUS_AWARD_APPROVAL,
            ]
        ).count()

        active_pos_qs = pos.filter(
            status__in=[
                PurchaseOrder.STATUS_ISSUED,
                PurchaseOrder.STATUS_ACKNOWLEDGED,
                PurchaseOrder.STATUS_PARTIAL_RECEIPT,
            ]
        )
        active_pos_count = active_pos_qs.count()
        active_pos_amount = float(active_pos_qs.aggregate(total=Sum("total_amount"))["total"] or 0)

        # Bottleneck PRs: pending approval >= 3 days
        bottlenecks_cutoff = now - timezone.timedelta(days=3)
        bottleneck_prs_qs = approval_pending_qs.filter(created_at__lte=bottlenecks_cutoff)
        bottlenecks_count = bottleneck_prs_qs.count()
        bottlenecks_amount = float(
            bottleneck_prs_qs.aggregate(total=Sum("total_amount"))["total"] or 0
        )

        total_pipeline_value = active_prs_amount + active_pos_amount

        summary_data = {
            "total_active_prs": active_prs_count,
            "total_active_pr_value": active_prs_amount,
            "total_pipeline_value": total_pipeline_value,
            "approval_pending_count": approval_pending_count,
            "approval_pending_amount": approval_pending_amount,
            "sourcing_in_progress_count": sourcing_in_progress_count,
            "active_pos_count": active_pos_count,
            "active_pos_value": active_pos_amount,
            "bottlenecks_count": bottlenecks_count,
            "bottlenecks_amount": bottlenecks_amount,
            "receipts_pending_inspection": receipts_data["total_grns"]
            - (receipts_data["inspections_passed"] + receipts_data["inspections_failed"]),
        }

        # 7. Filtered Requisitions Table / Record List
        filtered_prs = prs.select_related("requester", "department", "cost_center")

        # Stage filter
        stage_filter = request.GET.get("stage", "all").strip().lower()
        if stage_filter == "active":
            filtered_prs = filtered_prs.filter(status__in=active_pr_statuses)
        elif stage_filter == "pending_approval":
            filtered_prs = filtered_prs.filter(status__in=approval_pending_statuses)
        elif stage_filter == "submitted":
            filtered_prs = filtered_prs.filter(status=PurchaseRequisition.STATUS_SUBMITTED)
        elif stage_filter == "manager_review":
            filtered_prs = filtered_prs.filter(status=PurchaseRequisition.STATUS_MANAGER_REVIEW)
        elif stage_filter == "budget_review":
            filtered_prs = filtered_prs.filter(status=PurchaseRequisition.STATUS_BUDGET_REVIEW)
        elif stage_filter == "approved":
            filtered_prs = filtered_prs.filter(status=PurchaseRequisition.STATUS_APPROVED)
        elif stage_filter in ["sourcing", "in_sourcing"]:
            filtered_prs = filtered_prs.filter(status=PurchaseRequisition.STATUS_SOURCING)
        elif stage_filter == "po_issued":
            filtered_prs = filtered_prs.filter(status=PurchaseRequisition.STATUS_PO_ISSUED)
        elif stage_filter == "draft":
            filtered_prs = filtered_prs.filter(status=PurchaseRequisition.STATUS_DRAFT)
        elif stage_filter == "rejected":
            filtered_prs = filtered_prs.filter(status=PurchaseRequisition.STATUS_REJECTED)
        elif stage_filter == "cancelled":
            filtered_prs = filtered_prs.filter(status=PurchaseRequisition.STATUS_CANCELLED)
        elif stage_filter == "bottlenecks":
            filtered_prs = filtered_prs.filter(
                status__in=approval_pending_statuses, created_at__lte=bottlenecks_cutoff
            )

        # Status filter
        status_filter = request.GET.get("status")
        if status_filter:
            filtered_prs = filtered_prs.filter(status=status_filter)

        # Department filter
        dept_filter = request.GET.get("department")
        if dept_filter:
            filtered_prs = filtered_prs.filter(department_id=dept_filter)

        # Search query
        search_query = request.GET.get("search", "").strip()
        if search_query:
            filtered_prs = filtered_prs.filter(
                Q(pr_number__icontains=search_query)
                | Q(title__icontains=search_query)
                | Q(requester__email__icontains=search_query)
                | Q(department__name__icontains=search_query)
                | Q(department__code__icontains=search_query)
                | Q(cost_center__code__icontains=search_query)
            )

        # Aging bracket filter
        aging_filter = request.GET.get("aging")
        if aging_filter == "under_3d":
            filtered_prs = filtered_prs.filter(created_at__gte=now - timezone.timedelta(days=3))
        elif aging_filter == "3_to_7d":
            filtered_prs = filtered_prs.filter(
                created_at__lt=now - timezone.timedelta(days=3),
                created_at__gte=now - timezone.timedelta(days=7),
            )
        elif aging_filter == "7_to_14d":
            filtered_prs = filtered_prs.filter(
                created_at__lt=now - timezone.timedelta(days=7),
                created_at__gte=now - timezone.timedelta(days=14),
            )
        elif aging_filter == "over_14d":
            filtered_prs = filtered_prs.filter(created_at__lt=now - timezone.timedelta(days=14))

        # Sorting
        sort_by = request.GET.get("sort_by", "date_desc")
        if sort_by == "date_asc":
            filtered_prs = filtered_prs.order_by("created_at")
        elif sort_by == "amount_desc":
            filtered_prs = filtered_prs.order_by("-total_amount")
        elif sort_by == "amount_asc":
            filtered_prs = filtered_prs.order_by("total_amount")
        elif sort_by == "age_desc":
            filtered_prs = filtered_prs.order_by("created_at")
        else:
            filtered_prs = filtered_prs.order_by("-created_at")

        # Pagination
        try:
            page_num = max(1, int(request.GET.get("page", 1)))
        except (ValueError, TypeError):
            page_num = 1

        try:
            page_size = min(100, max(1, int(request.GET.get("page_size", 10))))
        except (ValueError, TypeError):
            page_size = 10

        paginator = Paginator(filtered_prs, page_size)
        current_page_obj = paginator.get_page(page_num)

        items_data = []
        for pr in current_page_obj:
            age_days = (now.date() - pr.created_at.date()).days

            # Pending approver role attribution
            if pr.status == PurchaseRequisition.STATUS_SUBMITTED:
                pending_approver = "Department Approver"
            elif pr.status == PurchaseRequisition.STATUS_MANAGER_REVIEW:
                pending_approver = "Procurement Manager"
            elif pr.status == PurchaseRequisition.STATUS_BUDGET_REVIEW:
                pending_approver = "Finance / Budget Specialist"
            elif pr.status == PurchaseRequisition.STATUS_APPROVED:
                pending_approver = "Procurement Executive (Sourcing)"
            elif pr.status == PurchaseRequisition.STATUS_SOURCING:
                pending_approver = "Sourcing Desk (Bidding / Award)"
            elif pr.status == PurchaseRequisition.STATUS_PO_ISSUED:
                pending_approver = "Vendor (Fulfillment)"
            else:
                pending_approver = "None"

            is_bottleneck = pr.status in approval_pending_statuses and age_days >= 3

            items_data.append(
                {
                    "id": str(pr.id),
                    "pr_number": pr.pr_number,
                    "title": pr.title,
                    "justification": pr.justification,
                    "requester_id": str(pr.requester.id),
                    "requester_email": pr.requester.email,
                    "department_id": str(pr.department.id) if pr.department else None,
                    "department_name": pr.department.name if pr.department else "N/A",
                    "department_code": pr.department.code if pr.department else "N/A",
                    "cost_center_code": pr.cost_center.code if pr.cost_center else "N/A",
                    "total_amount": float(pr.total_amount),
                    "status": pr.status,
                    "status_display": pr.get_status_display(),
                    "created_at": pr.created_at.isoformat(),
                    "requested_delivery_date": (
                        pr.requested_delivery_date.isoformat()
                        if pr.requested_delivery_date
                        else None
                    ),
                    "age_days": age_days,
                    "pending_approver": pending_approver,
                    "is_bottleneck": is_bottleneck,
                }
            )

        # List of departments for filter dropdown
        depts_qs = (
            Department.objects.filter(organization=org) if org else Department.objects.all()
        ).order_by("name")
        departments_data = [{"id": str(d.id), "name": d.name, "code": d.code} for d in depts_qs]

        pipeline_response = {
            "summary": summary_data,
            "requisitions": requisitions_data,
            "sourcing": sourcing_data,
            "orders": orders_data,
            "receipts": receipts_data,
            "invoices": invoices_data,
            "items": items_data,
            "pagination": {
                "total_count": paginator.count,
                "page": current_page_obj.number,
                "page_size": page_size,
                "total_pages": paginator.num_pages,
                "has_next": current_page_obj.has_next(),
                "has_previous": current_page_obj.has_previous(),
            },
            "departments": departments_data,
        }

        return Response(pipeline_response, status=status.HTTP_200_OK)


class ManagerPRAgingAPIView(APIView):
    """
    Returns real PR aging data categorized by standard SLA aging brackets:
    - Under 3 days (< 3d)
    - 3 to 7 days (3_to_7d)
    - 7 to 14 days (7_to_14d)
    - Over 14 days (over_14d)
    Includes pending approver, bottleneck attribution, department bottleneck breakdown,
    and server-side filtered/paginated PR records.
    """

    permission_classes = [IsAuthenticated, IsProcurementManager]

    def get(self, request):
        now = timezone.now()
        org = get_user_org(request.user)
        bracket_filter = request.GET.get("bracket", "all").strip().lower()
        dept_filter = request.GET.get("department")
        status_filter = request.GET.get("status")
        search_query = request.GET.get("search", "").strip()
        sort_by = request.GET.get("sort_by", "age_desc")

        base_pending_prs = PurchaseRequisition.objects.filter(
            status__in=[
                PurchaseRequisition.STATUS_SUBMITTED,
                PurchaseRequisition.STATUS_MANAGER_REVIEW,
                PurchaseRequisition.STATUS_BUDGET_REVIEW,
            ]
        ).select_related("requester", "department", "cost_center")

        if org:
            base_pending_prs = base_pending_prs.filter(department__organization=org)

        # 1. Compute summary brackets across all pending PRs in scope
        bracket_under_3d = []
        bracket_3_to_7d = []
        bracket_7_to_14d = []
        bracket_over_14d = []
        all_unfiltered_items = []

        # Department aggregation mapping: dept_id -> stats
        dept_stats = {}

        for pr in base_pending_prs.order_by("-created_at"):
            age_days = (now.date() - pr.created_at.date()).days
            if age_days < 3:
                b_code = "under_3d"
                b_label = "< 3 Days"
                severity = "normal"
            elif 3 <= age_days <= 7:
                b_code = "3_to_7d"
                b_label = "3–7 Days"
                severity = "aging"
            elif 7 < age_days <= 14:
                b_code = "7_to_14d"
                b_label = "7–14 Days"
                severity = "bottleneck"
            else:
                b_code = "over_14d"
                b_label = "> 14 Days"
                severity = "critical"

            if pr.status == PurchaseRequisition.STATUS_SUBMITTED:
                pending_approver = "Department Approver"
            elif pr.status == PurchaseRequisition.STATUS_MANAGER_REVIEW:
                pending_approver = "Procurement Manager"
            elif pr.status == PurchaseRequisition.STATUS_BUDGET_REVIEW:
                pending_approver = "Finance / Budget Specialist"
            else:
                pending_approver = "Workflow Approver"

            item_data = {
                "id": str(pr.id),
                "pr_number": pr.pr_number,
                "title": pr.title,
                "justification": pr.justification,
                "requester_id": str(pr.requester.id),
                "requester_email": pr.requester.email,
                "department_id": str(pr.department.id) if pr.department else None,
                "department_name": pr.department.name if pr.department else "N/A",
                "department_code": pr.department.code if pr.department else "N/A",
                "cost_center_code": pr.cost_center.code if pr.cost_center else "N/A",
                "total_amount": float(pr.total_amount),
                "status": pr.status,
                "status_display": pr.get_status_display(),
                "created_at": pr.created_at.isoformat(),
                "age_days": age_days,
                "aging_bracket": b_code,
                "aging_bracket_display": b_label,
                "severity": severity,
                "pending_approver": pending_approver,
            }

            if b_code == "under_3d":
                bracket_under_3d.append(item_data)
            elif b_code == "3_to_7d":
                bracket_3_to_7d.append(item_data)
            elif b_code == "7_to_14d":
                bracket_7_to_14d.append(item_data)
            else:
                bracket_over_14d.append(item_data)

            all_unfiltered_items.append(item_data)

            # Department breakdown aggregation
            d_id = str(pr.department.id) if pr.department else "unassigned"
            d_name = pr.department.name if pr.department else "Unassigned"
            d_code = pr.department.code if pr.department else "N/A"
            if d_id not in dept_stats:
                dept_stats[d_id] = {
                    "department_id": d_id,
                    "department_name": d_name,
                    "department_code": d_code,
                    "total_count": 0,
                    "total_amount": 0.0,
                    "aged_count": 0,
                    "critical_count": 0,
                    "pending_roles": {},
                }
            dept_stats[d_id]["total_count"] += 1
            dept_stats[d_id]["total_amount"] += float(pr.total_amount)
            if age_days >= 3:
                dept_stats[d_id]["aged_count"] += 1
            if age_days > 14:
                dept_stats[d_id]["critical_count"] += 1
            dept_stats[d_id]["pending_roles"][pending_approver] = (
                dept_stats[d_id]["pending_roles"].get(pending_approver, 0) + 1
            )

        # Summarize department analysis list
        department_analysis = []
        for d_id, s in dept_stats.items():
            primary_role = (
                max(s["pending_roles"].items(), key=lambda x: x[1])[0]
                if s["pending_roles"]
                else "N/A"
            )
            department_analysis.append(
                {
                    "department_id": s["department_id"],
                    "department_name": s["department_name"],
                    "department_code": s["department_code"],
                    "total_count": s["total_count"],
                    "total_amount": round(s["total_amount"], 2),
                    "aged_count": s["aged_count"],
                    "critical_count": s["critical_count"],
                    "primary_bottleneck": primary_role,
                }
            )
        department_analysis.sort(
            key=lambda x: (x["critical_count"], x["aged_count"], x["total_amount"]), reverse=True
        )

        # Summary statistics
        summary = {
            "total_pending_count": len(all_unfiltered_items),
            "total_pending_amount": sum(item["total_amount"] for item in all_unfiltered_items),
            "brackets": {
                "under_3d": {
                    "count": len(bracket_under_3d),
                    "amount": sum(item["total_amount"] for item in bracket_under_3d),
                    "label": "< 3 Days",
                },
                "3_to_7d": {
                    "count": len(bracket_3_to_7d),
                    "amount": sum(item["total_amount"] for item in bracket_3_to_7d),
                    "label": "3–7 Days",
                },
                "7_to_14d": {
                    "count": len(bracket_7_to_14d),
                    "amount": sum(item["total_amount"] for item in bracket_7_to_14d),
                    "label": "7–14 Days",
                },
                "over_14d": {
                    "count": len(bracket_over_14d),
                    "amount": sum(item["total_amount"] for item in bracket_over_14d),
                    "label": "> 14 Days (Critical Bottleneck)",
                },
            },
        }

        # 2. Filter items according to requested parameters
        target_items = all_unfiltered_items
        if bracket_filter == "under_3d":
            target_items = bracket_under_3d
        elif bracket_filter == "3_to_7d":
            target_items = bracket_3_to_7d
        elif bracket_filter == "7_to_14d":
            target_items = bracket_7_to_14d
        elif bracket_filter == "over_14d":
            target_items = bracket_over_14d
        elif bracket_filter == "aged":
            target_items = [i for i in all_unfiltered_items if i["age_days"] >= 3]

        if dept_filter:
            target_items = [i for i in target_items if i["department_id"] == str(dept_filter)]

        if status_filter:
            target_items = [i for i in target_items if i["status"] == status_filter]

        if search_query:
            sq = search_query.lower()
            target_items = [
                i
                for i in target_items
                if sq in i["pr_number"].lower()
                or sq in i["title"].lower()
                or sq in i["requester_email"].lower()
                or sq in i["department_name"].lower()
                or sq in i["department_code"].lower()
            ]

        # Sorting
        if sort_by == "age_asc":
            target_items.sort(key=lambda x: x["age_days"])
        elif sort_by == "amount_desc":
            target_items.sort(key=lambda x: x["total_amount"], reverse=True)
        elif sort_by == "amount_asc":
            target_items.sort(key=lambda x: x["total_amount"])
        elif sort_by == "date_desc":
            target_items.sort(key=lambda x: x["created_at"], reverse=True)
        else:  # default age_desc
            target_items.sort(key=lambda x: x["age_days"], reverse=True)

        # Pagination
        try:
            page_num = max(1, int(request.GET.get("page", 1)))
        except (ValueError, TypeError):
            page_num = 1

        try:
            page_size = min(100, max(1, int(request.GET.get("page_size", 10))))
        except (ValueError, TypeError):
            page_size = 10

        total_items_count = len(target_items)
        total_pages = max(1, (total_items_count + page_size - 1) // page_size)
        page_num = min(page_num, total_pages)
        start_idx = (page_num - 1) * page_size
        end_idx = start_idx + page_size
        paginated_items = target_items[start_idx:end_idx]

        # List of departments for filter dropdown
        depts_qs = (
            Department.objects.filter(organization=org) if org else Department.objects.all()
        ).order_by("name")
        departments_data = [{"id": str(d.id), "name": d.name, "code": d.code} for d in depts_qs]

        return Response(
            {
                "summary": summary,
                "department_analysis": department_analysis,
                "items": paginated_items,
                "bottlenecks": [i for i in all_unfiltered_items if i["age_days"] >= 3],
                "pagination": {
                    "total_count": total_items_count,
                    "page": page_num,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "has_next": page_num < total_pages,
                    "has_previous": page_num > 1,
                },
                "departments": departments_data,
            },
            status=status.HTTP_200_OK,
        )


class ManagerSpendAnalyticsAPIView(APIView):
    """
    GET /api/v1/manager/spend/
    Comprehensive spend analytics with multi-dimensional breakdowns, trends, and pagination.
    """

    permission_classes = [IsAuthenticated, IsProcurementManager]

    def get(self, request):
        org = get_user_org(request.user)

        # Scoped QuerySets
        budget_qs = Budget.objects.select_related(
            "cost_center", "cost_center__department", "fiscal_period"
        ).all()
        spend_qs = SpendLedger.objects.select_related(
            "budget",
            "budget__cost_center",
            "budget__cost_center__department",
            "budget__fiscal_period",
        ).all()
        pos_qs = PurchaseOrder.objects.select_related(
            "vendor", "vendor__category", "cost_center", "cost_center__department"
        ).exclude(status=PurchaseOrder.STATUS_CANCELLED)

        if org:
            budget_qs = budget_qs.filter(cost_center__department__organization=org)
            spend_qs = spend_qs.filter(budget__cost_center__department__organization=org)
            pos_qs = pos_qs.filter(cost_center__department__organization=org)

        # Filters
        fiscal_period_param = request.GET.get("fiscal_period", "").strip()
        if fiscal_period_param:
            budget_qs = budget_qs.filter(
                Q(fiscal_period_id=fiscal_period_param)
                | Q(fiscal_period__name__iexact=fiscal_period_param)
            )
            spend_qs = spend_qs.filter(
                Q(budget__fiscal_period_id=fiscal_period_param)
                | Q(budget__fiscal_period__name__iexact=fiscal_period_param)
            )

        dept_param = request.GET.get("department", "").strip()
        if dept_param:
            budget_qs = budget_qs.filter(
                Q(cost_center__department_id=dept_param)
                | Q(cost_center__department__code__iexact=dept_param)
            )
            spend_qs = spend_qs.filter(
                Q(budget__cost_center__department_id=dept_param)
                | Q(budget__cost_center__department__code__iexact=dept_param)
            )
            pos_qs = pos_qs.filter(
                Q(cost_center__department_id=dept_param)
                | Q(cost_center__department__code__iexact=dept_param)
            )

        cost_center_param = request.GET.get("cost_center", "").strip()
        if cost_center_param:
            budget_qs = budget_qs.filter(
                Q(cost_center_id=cost_center_param) | Q(cost_center__code__iexact=cost_center_param)
            )
            spend_qs = spend_qs.filter(
                Q(budget__cost_center_id=cost_center_param)
                | Q(budget__cost_center__code__iexact=cost_center_param)
            )
            pos_qs = pos_qs.filter(
                Q(cost_center_id=cost_center_param) | Q(cost_center__code__iexact=cost_center_param)
            )

        vendor_param = request.GET.get("vendor", "").strip()
        if vendor_param:
            pos_qs = pos_qs.filter(vendor_id=vendor_param)

        category_param = request.GET.get("category", "").strip()
        if category_param:
            pos_qs = pos_qs.filter(
                Q(vendor__category_id=category_param)
                | Q(vendor__category__code__iexact=category_param)
            )

        # Date range on spend ledger
        start_date = request.GET.get("start_date")
        if start_date:
            spend_qs = spend_qs.filter(created_at__date__gte=start_date)
            pos_qs = pos_qs.filter(created_at__date__gte=start_date)

        end_date = request.GET.get("end_date")
        if end_date:
            spend_qs = spend_qs.filter(created_at__date__lte=end_date)
            pos_qs = pos_qs.filter(created_at__date__lte=end_date)

        # 1. Summary KPIs
        total_allocated = budget_qs.aggregate(s=Sum("allocated_amount"))["s"] or Decimal("0.00")
        total_reserved = budget_qs.aggregate(s=Sum("reserved_amount"))["s"] or Decimal("0.00")
        total_committed = budget_qs.aggregate(s=Sum("committed_amount"))["s"] or Decimal("0.00")
        total_actual = budget_qs.aggregate(s=Sum("actual_amount"))["s"] or Decimal("0.00")
        total_available = total_allocated - (total_reserved + total_committed + total_actual)
        utilization_rate = (
            ((total_committed + total_actual + total_reserved) / total_allocated * Decimal("100.0"))
            if total_allocated > Decimal("0.00")
            else Decimal("0.00")
        )

        open_commitments_count = pos_qs.filter(
            status__in=[
                PurchaseOrder.STATUS_ISSUED,
                PurchaseOrder.STATUS_ACKNOWLEDGED,
                PurchaseOrder.STATUS_PARTIAL_RECEIPT,
            ]
        ).count()

        summary = {
            "allocated_budget": float(total_allocated),
            "reserved_amount": float(total_reserved),
            "committed_spend": float(total_committed),
            "actual_spend": float(total_actual),
            "available_balance": float(total_available),
            "utilization_rate": round(float(utilization_rate), 1),
            "active_transactions_count": spend_qs.count(),
            "open_commitments_count": open_commitments_count,
        }

        # 2. Breakdown by Department
        depts_dict = {}
        for b in budget_qs:
            dept = b.cost_center.department
            dept_id = str(dept.id) if dept else "unassigned"
            dept_name = dept.name if dept else "General"
            dept_code = dept.code if dept else "GEN"
            if dept_id not in depts_dict:
                depts_dict[dept_id] = {
                    "id": dept_id,
                    "name": dept_name,
                    "code": dept_code,
                    "allocated": Decimal("0.00"),
                    "reserved": Decimal("0.00"),
                    "committed": Decimal("0.00"),
                    "actual": Decimal("0.00"),
                }
            depts_dict[dept_id]["allocated"] += b.allocated_amount
            depts_dict[dept_id]["reserved"] += b.reserved_amount
            depts_dict[dept_id]["committed"] += b.committed_amount
            depts_dict[dept_id]["actual"] += b.actual_amount

        by_department = []
        for d in depts_dict.values():
            avail = d["allocated"] - (d["reserved"] + d["committed"] + d["actual"])
            util = (
                ((d["committed"] + d["actual"] + d["reserved"]) / d["allocated"] * Decimal("100.0"))
                if d["allocated"] > Decimal("0.00")
                else Decimal("0.00")
            )
            by_department.append(
                {
                    "id": d["id"],
                    "name": d["name"],
                    "code": d["code"],
                    "allocated": float(d["allocated"]),
                    "reserved": float(d["reserved"]),
                    "committed": float(d["committed"]),
                    "actual": float(d["actual"]),
                    "available": float(avail),
                    "utilization_percentage": round(float(util), 1),
                }
            )
        by_department.sort(key=lambda x: x["allocated"], reverse=True)

        # 3. Breakdown by Cost Center
        by_cost_center = []
        for b in budget_qs:
            avail = b.available_amount
            util = (
                (
                    (b.committed_amount + b.actual_amount + b.reserved_amount)
                    / b.allocated_amount
                    * Decimal("100.0")
                )
                if b.allocated_amount > Decimal("0.00")
                else Decimal("0.00")
            )
            by_cost_center.append(
                {
                    "id": str(b.cost_center.id),
                    "code": b.cost_center.code,
                    "name": b.cost_center.name,
                    "department": (
                        b.cost_center.department.name if b.cost_center.department else "N/A"
                    ),
                    "fiscal_period": b.fiscal_period.name if b.fiscal_period else "N/A",
                    "allocated": float(b.allocated_amount),
                    "reserved": float(b.reserved_amount),
                    "committed": float(b.committed_amount),
                    "actual": float(b.actual_amount),
                    "available": float(avail),
                    "utilization_percentage": round(float(util), 1),
                }
            )
        by_cost_center.sort(key=lambda x: x["allocated"], reverse=True)

        # 4. Breakdown by Vendor
        vendor_spend = {}
        for po in pos_qs:
            v = po.vendor
            v_id = str(v.id)
            if v_id not in vendor_spend:
                vendor_spend[v_id] = {
                    "id": v_id,
                    "legal_name": v.legal_name,
                    "vendor_number": v.vendor_number,
                    "category": v.category.name if v.category else "General",
                    "committed_spend": Decimal("0.00"),
                    "po_count": 0,
                }
            vendor_spend[v_id]["committed_spend"] += po.total_amount
            vendor_spend[v_id]["po_count"] += 1

        by_vendor = [
            {
                "id": v["id"],
                "legal_name": v["legal_name"],
                "vendor_number": v["vendor_number"],
                "category": v["category"],
                "committed_spend": float(v["committed_spend"]),
                "po_count": v["po_count"],
            }
            for v in vendor_spend.values()
        ]
        by_vendor.sort(key=lambda x: x["committed_spend"], reverse=True)

        # 5. Breakdown by Category
        cat_spend = {}
        for po in pos_qs:
            cat_name = (
                po.vendor.category.name if (po.vendor and po.vendor.category) else "Uncategorized"
            )
            if cat_name not in cat_spend:
                cat_spend[cat_name] = {
                    "category": cat_name,
                    "spend": Decimal("0.00"),
                    "po_count": 0,
                }
            cat_spend[cat_name]["spend"] += po.total_amount
            cat_spend[cat_name]["po_count"] += 1

        by_category = [
            {
                "category": c["category"],
                "spend": float(c["spend"]),
                "po_count": c["po_count"],
            }
            for c in cat_spend.values()
        ]
        by_category.sort(key=lambda x: x["spend"], reverse=True)

        # 6. Monthly SpendLedger Trends
        trends_dict = {}
        for entry in spend_qs.order_by("created_at"):
            month_key = entry.created_at.strftime("%Y-%m")
            if month_key not in trends_dict:
                trends_dict[month_key] = {
                    "month": month_key,
                    "reservation": Decimal("0.00"),
                    "commitment": Decimal("0.00"),
                    "actual": Decimal("0.00"),
                }
            if entry.entry_type == SpendLedger.ENTRY_RESERVATION:
                trends_dict[month_key]["reservation"] += entry.amount
            elif entry.entry_type == SpendLedger.ENTRY_COMMITMENT:
                trends_dict[month_key]["commitment"] += entry.amount
            elif entry.entry_type == SpendLedger.ENTRY_ACTUAL:
                trends_dict[month_key]["actual"] += entry.amount

        trends = [
            {
                "month": m["month"],
                "reservation": float(m["reservation"]),
                "commitment": float(m["commitment"]),
                "actual": float(m["actual"]),
            }
            for m in sorted(trends_dict.values(), key=lambda x: x["month"])
        ]

        # 7. Paginated SpendLedger Entries
        page_num = max(1, int(request.GET.get("page", 1)))
        page_size = min(100, max(1, int(request.GET.get("page_size", 10))))
        total_entries_count = spend_qs.count()
        total_pages = max(1, (total_entries_count + page_size - 1) // page_size)
        start_idx = (page_num - 1) * page_size
        end_idx = start_idx + page_size

        ledger_slice = spend_qs.order_by("-created_at")[start_idx:end_idx]
        ledger_entries = [
            {
                "id": str(e.id),
                "created_at": e.created_at.strftime("%Y-%m-%d %H:%M"),
                "cost_center_code": e.budget.cost_center.code if e.budget else "N/A",
                "department_name": (
                    e.budget.cost_center.department.name
                    if (e.budget and e.budget.cost_center.department)
                    else "N/A"
                ),
                "fiscal_period": (
                    e.budget.fiscal_period.name if (e.budget and e.budget.fiscal_period) else "N/A"
                ),
                "entry_type": e.entry_type,
                "amount": float(e.amount),
                "reference_number": e.reference_number,
                "description": e.description,
            }
            for e in ledger_slice
        ]

        # Metadata for dropdown filters
        depts_list = list(
            Department.objects.filter(organization=org).values("id", "name", "code")
            if org
            else Department.objects.values("id", "name", "code")
        )
        periods_list = list(
            FiscalPeriod.objects.filter(organization=org).values("id", "name", "year")
            if org
            else FiscalPeriod.objects.values("id", "name", "year")
        )

        return Response(
            {
                "summary": summary,
                "by_department": by_department,
                "by_cost_center": by_cost_center,
                "by_vendor": by_vendor,
                "by_category": by_category,
                "trends": trends,
                "ledger_entries": ledger_entries,
                "pagination": {
                    "total_count": total_entries_count,
                    "page": page_num,
                    "page_size": page_size,
                    "total_pages": total_pages,
                },
                "departments": depts_list,
                "fiscal_periods": periods_list,
            },
            status=status.HTTP_200_OK,
        )


class ManagerSpendSummaryAPIView(APIView):
    """
    GET /api/v1/manager/spend/summary/
    Returns spend summary KPIs reconciling directly with SpendLedger and Budget models.
    """

    permission_classes = [IsAuthenticated, IsProcurementManager]

    def get(self, request):
        org = get_user_org(request.user)

        budget_qs = Budget.objects.all()
        spend_qs = SpendLedger.objects.all()

        if org:
            budget_qs = budget_qs.filter(cost_center__department__organization=org)
            spend_qs = spend_qs.filter(budget__cost_center__department__organization=org)

        total_allocated = budget_qs.aggregate(s=Sum("allocated_amount"))["s"] or Decimal("0.00")
        total_reserved = budget_qs.aggregate(s=Sum("reserved_amount"))["s"] or Decimal("0.00")
        total_committed = budget_qs.aggregate(s=Sum("committed_amount"))["s"] or Decimal("0.00")
        total_actual = budget_qs.aggregate(s=Sum("actual_amount"))["s"] or Decimal("0.00")
        total_available = total_allocated - (total_reserved + total_committed + total_actual)

        return Response(
            {
                "allocated_budget": float(total_allocated),
                "reserved_amount": float(total_reserved),
                "committed_spend": float(total_committed),
                "actual_spend": float(total_actual),
                "available_balance": float(total_available),
                "active_transactions": spend_qs.count(),
            },
            status=status.HTTP_200_OK,
        )


class ManagerSpendExportAPIView(APIView):
    """
    GET /api/v1/manager/spend/export/
    Streams a CSV file of SpendLedger transactions adhering to tenant isolation and active filters.
    """

    permission_classes = [IsAuthenticated, IsProcurementManager]

    def get(self, request):
        import csv

        from django.http import HttpResponse

        org = get_user_org(request.user)
        spend_qs = SpendLedger.objects.select_related(
            "budget",
            "budget__cost_center",
            "budget__cost_center__department",
            "budget__fiscal_period",
        ).all()

        if org:
            spend_qs = spend_qs.filter(budget__cost_center__department__organization=org)

        dept_param = request.GET.get("department")
        if dept_param:
            spend_qs = spend_qs.filter(
                Q(budget__cost_center__department_id=dept_param)
                | Q(budget__cost_center__department__code__iexact=dept_param)
            )

        period_param = request.GET.get("fiscal_period")
        if period_param:
            spend_qs = spend_qs.filter(
                Q(budget__fiscal_period_id=period_param)
                | Q(budget__fiscal_period__name__iexact=period_param)
            )

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="manager_spend_ledger_export.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "Date",
                "Entry Type",
                "Amount ($)",
                "Reference Number",
                "Cost Center",
                "Department",
                "Fiscal Period",
                "Description",
            ]
        )

        for entry in spend_qs.order_by("-created_at"):
            writer.writerow(
                [
                    entry.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    entry.entry_type,
                    f"{entry.amount:.2f}",
                    entry.reference_number,
                    entry.budget.cost_center.code if entry.budget else "N/A",
                    (
                        entry.budget.cost_center.department.name
                        if (entry.budget and entry.budget.cost_center.department)
                        else "N/A"
                    ),
                    (
                        entry.budget.fiscal_period.name
                        if (entry.budget and entry.budget.fiscal_period)
                        else "N/A"
                    ),
                    entry.description,
                ]
            )

        return response


class ManagerSupplierPerformanceAPIView(APIView):
    """
    GET /api/v1/manager/performance/
    Supplier Performance Scorecards Directory and Metrics for Procurement Managers.
    """

    permission_classes = [IsAuthenticated, IsProcurementManager]

    def get(self, request):
        from apps.scorecards.models import VendorScorecard
        from apps.vendors.models import VendorCategory

        qs = VendorScorecard.objects.select_related(
            "vendor", "vendor__category", "evaluated_by"
        ).order_by("-created_at")

        search_query = request.GET.get("search", "").strip()
        if search_query:
            qs = qs.filter(
                Q(vendor__legal_name__icontains=search_query)
                | Q(vendor__vendor_number__icontains=search_query)
                | Q(evaluation_period__icontains=search_query)
            )

        period_param = request.GET.get("period", "").strip()
        if period_param:
            qs = qs.filter(evaluation_period=period_param)

        status_param = request.GET.get("performance_status", "").strip().upper()
        if status_param == "EXCELLENT":
            qs = qs.filter(composite_score__gte=Decimal("85.00"))
        elif status_param == "SATISFACTORY":
            qs = qs.filter(
                composite_score__gte=Decimal("70.00"), composite_score__lt=Decimal("85.00")
            )
        elif status_param in ["ATTENTION_REQUIRED", "ATTENTION", "NEEDS_ATTENTION"]:
            qs = qs.filter(composite_score__lt=Decimal("70.00"))

        category_param = request.GET.get("category", "").strip()
        if category_param:
            qs = qs.filter(
                Q(vendor__category_id=category_param)
                | Q(vendor__category__code__iexact=category_param)
            )

        # Summary KPIs
        total_count = qs.count()
        distinct_vendors = qs.values("vendor_id").distinct().count()

        avg_data = qs.aggregate(
            avg_composite=Avg("composite_score"),
            avg_quality=Avg("quality_score"),
            avg_delivery=Avg("delivery_score"),
            avg_price=Avg("price_score"),
            avg_compliance=Avg("compliance_score"),
        )

        top_performing = qs.filter(composite_score__gte=Decimal("85.00")).count()
        satisfactory = qs.filter(
            composite_score__gte=Decimal("70.00"), composite_score__lt=Decimal("85.00")
        ).count()
        attention_required = qs.filter(composite_score__lt=Decimal("70.00")).count()

        summary = {
            "total_scorecards": total_count,
            "distinct_vendors_evaluated": distinct_vendors,
            "average_composite_score": round(float(avg_data["avg_composite"] or 0), 1),
            "average_quality_score": round(float(avg_data["avg_quality"] or 0), 1),
            "average_delivery_score": round(float(avg_data["avg_delivery"] or 0), 1),
            "average_price_score": round(float(avg_data["avg_price"] or 0), 1),
            "average_compliance_score": round(float(avg_data["avg_compliance"] or 0), 1),
            "top_performing_count": top_performing,
            "satisfactory_count": satisfactory,
            "attention_required_count": attention_required,
        }

        # Pagination
        page_num = max(1, int(request.GET.get("page", 1)))
        page_size = min(100, max(1, int(request.GET.get("page_size", 10))))
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        start_idx = (page_num - 1) * page_size
        end_idx = start_idx + page_size

        scorecard_items = [
            {
                "id": str(sc.id),
                "vendor_id": str(sc.vendor.id),
                "vendor_name": sc.vendor.legal_name,
                "vendor_number": sc.vendor.vendor_number,
                "vendor_category": sc.vendor.category.name if sc.vendor.category else "General",
                "vendor_status": sc.vendor.status,
                "evaluation_period": sc.evaluation_period,
                "delivery_score": (
                    float(sc.delivery_score) if sc.delivery_score is not None else None
                ),
                "quality_score": (
                    float(sc.quality_score) if sc.quality_score is not None else None
                ),
                "price_score": float(sc.price_score) if sc.price_score is not None else None,
                "compliance_score": (
                    float(sc.compliance_score) if sc.compliance_score is not None else None
                ),
                "composite_score": (
                    float(sc.composite_score) if sc.composite_score is not None else None
                ),
                "performance_status": (
                    "NOT_EVALUATED"
                    if sc.composite_score is None
                    else (
                        "EXCELLENT"
                        if sc.composite_score >= Decimal("85.00")
                        else (
                            "SATISFACTORY"
                            if sc.composite_score >= Decimal("70.00")
                            else "ATTENTION_REQUIRED"
                        )
                    )
                ),
                "evaluator_comments": sc.evaluator_comments,
                "evaluated_by_email": sc.evaluated_by.email if sc.evaluated_by else "System",
                "created_at": sc.created_at.strftime("%Y-%m-%d"),
            }
            for sc in qs[start_idx:end_idx]
        ]

        # Available periods for filter dropdown
        periods = list(
            VendorScorecard.objects.values_list("evaluation_period", flat=True)
            .distinct()
            .order_by("-evaluation_period")
        )

        categories = list(VendorCategory.objects.values("id", "name", "code"))

        return Response(
            {
                "summary": summary,
                "scorecards": scorecard_items,
                "pagination": {
                    "total_count": total_count,
                    "page": page_num,
                    "page_size": page_size,
                    "total_pages": total_pages,
                },
                "periods": periods,
                "categories": categories,
            },
            status=status.HTTP_200_OK,
        )


class ManagerPerformanceSummaryAPIView(APIView):
    """
    GET /api/v1/manager/performance/summary/
    Returns live supplier performance KPI metrics.
    """

    permission_classes = [IsAuthenticated, IsProcurementManager]

    def get(self, request):
        from apps.scorecards.models import VendorScorecard

        qs = VendorScorecard.objects.all()
        total_count = qs.count()
        distinct_vendors = qs.values("vendor_id").distinct().count()

        avg_data = qs.aggregate(
            avg_composite=Avg("composite_score"),
            avg_quality=Avg("quality_score"),
            avg_delivery=Avg("delivery_score"),
            avg_price=Avg("price_score"),
            avg_compliance=Avg("compliance_score"),
        )

        top_performing = qs.filter(composite_score__gte=Decimal("85.00")).count()
        satisfactory = qs.filter(
            composite_score__gte=Decimal("70.00"), composite_score__lt=Decimal("85.00")
        ).count()
        attention_required = qs.filter(composite_score__lt=Decimal("70.00")).count()

        return Response(
            {
                "total_scorecards": total_count,
                "distinct_vendors_evaluated": distinct_vendors,
                "average_composite_score": round(float(avg_data["avg_composite"] or 0), 1),
                "average_quality_score": round(float(avg_data["avg_quality"] or 0), 1),
                "average_delivery_score": round(float(avg_data["avg_delivery"] or 0), 1),
                "average_price_score": round(float(avg_data["avg_price"] or 0), 1),
                "average_compliance_score": round(float(avg_data["avg_compliance"] or 0), 1),
                "top_performing_count": top_performing,
                "satisfactory_count": satisfactory,
                "attention_required_count": attention_required,
            },
            status=status.HTTP_200_OK,
        )


class ManagerSupplierPerformanceDetailAPIView(APIView):
    """
    GET /api/v1/manager/performance/<uuid:vendor_id>/
    Returns comprehensive supplier performance history, quality inspection metrics, and PO delivery history.
    """

    permission_classes = [IsAuthenticated, IsProcurementManager]

    def get(self, request, vendor_id):
        from django.shortcuts import get_object_or_404

        from apps.orders.models import DeliverySchedule
        from apps.receipts.models import ReceiptLine
        from apps.vendors.models import Vendor

        org = get_user_org(request.user)
        vendor = get_object_or_404(Vendor, pk=vendor_id)

        # Historical scorecards
        scorecards_qs = vendor.scorecards.select_related("evaluated_by").order_by("-created_at")
        scorecards_data = [
            {
                "id": str(sc.id),
                "evaluation_period": sc.evaluation_period,
                "delivery_score": (
                    float(sc.delivery_score) if sc.delivery_score is not None else None
                ),
                "quality_score": (
                    float(sc.quality_score) if sc.quality_score is not None else None
                ),
                "price_score": float(sc.price_score) if sc.price_score is not None else None,
                "compliance_score": (
                    float(sc.compliance_score) if sc.compliance_score is not None else None
                ),
                "composite_score": (
                    float(sc.composite_score) if sc.composite_score is not None else None
                ),
                "performance_status": (
                    "NOT_EVALUATED"
                    if sc.composite_score is None
                    else (
                        "EXCELLENT"
                        if sc.composite_score >= Decimal("85.00")
                        else (
                            "SATISFACTORY"
                            if sc.composite_score >= Decimal("70.00")
                            else "ATTENTION_REQUIRED"
                        )
                    )
                ),
                "evaluator_comments": sc.evaluator_comments,
                "evaluated_by_email": sc.evaluated_by.email if sc.evaluated_by else "System",
                "created_at": sc.created_at.strftime("%Y-%m-%d"),
            }
            for sc in scorecards_qs
        ]

        # Receipts & Inspection Metrics
        receipt_lines_qs = ReceiptLine.objects.filter(receipt__po__vendor=vendor)
        if org:
            receipt_lines_qs = receipt_lines_qs.filter(
                receipt__po__cost_center__department__organization=org
            )

        total_received = receipt_lines_qs.aggregate(s=Sum("quantity_received"))["s"] or Decimal(
            "0.00"
        )
        total_accepted = receipt_lines_qs.aggregate(s=Sum("quantity_accepted"))["s"] or Decimal(
            "0.00"
        )
        total_rejected = receipt_lines_qs.aggregate(s=Sum("quantity_rejected"))["s"] or Decimal(
            "0.00"
        )
        rejection_rate = (
            ((total_rejected / total_received) * Decimal("100.0"))
            if total_received > Decimal("0.00")
            else Decimal("0.00")
        )

        # Delivery schedules
        schedules_qs = DeliverySchedule.objects.filter(po__vendor=vendor)
        if org:
            schedules_qs = schedules_qs.filter(po__cost_center__department__organization=org)
        total_schedules = schedules_qs.count()

        # Risk context
        latest_risk = vendor.risk_records.order_by("-created_at").first()

        # Recent POs
        pos_qs = vendor.purchase_orders.all()
        if org:
            pos_qs = pos_qs.filter(cost_center__department__organization=org)
        recent_pos = [
            {
                "id": str(po.id),
                "po_number": po.po_number,
                "version": po.version,
                "status": po.status,
                "total_amount": float(po.total_amount),
                "created_at": po.created_at.strftime("%Y-%m-%d"),
            }
            for po in pos_qs.order_by("-created_at")[:8]
        ]

        return Response(
            {
                "vendor": {
                    "id": str(vendor.id),
                    "legal_name": vendor.legal_name,
                    "trade_name": vendor.trade_name,
                    "vendor_number": vendor.vendor_number,
                    "tax_id": vendor.tax_identification_number,
                    "category": vendor.category.name if vendor.category else "General",
                    "status": vendor.status,
                    "status_notes": vendor.status_notes,
                    "current_risk_level": latest_risk.risk_level if latest_risk else "LOW",
                },
                "scorecards": scorecards_data,
                "quality_metrics": {
                    "total_received_units": float(total_received),
                    "total_accepted_units": float(total_accepted),
                    "total_rejected_units": float(total_rejected),
                    "rejection_rate_percentage": round(float(rejection_rate), 2),
                },
                "delivery_metrics": {
                    "total_schedules_tracked": total_schedules,
                },
                "recent_purchase_orders": recent_pos,
            },
            status=status.HTTP_200_OK,
        )


class ManagerSupplierCompareAPIView(APIView):
    """
    GET /api/v1/manager/performance/compare/?vendor_a=<uuid>&vendor_b=<uuid>
    Side-by-side comparison of two vendors across overall scores, quality, delivery, price, and compliance.
    """

    permission_classes = [IsAuthenticated, IsProcurementManager]

    def get(self, request):
        from django.shortcuts import get_object_or_404

        from apps.receipts.models import ReceiptLine
        from apps.vendors.models import Vendor

        org = get_user_org(request.user)
        vendor_a_id = request.GET.get("vendor_a")
        vendor_b_id = request.GET.get("vendor_b")

        if not vendor_a_id or not vendor_b_id:
            return Response(
                {"error": "Both vendor_a and vendor_b query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vendor_a = get_object_or_404(Vendor, pk=vendor_a_id)
        vendor_b = get_object_or_404(Vendor, pk=vendor_b_id)

        def get_vendor_summary(v):
            latest_sc = v.scorecards.order_by("-created_at").first()
            rl_qs = ReceiptLine.objects.filter(receipt__po__vendor=v)
            if org:
                rl_qs = rl_qs.filter(receipt__po__cost_center__department__organization=org)
            tot_recv = rl_qs.aggregate(s=Sum("quantity_received"))["s"] or Decimal("0.00")
            tot_acc = rl_qs.aggregate(s=Sum("quantity_accepted"))["s"] or Decimal("0.00")
            tot_rej = rl_qs.aggregate(s=Sum("quantity_rejected"))["s"] or Decimal("0.00")
            rej_rate = (
                ((tot_rej / tot_recv) * Decimal("100.0"))
                if tot_recv > Decimal("0.00")
                else Decimal("0.00")
            )
            latest_risk = v.risk_records.order_by("-created_at").first()

            return {
                "id": str(v.id),
                "legal_name": v.legal_name,
                "vendor_number": v.vendor_number,
                "category": v.category.name if v.category else "General",
                "status": v.status,
                "risk_level": latest_risk.risk_level if latest_risk else "LOW",
                "composite_score": float(latest_sc.composite_score) if latest_sc else 0.0,
                "quality_score": float(latest_sc.quality_score) if latest_sc else 0.0,
                "delivery_score": float(latest_sc.delivery_score) if latest_sc else 0.0,
                "price_score": float(latest_sc.price_score) if latest_sc else 0.0,
                "compliance_score": float(latest_sc.compliance_score) if latest_sc else 0.0,
                "evaluation_period": latest_sc.evaluation_period if latest_sc else "N/A",
                "total_received": float(tot_recv),
                "total_accepted": float(tot_acc),
                "total_rejected": float(tot_rej),
                "rejection_rate": round(float(rej_rate), 2),
            }

        return Response(
            {
                "vendor_a": get_vendor_summary(vendor_a),
                "vendor_b": get_vendor_summary(vendor_b),
            },
            status=status.HTTP_200_OK,
        )


class ManagerVendorWatchlistAPIView(APIView):
    """
    GET /api/v1/manager/vendor-watchlist/
    Returns high-priority vendors for the Manager Governance & Sanctions Watchlist on the dashboard:
    currently SUSPENDED, ON_HOLD, or assessed as HIGH risk.
    """

    permission_classes = [IsAuthenticated, IsProcurementManager]

    def get(self, request):
        org = get_user_org(request.user)
        from apps.vendors.services import allowed_governance_transitions

        # Target suppliers: SUSPENDED, ON_HOLD, or with HIGH risk level
        high_risk_ids = set(
            VendorRiskRecord.objects.filter(
                risk_level=VendorRiskRecord.RISK_LEVEL_HIGH
            ).values_list("vendor_id", flat=True)
        )
        governance_status_ids = set(
            Vendor.objects.filter(
                status__in=[Vendor.STATUS_SUSPENDED, Vendor.STATUS_ON_HOLD]
            ).values_list("id", flat=True)
        )

        target_ids = list(high_risk_ids.union(governance_status_ids))
        qs = (
            Vendor.objects.filter(id__in=target_ids)
            .select_related("category")
            .order_by("-updated_at")
        )
        if org:
            qs = qs.filter(organization=org)
        elif not request.user.is_superuser:
            qs = qs.none()
        qs = qs[:15]

        # If empty, fallback to recently updated vendors in scope so dashboard is never empty
        if not qs.exists():
            if org:
                qs = Vendor.objects.filter(organization=org).select_related("category").order_by("-updated_at")[:5]
            elif request.user.is_superuser:
                qs = Vendor.objects.select_related("category").order_by("-updated_at")[:5]
            else:
                qs = Vendor.objects.none()

        vendor_ids = [v.id for v in qs]
        from apps.orders.models import PurchaseOrder

        # Batch aggregate open exposure per vendor in a single query (eliminates N+1)
        open_pos = (
            PurchaseOrder.objects.filter(
                vendor_id__in=vendor_ids,
                status__in=[
                    PurchaseOrder.STATUS_ISSUED,
                    PurchaseOrder.STATUS_PARTIAL_RECEIPT,
                ],
            )
            .values("vendor_id")
            .annotate(
                total_amount=Sum("total_amount"),
                po_count=Count("id"),
            )
        )
        exposure_map = {
            item["vendor_id"]: {
                "total_open_pos_count": item["po_count"],
                "total_open_pos_amount": float(item["total_amount"] or Decimal("0.00")),
                "total_exposure_amount": float(item["total_amount"] or Decimal("0.00")),
            }
            for item in open_pos
        }

        # Batch fetch latest risk records in a single query (eliminates N+1)
        latest_risks = {}
        for r in (
            VendorRiskRecord.objects.filter(vendor_id__in=vendor_ids)
            .select_related("assessed_by")
            .order_by("vendor_id", "-created_at")
        ):
            if r.vendor_id not in latest_risks:
                latest_risks[r.vendor_id] = r

        results = []
        for v in qs:
            latest_risk = latest_risks.get(v.id)
            exp = exposure_map.get(v.id, {
                "total_open_pos_count": 0,
                "total_open_pos_amount": 0.0,
                "total_exposure_amount": 0.0,
            })
            transitions = allowed_governance_transitions(v, request.user)
            results.append(
                {
                    "id": str(v.id),
                    "legal_name": v.legal_name,
                    "trade_name": v.trade_name,
                    "vendor_number": v.vendor_number,
                    "category": v.category.name if v.category else "General Supplier",
                    "status": v.status,
                    "status_display": v.get_status_display(),
                    "status_notes": v.status_notes or "",
                    "current_risk_level": latest_risk.risk_level if latest_risk else "LOW",
                    "updated_at": v.updated_at.isoformat(),
                    "exposure": exp,
                    "allowed_transitions": transitions,
                }
            )

        return Response({"results": results, "vendors": results, "count": len(results)}, status=status.HTTP_200_OK)


class ManagerApprovalsAPIView(APIView):
    """
    Returns real database-backed pending and evaluated approval records
    for the Procurement Manager governance desk.
    Supports tab ('pending', 'history'), type ('all', 'pr', 'po_amendment'),
    search filtering, and pagination.
    """
    permission_classes = [IsAuthenticated, IsProcurementManager]

    def get(self, request):
        org = get_user_org(request.user)
        tab = request.GET.get('tab', 'pending').strip().lower()
        type_filter = request.GET.get('type', 'all').strip().lower()
        search_query = request.GET.get('search', '').strip()

        # 1. Base Querysets
        pr_pending_statuses = [
            PurchaseRequisition.STATUS_SUBMITTED,
            PurchaseRequisition.STATUS_MANAGER_REVIEW,
            PurchaseRequisition.STATUS_BUDGET_REVIEW,
        ]
        pr_history_statuses = [
            PurchaseRequisition.STATUS_APPROVED,
            PurchaseRequisition.STATUS_REJECTED,
            PurchaseRequisition.STATUS_SOURCING,
            PurchaseRequisition.STATUS_PO_ISSUED,
        ]

        prs_qs = PurchaseRequisition.objects.select_related('department', 'requester').prefetch_related('lines')
        if org:
            prs_qs = prs_qs.filter(department__organization=org)
        elif not request.user.is_superuser:
            prs_qs = prs_qs.none()

        if tab == 'history':
            prs_filtered = prs_qs.filter(status__in=pr_history_statuses)
        else:
            prs_filtered = prs_qs.filter(status__in=pr_pending_statuses)

        # PO Amendments
        amendments_qs = POAmendment.objects.select_related(
            'po', 'po__vendor', 'po__cost_center__department', 'requested_by', 'approved_by'
        )
        if org:
            amendments_qs = amendments_qs.filter(po__cost_center__department__organization=org)
        elif not request.user.is_superuser:
            amendments_qs = amendments_qs.none()

        if tab == 'history':
            amendments_filtered = amendments_qs.filter(status__in=[POAmendment.STATUS_APPROVED, POAmendment.STATUS_REJECTED])
        else:
            amendments_filtered = amendments_qs.filter(status=POAmendment.STATUS_PENDING)

        # New Purchase Orders awaiting approval (DRAFT -> APPROVAL lifecycle)
        po_approval_qs = PurchaseOrder.objects.select_related(
            'vendor', 'cost_center__department', 'submitted_by'
        ).filter(status=PurchaseOrder.STATUS_APPROVAL)
        if org:
            po_approval_qs = po_approval_qs.filter(
                Q(cost_center__department__organization=org)
                | Q(requisition__department__organization=org)
            )
        elif not request.user.is_superuser:
            po_approval_qs = po_approval_qs.none()

        po_history_statuses = [
            PurchaseOrder.STATUS_APPROVED,
            PurchaseOrder.STATUS_ISSUED,
            PurchaseOrder.STATUS_ACKNOWLEDGED,
            PurchaseOrder.STATUS_PARTIAL_RECEIPT,
            PurchaseOrder.STATUS_COMPLETED,
            PurchaseOrder.STATUS_CANCELLED,
        ]
        if tab == 'history':
            po_filtered = po_approval_qs.model.objects.select_related(
                'vendor', 'cost_center__department', 'submitted_by', 'approved_by'
            ).filter(
                status__in=po_history_statuses,
                approved_by__isnull=False,
            )
            if org:
                po_filtered = po_filtered.filter(
                    Q(cost_center__department__organization=org)
                    | Q(requisition__department__organization=org)
                )
            elif not request.user.is_superuser:
                po_filtered = po_filtered.none()
        else:
            po_filtered = po_approval_qs

        # 2. Summary KPIs (Database-backed)
        total_pending_prs = prs_qs.filter(status__in=pr_pending_statuses).count()
        total_pending_amendments = amendments_qs.filter(status=POAmendment.STATUS_PENDING).count()
        total_pending_pos = PurchaseOrder.objects.filter(status=PurchaseOrder.STATUS_APPROVAL)
        if org:
            total_pending_pos = total_pending_pos.filter(
                Q(cost_center__department__organization=org)
                | Q(requisition__department__organization=org)
            )
        elif not request.user.is_superuser:
            total_pending_pos = total_pending_pos.none()
        total_pending_pos = total_pending_pos.count()
        total_pending_count = total_pending_prs + total_pending_amendments + total_pending_pos

        pr_pending_val = prs_qs.filter(status__in=pr_pending_statuses).aggregate(tot=Sum('total_amount'))['tot'] or Decimal('0.00')
        amend_pending_val = amendments_qs.filter(status=POAmendment.STATUS_PENDING).aggregate(tot=Sum('delta_amount'))['tot'] or Decimal('0.00')
        po_pending_val = (
            PurchaseOrder.objects.filter(status=PurchaseOrder.STATUS_APPROVAL)
        )
        if org:
            po_pending_val = po_pending_val.filter(
                Q(cost_center__department__organization=org)
                | Q(requisition__department__organization=org)
            )
        elif not request.user.is_superuser:
            po_pending_val = po_pending_val.none()
        po_pending_val = po_pending_val.aggregate(tot=Sum('total_amount'))['tot'] or Decimal('0.00')
        total_pending_value = float(pr_pending_val + amend_pending_val + po_pending_val)

        total_history_count = (
            prs_qs.filter(status__in=pr_history_statuses).count()
            + amendments_qs.filter(status__in=[POAmendment.STATUS_APPROVED, POAmendment.STATUS_REJECTED]).count()
        )

        items = []

        # Process PRs
        if type_filter in ['all', 'pr', 'requisition']:
            for pr in prs_filtered.order_by('-updated_at')[:100]:
                urgency = 'HIGH' if pr.status == PurchaseRequisition.STATUS_BUDGET_REVIEW or pr.total_amount > Decimal('50000.00') else 'NORMAL'
                req_name = f"{pr.requester.first_name} {pr.requester.last_name}".strip() if pr.requester else "Unknown"
                if not req_name and pr.requester:
                    req_name = pr.requester.email
                items.append({
                    'id': str(pr.id),
                    'type': 'PR',
                    'type_display': 'Purchase Requisition',
                    'reference_number': pr.pr_number,
                    'title': pr.title,
                    'department': pr.department.name if pr.department else 'General',
                    'requester_name': req_name,
                    'requester_email': pr.requester.email if pr.requester else '',
                    'vendor_name': '-',
                    'amount': float(pr.total_amount),
                    'previous_amount': None,
                    'revised_amount': None,
                    'delta_amount': None,
                    'currency': 'USD',
                    'status': pr.status,
                    'status_display': pr.get_status_display(),
                    'urgency': urgency,
                    'justification': pr.justification or '',
                    'lines_count': len(pr.lines.all()),
                    'created_at': pr.created_at.isoformat(),
                    'updated_at': pr.updated_at.isoformat(),
                    'detail_url': f'/requisitions/{pr.id}/',
                    'can_approve': pr.status in pr_pending_statuses,
                })

        # Process PO Amendments
        if type_filter in ['all', 'po', 'po_amendment', 'amendment']:
            for am in amendments_filtered.order_by('-updated_at')[:100]:
                po = am.po
                prev_amt = am.previous_version_snapshot.get('total_amount') if am.previous_version_snapshot else (po.total_amount - am.delta_amount)
                rev_amt = float(prev_amt) + float(am.delta_amount) if prev_amt is not None else float(po.total_amount)
                req_name = f"{am.requested_by.first_name} {am.requested_by.last_name}".strip() if am.requested_by else "Manager"
                if not req_name and am.requested_by:
                    req_name = am.requested_by.email
                items.append({
                    'id': str(am.id),
                    'type': 'PO_AMENDMENT',
                    'type_display': 'PO Amendment',
                    'reference_number': f"{po.po_number} (Amd #{am.amendment_number})",
                    'po_id': str(po.id),
                    'po_number': po.po_number,
                    'amendment_number': am.amendment_number,
                    'title': f"Amendment #{am.amendment_number} for PO {po.po_number}",
                    'department': po.cost_center.department.name if po.cost_center and po.cost_center.department else 'Procurement',
                    'requester_name': req_name,
                    'requester_email': am.requested_by.email if am.requested_by else '',
                    'vendor_name': po.vendor.legal_name if po.vendor else 'Unknown Vendor',
                    'amount': float(am.delta_amount),
                    'previous_amount': float(prev_amt) if prev_amt is not None else float(po.total_amount),
                    'revised_amount': rev_amt,
                    'delta_amount': float(am.delta_amount),
                    'currency': 'USD',
                    'status': am.status,
                    'status_display': am.get_status_display(),
                    'urgency': 'HIGH' if am.delta_amount > Decimal('10000.00') else 'NORMAL',
                    'justification': am.reason or '',
                    'lines_count': len(am.pending_line_items or []),
                    'created_at': am.created_at.isoformat(),
                    'updated_at': am.updated_at.isoformat(),
                    'detail_url': '/manager/purchase-orders/',
                    'can_approve': am.status == POAmendment.STATUS_PENDING,
                })

        # Process Purchase Orders awaiting approval
        if type_filter in ['all', 'po', 'po_approval']:
            for po in po_filtered.order_by('-updated_at')[:100]:
                submitter = po.submitted_by
                req_name = f"{submitter.first_name} {submitter.last_name}".strip() if submitter else "Procurement"
                if not req_name and submitter:
                    req_name = submitter.email
                items.append({
                    'id': str(po.id),
                    'type': 'PO_APPROVAL',
                    'type_display': 'Purchase Order Approval',
                    'reference_number': po.po_number,
                    'po_id': str(po.id),
                    'po_number': po.po_number,
                    'title': f"Purchase Order {po.po_number} for {po.vendor.legal_name}",
                    'department': po.cost_center.department.name if po.cost_center and po.cost_center.department else 'Procurement',
                    'requester_name': req_name,
                    'requester_email': submitter.email if submitter else '',
                    'vendor_name': po.vendor.legal_name if po.vendor else 'Unknown Vendor',
                    'amount': float(po.total_amount),
                    'previous_amount': None,
                    'revised_amount': None,
                    'delta_amount': None,
                    'currency': 'USD',
                    'status': po.status,
                    'status_display': po.get_status_display(),
                    'urgency': 'HIGH' if po.total_amount > Decimal('50000.00') else 'NORMAL',
                    'justification': f"Purchase order submitted for approval by {req_name}.",
                    'lines_count': po.lines.count(),
                    'created_at': po.created_at.isoformat(),
                    'updated_at': po.updated_at.isoformat(),
                    'detail_url': f'/orders/{po.id}/',
                    'can_approve': po.status == PurchaseOrder.STATUS_APPROVAL,
                })

        # Apply search filter
        if search_query:
            sq = search_query.lower()
            items = [
                it for it in items
                if sq in it['reference_number'].lower()
                or sq in it['title'].lower()
                or sq in it['department'].lower()
                or sq in it['requester_name'].lower()
                or sq in it['requester_email'].lower()
                or sq in it['vendor_name'].lower()
                or sq in it['justification'].lower()
            ]

        items.sort(key=lambda x: x['updated_at'], reverse=True)

        try:
            page = max(1, int(request.GET.get('page', 1)))
        except (ValueError, TypeError):
            page = 1
        try:
            page_size = max(1, min(100, int(request.GET.get('page_size', 10))))
        except (ValueError, TypeError):
            page_size = 10

        paginator = Paginator(items, page_size)
        page_obj = paginator.get_page(page)

        return Response({
            'summary': {
                'total_pending_count': total_pending_count,
                'pr_pending_count': total_pending_prs,
                'po_amendment_pending_count': total_pending_amendments,
                'po_approval_pending_count': total_pending_pos,
                'total_pending_value': total_pending_value,
                'history_count': total_history_count,
            },
            'results': list(page_obj.object_list),
            'count': paginator.count,
            'page': page,
            'page_size': page_size,
            'total_pages': paginator.num_pages,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        }, status=status.HTTP_200_OK)


class ManagerApprovalActionAPIView(APIView):
    """
    Executes approval or rejection governance action on PR or PO Amendment.
    """
    permission_classes = [IsAuthenticated, IsProcurementManager]

    def post(self, request):
        item_type = str(request.data.get('item_type', '')).strip().upper()
        item_id = str(request.data.get('item_id', '')).strip()
        action = str(request.data.get('action', '')).strip().upper()
        comments = str(request.data.get('comments', '')).strip()

        if action not in ['APPROVE', 'REJECT']:
            return Response(
                {'error': "Invalid action. Supported actions are 'APPROVE' or 'REJECT'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not item_id:
            return Response(
                {'error': 'Missing required item_id.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.orders.models import POAmendment
        from apps.requisitions.models import PurchaseRequisition

        try:
            if item_type == 'PR':
                from apps.approvals.services import process_approval_action_service
                pr = PurchaseRequisition.objects.get(id=item_id)
                # Anti-IDOR: verify PR belongs to caller's organization
                caller_org = get_user_org(request.user)
                if not request.user.is_superuser:
                    pr_org_id = pr.department.organization_id if pr.department else None
                    if not caller_org or (pr_org_id and caller_org.id != pr_org_id):
                        return Response(
                            {'error': 'Permission Denied: Requisition belongs to another organization.'},
                            status=status.HTTP_403_FORBIDDEN,
                        )
                action_rec = process_approval_action_service(
                    target_object=pr,
                    actor=request.user,
                    action=action,
                    comments=comments,
                )
                pr.refresh_from_db()
                return Response({
                    'success': True,
                    'message': f"Requisition {pr.pr_number} has been {action.lower()}d successfully.",
                    'item_id': str(pr.id),
                    'new_status': pr.status,
                    'action_id': str(action_rec.id) if action_rec else None,
                }, status=status.HTTP_200_OK)

            elif item_type == 'PO_APPROVAL':
                from apps.orders.services import (
                    approve_purchase_order_service,
                    reject_purchase_order_service,
                )
                po = PurchaseOrder.objects.select_related(
                    'vendor', 'cost_center__department'
                ).get(id=item_id)
                # Anti-IDOR: verify PO belongs to caller's organization
                caller_org = get_user_org(request.user)
                if caller_org and not request.user.is_superuser:
                    po_org_id = (
                        po.cost_center.department.organization_id
                        if po.cost_center and po.cost_center.department
                        else None
                    )
                    if po_org_id != caller_org.id:
                        return Response(
                            {'error': 'Permission Denied: Purchase Order belongs to another organization.'},
                            status=status.HTTP_403_FORBIDDEN,
                        )
                if action == 'APPROVE':
                    updated_po = approve_purchase_order_service(
                        po=po,
                        approver=request.user,
                        comments=comments or 'Approved',
                    )
                    return Response({
                        'success': True,
                        'message': f"Purchase Order {updated_po.po_number} approved successfully.",
                        'item_id': str(po.id),
                        'new_status': updated_po.status,
                    }, status=status.HTTP_200_OK)
                else:
                    if not comments:
                        return Response(
                            {'error': 'A rejection reason is required.'},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    updated_po = reject_purchase_order_service(
                        po=po,
                        approver=request.user,
                        reason=comments,
                    )
                    return Response({
                        'success': True,
                        'message': f"Purchase Order {updated_po.po_number} rejected and returned to draft.",
                        'item_id': str(po.id),
                        'new_status': updated_po.status,
                    }, status=status.HTTP_200_OK)
            elif item_type in ['PO_AMENDMENT', 'PO']:
                from apps.orders.services import (
                    approve_po_amendment_service,
                    reject_po_amendment_service,
                )
                amendment = POAmendment.objects.get(id=item_id)
                # Anti-IDOR: verify PO amendment belongs to caller's organization
                caller_org = get_user_org(request.user)
                if caller_org and not request.user.is_superuser:
                    po_org_id = (
                        amendment.po.cost_center.department.organization_id
                        if amendment.po and amendment.po.cost_center and amendment.po.cost_center.department
                        else None
                    )
                    if po_org_id != caller_org.id:
                        return Response(
                            {'error': 'Permission Denied: PO Amendment belongs to another organization.'},
                            status=status.HTTP_403_FORBIDDEN,
                        )
                if action == 'APPROVE':
                    updated_po = approve_po_amendment_service(
                        amendment=amendment,
                        approver=request.user,
                        comments=comments,
                    )
                    amendment.refresh_from_db()
                    return Response({
                        'success': True,
                        'message': f"PO Amendment #{amendment.amendment_number} for PO {updated_po.po_number} approved successfully.",
                        'item_id': str(amendment.id),
                        'new_status': amendment.status,
                        'po_status': updated_po.status,
                    }, status=status.HTTP_200_OK)
                else:
                    if not comments:
                        comments = 'Rejected by Procurement Manager.'
                    updated_po = reject_po_amendment_service(
                        amendment=amendment,
                        rejector=request.user,
                        reason=comments,
                    )
                    amendment.refresh_from_db()
                    return Response({
                        'success': True,
                        'message': f"PO Amendment #{amendment.amendment_number} for PO {updated_po.po_number} rejected.",
                        'item_id': str(amendment.id),
                        'new_status': amendment.status,
                        'po_status': updated_po.status,
                    }, status=status.HTTP_200_OK)
            else:
                return Response(
                    {'error': f"Unsupported item_type '{item_type}'. Supported: 'PR', 'PO_APPROVAL', 'PO_AMENDMENT'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        except (PurchaseRequisition.DoesNotExist, POAmendment.DoesNotExist, PurchaseOrder.DoesNotExist):
            return Response(
                {'error': f"Target {item_type} record with ID {item_id} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class ManagerBudgetExceptionsAPIView(APIView):
    """
    GET /api/v1/manager/budget-exceptions/
    GET /api/v1/manager/policy-exceptions/

    Database-backed Policy & Budget Exceptions Desk for Procurement Manager.
    Returns PRs in STATUS_BUDGET_REVIEW and open Invoice 3-Way Match Exceptions across the organization.
    """
    permission_classes = [IsAuthenticated, IsProcurementManager]

    def get(self, request):
        org = get_user_org(request.user)

        from decimal import Decimal

        from django.db.models import Sum

        from apps.invoices.models import MatchException
        from apps.requisitions.models import PurchaseRequisition

        # 1. Budget Review PRs (Overruns)
        budget_prs_qs = PurchaseRequisition.objects.filter(
            status=PurchaseRequisition.STATUS_BUDGET_REVIEW
        ).select_related('department', 'requester', 'cost_center')
        if org:
            budget_prs_qs = budget_prs_qs.filter(department__organization=org)

        # 2. Match Exceptions (Variances)
        exceptions_qs = MatchException.objects.filter(
            status=MatchException.STATUS_OPEN
        ).select_related('invoice', 'invoice__vendor', 'invoice__po')
        if org:
            exceptions_qs = exceptions_qs.filter(
                invoice__po__cost_center__department__organization=org
            )

        kpi_overrun_count = budget_prs_qs.count()
        kpi_overrun_val = budget_prs_qs.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        kpi_match_count = exceptions_qs.count()

        prs_data = [
            {
                "id": str(pr.id),
                "pr_number": pr.pr_number,
                "requisition_number": pr.pr_number,
                "title": pr.title,
                "department_name": pr.department.name if pr.department else "N/A",
                "cost_center_code": pr.cost_center.code if pr.cost_center else "N/A",
                "requester_name": (pr.requester.get_full_name() or pr.requester.email) if pr.requester else "N/A",
                "total_amount": float(pr.total_amount),
                "currency": getattr(pr, 'currency', 'USD'),
                "created_at": pr.created_at.isoformat(),
                "status": pr.status,
                "status_display": pr.get_status_display(),
            }
            for pr in budget_prs_qs.order_by('-updated_at')[:50]
        ]

        exceptions_data = [
            {
                "id": str(exc.id),
                "invoice_number": exc.invoice.invoice_number if exc.invoice else "N/A",
                "vendor_name": exc.invoice.vendor.legal_name if exc.invoice and exc.invoice.vendor else "N/A",
                "exception_type": exc.exception_type,
                "exception_type_display": exc.get_exception_type_display(),
                "variance_amount": float(exc.variance_amount or 0),
                "discrepancy_amount": float(exc.variance_amount or 0),
                "status": exc.status,
                "created_at": exc.created_at.isoformat(),
            }
            for exc in exceptions_qs.order_by('-created_at')[:50]
        ]

        return Response(
            {
                "metrics": {
                    "kpi_overrun_count": kpi_overrun_count,
                    "kpi_overrun_value": float(kpi_overrun_val),
                    "kpi_match_exceptions_count": kpi_match_count,
                    "total_exceptions_count": kpi_overrun_count + kpi_match_count,
                },
                "summary": {
                    "kpi_overrun_count": kpi_overrun_count,
                    "kpi_overrun_value": float(kpi_overrun_val),
                    "kpi_match_exceptions_count": kpi_match_count,
                    "kpi_approved_exceptions_count": 0,
                },
                "budget_overrun_prs": prs_data,
                "invoice_match_exceptions": exceptions_data,
            },
            status=status.HTTP_200_OK,
        )
