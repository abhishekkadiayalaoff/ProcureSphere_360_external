"""
Read models for the two sourcing workspaces:

- Vendor Bid Portal monitor (internal): restricted submission, validation, attachments,
  amendments before close and sealed visibility. While the bid window is open only bid
  METADATA is exposed (who / when / version count / validity / attachment counts) — never
  amounts, proposal text, validation messages or amendment reasons.
- Evaluation & Award: commercial comparison matrix and decision audit trail.
"""

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.vendors.models import Vendor

from .models import BidInvite, SourcingEvent, VendorBid

BID_PORTAL_STATUSES = [SourcingEvent.STATUS_PUBLISHED, SourcingEvent.STATUS_BID_WINDOW]
EVALUATION_STATUSES = [
    SourcingEvent.STATUS_TECHNICAL_REVIEW,
    SourcingEvent.STATUS_COMMERCIAL_REVIEW,
    SourcingEvent.STATUS_AWARD_APPROVAL,
    SourcingEvent.STATUS_AWARDED,
]
RESPONSE_STATUSES = [VendorBid.STATUS_SUBMITTED, VendorBid.STATUS_AMENDED]


# ------------------------------------------------------------------ vendor bid portal ------


def get_bid_portal_metrics() -> dict:
    now = timezone.now()
    live = SourcingEvent.objects.filter(status__in=BID_PORTAL_STATUSES)
    live_bids = VendorBid.objects.filter(event__status__in=BID_PORTAL_STATUSES)
    return {
        "open_windows": live.filter(status=SourcingEvent.STATUS_BID_WINDOW).count(),
        "scheduled": live.filter(status=SourcingEvent.STATUS_PUBLISHED).count(),
        "closing_soon": live.filter(
            status=SourcingEvent.STATUS_BID_WINDOW,
            bid_end_date__gt=now,
            bid_end_date__lte=now + timedelta(days=3),
        ).count(),
        "awaiting_response": BidInvite.objects.filter(
            event__status__in=BID_PORTAL_STATUSES, is_responded=False
        ).count(),
        "drafts": live_bids.filter(status=VendorBid.STATUS_DRAFT).count(),
        "submitted": live_bids.filter(status__in=RESPONSE_STATUSES).count(),
        "amended": live_bids.filter(version__gt=1).count(),
        "withdrawn": live_bids.filter(status=VendorBid.STATUS_WITHDRAWN).count(),
    }


def get_bid_portal_events():
    """Events in the bid-portal stage, plus those that closed within the last 14 days."""
    recent = timezone.now() - timedelta(days=14)
    return (
        SourcingEvent.objects.filter(
            Q(status__in=BID_PORTAL_STATUSES)
            | Q(status=SourcingEvent.STATUS_TECHNICAL_REVIEW, bid_end_date__gte=recent)
        )
        .annotate(
            invite_count=Count("invitations", distinct=True),
            responded_count=Count(
                "invitations", filter=Q(invitations__is_responded=True), distinct=True
            ),
            submitted_bid_count=Count(
                "bids", filter=Q(bids__status__in=RESPONSE_STATUSES), distinct=True
            ),
            draft_bid_count=Count(
                "bids", filter=Q(bids__status=VendorBid.STATUS_DRAFT), distinct=True
            ),
        )
        .order_by("bid_end_date")
    )


def _submission_access(event, vendor, now):
    """Whether the server would currently accept a submission from this invited vendor."""
    if vendor.status == Vendor.STATUS_SUSPENDED:
        return {"code": "blocked", "label": "Blocked — vendor suspended"}
    if vendor.status != Vendor.STATUS_ACTIVE:
        return {"code": "blocked", "label": f"Blocked — vendor {vendor.get_status_display()}"}
    if event.status == SourcingEvent.STATUS_PUBLISHED or now < event.bid_start_date:
        opens = timezone.localtime(event.bid_start_date).strftime("%Y-%m-%d %H:%M")
        return {"code": "scheduled", "label": f"Opens {opens}"}
    if event.status == SourcingEvent.STATUS_BID_WINDOW and now <= event.bid_end_date:
        return {"code": "open", "label": "Open until deadline"}
    return {"code": "closed", "label": "Closed — deadline passed"}


# Validation errors that only describe the window state, not the bid's content.
_WINDOW_STATE_ERRORS = ("deadline", "not currently accepting")


def get_bid_portal_rows(event: SourcingEvent):
    """One row per invited vendor with submission access, bid status, versions, validation."""
    from .services import validate_bid_service

    now = timezone.now()
    sealed = not event.bids_visible_to_evaluators
    bids = {
        b.vendor_id: b
        for b in VendorBid.objects.filter(event=event)
        .select_related("event", "vendor")
        .prefetch_related("lines", "attachments", "versions")
    }
    rows = []
    for invite in event.invitations.select_related("vendor", "vendor__category").order_by(
        "vendor__legal_name"
    ):
        bid = bids.get(invite.vendor_id)
        row = {
            "invite": invite,
            "vendor": invite.vendor,
            "access": _submission_access(event, invite.vendor, now),
            "bid": bid,
            "versions": [],
            "attachments": [],
            "validation": None,
        }
        if bid:
            row["versions"] = [
                {
                    "number": v.version_number,
                    "status": v.status,
                    "at": v.submitted_at or v.created_at,
                    "reason": None if sealed else v.amendment_reason,
                }
                for v in sorted(bid.versions.all(), key=lambda v: v.version_number)
            ]
            counts = {}
            for att in bid.attachments.all():
                label = att.get_document_type_display()
                counts[label] = counts.get(label, 0) + 1
            row["attachments"] = sorted(counts.items())
            result = validate_bid_service(bid=bid)
            content_errors = [
                e for e in result["errors"] if not any(k in e.lower() for k in _WINDOW_STATE_ERRORS)
            ]
            row["validation"] = {
                "is_valid": not content_errors,
                "issue_count": len(content_errors) + len(result["warnings"]),
                "messages": None if sealed else content_errors + result["warnings"],
            }
        rows.append(row)
    return rows


# ------------------------------------------------------------------ evaluation & award -----


def get_evaluation_metrics() -> dict:
    from apps.orders.models import PurchaseOrder

    counts = {s: SourcingEvent.objects.filter(status=s).count() for s in EVALUATION_STATUSES}
    awarded_with_po = (
        SourcingEvent.objects.filter(status=SourcingEvent.STATUS_AWARDED)
        .filter(purchase_orders__isnull=False)
        .exclude(purchase_orders__status=PurchaseOrder.STATUS_CANCELLED)
        .distinct()
        .count()
    )
    return {
        "technical": counts[SourcingEvent.STATUS_TECHNICAL_REVIEW],
        "commercial": counts[SourcingEvent.STATUS_COMMERCIAL_REVIEW],
        "approval": counts[SourcingEvent.STATUS_AWARD_APPROVAL],
        "awarded": counts[SourcingEvent.STATUS_AWARDED],
        "awarded_without_po": counts[SourcingEvent.STATUS_AWARDED] - awarded_with_po,
    }


def get_evaluation_events(status=None):
    qs = SourcingEvent.objects.filter(status__in=EVALUATION_STATUSES)
    if status in EVALUATION_STATUSES:
        qs = qs.filter(status=status)
    return qs.annotate(
        submitted_bid_count=Count(
            "bids", filter=Q(bids__status__in=RESPONSE_STATUSES), distinct=True
        ),
        evaluation_count=Count("evaluations", distinct=True),
    ).order_by("-updated_at")


def build_commercial_comparison(event: SourcingEvent, rows):
    """
    Side-by-side price matrix built from evaluation rows (only once commercial is unsealed).
    Lines are matched across vendors by normalised item description; the lowest price per
    line and the lowest total are flagged, and each total shows its % above the lowest.
    """
    if not event.commercial_visible_to_evaluators or not rows:
        return None
    order, matrix = [], {}
    for idx, r in enumerate(rows):
        for line in r["lines"]:
            key = " ".join(line.item_description.lower().split())
            if key not in matrix:
                matrix[key] = {"label": line.item_description, "cells": [None] * len(rows)}
                order.append(key)
            matrix[key]["cells"][idx] = line

    lines = []
    for key in order:
        cells = matrix[key]["cells"]
        prices = [c.quoted_total_price for c in cells if c is not None]
        low = min(prices) if prices else None
        lines.append(
            {
                "label": matrix[key]["label"],
                "cells": [
                    {"line": c, "is_lowest": c is not None and c.quoted_total_price == low}
                    for c in cells
                ],
            }
        )

    amounts = [r["amount"] for r in rows if r["amount"] is not None]
    lowest = min(amounts) if amounts else None
    totals = []
    for r in rows:
        amount = r["amount"]
        delta = None
        if amount is not None and lowest:
            delta = round((amount - lowest) / lowest * 100, 1)
        totals.append({"amount": amount, "is_lowest": amount == lowest, "delta_pct": delta})
    return {"vendors": [r["vendor"] for r in rows], "lines": lines, "totals": totals}


def get_decision_audit(event: SourcingEvent):
    """Evaluation/award decision trail: stage changes, scores, negotiation, award decisions."""
    ids = [str(i) for i in event.award_decisions.values_list("id", flat=True)]
    ids += [str(i) for i in event.evaluations.values_list("id", flat=True)]
    ids += [str(i) for i in event.negotiation_notes.values_list("id", flat=True)]
    stage_changes = Q(
        target_model="SourcingEvent",
        target_object_id=str(event.id),
        new_state__status__in=EVALUATION_STATUSES,
    )
    return (
        AuditLog.objects.filter(
            Q(
                target_model__in=["AwardDecision", "BidEvaluation", "NegotiationNote"],
                target_object_id__in=ids,
            )
            | stage_changes
        )
        .select_related("actor", "actor__role")
        .order_by("-timestamp")
    )
