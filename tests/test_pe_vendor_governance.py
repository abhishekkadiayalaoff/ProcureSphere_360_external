"""
Procurement Executive — Vendor Governance.
Pages, search/filter/pagination, metrics, risk + flags, hold/suspension RBAC and transitions,
open-transaction exposure, performance (no fabricated scores), documents, contacts, history,
API RBAC and IDOR/BOLA protection.
"""

from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.scorecards.services import calculate_vendor_scorecard_service
from apps.sourcing import services as sourcing_svc
from apps.sourcing.models import SourcingEvent
from apps.vendors.models import Vendor, VendorContact, VendorRiskRecord
from apps.vendors.selectors import get_governance_metrics
from apps.vendors.services import (
    record_vendor_risk_assessment_service,
    register_vendor_service,
    set_vendor_status_governance_service,
    upload_vendor_document_service,
)

pytestmark = [pytest.mark.django_db, pytest.mark.regression]


def upload_doc(world, vendor_key, user_key, name="kyc.pdf"):
    return upload_vendor_document_service(
        vendor=world[vendor_key],
        user=world[user_key],
        file=SimpleUploadedFile(name, b"%PDF-1.4 test", content_type="application/pdf"),
        document_type="TAX_CLEARANCE",
        title=f"{vendor_key} tax",
    )


class TestGovernancePages:
    @pytest.mark.parametrize(
        "url",
        [
            "/vendors/",
            "/vendors/governance/",
            "/vendors/onboarding/",
            "/vendors/create/",
            "/scorecards/",
        ],
    )
    def test_pages_load_for_procurement_executive(self, client, procurement_world, url):
        client.force_login(procurement_world["exec"])
        assert client.get(url).status_code == 200

    def test_detail_page_shows_all_governance_sections(self, client, procurement_world):
        w = procurement_world
        VendorContact.objects.create(
            vendor=w["vendor_a"],
            first_name="Ada",
            last_name="Lovelace",
            email="ada@alpha.test",
            is_primary=True,
        )
        upload_doc(w, "vendor_a", "user_a")
        record_vendor_risk_assessment_service(
            vendor=w["vendor_a"],
            assessor=w["exec"],
            risk_level="MEDIUM",
            risk_flags=["FINANCIAL"],
            notes="Thin margins",
        )
        client.force_login(w["exec"])
        body = client.get(f"/vendors/{w['vendor_a'].id}/").content.decode()
        for expected in [
            "Alpha Hardware Ltd",
            "Hardware",
            "Medium Risk",
            "Financial stability",
            "Thin margins",
            "No performance data available.",
            "vendor_a tax",
            "Ada Lovelace",
            "Change history",
            "Open exposure",
        ]:
            assert expected in body, expected

    @pytest.mark.parametrize("user_key", ["requester", "stores", "user_a"])
    def test_pages_forbidden_for_unauthorised_roles(self, client, procurement_world, user_key):
        w = procurement_world
        client.force_login(w[user_key])
        for url in ["/vendors/", "/vendors/governance/", f"/vendors/{w['vendor_b'].id}/"]:
            assert client.get(url).status_code == 403, url
        assert (
            client.post(
                f"/vendors/{w['vendor_b'].id}/status/", {"status": "ON_HOLD", "notes": "x"}
            ).status_code
            == 403
        )
        w["vendor_b"].refresh_from_db()
        assert w["vendor_b"].status == Vendor.STATUS_ACTIVE

    def test_finance_and_auditor_read_only(self, client, procurement_world):
        w = procurement_world
        for key in ("finance", "auditor"):
            client.force_login(w[key])
            assert client.get(f"/vendors/{w['vendor_a'].id}/").status_code == 200
            assert (
                client.post(
                    f"/vendors/{w['vendor_a'].id}/risk/", {"risk_level": "HIGH", "notes": "x"}
                ).status_code
                == 403
            )
        assert not VendorRiskRecord.objects.exists()


class TestSearchFilterPagination:
    def _ids(self, response):
        return {v.id for v in response.context["vendors"]}

    def test_search_by_number_name_tax_id_and_category(self, client, procurement_world):
        w = procurement_world
        client.force_login(w["exec"])
        assert self._ids(client.get("/vendors/?q=Alpha")) == {w["vendor_a"].id}
        assert self._ids(client.get(f"/vendors/?q={w['vendor_b'].vendor_number}")) == {
            w["vendor_b"].id
        }
        assert self._ids(client.get("/vendors/?q=TIN-C")) == {w["vendor_c"].id}
        assert self._ids(client.get("/vendors/?q=Services")) == {w["vendor_c"].id}

    def test_filters(self, client, procurement_world):
        w = procurement_world
        record_vendor_risk_assessment_service(
            vendor=w["vendor_b"], assessor=w["exec"], risk_level="HIGH", risk_flags=[], notes="x"
        )
        client.force_login(w["exec"])
        assert self._ids(client.get("/vendors/?risk_level=HIGH")) == {w["vendor_b"].id}
        assert self._ids(client.get("/vendors/?restriction=ON_HOLD")) == {w["vendor_hold"].id}
        assert self._ids(client.get("/vendors/?restriction=ANY")) == {
            w["vendor_hold"].id,
            w["vendor_susp"].id,
        }
        assert self._ids(client.get("/vendors/?operational_status=SUSPENDED")) == {
            w["vendor_susp"].id
        }
        assert self._ids(client.get("/vendors/?approval_status=KYC_REVIEW")) == {w["vendor_kyc"].id}
        assert self._ids(client.get(f"/vendors/?category={w['services'].id}")) == {w["vendor_c"].id}
        assert w["vendor_a"].id in self._ids(client.get("/vendors/?performance=NO_DATA"))
        onboarding = self._ids(client.get("/vendors/onboarding/"))
        assert w["vendor_kyc"].id in onboarding and w["vendor_a"].id not in onboarding

    def test_pagination(self, client, procurement_world):
        for i in range(25):
            register_vendor_service(
                legal_name=f"Bulk {i:02d}",
                tax_identification_number=f"TIN-BULK-{i}",
                category=procurement_world["hardware"],
                email=f"b{i}@x.test",
                address="x",
            )
        client.force_login(procurement_world["exec"])
        first = client.get("/vendors/")
        second = client.get("/vendors/?page=2")
        assert len(first.context["vendors"]) == 20
        assert first.context["page_obj"].paginator.count == 32
        assert len(second.context["vendors"]) == 12
        assert self._ids(first).isdisjoint(self._ids(second))

    def test_metrics_come_from_database(self, procurement_world):
        m = get_governance_metrics()
        assert m["total"] == 7
        assert m["active"] == 3
        assert m["on_hold"] == 1 and m["suspended"] == 1
        assert m["pending_review"] == 1  # KYC_REVIEW
        assert m["high_risk"] == 0 and m["performance_issues"] == 0
        assert m["requiring_attention"] == 1  # the on-hold vendor


class TestRiskAndStatusGovernance:
    def test_risk_assessment_with_flags_is_append_only_and_audited(self, procurement_world):
        w = procurement_world
        first = record_vendor_risk_assessment_service(
            vendor=w["vendor_a"], assessor=w["exec"], risk_level="LOW", risk_flags=[], notes="ok"
        )
        second = record_vendor_risk_assessment_service(
            vendor=w["vendor_a"],
            assessor=w["exec"],
            risk_level="HIGH",
            risk_flags=["SANCTIONS", "LEGAL"],
            notes="Watchlist hit",
        )
        assert w["vendor_a"].risk_records.count() == 2
        assert second.risk_flag_labels == ["Sanctions / watchlist", "Legal / litigation"]
        log = AuditLog.objects.get(target_model="VendorRiskRecord", target_object_id=str(second.id))
        assert log.previous_state == {"risk_level": "LOW", "risk_flags": []}
        assert first.pk != second.pk

    def test_risk_validation(self, procurement_world):
        w = procurement_world
        with pytest.raises(ValidationError, match="Unknown risk flag"):
            record_vendor_risk_assessment_service(
                vendor=w["vendor_a"],
                assessor=w["exec"],
                risk_level="LOW",
                risk_flags=["MADE_UP"],
                notes="x",
            )
        with pytest.raises(ValidationError, match="Invalid risk level"):
            record_vendor_risk_assessment_service(
                vendor=w["vendor_a"],
                assessor=w["exec"],
                risk_level="EXTREME",
                risk_flags=[],
                notes="x",
            )
        with pytest.raises(PermissionDenied):
            record_vendor_risk_assessment_service(
                vendor=w["vendor_a"],
                assessor=w["requester"],
                risk_level="LOW",
                risk_flags=[],
                notes="x",
            )

    def test_executive_can_hold_and_release_but_not_suspend(self, procurement_world):
        w = procurement_world
        set_vendor_status_governance_service(
            vendor=w["vendor_a"], actor=w["exec"], new_status="ON_HOLD", notes="Docs expired"
        )
        assert w["vendor_a"].status == Vendor.STATUS_ON_HOLD
        with pytest.raises(PermissionDenied):
            set_vendor_status_governance_service(
                vendor=w["vendor_a"], actor=w["exec"], new_status="SUSPENDED", notes="x"
            )
        set_vendor_status_governance_service(
            vendor=w["vendor_a"], actor=w["exec"], new_status="ACTIVE", notes="Renewed"
        )
        assert w["vendor_a"].status == Vendor.STATUS_ACTIVE

    def test_manager_suspends_and_reinstates_with_exposure_in_audit(self, procurement_world):
        w = procurement_world
        event = sourcing_svc.create_sourcing_event_service(
            title="Open RFQ",
            event_type="RFQ",
            bid_start_date=timezone.now() - timedelta(hours=1),
            bid_end_date=timezone.now() + timedelta(days=2),
            description="x",
            created_by_user=w["exec"],
        )
        sourcing_svc.invite_vendors_to_event_service(
            event=event, vendor_ids=[w["vendor_a"].id], invited_by=w["exec"]
        )
        sourcing_svc.publish_sourcing_event_service(event=event, user=w["exec"])

        set_vendor_status_governance_service(
            vendor=w["vendor_a"], actor=w["mgr"], new_status="SUSPENDED", notes="Fraud probe"
        )
        log = AuditLog.objects.filter(
            target_model="Vendor", target_object_id=str(w["vendor_a"].id)
        ).first()
        assert log.new_state["open_transactions_at_change"]["open_invitations"] == 1
        assert log.previous_state == {"status": "ACTIVE"}

        # Suspended vendor: no new invites / bids
        event2 = sourcing_svc.create_sourcing_event_service(
            title="Next RFQ",
            event_type="RFQ",
            bid_start_date=timezone.now(),
            bid_end_date=timezone.now() + timedelta(days=2),
            description="x",
            created_by_user=w["exec"],
        )
        with pytest.raises(ValidationError, match="not eligible"):
            sourcing_svc.invite_vendors_to_event_service(
                event=event2, vendor_ids=[w["vendor_a"].id], invited_by=w["exec"]
            )
        with pytest.raises(ValidationError, match="suspended"):
            sourcing_svc.submit_vendor_bid_service(
                event=event,
                vendor=w["vendor_a"],
                submitted_by_user=w["user_a"],
                line_items=[{"item_description": "x", "quantity": 1, "quoted_unit_price": 1}],
                technical_proposal="t",
            )
        set_vendor_status_governance_service(
            vendor=w["vendor_a"], actor=w["mgr"], new_status="ACTIVE", notes="Cleared"
        )
        assert w["vendor_a"].status == Vendor.STATUS_ACTIVE

    @pytest.mark.parametrize(
        "vendor_key,target",
        [
            ("vendor_draft", "ACTIVE"),
            ("vendor_a", "REJECTED"),
            ("vendor_kyc", "ON_HOLD"),
            ("vendor_a", "DRAFT"),
        ],
    )
    def test_invalid_transitions_rejected(self, procurement_world, vendor_key, target):
        with pytest.raises(ValidationError, match="Invalid vendor status transition"):
            set_vendor_status_governance_service(
                vendor=procurement_world[vendor_key],
                actor=procurement_world["mgr"],
                new_status=target,
                notes="x",
            )

    def test_reason_required(self, procurement_world):
        with pytest.raises(ValidationError, match="reason"):
            set_vendor_status_governance_service(
                vendor=procurement_world["vendor_a"],
                actor=procurement_world["exec"],
                new_status="ON_HOLD",
                notes=" ",
            )

    def test_status_change_via_ui_view_and_role_gate(self, client, procurement_world):
        w = procurement_world
        client.force_login(w["exec"])
        res = client.post(
            f"/vendors/{w['vendor_b'].id}/status/", {"status": "SUSPENDED", "notes": "x"}
        )
        assert res.status_code == 403
        res = client.post(
            f"/vendors/{w['vendor_b'].id}/status/", {"status": "ON_HOLD", "notes": "Late KYC"}
        )
        assert res.status_code == 302
        w["vendor_b"].refresh_from_db()
        assert w["vendor_b"].status == Vendor.STATUS_ON_HOLD

    def test_kyc_review_and_approval_from_governance(self, client, procurement_world):
        w = procurement_world
        vendor = w["vendor_kyc"]
        doc = upload_doc(w, "vendor_kyc", "exec")
        client.force_login(w["exec"])
        client.post(f"/vendors/{vendor.id}/kyc/verify-document/", {"document_id": str(doc.id)})
        doc.refresh_from_db()
        assert doc.is_verified and doc.verified_by == w["exec"]
        client.post(f"/vendors/{vendor.id}/kyc/approve/", {"notes": "KYC complete"})
        vendor.refresh_from_db()
        assert vendor.status == Vendor.STATUS_ACTIVE
        assert AuditLog.objects.filter(target_model="VendorDocument", action="VERIFY").exists()


class TestPerformance:
    def test_no_data_is_null_not_fabricated(self, procurement_world):
        card = calculate_vendor_scorecard_service(
            vendor=procurement_world["vendor_a"],
            evaluation_period="Q4-2026",
            evaluated_by_user=procurement_world["exec"],
        )
        assert card.delivery_score is None and card.quality_score is None
        assert (
            card.price_score is None
            and card.sla_score is None
            and card.responsiveness_score is None
        )
        assert card.compliance_score == 100  # ACTIVE governance status
        assert card.composite_score == 100  # only indicator with data

    def test_responsiveness_from_invitation_response(self, procurement_world):
        w = procurement_world
        event = sourcing_svc.create_sourcing_event_service(
            title="R",
            event_type="RFQ",
            bid_start_date=timezone.now() - timedelta(hours=1),
            bid_end_date=timezone.now() + timedelta(days=1),
            description="x",
            created_by_user=w["exec"],
        )
        sourcing_svc.invite_vendors_to_event_service(
            event=event, vendor_ids=[w["vendor_a"].id, w["vendor_b"].id], invited_by=w["exec"]
        )
        sourcing_svc.publish_sourcing_event_service(event=event, user=w["exec"])
        sourcing_svc.submit_vendor_bid_service(
            event=event,
            vendor=w["vendor_a"],
            submitted_by_user=w["user_a"],
            technical_proposal="t",
            line_items=[{"item_description": "x", "quantity": 1, "quoted_unit_price": 10}],
        )
        SourcingEvent.objects.filter(pk=event.pk).update(
            status=SourcingEvent.STATUS_TECHNICAL_REVIEW
        )
        a = calculate_vendor_scorecard_service(
            vendor=w["vendor_a"], evaluation_period="P", evaluated_by_user=w["exec"]
        )
        b = calculate_vendor_scorecard_service(
            vendor=w["vendor_b"], evaluation_period="P", evaluated_by_user=w["exec"]
        )
        assert a.responsiveness_score == 100 and b.responsiveness_score == 0

    def test_scorecards_page_and_calculation_rbac(self, client, procurement_world):
        w = procurement_world
        client.force_login(w["exec"])
        res = client.post(
            "/scorecards/calculate/", {"vendor_id": str(w["vendor_a"].id), "period": "Q4"}
        )
        assert res.status_code == 302
        body = client.get("/scorecards/").content.decode()
        assert "Alpha Hardware Ltd" in body and "No data" in body
        client.force_login(w["requester"])
        assert client.get("/scorecards/").status_code == 403
        assert (
            client.post(
                "/scorecards/calculate/", {"vendor_id": str(w["vendor_a"].id), "period": "Q4"}
            ).status_code
            == 403
        )
        client.force_login(w["stores"])
        assert client.get("/scorecards/").status_code == 200
        assert (
            client.post(
                "/scorecards/calculate/", {"vendor_id": str(w["vendor_a"].id), "period": "Q4"}
            ).status_code
            == 403
        )


class TestDocumentsAndApiSecurity:
    def test_internal_document_download_and_role_gate(self, client, procurement_world):
        w = procurement_world
        doc = upload_doc(w, "vendor_a", "user_a")
        url = f"/vendors/{w['vendor_a'].id}/documents/{doc.id}/download/"
        client.force_login(w["exec"])
        assert client.get(url).status_code == 200
        client.force_login(w["requester"])
        assert client.get(url).status_code == 403
        # wrong vendor in the path cannot be used to reach the document
        client.force_login(w["exec"])
        assert (
            client.get(f"/vendors/{w['vendor_b'].id}/documents/{doc.id}/download/").status_code
            == 404
        )

    def test_upload_rejects_disallowed_extension(self, procurement_world):
        with pytest.raises(ValidationError, match="not permitted"):
            upload_vendor_document_service(
                vendor=procurement_world["vendor_a"],
                user=procurement_world["user_a"],
                file=SimpleUploadedFile("evil.html", b"<script>"),
                document_type="OTHER",
            )

    def test_vendor_api_scoping_and_idor(self, api_client, procurement_world):
        w = procurement_world
        doc_b = upload_doc(w, "vendor_b", "user_b")
        api_client.force_authenticate(w["user_a"])
        results = api_client.get("/api/v1/vendors/").json()["results"]
        assert [r["id"] for r in results] == [str(w["vendor_a"].id)]
        assert api_client.get(f"/api/v1/vendors/{w['vendor_b'].id}/").status_code == 404
        assert (
            api_client.get(
                f"/api/v1/vendors/{w['vendor_b'].id}/documents/{doc_b.id}/download/"
            ).status_code
            == 404
        )
        assert api_client.get(f"/api/v1/vendors/{w['vendor_a'].id}/risk/").status_code == 403
        assert api_client.get(f"/api/v1/vendors/{w['vendor_a'].id}/history/").status_code == 403
        # vendor cannot change its own status
        res = api_client.post(
            f"/api/v1/vendors/{w['vendor_a'].id}/set-status/", {"status": "ACTIVE", "notes": "x"}
        )
        assert res.status_code == 403
        # no raw PATCH of master data / status
        assert api_client.patch(
            f"/api/v1/vendors/{w['vendor_a'].id}/", {"status": "ACTIVE"}
        ).status_code in (403, 405)
        # documents never expose storage paths
        docs = api_client.get(f"/api/v1/vendors/{w['vendor_a'].id}/documents/").json()
        assert all("file" not in d for d in docs)

    def test_requester_api_denied(self, api_client, procurement_world):
        api_client.force_authenticate(procurement_world["requester"])
        assert api_client.get("/api/v1/vendors/").status_code == 403
        assert api_client.get("/api/v1/sourcing-events/events/").status_code == 403
        assert api_client.get("/api/v1/scorecards/").json()["count"] == 0

    def test_governance_api_actions_and_structured_errors(self, api_client, procurement_world):
        w = procurement_world
        api_client.force_authenticate(w["exec"])
        res = api_client.get("/api/v1/vendors/?risk_level=NONE&restriction=NONE&q=Alpha")
        assert [r["vendor_number"] for r in res.json()["results"]] == [w["vendor_a"].vendor_number]
        res = api_client.post(
            f"/api/v1/vendors/{w['vendor_a'].id}/risk/",
            {"risk_level": "HIGH", "risk_flags": ["QUALITY"], "notes": "Rejects"},
            format="json",
        )
        assert res.status_code == 201
        res = api_client.post(
            f"/api/v1/vendors/{w['vendor_a'].id}/set-status/", {"status": "SUSPENDED", "notes": "x"}
        )
        assert res.status_code == 403
        res = api_client.post(
            f"/api/v1/vendors/{w['vendor_draft'].id}/set-status/",
            {"status": "ON_HOLD", "notes": "x"},
        )
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "INVALID"
        allowed = api_client.get(f"/api/v1/vendors/{w['vendor_a'].id}/allowed-transitions/").json()[
            "allowed"
        ]
        assert allowed == ["ON_HOLD"]
        history = api_client.get(f"/api/v1/vendors/{w['vendor_a'].id}/history/").json()
        assert any(h["object"] == "VendorRiskRecord" for h in history)
