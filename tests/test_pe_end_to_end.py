"""
End-to-end Procurement Executive business scenario through the real HTTP views:

Vendor Governance -> eligibility -> RFQ/RFP -> invitation -> publish -> vendor bid (portal)
-> deadline -> technical review -> commercial review -> negotiation -> award recommendation
-> manager approval -> Purchase Order -> supplier performance -> governance history / audit.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.orders.models import PurchaseOrder
from apps.sourcing.models import AwardDecision, SourcingEvent, VendorBid
from apps.vendors.services import record_vendor_risk_assessment_service

pytestmark = [pytest.mark.django_db, pytest.mark.integration, pytest.mark.regression]


def _ok(response, url=""):
    assert response.status_code in (200, 302), (url, response.status_code)
    return response


def test_procurement_executive_end_to_end(client, procurement_world):
    w = procurement_world
    now = timezone.localtime()

    # 1-4. Procurement Executive reviews an approved active vendor in Vendor Governance
    record_vendor_risk_assessment_service(
        vendor=w["vendor_a"], assessor=w["exec"], risk_level="LOW", risk_flags=[], notes="Baseline"
    )
    client.force_login(w["exec"])
    gov = _ok(client.get("/vendors/governance/?operational_status=ACTIVE&q=Alpha"))
    assert [v.id for v in gov.context["vendors"]] == [w["vendor_a"].id]
    detail = client.get(f"/vendors/{w['vendor_a'].id}/").content.decode()
    assert "Low Risk" in detail and "No performance data available." in detail

    # 5-6. New RFP with technical and commercial sections and bid window
    res = client.post(
        "/sourcing-events/create/",
        {
            "title": "E2E Storage RFP",
            "event_type": "RFP",
            "bid_start_date": (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M"),
            "bid_end_date": (now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
            "description": "All-flash storage for DC-2",
            "technical_requirements": "NVMe, 200TB usable, dual controllers",
            "commercial_requirements": "Fixed price, 5y support",
            "technical_weight": "60",
            "commercial_weight": "40",
        },
    )
    assert res.status_code == 302
    event = SourcingEvent.objects.get(title="E2E Storage RFP")
    assert event.status == SourcingEvent.STATUS_DRAFT

    # 7-9. Select eligible vendors (ineligible vendor rejected), invite, publish
    res = client.post(
        f"/sourcing-events/{event.id}/actions/invite/",
        {"vendor_ids": [str(w["vendor_hold"].id)]},
        follow=True,
    )
    assert "not eligible" in res.content.decode()
    _ok(
        client.post(
            f"/sourcing-events/{event.id}/actions/invite/",
            {"vendor_ids": [str(w["vendor_a"].id), str(w["vendor_b"].id)]},
        )
    )
    _ok(client.post(f"/sourcing-events/{event.id}/actions/publish/"))
    event.refresh_from_db()
    assert event.status == SourcingEvent.STATUS_BID_WINDOW

    # 10-16. Vendors respond through the vendor portal (technical + commercial + attachment)
    for user_key, price in (("user_a", "50000.00"), ("user_b", "45000.00")):
        client.force_login(w[user_key])
        _ok(client.get(f"/vendor/sourcing/{event.id}/"))
        res = client.post(
            f"/vendor/bids/create/{event.id}/",
            {
                "action": "submit_bid",
                "proposal_summary": "Storage proposal",
                "technical_proposal": f"Technical design by {user_key}",
                "commercial_proposal": f"Commercial terms by {user_key}",
                "line_description[]": ["Storage array"],
                "line_quantity[]": ["1"],
                "line_price[]": [price],
                "attachment_type": "TECHNICAL",
                "attachment_title": "Datasheet",
                "attachment_file": SimpleUploadedFile(
                    "datasheet.pdf", b"%PDF-1.4", content_type="application/pdf"
                ),
            },
        )
        assert res.status_code == 302
    bid_a = VendorBid.objects.get(event=event, vendor=w["vendor_a"])
    bid_b = VendorBid.objects.get(event=event, vendor=w["vendor_b"])
    assert bid_a.status == bid_b.status == VendorBid.STATUS_SUBMITTED
    assert bid_a.attachments.count() == 1

    # Vendor A cannot see vendor B's bid
    client.force_login(w["user_a"])
    assert client.get(f"/vendor/bids/{bid_b.id}/").status_code in (403, 404)

    # Sealed: the executive sees no bid content during the window
    client.force_login(w["exec"])
    assert (
        "Technical design by user_a"
        not in client.get(f"/sourcing-events/{event.id}/").content.decode()
    )

    # 17-18. Deadline passes (server clock); vendor cannot submit/amend afterwards
    SourcingEvent.objects.filter(pk=event.pk).update(
        bid_end_date=timezone.now() - timedelta(minutes=1)
    )
    client.force_login(w["user_a"])
    client.post(
        f"/vendor/bids/{bid_a.id}/amend/",
        {
            "amendment_reason": "late",
            "line_description[]": ["x"],
            "line_quantity[]": ["1"],
            "line_price[]": ["1"],
        },
    )
    bid_a.refresh_from_db()
    assert bid_a.version == 1 and bid_a.total_bid_amount == Decimal("50000.00")

    # 19-20. Executive opens the event: window auto-closed, technical envelope only
    client.force_login(w["exec"])
    page = client.get(f"/sourcing-events/{event.id}/")
    event.refresh_from_db()
    assert event.status == SourcingEvent.STATUS_TECHNICAL_REVIEW
    body = page.content.decode()
    assert "Technical design by user_a" in body and "Commercial terms by user_a" not in body
    for bid, score in ((bid_a, "90"), (bid_b, "70")):
        _ok(
            client.post(
                f"/sourcing-events/{event.id}/actions/technical-score/",
                {"bid_id": bid.id, "score": score},
            )
        )
    _ok(client.post(f"/sourcing-events/{event.id}/actions/start-commercial/"))
    event.refresh_from_db()
    assert event.status == SourcingEvent.STATUS_COMMERCIAL_REVIEW

    # 21-23. Commercial review, evaluation, negotiation notes
    body = client.get(f"/sourcing-events/{event.id}/").content.decode()
    assert "Commercial terms by user_a" in body
    for bid, score in ((bid_a, "80"), (bid_b, "95")):
        _ok(
            client.post(
                f"/sourcing-events/{event.id}/actions/commercial-score/",
                {"bid_id": bid.id, "score": score},
            )
        )
    _ok(
        client.post(
            f"/sourcing-events/{event.id}/actions/negotiation-note/",
            {"bid_id": bid_a.id, "note": "Requested 3% discount for multi-year commitment"},
        )
    )

    # 24. Award: executive recommends (weighted: A=86, B=80); manager approves
    _ok(
        client.post(
            f"/sourcing-events/{event.id}/actions/recommend-award/",
            {"bid_id": bid_a.id, "award_reason": "Highest weighted score"},
        )
    )
    assert client.post(f"/sourcing-events/{event.id}/actions/approve-award/").status_code == 403
    client.force_login(w["mgr"])
    _ok(
        client.post(f"/sourcing-events/{event.id}/actions/approve-award/", {"comments": "Approved"})
    )
    event.refresh_from_db()
    assert event.status == SourcingEvent.STATUS_AWARDED
    decision = event.award_decision
    assert decision.status == AwardDecision.STATUS_APPROVED and decision.winning_bid == bid_a

    # 25. Purchase Order generated from the award
    client.force_login(w["exec"])
    _ok(
        client.post(
            f"/sourcing-events/{event.id}/actions/generate-po/",
            {"cost_center_id": str(w["cost_center"].id)},
        )
    )
    po = PurchaseOrder.objects.get(sourcing_event=event)
    assert po.vendor == w["vendor_a"] and po.subtotal == Decimal("50000.00")
    _ok(client.get(f"/purchase-orders/{po.id}/"))

    # 26. Supplier performance observed (responsiveness from the RFP response)
    _ok(
        client.post(
            "/scorecards/calculate/", {"vendor_id": str(w["vendor_a"].id), "period": "Q4-2026"}
        )
    )
    card = w["vendor_a"].scorecards.get()
    assert card.responsiveness_score is not None and card.delivery_score is None

    # 27-29. Governance shows sourcing/PO relationship, performance and audit history
    detail = client.get(f"/vendors/{w['vendor_a'].id}/").content.decode()
    assert event.event_number in detail and po.po_number in detail and "Q4-2026" in detail
    trail = set(
        AuditLog.objects.filter(target_object_id=str(event.id)).values_list(
            "new_state__status", flat=True
        )
    )
    assert {
        "DRAFT",
        "PUBLISHED",
        "BID_WINDOW",
        "TECHNICAL_REVIEW",
        "COMMERCIAL_REVIEW",
        "AWARD_APPROVAL",
        "AWARDED",
    } <= trail
    assert AuditLog.objects.filter(
        target_model="PurchaseOrder", target_object_id=str(po.id)
    ).exists()
