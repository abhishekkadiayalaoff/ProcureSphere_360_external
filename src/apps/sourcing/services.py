from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.vendors.models import Vendor

from .models import AwardDecision, BidInvite, BidLine, SourcingEvent, VendorBid


@transaction.atomic
def create_sourcing_event_service(
    *,
    title: str,
    event_type: str,
    bid_start_date,
    bid_end_date,
    description: str,
    requisition=None,
    created_by_user: User = None,
) -> SourcingEvent:
    """
    Creates a new RFQ/RFP sourcing event in DRAFT status.
    """
    event_count = SourcingEvent.objects.count() + 1
    prefix = "RFQ" if event_type == SourcingEvent.TYPE_RFQ else "RFP"
    event_number = f"{prefix}-{timezone.now().strftime('%Y')}-{event_count:05d}"

    event = SourcingEvent.objects.create(
        event_number=event_number,
        title=title,
        event_type=event_type,
        requisition=requisition,
        status=SourcingEvent.STATUS_DRAFT,
        bid_start_date=bid_start_date,
        bid_end_date=bid_end_date,
        description=description,
        is_sealed=True,
    )

    AuditLog.objects.create(
        actor=created_by_user,
        action=AuditLog.ACTION_CREATE,
        target_model="SourcingEvent",
        target_object_id=str(event.id),
        new_state={
            "event_number": event.event_number,
            "status": event.status,
            "event_type": event.event_type,
        },
    )

    return event


@transaction.atomic
def publish_sourcing_event_service(*, event: SourcingEvent, user: User) -> SourcingEvent:
    """
    Publishes a sourcing event and opens the bid window.
    """
    if event.status != SourcingEvent.STATUS_DRAFT:
        raise ValidationError(f"Cannot publish event in status '{event.status}'. Must be DRAFT.")

    previous_status = event.status
    event.status = SourcingEvent.STATUS_BID_WINDOW
    event.save(update_fields=["status", "updated_at"])

    AuditLog.objects.create(
        actor=user,
        action=AuditLog.ACTION_UPDATE,
        target_model="SourcingEvent",
        target_object_id=str(event.id),
        previous_state={"status": previous_status},
        new_state={"status": event.status},
    )

    return event


@transaction.atomic
def invite_vendors_to_event_service(
    *, event: SourcingEvent, vendor_ids: list, invited_by: User
) -> list:
    """
    Invites active eligible vendors to participate in a sourcing event.
    Blocks suspended/blacklisted vendors.
    """
    invitations = []
    for vid in vendor_ids:
        vendor = Vendor.objects.get(id=vid)
        if vendor.status == Vendor.STATUS_SUSPENDED:
            raise ValidationError(
                f"Vendor '{vendor.legal_name}' is currently suspended and cannot be invited."
            )

        invite, _ = BidInvite.objects.get_or_create(event=event, vendor=vendor)
        invitations.append(invite)

    return invitations


@transaction.atomic
def submit_vendor_bid_service(
    *,
    event: SourcingEvent,
    vendor: Vendor,
    line_items: list,
    proposal_summary: str = "",
    submitted_by_user: User = None,
) -> VendorBid:
    """
    Submits a sealed bid for a vendor during the BID_WINDOW.
    """
    if event.status != SourcingEvent.STATUS_BID_WINDOW:
        raise ValidationError(
            f"Bidding is closed for event '{event.event_number}'. Current status: {event.status}"
        )

    if vendor.status == Vendor.STATUS_SUSPENDED:
        raise ValidationError(f"Vendor '{vendor.legal_name}' is suspended and cannot submit bids.")

    bid_count = VendorBid.objects.count() + 1
    bid_number = f"BID-{timezone.now().strftime('%Y')}-{bid_count:05d}"

    bid, created = VendorBid.objects.get_or_create(
        event=event,
        vendor=vendor,
        defaults={
            "bid_number": bid_number,
            "status": VendorBid.STATUS_SUBMITTED,
            "proposal_summary": proposal_summary,
            "total_bid_amount": Decimal("0.00"),
        },
    )

    if not created:
        bid.status = VendorBid.STATUS_SUBMITTED
        bid.proposal_summary = proposal_summary
        bid.lines.all().delete()

    total = Decimal("0.00")
    for item in line_items:
        line = BidLine.objects.create(
            bid=bid,
            pr_line=item.get("pr_line"),
            item_description=item["item_description"],
            quantity=Decimal(str(item["quantity"])),
            quoted_unit_price=Decimal(str(item["quoted_unit_price"])),
        )
        total += line.quoted_total_price

    bid.total_bid_amount = total
    bid.save(update_fields=["total_bid_amount", "status", "proposal_summary", "updated_at"])

    # Update invite status
    BidInvite.objects.filter(event=event, vendor=vendor).update(is_responded=True)

    AuditLog.objects.create(
        actor=submitted_by_user,
        action=AuditLog.ACTION_CREATE if created else AuditLog.ACTION_UPDATE,
        target_model="VendorBid",
        target_object_id=str(bid.id),
        new_state={
            "bid_number": bid.bid_number,
            "total_amount": str(bid.total_bid_amount),
            "vendor": vendor.legal_name,
        },
    )

    return bid


@transaction.atomic
def evaluate_and_award_sourcing_event_service(
    *, event: SourcingEvent, winning_bid: VendorBid, award_reason: str, approved_by_user: User
) -> AwardDecision:
    """
    Executes technical/commercial evaluation completion and records AwardDecision.
    Transitions event status to AWARDED.
    """
    if winning_bid.event_id != event.id:
        raise ValidationError("Winning bid does not belong to target sourcing event.")

    previous_status = event.status
    event.status = SourcingEvent.STATUS_AWARDED
    event.save(update_fields=["status", "updated_at"])

    decision = AwardDecision.objects.create(
        event=event,
        winning_bid=winning_bid,
        award_reason=award_reason,
        approved_by=approved_by_user,
    )

    AuditLog.objects.create(
        actor=approved_by_user,
        action=AuditLog.ACTION_APPROVE,
        target_model="AwardDecision",
        target_object_id=str(decision.id),
        previous_state={"status": previous_status},
        new_state={
            "event_number": event.event_number,
            "winner": winning_bid.vendor.legal_name,
            "status": event.status,
        },
    )

    return decision
