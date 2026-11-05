"""
Purchase Order lifecycle (DRAFT -> APPROVAL -> APPROVED -> ISSUED -> ACKNOWLEDGED),
vendor rejection, request-changes/reject loops, separation of duties, budget commitment,
org-scoped visibility (404), REST lifecycle actions, and minimal stock inventory posting
on GRN handoff.
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.budgets.models import Budget, SpendLedger
from apps.notifications.models import Notification
from apps.orders.models import PurchaseOrder
from apps.orders.services import (
    acknowledge_purchase_order_service,
    approve_purchase_order_service,
    generate_purchase_order_service,
    issue_purchase_order_service,
    reject_purchase_order_service,
    request_changes_purchase_order_service,
    submit_purchase_order_for_approval_service,
    vendor_reject_purchase_order_service,
)
from apps.organization.models import CostCenter, Department, FiscalPeriod, Organization
from apps.receipts.models import StockItem, StockMovement
from apps.receipts.services import (
    create_goods_receipt_service,
    handoff_goods_to_stock_service,
)
from apps.vendors.models import Vendor, VendorCategory

pytestmark = [pytest.mark.django_db, pytest.mark.regression]


@pytest.fixture
def po_world(db):
    org = Organization.objects.create(name="Lifecycle Org", code="LC-ORG")
    dept = Department.objects.create(organization=org, name="IT", code="LC-IT")
    cc = CostCenter.objects.create(department=dept, code="LC-CC", name="Infrastructure")

    today = timezone.now().date()
    period = FiscalPeriod.objects.create(
        organization=org,
        name="FY2026",
        year=2026,
        period_number=1,
        start_date=today.replace(month=1, day=1),
        end_date=today.replace(month=12, day=31),
        is_closed=False,
    )
    budget = Budget.objects.create(
        cost_center=cc,
        fiscal_period=period,
        allocated_amount=Decimal("100000.00"),
        committed_amount=Decimal("0.00"),
        actual_amount=Decimal("0.00"),
    )

    category = VendorCategory.objects.create(name="Hardware", code="LC-HW")
    vendor = Vendor.objects.create(
        organization=org,
        category=category,
        legal_name="Lifecycle Vendor Ltd",
        vendor_number="VND-LC-01",
        tax_identification_number="TIN-LC-01",
        status=Vendor.STATUS_ACTIVE,
    )

    roles = {}
    for code, name in [
        (Role.PROC_EXEC, "Procurement Executive"),
        (Role.PROC_MGR, "Procurement Manager"),
        (Role.VENDOR_USER, "Vendor Representative"),
        (Role.STORES_RECEIVER, "Stores Receiver"),
    ]:
        roles[code], _ = Role.objects.get_or_create(code=code, defaults={"name": name})

    def user(email, role_code, **extra):
        return User.objects.create_user(
            email=email, role=roles[role_code], **extra
        )

    world = {
        "org": org,
        "cc": cc,
        "budget": budget,
        "vendor": vendor,
        "exec": user("lc.exec@test.local", Role.PROC_EXEC, organization=org),
        "mgr": user("lc.mgr@test.local", Role.PROC_MGR, organization=org),
        "stores": user("lc.stores@test.local", Role.STORES_RECEIVER, organization=org),
        "vendor_user": user(
            "lc.vendor@test.local", Role.VENDOR_USER, vendor=vendor
        ),
    }
    return world


def make_draft_po(world, *, qty="10", price="1000.00"):
    return generate_purchase_order_service(
        vendor=world["vendor"],
        cost_center=world["cc"],
        line_items=[
            {
                "item_description": "Rack Server",
                "quantity": Decimal(qty),
                "unit_price": Decimal(price),
            }
        ],
        created_by_user=world["exec"],
    )


def issued_po(world):
    po = make_draft_po(world)
    po = submit_purchase_order_for_approval_service(po=po, actor=world["exec"])
    po = approve_purchase_order_service(po=po, approver=world["mgr"], comments="OK")
    return issue_purchase_order_service(po=po, actor=world["exec"])


def test_generated_po_starts_as_draft(po_world):
    po = make_draft_po(po_world)
    assert po.status == PurchaseOrder.STATUS_DRAFT
    assert po.submitted_by_id is None and po.approved_by_id is None


def test_submit_sets_submitter_notifies_managers_and_audits(po_world):
    po = make_draft_po(po_world)
    po = submit_purchase_order_for_approval_service(po=po, actor=po_world["exec"])

    assert po.status == PurchaseOrder.STATUS_APPROVAL
    assert po.submitted_by_id == po_world["exec"].id
    assert po.submitted_at is not None
    assert Notification.objects.filter(
        recipient=po_world["mgr"],
        notification_type=Notification.TYPE_APPROVAL_REQUIRED,
    ).exists()
    assert AuditLog.objects.filter(
        target_object_id=str(po.id), action=AuditLog.ACTION_SUBMIT
    ).exists()


def test_submitter_cannot_approve_own_po(po_world):
    po = make_draft_po(po_world)
    po = submit_purchase_order_for_approval_service(po=po, actor=po_world["exec"])
    with pytest.raises(ValidationError, match="Separation of duties"):
        approve_purchase_order_service(po=po, approver=po_world["exec"])


def test_approve_sets_approved_fields_and_commits_budget_once(po_world):
    po = make_draft_po(po_world)
    po = submit_purchase_order_for_approval_service(po=po, actor=po_world["exec"])
    po = approve_purchase_order_service(po=po, approver=po_world["mgr"], comments="OK")

    assert po.status == PurchaseOrder.STATUS_APPROVED
    assert po.approved_by_id == po_world["mgr"].id
    assert po.approved_at is not None
    po_world["budget"].refresh_from_db()
    assert po_world["budget"].committed_amount == po.total_amount

    commitments = SpendLedger.objects.filter(
        reference_number=po.po_number, entry_type=SpendLedger.ENTRY_COMMITMENT
    )
    assert commitments.count() == 1

    # Re-approval attempt must not double-commit.
    with pytest.raises(ValidationError):
        approve_purchase_order_service(po=po, approver=po_world["mgr"])
    assert commitments.count() == 1


def test_issue_requires_approved_and_notifies_vendor(po_world):
    po = make_draft_po(po_world)
    with pytest.raises(ValidationError):
        issue_purchase_order_service(po=po, actor=po_world["exec"])

    po = submit_purchase_order_for_approval_service(po=po, actor=po_world["exec"])
    po = approve_purchase_order_service(po=po, approver=po_world["mgr"])
    po = issue_purchase_order_service(po=po, actor=po_world["exec"])

    assert po.status == PurchaseOrder.STATUS_ISSUED
    assert po.issued_by_id == po_world["exec"].id
    assert po.issued_at is not None
    assert Notification.objects.filter(
        recipient=po_world["vendor_user"],
        notification_type=Notification.TYPE_PO_ISSUED,
    ).exists()


def test_issue_forbidden_for_non_procurement_role(po_world):
    po = make_draft_po(po_world)
    po = submit_purchase_order_for_approval_service(po=po, actor=po_world["exec"])
    po = approve_purchase_order_service(po=po, approver=po_world["mgr"])
    with pytest.raises(ValidationError, match="Permission Denied"):
        issue_purchase_order_service(po=po, actor=po_world["stores"])


def test_request_changes_returns_to_draft_with_note(po_world):
    po = make_draft_po(po_world)
    po = submit_purchase_order_for_approval_service(po=po, actor=po_world["exec"])
    with pytest.raises(ValidationError, match="comment|note|reason"):
        request_changes_purchase_order_service(
            po=po, reviewer=po_world["mgr"], note=""
        )
    po = request_changes_purchase_order_service(
        po=po, reviewer=po_world["mgr"], note="Please add delivery terms."
    )
    assert po.status == PurchaseOrder.STATUS_DRAFT
    assert "delivery terms" in po.rejection_reason
    assert Notification.objects.filter(
        recipient=po_world["exec"],
        notification_type=Notification.TYPE_PO_AMENDMENT,
    ).exists()


def test_reject_returns_to_draft_with_reason(po_world):
    po = make_draft_po(po_world)
    po = submit_purchase_order_for_approval_service(po=po, actor=po_world["exec"])
    with pytest.raises(ValidationError):
        reject_purchase_order_service(po=po, approver=po_world["mgr"], reason="")
    po = reject_purchase_order_service(
        po=po, approver=po_world["mgr"], reason="Budget frozen"
    )
    assert po.status == PurchaseOrder.STATUS_DRAFT
    assert po.rejection_reason == "Budget frozen"
    assert AuditLog.objects.filter(
        target_object_id=str(po.id), action=AuditLog.ACTION_REJECT
    ).exists()


def test_vendor_reject_returns_po_to_approved(po_world):
    po = issued_po(po_world)
    with pytest.raises(ValidationError):
        vendor_reject_purchase_order_service(
            po=po, vendor_user=po_world["vendor_user"], reason=""
        )

    other_vendor = Vendor.objects.create(
        organization=po_world["org"],
        category=VendorCategory.objects.create(name="Other", code="LC-OTHER"),
        legal_name="Other Vendor Ltd",
        vendor_number="VND-LC-02",
        tax_identification_number="TIN-LC-02",
        status=Vendor.STATUS_ACTIVE,
    )
    foreign_user = User.objects.create_user(
        email="lc.foreign@test.local",
        role=Role.objects.get(code=Role.VENDOR_USER),
        vendor=other_vendor,
    )
    with pytest.raises(ValidationError, match="Permission Denied"):
        vendor_reject_purchase_order_service(
            po=po, vendor_user=foreign_user, reason="Not my order"
        )

    po = vendor_reject_purchase_order_service(
        po=po, vendor_user=po_world["vendor_user"], reason="Cannot supply at this price"
    )
    assert po.status == PurchaseOrder.STATUS_APPROVED
    assert po.vendor_rejection_reason == "Cannot supply at this price"
    assert po.vendor_rejected_at is not None
    assert Notification.objects.filter(
        recipient=po_world["exec"],
        notification_type=Notification.TYPE_PO_ISSUED,
    ).exists()


def test_cross_org_user_gets_404_on_po_detail(client, po_world):
    po = make_draft_po(po_world)
    other_org = Organization.objects.create(name="Rival Org", code="LC-RIVAL")
    outsider = User.objects.create_user(
        email="rival.exec@test.local",
        role=Role.objects.get(code=Role.PROC_EXEC),
        organization=other_org,
    )
    client.force_login(outsider)
    assert client.get(f"/purchase-orders/{po.id}/").status_code == 404

    client.force_login(po_world["exec"])
    assert client.get(f"/purchase-orders/{po.id}/").status_code == 200


def test_rest_lifecycle_endpoints(po_world):
    api = APIClient()
    api.force_authenticate(user=po_world["exec"])
    po = make_draft_po(po_world)

    submit = api.post(f"/api/v1/purchase-orders/{po.id}/submit/")
    assert submit.status_code == 200, submit.data
    assert submit.data["status"] == PurchaseOrder.STATUS_APPROVAL

    api.force_authenticate(user=po_world["mgr"])
    approve = api.post(
        f"/api/v1/purchase-orders/{po.id}/approve/", {"comments": "OK"}, format="json"
    )
    assert approve.status_code == 200, approve.data
    assert approve.data["status"] == PurchaseOrder.STATUS_APPROVED

    api.force_authenticate(user=po_world["exec"])
    issue = api.post(f"/api/v1/purchase-orders/{po.id}/issue/")
    assert issue.status_code == 200, issue.data
    assert issue.data["status"] == PurchaseOrder.STATUS_ISSUED


def test_rest_request_changes_and_reject(po_world):
    api = APIClient()
    api.force_authenticate(user=po_world["exec"])
    po = make_draft_po(po_world)
    api.post(f"/api/v1/purchase-orders/{po.id}/submit/")

    api.force_authenticate(user=po_world["mgr"])
    bad = api.post(f"/api/v1/purchase-orders/{po.id}/request-changes/", {}, format="json")
    assert bad.status_code == 400
    changed = api.post(
        f"/api/v1/purchase-orders/{po.id}/request-changes/",
        {"note": "Clarify scope"},
        format="json",
    )
    assert changed.status_code == 200
    assert changed.data["status"] == PurchaseOrder.STATUS_DRAFT


def test_rest_vendor_cannot_issue_or_approve(po_world):
    api = APIClient()
    api.force_authenticate(user=po_world["vendor_user"])
    po = issued_po(po_world)
    assert api.post(f"/api/v1/purchase-orders/{po.id}/issue/").status_code == 403
    assert api.post(f"/api/v1/purchase-orders/{po.id}/approve/").status_code == 403


def test_stock_handoff_posts_inventory_once(po_world):
    po = issued_po(po_world)
    po = acknowledge_purchase_order_service(
        po=po, vendor_user=po_world["vendor_user"]
    )
    line = po.lines.first()

    receipt = create_goods_receipt_service(
        po=po,
        received_by=po_world["stores"],
        receipt_items=[
            {
                "po_line_id": line.id,
                "quantity_received": 10,
                "quantity_accepted": 10,
                "inspection_notes": "All units pass inspection",
            }
        ],
        delivery_note_number="DN-LC-001",
    )

    handoff_goods_to_stock_service(
        receipt=receipt,
        handed_off_by=po_world["stores"],
        storage_location="MAIN-WH",
        handoff_notes="Shelved",
    )
    receipt.refresh_from_db()
    assert receipt.stock_handoff_status == "HANDED_OFF"

    stock_item = StockItem.objects.get(po_line=line, location="MAIN-WH")
    assert stock_item.quantity_on_hand == Decimal("10.00")
    assert StockMovement.objects.filter(stock_item=stock_item).count() == 1
    movement = StockMovement.objects.get(stock_item=stock_item)
    assert movement.movement_type == StockMovement.MOVE_IN
    assert movement.quantity == Decimal("10.00")
    assert movement.reference_number == receipt.grn_number

    # Repeat handoff is idempotent: no double count, no extra movement.
    handoff_goods_to_stock_service(
        receipt=receipt,
        handed_off_by=po_world["stores"],
        storage_location="MAIN-WH",
    )
    stock_item.refresh_from_db()
    assert stock_item.quantity_on_hand == Decimal("10.00")
    assert StockMovement.objects.filter(stock_item=stock_item).count() == 1


def test_manager_cancels_po_via_web_and_releases_commitment(client, po_world):
    po = issued_po(po_world)
    po_world["budget"].refresh_from_db()
    committed_before = po_world["budget"].committed_amount
    assert committed_before == po.total_amount

    client.force_login(po_world["mgr"])
    response = client.post(
        f"/purchase-orders/{po.id}/cancel/",
        {"reason": "Duplicate order raised by mistake"},
    )

    assert response.status_code == 302
    po.refresh_from_db()
    assert po.status == PurchaseOrder.STATUS_CANCELLED
    po_world["budget"].refresh_from_db()
    assert po_world["budget"].committed_amount == Decimal("0.00")
    assert SpendLedger.objects.filter(
        reference_number=f"{po.po_number}-CANCEL"
    ).exists()
    assert AuditLog.objects.filter(
        target_object_id=str(po.id), action=AuditLog.ACTION_REJECT
    ).exists()


def test_cancel_web_requires_reason_and_is_forbidden_for_exec(client, po_world):
    po = issued_po(po_world)

    client.force_login(po_world["mgr"])
    client.post(f"/purchase-orders/{po.id}/cancel/", {"reason": "   "})
    po.refresh_from_db()
    assert po.status != PurchaseOrder.STATUS_CANCELLED

    client.force_login(po_world["exec"])
    response = client.post(
        f"/purchase-orders/{po.id}/cancel/", {"reason": "Exec cannot cancel"}
    )
    assert response.status_code == 403


def test_cancel_is_org_scoped(client, po_world):
    other_org = Organization.objects.create(name="Other Cancel Org", code="OC-ORG")
    other_mgr = User.objects.create_user(
        email="oc.mgr@test.local",
        role=po_world["mgr"].role,
        organization=other_org,
    )

    po = issued_po(po_world)
    client.force_login(other_mgr)
    response = client.post(
        f"/purchase-orders/{po.id}/cancel/", {"reason": "Cross org attempt"}
    )
    assert response.status_code == 404
    po.refresh_from_db()
    assert po.status != PurchaseOrder.STATUS_CANCELLED


def test_draft_edit_updates_lines_and_recomputes_totals(client, po_world):
    po = make_draft_po(po_world)
    line = po.lines.first()
    original_total = po.total_amount

    client.force_login(po_world["exec"])
    modal = client.get(f"/purchase-orders/{po.id}/edit/")
    assert modal.status_code == 200
    assert b"Edit Draft" in modal.content

    response = client.post(
        f"/purchase-orders/{po.id}/edit/",
        {
            f"quantity_{line.id}": "4.00",
            f"unit_price_{line.id}": "3000.00",
        },
    )
    assert response.status_code == 302

    po.refresh_from_db()
    line.refresh_from_db()
    assert line.quantity == Decimal("4.00")
    assert line.unit_price == Decimal("3000.00")
    assert line.line_total == Decimal("12000.00")
    assert po.subtotal == Decimal("12000.00")
    assert po.tax_amount == Decimal("1200.00")
    assert po.total_amount == Decimal("13200.00")
    assert po.total_amount != original_total
    assert AuditLog.objects.filter(
        target_object_id=str(po.id), action=AuditLog.ACTION_UPDATE
    ).exists()


def test_draft_edit_blocked_once_submitted(client, po_world):
    po = make_draft_po(po_world)
    po = submit_purchase_order_for_approval_service(po=po, actor=po_world["exec"])
    line = po.lines.first()

    client.force_login(po_world["exec"])
    response = client.post(
        f"/purchase-orders/{po.id}/edit/",
        {
            f"quantity_{line.id}": "1.00",
            f"unit_price_{line.id}": "1.00",
        },
    )
    assert response.status_code == 403
    po.refresh_from_db()
    assert po.total_amount == Decimal("11000.00")


def test_draft_edit_is_org_scoped_and_requires_procurement(client, po_world):
    other_org = Organization.objects.create(name="Other Draft Org", code="OD-ORG")
    other_exec = User.objects.create_user(
        email="od.exec@test.local",
        role=po_world["exec"].role,
        organization=other_org,
    )
    po = make_draft_po(po_world)

    client.force_login(other_exec)
    assert client.get(f"/purchase-orders/{po.id}/edit/").status_code == 404

    client.force_login(po_world["stores"])
    assert client.get(f"/purchase-orders/{po.id}/edit/").status_code == 403


def test_purchase_order_register_exposes_awards_pending_generate_panel(
    client, po_world
):
    client.force_login(po_world["exec"])
    response = client.get("/purchase-orders/")
    assert response.status_code == 200
    body = response.content.decode()
    assert 'id="awards-pending"' in body
    assert "/purchase-orders/htmx/awards-pending/" in body

    pending_tab = client.get("/purchase-orders/htmx/awards-pending/")
    assert pending_tab.status_code == 200


def test_awards_pending_panel_hidden_from_stores(client, po_world):
    client.force_login(po_world["stores"])
    response = client.get("/purchase-orders/")
    assert response.status_code == 200
    assert 'id="awards-pending"' not in response.content.decode()
