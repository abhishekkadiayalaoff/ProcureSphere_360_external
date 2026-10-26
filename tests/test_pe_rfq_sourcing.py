"""
Procurement Executive — RFQ/RFP Sourcing.
Lifecycle, publish validation, eligibility, invitations, bid window/deadline, sealed and
two-envelope visibility, evaluation, award approval, award -> PO, clarifications, RBAC/IDOR.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.notifications.models import Notification
from apps.orders.models import PurchaseOrder
from apps.sourcing import services as svc
from apps.sourcing.models import (
    AwardDecision,
    BidAttachment,
    BidInvite,
    NegotiationNote,
    SourcingEvent,
    VendorBid,
)
from apps.sourcing.selectors import get_sealed_vendor_bids
from apps.vendors.models import Vendor

pytestmark = [pytest.mark.django_db, pytest.mark.regression]

LINES = [{"item_description": "Server", "quantity": "2", "quoted_unit_price": "1000.00"}]


def make_event(world, *, start=None, end=None, event_type=SourcingEvent.TYPE_RFQ, **kw):
    now = timezone.now()
    return svc.create_sourcing_event_service(
        title=kw.pop("title", "Compute refresh"),
        event_type=event_type,
        bid_start_date=start or now - timedelta(hours=1),
        bid_end_date=end or now + timedelta(days=5),
        description="Replace compute nodes",
        technical_requirements="2U, redundant PSU",
        commercial_requirements="Net 30, 3y warranty",
        created_by_user=world["exec"],
        **kw,
    )


def open_event(world, vendors=("vendor_a", "vendor_b"), **kw):
    event = make_event(world, **kw)
    svc.invite_vendors_to_event_service(
        event=event, vendor_ids=[world[v].id for v in vendors], invited_by=world["exec"]
    )
    svc.publish_sourcing_event_service(event=event, user=world["exec"])
    return event


def submit(world, event, vendor_key, user_key, price="1000.00"):
    lines = [dict(LINES[0], quoted_unit_price=price)]
    return svc.submit_vendor_bid_service(
        event=event,
        vendor=world[vendor_key],
        line_items=lines,
        proposal_summary="Summary",
        technical_proposal=f"Technical proposal from {vendor_key}",
        commercial_proposal=f"Commercial terms from {vendor_key}",
        submitted_by_user=world[user_key],
    )


def expire(event):
    """Simulate the server clock passing the bid deadline."""
    event.bid_end_date = timezone.now() - timedelta(minutes=1)
    event.save(update_fields=["bid_end_date"])


def to_commercial_review(world, event, scores=None):
    expire(event)
    svc.sync_event_window_status(event=event)
    assert event.status == SourcingEvent.STATUS_TECHNICAL_REVIEW
    for bid in event.bids.filter(status__in=svc.EVALUABLE_BID_STATUSES):
        svc.record_technical_evaluation_service(
            event=event, bid=bid, evaluator=world["exec"], score=(scores or {}).get(bid.id, 80)
        )
    svc.advance_to_commercial_review_service(event=event, user=world["exec"])
    return event


# ---------------------------------------------------------------- creation & draft --------


class TestCreateAndDraft:
    def test_create_rfq_and_rfp_in_draft_with_numbering_and_audit(self, procurement_world):
        rfq = make_event(procurement_world)
        rfp = make_event(procurement_world, event_type=SourcingEvent.TYPE_RFP)
        assert rfq.status == rfp.status == SourcingEvent.STATUS_DRAFT
        assert rfq.event_number.startswith("RFQ-") and rfp.event_number.startswith("RFP-")
        assert AuditLog.objects.filter(
            target_model="SourcingEvent", target_object_id=str(rfq.id), action="CREATE"
        ).exists()

    @pytest.mark.parametrize(
        "overrides,message",
        [
            ({"title": ""}, "Title is required"),
            ({"event_type": "AUCTION"}, "RFQ or RFP"),
            ({"description": ""}, "Description"),
            ({"technical_weight": 70, "commercial_weight": 40}, "add up to 100"),
        ],
    )
    def test_create_validates_required_fields(self, procurement_world, overrides, message):
        now = timezone.now()
        kwargs = dict(
            title="T",
            event_type="RFQ",
            bid_start_date=now,
            bid_end_date=now + timedelta(days=1),
            description="D",
            created_by_user=procurement_world["exec"],
        )
        kwargs.update(overrides)
        with pytest.raises(ValidationError, match=message):
            svc.create_sourcing_event_service(**kwargs)

    def test_bid_start_must_precede_deadline(self, procurement_world):
        now = timezone.now()
        with pytest.raises(ValidationError, match="earlier than the bid deadline"):
            make_event(
                procurement_world, start=now + timedelta(days=2), end=now + timedelta(days=1)
            )

    def test_edit_draft_audits_previous_values_and_published_is_locked(self, procurement_world):
        event = make_event(procurement_world)
        svc.update_draft_sourcing_event_service(
            event=event, user=procurement_world["exec"], data={"title": "Renamed"}
        )
        event.refresh_from_db()
        assert event.title == "Renamed"
        log = AuditLog.objects.filter(target_object_id=str(event.id), action="UPDATE").first()
        assert log.previous_state["title"] == "Compute refresh"

        svc.invite_vendors_to_event_service(
            event=event,
            vendor_ids=[procurement_world["vendor_a"].id],
            invited_by=procurement_world["exec"],
        )
        svc.publish_sourcing_event_service(event=event, user=procurement_world["exec"])
        with pytest.raises(ValidationError, match="Only DRAFT"):
            svc.update_draft_sourcing_event_service(
                event=event, user=procurement_world["exec"], data={"title": "Too late"}
            )


# ---------------------------------------------------------------- publish ------------------


class TestPublish:
    def test_publish_requires_invited_vendor(self, procurement_world):
        event = make_event(procurement_world)
        with pytest.raises(ValidationError, match="Invite at least one eligible vendor"):
            svc.publish_sourcing_event_service(event=event, user=procurement_world["exec"])
        event.refresh_from_db()
        assert event.status == SourcingEvent.STATUS_DRAFT

    def test_publish_rejects_past_deadline(self, procurement_world):
        now = timezone.now()
        event = make_event(
            procurement_world, start=now - timedelta(days=3), end=now + timedelta(days=1)
        )
        svc.invite_vendors_to_event_service(
            event=event,
            vendor_ids=[procurement_world["vendor_a"].id],
            invited_by=procurement_world["exec"],
        )
        expire(event)
        with pytest.raises(ValidationError, match="deadline is in the past"):
            svc.publish_sourcing_event_service(event=event, user=procurement_world["exec"])

    def test_future_start_publishes_then_opens_window_on_schedule(self, procurement_world):
        now = timezone.now()
        event = make_event(
            procurement_world, start=now + timedelta(hours=2), end=now + timedelta(days=2)
        )
        svc.invite_vendors_to_event_service(
            event=event,
            vendor_ids=[procurement_world["vendor_a"].id],
            invited_by=procurement_world["exec"],
        )
        svc.publish_sourcing_event_service(event=event, user=procurement_world["exec"])
        assert event.status == SourcingEvent.STATUS_PUBLISHED

        with pytest.raises(ValidationError):
            submit(procurement_world, event, "vendor_a", "user_a")

        svc.sync_event_window_status(event=event, now=now + timedelta(hours=3))
        assert event.status == SourcingEvent.STATUS_BID_WINDOW
        assert AuditLog.objects.filter(
            target_object_id=str(event.id), new_state__status="BID_WINDOW", actor__isnull=True
        ).exists()

    def test_publish_notifies_invited_vendor_users_and_audits(self, procurement_world):
        event = open_event(procurement_world)
        assert event.status == SourcingEvent.STATUS_BID_WINDOW
        assert Notification.objects.filter(
            recipient=procurement_world["user_a"],
            notification_type=Notification.TYPE_RFQ_INVITATION,
        ).exists()
        assert not Notification.objects.filter(recipient=procurement_world["user_c"]).exists()
        assert AuditLog.objects.filter(
            target_object_id=str(event.id),
            new_state__status="PUBLISHED",
            actor=procurement_world["exec"],
        ).exists()


# ---------------------------------------------------------------- eligibility & invites ----


class TestEligibilityAndInvitations:
    @pytest.mark.parametrize(
        "vendor_key", ["vendor_hold", "vendor_susp", "vendor_draft", "vendor_kyc"]
    )
    def test_ineligible_vendors_cannot_be_invited(self, procurement_world, vendor_key):
        event = make_event(procurement_world)
        with pytest.raises(ValidationError, match="not eligible"):
            svc.invite_vendors_to_event_service(
                event=event,
                vendor_ids=[procurement_world[vendor_key].id],
                invited_by=procurement_world["exec"],
            )
        assert not BidInvite.objects.filter(event=event).exists()

    def test_duplicate_invitation_rejected(self, procurement_world):
        event = make_event(procurement_world)
        svc.invite_vendors_to_event_service(
            event=event,
            vendor_ids=[procurement_world["vendor_a"].id],
            invited_by=procurement_world["exec"],
        )
        with pytest.raises(ValidationError, match="already invited"):
            svc.invite_vendors_to_event_service(
                event=event,
                vendor_ids=[procurement_world["vendor_a"].id],
                invited_by=procurement_world["exec"],
            )
        assert BidInvite.objects.filter(event=event).count() == 1

    def test_vendor_suspended_after_invite_blocks_publish(self, procurement_world):
        event = make_event(procurement_world)
        svc.invite_vendors_to_event_service(
            event=event,
            vendor_ids=[procurement_world["vendor_a"].id],
            invited_by=procurement_world["exec"],
        )
        Vendor.objects.filter(pk=procurement_world["vendor_a"].pk).update(
            status=Vendor.STATUS_SUSPENDED
        )
        with pytest.raises(ValidationError, match="no longer eligible"):
            svc.publish_sourcing_event_service(event=event, user=procurement_world["exec"])

    def test_late_invite_during_bid_window_notifies_and_after_deadline_is_blocked(
        self, procurement_world
    ):
        event = open_event(procurement_world, vendors=("vendor_a",))
        svc.invite_vendors_to_event_service(
            event=event,
            vendor_ids=[procurement_world["vendor_c"].id],
            invited_by=procurement_world["exec"],
        )
        assert Notification.objects.filter(recipient=procurement_world["user_c"]).exists()
        expire(event)
        with pytest.raises(ValidationError):
            svc.invite_vendors_to_event_service(
                event=event,
                vendor_ids=[procurement_world["vendor_b"].id],
                invited_by=procurement_world["exec"],
            )

    def test_draft_event_is_invisible_to_invited_vendor_portal(self, client, procurement_world):
        event = make_event(procurement_world)
        svc.invite_vendors_to_event_service(
            event=event,
            vendor_ids=[procurement_world["vendor_a"].id],
            invited_by=procurement_world["exec"],
        )
        client.force_login(procurement_world["user_a"])
        assert client.get(f"/vendor/sourcing/{event.id}/").status_code == 403
        assert event.event_number not in client.get("/vendor/sourcing/").content.decode()
        with pytest.raises(ValidationError):
            svc.ask_clarification_service(
                event=event,
                vendor=procurement_world["vendor_a"],
                user=procurement_world["user_a"],
                question="?",
            )


# ---------------------------------------------------------------- bid window & deadline ----


class TestBidWindowAndDeadline:
    def test_deadline_blocks_submission_amendment_withdrawal_and_attachments(
        self, procurement_world
    ):
        event = open_event(procurement_world)
        bid = submit(procurement_world, event, "vendor_a", "user_a")
        expire(event)
        with pytest.raises(ValidationError, match="deadline"):
            submit(procurement_world, event, "vendor_b", "user_b")
        with pytest.raises(ValidationError, match="deadline"):
            svc.amend_vendor_bid_service(
                bid=bid,
                vendor_user=procurement_world["user_a"],
                amendment_reason="late",
                line_items=LINES,
            )
        with pytest.raises(ValidationError):
            svc.withdraw_vendor_bid_service(
                bid=bid, user=procurement_world["user_a"], reason="late"
            )
        with pytest.raises(ValidationError):
            svc.upload_bid_attachment_service(
                bid=bid,
                user=procurement_world["user_a"],
                file=SimpleUploadedFile("late.pdf", b"%PDF-1.4", content_type="application/pdf"),
            )

    def test_close_before_deadline_rejected_and_auto_closure_after(self, procurement_world):
        event = open_event(procurement_world)
        with pytest.raises(ValidationError, match="before the deadline"):
            svc.close_bid_window_service(event=event, user=procurement_world["exec"])
        expire(event)
        assert svc.sync_all_event_windows() == 1
        event.refresh_from_db()
        assert event.status == SourcingEvent.STATUS_TECHNICAL_REVIEW

    def test_celery_task_closes_expired_windows_with_run_evidence(self, procurement_world):
        from apps.sourcing.tasks import sync_sourcing_bid_windows_task

        event = open_event(procurement_world)
        expire(event)
        assert sync_sourcing_bid_windows_task() == 1
        assert AuditLog.objects.filter(target_model="CeleryTaskRun").exists()

    def test_withdrawal_before_close_preserves_version(self, procurement_world):
        event = open_event(procurement_world)
        bid = submit(procurement_world, event, "vendor_a", "user_a")
        svc.withdraw_vendor_bid_service(
            bid=bid, user=procurement_world["user_a"], reason="capacity"
        )
        bid.refresh_from_db()
        assert bid.status == VendorBid.STATUS_WITHDRAWN
        assert bid.versions.filter(version_number=1).exists()
        with pytest.raises(ValidationError):
            svc.amend_vendor_bid_service(
                bid=bid,
                vendor_user=procurement_world["user_a"],
                amendment_reason="x",
                line_items=LINES,
            )

    def test_attachment_upload_validates_extension_and_owner(self, procurement_world):
        event = open_event(procurement_world)
        bid = submit(procurement_world, event, "vendor_a", "user_a")
        with pytest.raises(ValidationError, match="not permitted"):
            svc.upload_bid_attachment_service(
                bid=bid,
                user=procurement_world["user_a"],
                file=SimpleUploadedFile("x.exe", b"MZ", content_type="application/octet-stream"),
            )
        with pytest.raises(ValidationError, match="Only the bidding vendor"):
            svc.upload_bid_attachment_service(
                bid=bid,
                user=procurement_world["user_b"],
                file=SimpleUploadedFile("x.pdf", b"%PDF", content_type="application/pdf"),
            )


# ---------------------------------------------------------------- sealed / two envelopes ---


class TestSealedVisibility:
    def test_bids_sealed_until_close_then_commercial_sealed_until_commercial_review(
        self, procurement_world
    ):
        event = open_event(procurement_world)
        submit(procurement_world, event, "vendor_a", "user_a")
        submit(procurement_world, event, "vendor_b", "user_b", price="900.00")

        assert get_sealed_vendor_bids(event, procurement_world["exec"]).count() == 0
        assert get_sealed_vendor_bids(event, procurement_world["user_a"]).count() == 1

        expire(event)
        svc.sync_event_window_status(event=event)
        assert get_sealed_vendor_bids(event, procurement_world["exec"]).count() == 2
        # Finance/requester have no bid-read right at any stage
        assert get_sealed_vendor_bids(event, procurement_world["finance"]).count() == 0

    def test_api_hides_commercial_envelope_during_technical_review(
        self, api_client, procurement_world
    ):
        event = open_event(procurement_world)
        submit(procurement_world, event, "vendor_a", "user_a")
        expire(event)
        api_client.force_authenticate(procurement_world["exec"])
        data = api_client.get(f"/api/v1/sourcing-events/events/{event.id}/bids/").json()
        assert len(data) == 1
        assert "technical_proposal" in data[0]
        assert "total_bid_amount" not in data[0] and "commercial_proposal" not in data[0]
        event.refresh_from_db()  # the API request closed the window server-side
        assert event.status == SourcingEvent.STATUS_TECHNICAL_REVIEW

        for bid in event.bids.all():
            svc.record_technical_evaluation_service(
                event=event, bid=bid, evaluator=procurement_world["exec"], score=75
            )
        svc.advance_to_commercial_review_service(event=event, user=procurement_world["exec"])
        data = api_client.get(f"/api/v1/sourcing-events/events/{event.id}/bids/").json()
        assert Decimal(data[0]["total_bid_amount"]) == Decimal("2000.00")

    def test_evaluator_cannot_see_bids_via_api_during_window(self, api_client, procurement_world):
        event = open_event(procurement_world)
        submit(procurement_world, event, "vendor_a", "user_a")
        api_client.force_authenticate(procurement_world["exec"])
        assert api_client.get(f"/api/v1/sourcing-events/events/{event.id}/bids/").json() == []
        assert api_client.get("/api/v1/sourcing-events/bids/").json()["count"] == 0


# ---------------------------------------------------------------- evaluation & award -------


class TestEvaluationAndAward:
    def test_commercial_review_requires_all_technical_scores(self, procurement_world):
        event = open_event(procurement_world)
        submit(procurement_world, event, "vendor_a", "user_a")
        submit(procurement_world, event, "vendor_b", "user_b")
        expire(event)
        svc.sync_event_window_status(event=event)
        bid_a = event.bids.get(vendor=procurement_world["vendor_a"])
        svc.record_technical_evaluation_service(
            event=event, bid=bid_a, evaluator=procurement_world["exec"], score=90
        )
        with pytest.raises(ValidationError, match="Technical evaluation pending"):
            svc.advance_to_commercial_review_service(event=event, user=procurement_world["exec"])

    def test_scores_are_stage_bound_and_range_checked(self, procurement_world):
        event = open_event(procurement_world)
        bid = submit(procurement_world, event, "vendor_a", "user_a")
        with pytest.raises(ValidationError, match="TECHNICAL REVIEW"):
            svc.record_technical_evaluation_service(
                event=event, bid=bid, evaluator=procurement_world["exec"], score=50
            )
        expire(event)
        svc.sync_event_window_status(event=event)
        with pytest.raises(ValidationError, match="between 0 and 100"):
            svc.record_technical_evaluation_service(
                event=event, bid=bid, evaluator=procurement_world["exec"], score=150
            )
        with pytest.raises(ValidationError, match="COMMERCIAL REVIEW"):
            svc.record_commercial_evaluation_service(
                event=event, bid=bid, evaluator=procurement_world["exec"], score=50
            )

    def test_weighted_score_uses_event_weights(self, procurement_world):
        event = open_event(procurement_world, technical_weight=70, commercial_weight=30)
        bid = submit(procurement_world, event, "vendor_a", "user_a")
        to_commercial_review(procurement_world, event, scores={bid.id: 80})
        ev = svc.record_commercial_evaluation_service(
            event=event, bid=bid, evaluator=procurement_world["exec"], score=60
        )
        assert ev.weighted_total_score == Decimal("74.00")  # 80*0.7 + 60*0.3

    def test_recommend_then_manager_approves_then_po_generated(self, procurement_world):
        w = procurement_world
        event = open_event(w)
        bid_a = submit(w, event, "vendor_a", "user_a")
        bid_b = submit(w, event, "vendor_b", "user_b", price="900.00")
        to_commercial_review(w, event)
        for bid in (bid_a, bid_b):
            svc.record_commercial_evaluation_service(
                event=event, bid=bid, evaluator=w["exec"], score=70
            )
        svc.add_negotiation_note_service(
            event=event, bid=bid_b, author=w["exec"], note="Asked for 5% off"
        )

        decision = svc.recommend_award_service(
            event=event,
            winning_bid=bid_b,
            recommended_by=w["exec"],
            award_reason="Lowest compliant",
        )
        assert event.status == SourcingEvent.STATUS_AWARD_APPROVAL
        assert decision.status == AwardDecision.STATUS_PENDING
        assert Notification.objects.filter(
            recipient=w["mgr"], notification_type=Notification.TYPE_APPROVAL_REQUIRED
        ).exists()

        svc.approve_award_service(event=event, approver=w["mgr"], comments="OK")
        event.refresh_from_db()
        assert event.status == SourcingEvent.STATUS_AWARDED
        assert event.award_decision.approved_by == w["mgr"]

        po = svc.generate_po_from_award_service(
            event=event, user=w["exec"], cost_center=w["cost_center"]
        )
        assert po.vendor == w["vendor_b"] and po.sourcing_event == event
        assert po.lines.count() == 1 and po.subtotal == Decimal("1800.00")
        with pytest.raises(ValidationError, match="already exists"):
            svc.generate_po_from_award_service(
                event=event, user=w["exec"], cost_center=w["cost_center"]
            )
        assert NegotiationNote.objects.filter(event=event).count() == 1

    def test_award_requires_commercial_score_and_rejection_preserves_history(
        self, procurement_world
    ):
        w = procurement_world
        event = open_event(w)
        bid = submit(w, event, "vendor_a", "user_a")
        to_commercial_review(w, event)
        with pytest.raises(ValidationError, match="no commercial evaluation"):
            svc.recommend_award_service(
                event=event, winning_bid=bid, recommended_by=w["exec"], award_reason="x"
            )
        svc.record_commercial_evaluation_service(
            event=event, bid=bid, evaluator=w["exec"], score=60
        )
        svc.recommend_award_service(
            event=event, winning_bid=bid, recommended_by=w["exec"], award_reason="x"
        )
        svc.reject_award_service(event=event, approver=w["mgr"], comments="Renegotiate price")
        assert event.status == SourcingEvent.STATUS_COMMERCIAL_REVIEW
        svc.recommend_award_service(
            event=event, winning_bid=bid, recommended_by=w["exec"], award_reason="y"
        )
        statuses = sorted(event.award_decisions.values_list("status", flat=True))
        assert statuses == ["PENDING", "REJECTED"]

    def test_suspended_vendor_cannot_be_awarded(self, procurement_world):
        w = procurement_world
        event = open_event(w)
        bid = submit(w, event, "vendor_a", "user_a")
        to_commercial_review(w, event)
        svc.record_commercial_evaluation_service(
            event=event, bid=bid, evaluator=w["exec"], score=60
        )
        svc.recommend_award_service(
            event=event, winning_bid=bid, recommended_by=w["exec"], award_reason="x"
        )
        Vendor.objects.filter(pk=w["vendor_a"].pk).update(status=Vendor.STATUS_SUSPENDED)
        bid.vendor.refresh_from_db()
        with pytest.raises(ValidationError, match="suspended"):
            svc.approve_award_service(event=event, approver=w["mgr"])
        assert event.status == SourcingEvent.STATUS_AWARD_APPROVAL

    def test_cancel_requires_reason_and_rejects_pending_award(self, procurement_world):
        event = open_event(procurement_world)
        with pytest.raises(ValidationError):
            svc.cancel_sourcing_event_service(
                event=event, user=procurement_world["exec"], reason=""
            )
        svc.cancel_sourcing_event_service(
            event=event, user=procurement_world["exec"], reason="Scope changed"
        )
        assert event.status == SourcingEvent.STATUS_CANCELLED
        with pytest.raises(ValidationError, match="Invalid sourcing transition"):
            svc.cancel_sourcing_event_service(
                event=event, user=procurement_world["exec"], reason="again"
            )


# ---------------------------------------------------------------- clarifications -----------


class TestClarifications:
    def test_vendor_asks_and_executive_answers_with_notification(self, procurement_world):
        w = procurement_world
        event = open_event(w)
        c = svc.ask_clarification_service(
            event=event, vendor=w["vendor_a"], user=w["user_a"], question="Rack units?"
        )
        svc.answer_clarification_service(clarification=c, user=w["exec"], answer="2U max")
        c.refresh_from_db()
        assert c.status == "ANSWERED" and c.answered_by == w["exec"]
        assert Notification.objects.filter(
            recipient=w["user_a"], notification_type=Notification.TYPE_CLARIFICATION_RESPONSE
        ).exists()
        assert (
            AuditLog.objects.filter(
                target_model="Clarification", target_object_id=str(c.id)
            ).count()
            == 2
        )

    def test_vendor_cannot_answer_or_read_other_vendor_clarifications(
        self, api_client, procurement_world
    ):
        w = procurement_world
        event = open_event(w)
        c = svc.ask_clarification_service(
            event=event, vendor=w["vendor_a"], user=w["user_a"], question="Q"
        )
        api_client.force_authenticate(w["user_b"])
        assert api_client.get("/api/v1/sourcing-events/clarifications/").json()["count"] == 0
        res = api_client.post(
            f"/api/v1/sourcing-events/clarifications/{c.id}/answer/", {"answer": "x"}
        )
        assert res.status_code in (403, 404)


# ---------------------------------------------------------------- RBAC / IDOR ---------------


class TestSourcingRBAC:
    @pytest.mark.parametrize("user_key", ["requester", "stores", "user_a"])
    def test_internal_pages_forbidden_for_unauthorised_roles(
        self, client, procurement_world, user_key
    ):
        event = open_event(procurement_world)
        client.force_login(procurement_world[user_key])
        assert client.get("/sourcing-events/").status_code == 403
        assert client.get(f"/sourcing-events/{event.id}/").status_code == 403
        assert (
            client.post(f"/sourcing-events/{event.id}/actions/cancel/", {"reason": "x"}).status_code
            == 403
        )

    @pytest.mark.parametrize("user_key", ["finance", "auditor"])
    def test_read_only_roles_can_view_but_not_act(self, client, procurement_world, user_key):
        event = open_event(procurement_world)
        client.force_login(procurement_world[user_key])
        assert client.get(f"/sourcing-events/{event.id}/").status_code == 200
        assert (
            client.post(f"/sourcing-events/{event.id}/actions/cancel/", {"reason": "x"}).status_code
            == 403
        )
        event.refresh_from_db()
        assert event.status == SourcingEvent.STATUS_BID_WINDOW

    def test_executive_cannot_approve_award(self, client, api_client, procurement_world):
        w = procurement_world
        event = open_event(w)
        bid = submit(w, event, "vendor_a", "user_a")
        to_commercial_review(w, event)
        svc.record_commercial_evaluation_service(
            event=event, bid=bid, evaluator=w["exec"], score=60
        )
        svc.recommend_award_service(
            event=event, winning_bid=bid, recommended_by=w["exec"], award_reason="x"
        )
        client.force_login(w["exec"])
        assert client.post(f"/sourcing-events/{event.id}/actions/approve-award/").status_code == 403
        api_client.force_authenticate(w["exec"])
        assert (
            api_client.post(f"/api/v1/sourcing-events/events/{event.id}/approve-award/").status_code
            == 403
        )
        api_client.force_authenticate(w["mgr"])
        assert (
            api_client.post(f"/api/v1/sourcing-events/events/{event.id}/approve-award/").status_code
            == 200
        )

    def test_vendor_api_cannot_create_modify_or_see_uninvited_events(
        self, api_client, procurement_world
    ):
        w = procurement_world
        invited = open_event(w, vendors=("vendor_a",))
        other = open_event(w, vendors=("vendor_b",), title="Other")
        draft = make_event(w, title="Draft only")
        svc.invite_vendors_to_event_service(
            event=draft, vendor_ids=[w["vendor_a"].id], invited_by=w["exec"]
        )

        api_client.force_authenticate(w["user_a"])
        ids = {e["id"] for e in api_client.get("/api/v1/sourcing-events/events/").json()["results"]}
        assert ids == {str(invited.id)}
        assert api_client.get(f"/api/v1/sourcing-events/events/{other.id}/").status_code == 404
        assert api_client.post("/api/v1/sourcing-events/events/", {"title": "x"}).status_code == 403
        assert (
            api_client.patch(
                f"/api/v1/sourcing-events/events/{invited.id}/", {"status": "AWARDED"}
            ).status_code
            == 403
        )
        assert (
            api_client.post(f"/api/v1/sourcing-events/events/{invited.id}/publish/").status_code
            == 403
        )

    def test_status_is_read_only_through_api_patch(self, api_client, procurement_world):
        event = make_event(procurement_world)
        api_client.force_authenticate(procurement_world["exec"])
        res = api_client.patch(
            f"/api/v1/sourcing-events/events/{event.id}/",
            {"status": "AWARDED", "title": "New"},
            format="json",
        )
        assert res.status_code == 200
        event.refresh_from_db()
        assert event.status == SourcingEvent.STATUS_DRAFT and event.title == "New"

    def test_cross_vendor_bid_isolation_via_api(self, api_client, procurement_world):
        w = procurement_world
        event = open_event(w)
        bid_b = submit(w, event, "vendor_b", "user_b")
        api_client.force_authenticate(w["user_a"])
        assert api_client.get(f"/api/v1/sourcing-events/bids/{bid_b.id}/").status_code == 404
        assert (
            api_client.post(
                f"/api/v1/sourcing-events/bids/{bid_b.id}/withdraw/", {"reason": "x"}
            ).status_code
            == 404
        )
        assert api_client.get("/api/v1/sourcing-events/bids/").json()["count"] == 0
        bids = api_client.get(f"/api/v1/sourcing-events/events/{event.id}/bids/").json()
        assert bids == []

    def test_bid_attachment_download_is_stage_gated(self, client, procurement_world):
        w = procurement_world
        event = open_event(w)
        bid = submit(w, event, "vendor_a", "user_a")
        tech = svc.upload_bid_attachment_service(
            bid=bid,
            user=w["user_a"],
            file=SimpleUploadedFile("t.pdf", b"%PDF"),
            document_type="TECHNICAL",
        )
        comm = svc.upload_bid_attachment_service(
            bid=bid,
            user=w["user_a"],
            file=SimpleUploadedFile("c.pdf", b"%PDF"),
            document_type="COMMERCIAL",
        )
        client.force_login(w["exec"])
        url = "/sourcing-events/{}/attachments/{}/download/"
        assert client.get(url.format(event.id, tech.id)).status_code == 404  # sealed
        expire(event)
        svc.sync_event_window_status(event=event)
        assert client.get(url.format(event.id, tech.id)).status_code == 200
        assert client.get(url.format(event.id, comm.id)).status_code == 404  # commercial sealed
        client.force_login(w["finance"])
        assert client.get(url.format(event.id, tech.id)).status_code == 404
        assert BidAttachment.objects.count() == 2


# ---------------------------------------------------------------- UI smoke ------------------


class TestSourcingPages:
    def test_register_detail_create_and_edit_pages_render(self, client, procurement_world):
        w = procurement_world
        draft = make_event(w)
        live = open_event(w)
        submit(w, live, "vendor_a", "user_a")
        client.force_login(w["exec"])
        for url in [
            "/sourcing-events/",
            "/sourcing-events/?status=EVALUATION&q=Compute&event_type=RFQ",
            "/sourcing-events/create/",
            f"/sourcing-events/{draft.id}/",
            f"/sourcing-events/{draft.id}/edit/",
            f"/sourcing-events/{live.id}/",
        ]:
            assert client.get(url).status_code == 200, url
        body = client.get(f"/sourcing-events/{live.id}/").content.decode()
        assert "Bids are sealed" in body and "Technical proposal from vendor_a" not in body

    def test_create_event_via_form_and_publish_via_action(self, client, procurement_world):
        w = procurement_world
        now = timezone.localtime()
        client.force_login(w["exec"])
        res = client.post(
            "/sourcing-events/create/",
            {
                "title": "Form RFP",
                "event_type": "RFP",
                "bid_start_date": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                "bid_end_date": (now + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"),
                "description": "Scope",
                "technical_requirements": "Tech",
                "commercial_requirements": "Comm",
                "technical_weight": "60",
                "commercial_weight": "40",
            },
        )
        assert res.status_code == 302
        event = SourcingEvent.objects.get(title="Form RFP")
        assert event.technical_weight == Decimal("60")
        client.post(
            f"/sourcing-events/{event.id}/actions/invite/", {"vendor_ids": [str(w["vendor_a"].id)]}
        )
        client.post(f"/sourcing-events/{event.id}/actions/publish/")
        event.refresh_from_db()
        assert event.status == SourcingEvent.STATUS_BID_WINDOW

    def test_form_rejects_inverted_dates(self, client, procurement_world):
        now = timezone.localtime()
        client.force_login(procurement_world["exec"])
        res = client.post(
            "/sourcing-events/create/",
            {
                "title": "Bad",
                "event_type": "RFQ",
                "bid_start_date": (now + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"),
                "bid_end_date": (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
                "description": "x",
                "technical_weight": "50",
                "commercial_weight": "50",
            },
        )
        assert res.status_code == 200
        assert not SourcingEvent.objects.filter(title="Bad").exists()

    def test_po_from_award_is_listed_and_dashboard_counts(self, client, procurement_world):
        w = procurement_world
        event = open_event(w)
        bid = submit(w, event, "vendor_a", "user_a")
        to_commercial_review(w, event)
        svc.record_commercial_evaluation_service(
            event=event, bid=bid, evaluator=w["exec"], score=60
        )
        svc.evaluate_and_award_sourcing_event_service(
            event=event, winning_bid=bid, award_reason="Direct", approved_by_user=w["mgr"]
        )
        client.force_login(w["exec"])
        client.post(
            f"/sourcing-events/{event.id}/actions/generate-po/",
            {"cost_center_id": str(w["cost_center"].id)},
        )
        assert PurchaseOrder.objects.filter(sourcing_event=event).count() == 1
        res = client.get("/")
        assert res.status_code == 200
        assert res.context["sourcing"]["awarded"] == 1
