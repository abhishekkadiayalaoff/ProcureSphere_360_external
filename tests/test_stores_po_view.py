from decimal import Decimal

import pytest

from apps.accounts.models import Role, User
from apps.orders.models import POLine, PurchaseOrder
from apps.organization.models import CostCenter, Department, Organization
from apps.vendors.models import Vendor, VendorCategory


@pytest.mark.django_db
def test_stores_receiver_po_list_filtering(client, db_roles):
    """
    Verify Stores Receiver sees only ISSUED, ACKNOWLEDGED, and PARTIAL_RECEIPT POs.
    """
    org = Organization.objects.create(name="HPE Tech", code="HPE-TST-PO")
    dept = Department.objects.create(organization=org, name="Operations", code="DEPT-OPS-PO")
    cost_center = CostCenter.objects.create(department=dept, code="CC-OPS-PO", name="Receiving Hub")
    category = VendorCategory.objects.create(name="IT Hardware", code="CAT-HW-PO")
    vendor = Vendor.objects.create(
        legal_name="Dell Technologies",
        tax_identification_number="TIN-DELL-PO",
        category=category,
        status=Vendor.STATUS_ACTIVE,
    )

    # Create POs in various statuses
    PurchaseOrder.objects.create(
        po_number="PO-TEST-DRAFT",
        vendor=vendor,
        cost_center=cost_center,
        status=PurchaseOrder.STATUS_DRAFT,
        total_amount=Decimal("1000.00"),
    )
    PurchaseOrder.objects.create(
        po_number="PO-TEST-ISSUED",
        vendor=vendor,
        cost_center=cost_center,
        status=PurchaseOrder.STATUS_ISSUED,
        total_amount=Decimal("2000.00"),
    )
    PurchaseOrder.objects.create(
        po_number="PO-TEST-ACK",
        vendor=vendor,
        cost_center=cost_center,
        status=PurchaseOrder.STATUS_ACKNOWLEDGED,
        total_amount=Decimal("3000.00"),
    )
    PurchaseOrder.objects.create(
        po_number="PO-TEST-PARTIAL",
        vendor=vendor,
        cost_center=cost_center,
        status=PurchaseOrder.STATUS_PARTIAL_RECEIPT,
        total_amount=Decimal("4000.00"),
    )
    PurchaseOrder.objects.create(
        po_number="PO-TEST-COMPLETED",
        vendor=vendor,
        cost_center=cost_center,
        status=PurchaseOrder.STATUS_COMPLETED,
        total_amount=Decimal("5000.00"),
    )

    stores_user = User.objects.create_user(
        email="receiver_test@hpe.com",
        password="Password123!",
        role=db_roles[Role.STORES_RECEIVER],
    )

    # 1. Unauthenticated request redirects to login
    response_unauth = client.get("/purchase-orders/")
    assert response_unauth.status_code == 302
    assert "/login/" in response_unauth.url

    # 2. Stores Receiver authenticated
    client.force_login(stores_user)
    response = client.get("/purchase-orders/")
    assert response.status_code == 200
    content = response.content.decode()

    # Receivable POs must be visible
    assert "PO-TEST-ISSUED" in content
    assert "PO-TEST-ACK" in content
    assert "PO-TEST-PARTIAL" in content

    # Non-receivable POs must NOT be in the list for Stores Receiver
    assert "PO-TEST-DRAFT" not in content
    assert "PO-TEST-COMPLETED" not in content

    # Vendor, amounts, statuses, and action button should be present
    assert "Dell Technologies" in content
    assert "$2000.00" in content
    assert "View Details" in content


@pytest.mark.django_db
def test_stores_receiver_po_detail_view(client, db_roles):
    """
    Verify PO detail page shows all required fields, line items with remaining quantity, and Start Goods Receipt action.
    """
    org = Organization.objects.create(name="HPE Tech", code="HPE-TST-DTL")
    dept = Department.objects.create(organization=org, name="Engineering", code="DEPT-ENG-DTL")
    cost_center = CostCenter.objects.create(department=dept, code="CC-ENG-DTL", name="Lab")
    category = VendorCategory.objects.create(name="Peripherals", code="CAT-PER-DTL")
    vendor = Vendor.objects.create(
        legal_name="Logitech Commercial",
        tax_identification_number="TIN-LOGI-DTL",
        category=category,
        status=Vendor.STATUS_ACTIVE,
    )

    po = PurchaseOrder.objects.create(
        po_number="PO-2026-DETAIL-01",
        version=1,
        vendor=vendor,
        cost_center=cost_center,
        status=PurchaseOrder.STATUS_PARTIAL_RECEIPT,
        subtotal=Decimal("15000.00"),
        tax_amount=Decimal("1500.00"),
        total_amount=Decimal("16500.00"),
        terms_and_conditions="Standard Net-30 enterprise fulfillment terms.",
    )

    line1 = POLine.objects.create(
        po=po,
        item_description="MX Master 3S Wireless Mouse",
        quantity=Decimal("50.00"),
        quantity_received=Decimal("20.00"),
        unit_of_measure="EA",
        unit_price=Decimal("100.00"),
    )

    line2 = POLine.objects.create(
        po=po,
        item_description="MX Mechanical Keyboard",
        quantity=Decimal("50.00"),
        quantity_received=Decimal("0.00"),
        unit_of_measure="EA",
        unit_price=Decimal("200.00"),
    )

    # Verify model remaining_quantity property
    assert line1.remaining_quantity == Decimal("30.00")
    assert line2.remaining_quantity == Decimal("50.00")

    stores_user = User.objects.create_user(
        email="receiver_detail@hpe.com",
        password="Password123!",
        role=db_roles[Role.STORES_RECEIVER],
    )

    client.force_login(stores_user)
    response = client.get(f"/purchase-orders/{po.id}/")
    assert response.status_code == 200
    content = response.content.decode()

    # Required PO information
    assert "PO-2026-DETAIL-01" in content
    assert "Logitech Commercial" in content
    assert "Partial Receipt" in content
    assert "$16500.00" in content
    assert "Standard Net-30 enterprise fulfillment terms." in content

    # Line item descriptions, quantities, and remaining quantities
    assert "MX Master 3S Wireless Mouse" in content
    assert "MX Mechanical Keyboard" in content
    assert "50.00" in content
    assert "20.00" in content
    assert "30.00" in content

    # Clear navigation action
    assert "Start Goods Receipt" in content
    assert "/receipts/" in content
