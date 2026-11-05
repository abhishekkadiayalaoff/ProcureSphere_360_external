"""
Multi-organization data isolation for role dashboards plus the single-use GRN
"Send to Finance & Vendor" dispatch action.

Scenario A (org isolation): a brand-new organization with its own role users
must never see data that was created under a previously created organization —
verified at the rendered-dashboard level for Finance/AP, Legal/Contract
Manager, Stores Receiver, Procurement Executive and Compliance Auditor.

Scenario B (GRN dispatch): the Stores Receiver "Send GRN to Finance & Vendor"
action is a one-time operation — the first dispatch notifies Finance/AP, the
Vendor portal users and Procurement (all scoped to the GRN's organization),
persists the dispatch state server-side, and every later attempt is rejected
(recorded, never duplicated) while the UI button renders disabled.
"""

import re
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.contracts.models import Contract
from apps.notifications.models import Notification
from apps.orders.models import POLine, PurchaseOrder
from apps.organization.models import CostCenter, Department, Organization
from apps.receipts.models import GoodsReceipt
from apps.receipts.services import (
    create_goods_receipt_service,
    record_inspection_service,
)
from apps.sourcing.models import SourcingEvent
from apps.vendors.models import Vendor, VendorCategory


def _date(days_from_now):
    return date.today() + timedelta(days=days_from_now)


@pytest.fixture
def two_org_world(db, db_roles):
    """
    Two organizations sharing one platform instance:
      - OLDCO: a previously created organization holding real transactional data.
      - NEWCO: a fresh organization whose users must see none of OLDCO's data.
    """
    old_org = Organization.objects.create(
        name="OldCo Industries", code="OLDCO", is_active=True
    )
    new_org = Organization.objects.create(
        name="NewCo Enterprises", code="NEWCO", is_active=True
    )

    def build_org(org, prefix):
        dept = Department.objects.create(
            organization=org,
            name=f"{prefix} Procurement Department",
            code=f"{prefix}-PROC",
        )
        cc = CostCenter.objects.create(
            department=dept,
            code=f"{prefix}-CC-01",
            name=f"{prefix} Main Cost Center",
        )
        cat = VendorCategory.objects.create(
            name=f"{prefix} Hardware", code=f"CAT-{prefix}"
        )
        vendor = Vendor.objects.create(
            vendor_number=f"VND-{prefix}-001",
            legal_name=f"{prefix} Vendors Ltd",
            tax_identification_number=f"TIN-{prefix}-001",
            category=cat,
            organization=org,
            status=Vendor.STATUS_ACTIVE,
            is_event_eligible=True,
            event_eligibility_status=Vendor.ELIGIBILITY_ELIGIBLE,
            email=f"{prefix.lower()}.vendor@test.local",
            address="1 Test Street",
        )
        return {"org": org, "prefix": prefix, "dept": dept, "cc": cc, "vendor": vendor}

    old = build_org(old_org, "OLD")
    new = build_org(new_org, "NEW")

    def user(email, role_code, scope):
        return User.objects.create_user(
            email=email,
            password="Password123!",
            role=db_roles[role_code],
            organization=scope["org"],
            department=scope["dept"],
        )

    roles_created = {
        "old_stores": user("old.stores@test.local", Role.STORES_RECEIVER, old),
        "old_exec": user("old.exec@test.local", Role.PROC_EXEC, old),
        "old_legal": user("old.legal@test.local", Role.LEGAL_MGR, old),
        "new_stores": user("new.stores@test.local", Role.STORES_RECEIVER, new),
        "new_exec": user("new.exec@test.local", Role.PROC_EXEC, new),
        "new_legal": user("new.legal@test.local", Role.LEGAL_MGR, new),
        "new_finance": user("new.finance@test.local", Role.FINANCE_AP, new),
        "new_auditor": user("new.auditor@test.local", Role.AUDITOR, new),
        "other_stores": user(
            "other.stores@test.local", Role.STORES_RECEIVER, new
        ),
    }

    old["vendor_user"] = User.objects.create_user(
        email="rep@oldvendor.test",
        password="Password123!",
        role=db_roles[Role.VENDOR_USER],
        vendor=old["vendor"],
    )

    def build_grn(scope, suffix, stores_user):
        po = PurchaseOrder.objects.create(
            po_number=f"PO-{scope['prefix']}-{suffix}",
            version=1,
            vendor=scope["vendor"],
            cost_center=scope["cc"],
            status=PurchaseOrder.STATUS_ISSUED,
            subtotal=Decimal("10000.00"),
            tax_amount=Decimal("1000.00"),
            total_amount=Decimal("11000.00"),
        )
        po_line = POLine.objects.create(
            po=po,
            item_description=f"{scope['prefix']} Server Node {suffix}",
            quantity=Decimal("10.00"),
            quantity_received=Decimal("0.00"),
            unit_of_measure="EA",
            unit_price=Decimal("1000.00"),
        )
        grn = create_goods_receipt_service(
            po=po,
            received_by=stores_user,
            receipt_items=[
                {
                    "po_line_id": str(po_line.id),
                    "quantity_received": Decimal("10.00"),
                    "quantity_accepted": Decimal("10.00"),
                }
            ],
            delivery_note_number=f"DN-{scope['prefix']}-{suffix}",
        )
        record_inspection_service(
            receipt=grn,
            inspected_by=stores_user,
            inspection_items=[
                {
                    "receipt_line_id": str(grn.lines.first().id),
                    "passed": True,
                    "inspection_notes": "All units verified OK.",
                }
            ],
        )
        grn.refresh_from_db()
        return {"po": po, "po_line": po_line, "grn": grn}

    # Transactional data under the OLD organization
    old["flow"] = build_grn(old, "001", roles_created["old_stores"])
    old["contract"] = Contract.objects.create(
        contract_number="CON-OLDCO-001",
        title="OLDCO OldCo Master Services Agreement",
        vendor=old["vendor"],
        po=old["flow"]["po"],
        contract_owner=roles_created["old_legal"],
        status=Contract.STATUS_LEGAL_REVIEW,
        contract_value=Decimal("50000.00"),
        start_date=_date(-10),
        end_date=_date(300),
    )
    old["event"] = SourcingEvent.objects.create(
        event_number="RFQ-OLDCO-001",
        title="OLDCO Legacy RFQ for Routers",
        event_type=SourcingEvent.TYPE_RFQ,
        status=SourcingEvent.STATUS_BID_WINDOW,
        bid_start_date=date.today() - timedelta(days=2),
        bid_end_date=date.today() + timedelta(days=2),
        description="OldCo RFQ body",
        is_sealed=True,
    )

    # Transactional data under the NEW organization
    new["flow"] = build_grn(new, "001", roles_created["new_stores"])
    new["contract"] = Contract.objects.create(
        contract_number="CON-NEWCO-001",
        title="NEWCO Fresh Services Agreement",
        vendor=new["vendor"],
        po=new["flow"]["po"],
        contract_owner=roles_created["new_legal"],
        status=Contract.STATUS_LEGAL_REVIEW,
        contract_value=Decimal("12000.00"),
        start_date=_date(-5),
        end_date=_date(200),
    )

    return {**roles_created, "old": old, "new": new}


# ---------------------------------------------------------------------------
# Scenario A — new-organization dashboards never expose old-organization data
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_new_org_stores_dashboard_hides_old_org_grns(client, two_org_world):
    w = two_org_world
    client.force_login(w["new_stores"])
    resp = client.get(reverse("home"))
    content = resp.content.decode()

    assert resp.status_code == 200
    assert w["old"]["flow"]["grn"].grn_number not in content
    assert w["old"]["flow"]["po"].po_number not in content
    assert w["old"]["vendor"].legal_name not in content
    # Own organization data is visible
    assert w["new"]["flow"]["grn"].grn_number in content


@pytest.mark.django_db
def test_new_org_stores_cannot_open_or_dispatch_old_org_grn(client, two_org_world):
    w = two_org_world
    old_grn = w["old"]["flow"]["grn"]
    client.force_login(w["new_stores"])

    assert client.get(reverse("receipt_detail", args=[old_grn.id])).status_code == 404
    assert (
        client.post(reverse("receipt_send_notifications", args=[old_grn.id])).status_code
        == 404
    )
    old_grn.refresh_from_db()
    assert old_grn.finance_dispatched_at is None


@pytest.mark.django_db
def test_new_org_legal_dashboard_hides_old_org_contracts(client, two_org_world):
    w = two_org_world
    client.force_login(w["new_legal"])
    resp = client.get(reverse("home"))
    content = resp.content.decode()

    assert resp.status_code == 200
    assert "OLDCO OldCo Master Services Agreement" not in content
    assert w["old"]["vendor"].legal_name not in content
    assert "CON-OLDCO-001" not in content
    # Own organization data is visible
    assert "NEWCO Fresh Services Agreement" in content


@pytest.mark.django_db
def test_new_org_finance_dashboard_hides_old_org_master_data(client, two_org_world):
    w = two_org_world
    client.force_login(w["new_finance"])
    resp = client.get(reverse("home"))
    content = resp.content.decode()

    assert resp.status_code == 200
    assert "OLD-PROC" not in content
    assert "OLD-CC-01" not in content
    assert "OLD Procurement Department" not in content
    assert w["old"]["vendor"].legal_name not in content
    # Own organization master data is visible
    assert "NEW-CC-01" in content


@pytest.mark.django_db
def test_new_org_procurement_dashboard_hides_old_org_sourcing(client, two_org_world):
    w = two_org_world
    client.force_login(w["new_exec"])
    resp = client.get(reverse("home"))
    content = resp.content.decode()

    assert resp.status_code == 200
    assert "OLDCO Legacy RFQ for Routers" not in content
    assert "RFQ-OLDCO-001" not in content
    assert w["old"]["vendor"].legal_name not in content


@pytest.mark.django_db
def test_new_org_auditor_views_hides_old_org_activity(client, two_org_world):
    w = two_org_world
    client.force_login(w["new_auditor"])

    resp = client.get(reverse("auditor_dashboard_hub"))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "old.stores@test.local" not in content
    assert "old.exec@test.local" not in content
    assert w["old"]["vendor"].legal_name not in content

    resp_logs = client.get(reverse("audit_log"))
    assert resp_logs.status_code == 200
    assert "old.stores@test.local" not in resp_logs.content.decode()


# ---------------------------------------------------------------------------
# Scenario B — "Send GRN to Finance & Vendor" is a single-use action
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_grn_dispatch_happens_exactly_once(client, two_org_world):
    w = two_org_world
    grn = w["new"]["flow"]["grn"]
    send_url = reverse("receipt_send_notifications", args=[grn.id])

    client.force_login(w["new_stores"])

    # Detail page offers the active send button before dispatch
    pre_content = client.get(reverse("receipt_detail", args=[grn.id])).content.decode()
    assert "Send GRN to Finance &amp; Vendor" in pre_content
    assert send_url in pre_content

    baseline_notifications = Notification.objects.count()

    # --- First dispatch: notifications are created and the GRN is locked ---
    resp = client.post(send_url)
    assert resp.status_code == 302

    grn.refresh_from_db()
    assert grn.finance_dispatched_at is not None
    assert grn.dispatched_by == w["new_stores"]

    notifications_after_first = Notification.objects.count()
    assert notifications_after_first > baseline_notifications

    # Recipients are scoped to the GRN's organization + the vendor's users
    dispatch_notification_qs = Notification.objects.filter(
        title__contains=str(grn.grn_number)
    )
    recipient_ids = set(
        dispatch_notification_qs.values_list("recipient_id", flat=True)
    )
    assert w["new_finance"].id in recipient_ids or w["new_legal"].id in recipient_ids
    assert w["old"]["vendor_user"].id not in recipient_ids

    # Dispatch is audited in the append-only audit log
    assert AuditLog.objects.filter(
        target_model="GoodsReceipt",
        target_object_id=str(grn.id),
        new_state__action="GRN_DISPATCHED_TO_FINANCE_VENDOR",
    ).exists()

    # --- Second dispatch attempt: rejected, nothing is duplicated ---
    resp_second = client.post(send_url)
    assert resp_second.status_code == 302  # graceful redirect back to detail

    grn.refresh_from_db()
    assert Notification.objects.count() == notifications_after_first

    # Dispatch timestamp preserved (never overwritten)
    assert grn.finance_dispatched_at is not None

    # --- UI after dispatch: button rendered disabled, no active send form ---
    post_content = client.get(reverse("receipt_detail", args=[grn.id])).content.decode()
    assert "Sent to Finance &amp; Vendor" in post_content
    assert send_url not in post_content
    assert re.search(
        r"<button[^>]*\bdisabled[^>]*>\s*<i[^>]*fa-circle-check", post_content
    ), "send button must render disabled after dispatch"


@pytest.mark.django_db
def test_grn_dispatch_service_rejects_second_call_directly(two_org_world):
    from django.core.exceptions import ValidationError

    from apps.receipts.services import (
        dispatch_grn_to_stakeholders_service,  # noqa: PLC0415
    )

    w = two_org_world
    grn = w["new"]["flow"]["grn"]

    dispatch_grn_to_stakeholders_service(grn=grn, dispatched_by=w["new_stores"])
    grn.refresh_from_db()
    first_ts = grn.finance_dispatched_at
    assert first_ts is not None

    with pytest.raises(ValidationError) as exc:
        dispatch_grn_to_stakeholders_service(grn=grn, dispatched_by=w["new_stores"])
    assert "only once" in str(exc.value)

    grn.refresh_from_db()
    assert grn.finance_dispatched_at == first_ts


@pytest.mark.django_db
def test_grn_dispatch_is_notified_once_per_recipient_with_notification_type(
    two_org_world,
):
    from apps.receipts.services import (
        dispatch_grn_to_stakeholders_service,  # noqa: PLC0415
    )

    w = two_org_world
    grn = w["new"]["flow"]["grn"]

    dispatch_grn_to_stakeholders_service(grn=grn, dispatched_by=w["new_stores"])

    assert (
        Notification.objects.filter(
            notification_type=Notification.TYPE_GOODS_RECEIVED
        ).count()
        == Notification.objects.count()
    )

    # Exactly one GRN-dispatch notification per recipient (deduplicated per user)
    finance_notifications = Notification.objects.filter(
        recipient=w["new_finance"],
        title__startswith="GRN Receipt Note Dispatched",
        title__contains=str(grn.grn_number),
    )
    assert finance_notifications.count() == 1
    assert "3-way match" in finance_notifications.first().message.lower()
