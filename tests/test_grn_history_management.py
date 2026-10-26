from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.orders.models import POLine, PurchaseOrder
from apps.organization.models import CostCenter, Department, Organization
from apps.receipts.models import GoodsReceipt, ReceiptLine
from apps.receipts.services import create_goods_receipt_service
from apps.vendors.models import Vendor, VendorCategory


@pytest.fixture
def grn_history_setup(db, db_roles):
    org = Organization.objects.create(name="HPE Global", code="HPE-HIST-ORG")
    dept = Department.objects.create(
        organization=org, name="Warehouse Operations", code="DEPT-WH-OPS"
    )
    cost_center = CostCenter.objects.create(
        department=dept, code="CC-HIST-01", name="Main Warehouse"
    )
    category = VendorCategory.objects.create(name="Hardware", code="CAT-HW-01")

    vendor1 = Vendor.objects.create(
        legal_name="Dell Technologies Global",
        vendor_number="VEND-DELL-HIST-01",
        tax_identification_number="TIN-DELL-HIST",
        category=category,
        status=Vendor.STATUS_ACTIVE,
    )
    vendor2 = Vendor.objects.create(
        legal_name="Lenovo Enterprise Systems",
        vendor_number="VEND-LENOVO-HIST-02",
        tax_identification_number="TIN-LENOVO-HIST",
        category=category,
        status=Vendor.STATUS_ACTIVE,
    )

    receiver = User.objects.create_user(
        email="receiver_hist@hpe.com",
        password="Password123!",
        role=db_roles[Role.STORES_RECEIVER],
    )

    # PO 1: Dell Servers
    po1 = PurchaseOrder.objects.create(
        po_number="PO-2026-DELL-001",
        version=1,
        vendor=vendor1,
        cost_center=cost_center,
        status=PurchaseOrder.STATUS_ISSUED,
        subtotal=Decimal("50000.00"),
        tax_amount=Decimal("5000.00"),
        total_amount=Decimal("55000.00"),
    )
    po1_line1 = POLine.objects.create(
        po=po1,
        item_description="Dell PowerEdge R750 Server",
        quantity=Decimal("10.00"),
        quantity_received=Decimal("0.00"),
        unit_of_measure="EA",
        unit_price=Decimal("5000.00"),
    )

    # PO 2: Lenovo Laptops
    po2 = PurchaseOrder.objects.create(
        po_number="PO-2026-LENOVO-002",
        version=1,
        vendor=vendor2,
        cost_center=cost_center,
        status=PurchaseOrder.STATUS_ISSUED,
        subtotal=Decimal("20000.00"),
        tax_amount=Decimal("2000.00"),
        total_amount=Decimal("22000.00"),
    )
    po2_line1 = POLine.objects.create(
        po=po2,
        item_description="Lenovo ThinkPad P16 Workstation",
        quantity=Decimal("20.00"),
        quantity_received=Decimal("0.00"),
        unit_of_measure="EA",
        unit_price=Decimal("1000.00"),
    )

    # Create GRN 1: Dell (Passed Inspection)
    grn1 = create_goods_receipt_service(
        po=po1,
        received_by=receiver,
        receipt_items=[
            {
                "po_line_id": str(po1_line1.id),
                "quantity_received": Decimal("5.00"),
                "quantity_accepted": Decimal("5.00"),
                "inspection_notes": "First 5 servers passed QA",
            }
        ],
        delivery_note_number="DN-DELL-9001",
        remarks="Delivered via BlueDart",
    )
    grn1.received_date = timezone.now()
    grn1.save(update_fields=["received_date"])

    # Create GRN 2: Lenovo (Failed / Rejection)
    grn2 = create_goods_receipt_service(
        po=po2,
        received_by=receiver,
        receipt_items=[
            {
                "po_line_id": str(po2_line1.id),
                "quantity_received": Decimal("10.00"),
                "quantity_accepted": Decimal("8.00"),
                "rejection_reason": "2 screens cracked",
                "inspection_notes": "Failed on 2 units due to broken glass",
            }
        ],
        delivery_note_number="DN-LENOVO-8002",
        remarks="Fragile packaging damaged",
    )

    # Create GRN 3: Pending inspection
    # Create manually or without inspection notes
    now = timezone.now()
    grn3 = GoodsReceipt.objects.create(
        grn_number=f"GRN-{now.strftime('%Y')}-99999",
        po=po2,
        received_by=receiver,
        received_date=now - timedelta(days=2),
        delivery_note_number="DN-LENOVO-PENDING",
        remarks="Awaiting QA officer",
    )
    ReceiptLine.objects.create(
        receipt=grn3,
        po_line=po2_line1,
        quantity_received=Decimal("5.00"),
        quantity_accepted=Decimal("5.00"),
    )

    return {
        "org": org,
        "vendor1": vendor1,
        "vendor2": vendor2,
        "receiver": receiver,
        "po1": po1,
        "po2": po2,
        "grn1": grn1,
        "grn2": grn2,
        "grn3": grn3,
    }


@pytest.mark.django_db
def test_authenticated_stores_receiver_can_access_grn_history(client, grn_history_setup):
    receiver = grn_history_setup["receiver"]
    client.force_login(receiver)

    response = client.get("/receipts/")
    assert response.status_code == 200
    assert b"Goods Receipt Notes (GRN)" in response.content
    assert grn_history_setup["grn1"].grn_number.encode() in response.content
    assert grn_history_setup["grn2"].grn_number.encode() in response.content
    assert grn_history_setup["grn3"].grn_number.encode() in response.content


@pytest.mark.django_db
def test_anonymous_user_is_redirected_to_login(client):
    response = client.get("/receipts/")
    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_search_by_grn_number(client, grn_history_setup):
    receiver = grn_history_setup["receiver"]
    grn1 = grn_history_setup["grn1"]
    client.force_login(receiver)

    response = client.get(f"/receipts/?q={grn1.grn_number}")
    assert response.status_code == 200
    assert grn1.grn_number.encode() in response.content
    assert grn_history_setup["grn2"].grn_number.encode() not in response.content


@pytest.mark.django_db
def test_search_by_po_number(client, grn_history_setup):
    receiver = grn_history_setup["receiver"]
    grn1 = grn_history_setup["grn1"]
    client.force_login(receiver)

    response = client.get("/receipts/?q=PO-2026-DELL-001")
    assert response.status_code == 200
    assert grn1.grn_number.encode() in response.content
    assert grn_history_setup["grn2"].grn_number.encode() not in response.content


@pytest.mark.django_db
def test_search_by_vendor(client, grn_history_setup):
    receiver = grn_history_setup["receiver"]
    grn1 = grn_history_setup["grn1"]
    client.force_login(receiver)

    response = client.get("/receipts/?q=Dell")
    assert response.status_code == 200
    assert grn1.grn_number.encode() in response.content
    assert grn_history_setup["grn2"].grn_number.encode() not in response.content


@pytest.mark.django_db
def test_search_by_delivery_note(client, grn_history_setup):
    receiver = grn_history_setup["receiver"]
    grn2 = grn_history_setup["grn2"]
    client.force_login(receiver)

    response = client.get("/receipts/?q=DN-LENOVO-8002")
    assert response.status_code == 200
    assert grn2.grn_number.encode() in response.content
    assert grn_history_setup["grn1"].grn_number.encode() not in response.content


@pytest.mark.django_db
def test_inspection_status_filtering(client, grn_history_setup):
    receiver = grn_history_setup["receiver"]
    grn1 = grn_history_setup["grn1"]  # Passed
    grn2 = grn_history_setup["grn2"]  # Failed/Rejection
    grn3 = grn_history_setup["grn3"]  # Pending
    client.force_login(receiver)

    # Filter PASSED
    resp_passed = client.get("/receipts/?status=PASSED")
    assert resp_passed.status_code == 200
    assert grn1.grn_number.encode() in resp_passed.content
    assert grn2.grn_number.encode() not in resp_passed.content
    assert grn3.grn_number.encode() not in resp_passed.content

    # Filter FAILED / REJECTED
    resp_failed = client.get("/receipts/?status=FAILED")
    assert resp_failed.status_code == 200
    assert grn2.grn_number.encode() in resp_failed.content
    assert grn1.grn_number.encode() not in resp_failed.content
    assert grn3.grn_number.encode() not in resp_failed.content

    # Filter PENDING
    resp_pending = client.get("/receipts/?status=PENDING")
    assert resp_pending.status_code == 200
    assert grn3.grn_number.encode() in resp_pending.content
    assert grn1.grn_number.encode() not in resp_pending.content


@pytest.mark.django_db
def test_po_filtering(client, grn_history_setup):
    receiver = grn_history_setup["receiver"]
    po1 = grn_history_setup["po1"]
    grn1 = grn_history_setup["grn1"]
    client.force_login(receiver)

    response = client.get(f"/receipts/?po={po1.id}")
    assert response.status_code == 200
    assert grn1.grn_number.encode() in response.content
    assert grn_history_setup["grn2"].grn_number.encode() not in response.content


@pytest.mark.django_db
def test_date_filtering(client, grn_history_setup):
    receiver = grn_history_setup["receiver"]
    grn1 = grn_history_setup["grn1"]  # Today
    grn3 = grn_history_setup["grn3"]  # 2 days ago
    client.force_login(receiver)

    today_str = timezone.localdate().strftime("%Y-%m-%d")
    response = client.get(f"/receipts/?date_from={today_str}&date_to={today_str}")
    assert response.status_code == 200
    assert grn1.grn_number.encode() in response.content
    assert grn3.grn_number.encode() not in response.content


@pytest.mark.django_db
def test_clear_filters_returns_complete_list(client, grn_history_setup):
    receiver = grn_history_setup["receiver"]
    client.force_login(receiver)

    # Filtered
    resp_filtered = client.get("/receipts/?q=NonExistentQueryXYZ")
    assert resp_filtered.status_code == 200
    assert b"No Goods Receipt Notes Found" in resp_filtered.content

    # Cleared / Default
    resp_all = client.get("/receipts/")
    assert resp_all.status_code == 200
    assert grn_history_setup["grn1"].grn_number.encode() in resp_all.content
    assert grn_history_setup["grn2"].grn_number.encode() in resp_all.content
    assert grn_history_setup["grn3"].grn_number.encode() in resp_all.content


@pytest.mark.django_db
def test_pagination_works(client, grn_history_setup):
    receiver = grn_history_setup["receiver"]
    po1 = grn_history_setup["po1"]
    client.force_login(receiver)

    # Create 12 additional GRNs to exceed 10 per page
    for i in range(12):
        GoodsReceipt.objects.create(
            grn_number=f"GRN-2026-PAGINATE-{i:03d}",
            po=po1,
            received_by=receiver,
            received_date=timezone.now(),
        )

    resp_p1 = client.get("/receipts/?page=1")
    assert resp_p1.status_code == 200
    assert resp_p1.context["page_obj"].number == 1
    assert resp_p1.context["page_obj"].has_next() is True

    resp_p2 = client.get("/receipts/?page=2")
    assert resp_p2.status_code == 200
    assert resp_p2.context["page_obj"].number == 2
    assert resp_p2.context["page_obj"].has_previous() is True


@pytest.mark.django_db
def test_completed_po_does_not_show_start_goods_receipt(client, grn_history_setup, db_roles):
    receiver = grn_history_setup["receiver"]
    po = grn_history_setup["po1"]
    po.status = PurchaseOrder.STATUS_COMPLETED
    po.save()

    client.force_login(receiver)
    # Stores Receiver viewing completed PO detail is redirected to orders list (scoped to receivable)
    response = client.get(f"/purchase-orders/{po.id}/")
    assert response.status_code == 302
    assert "/purchase-orders/" in response.url

    # Superadmin viewing completed PO detail does NOT see "Start Goods Receipt"
    admin = User.objects.create_user(
        email="admin_test@hpe.com",
        password="Password123!",
        role=db_roles[Role.SUPER_ADMIN],
        is_superuser=True,
    )
    client.force_login(admin)
    admin_resp = client.get(f"/purchase-orders/{po.id}/")
    assert admin_resp.status_code == 200
    assert b"Start Goods Receipt" not in admin_resp.content
