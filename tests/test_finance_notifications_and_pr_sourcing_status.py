from datetime import timedelta
from decimal import Decimal
import pytest
from django.test import Client
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.budgets.models import Budget
from apps.notifications.models import Notification
from apps.orders.models import PurchaseOrder
from apps.orders.services import generate_purchase_order_service
from apps.organization.models import CostCenter, Department, FiscalPeriod, Organization
from apps.receipts.models import GoodsReceipt, ReceiptLine
from apps.requisitions.models import PRLine, PurchaseRequisition
from apps.sourcing.models import SourcingEvent
from apps.sourcing.services import create_sourcing_event_service
from apps.vendors.models import Vendor, VendorCategory
from apps.vendors.services import register_vendor_service


@pytest.fixture
def base_test_data(db_roles):
    org = Organization.objects.create(name="HPE Tech Corp", code="HPE-NOTIF-TEST")
    dept = Department.objects.create(organization=org, name="Engineering", code="ENG")
    cc = CostCenter.objects.create(
        department=dept, name="Cloud Infrastructure", code="CC-ENG-01"
    )
    now = timezone.now()
    period = FiscalPeriod.objects.create(
        organization=org,
        year=now.year,
        period_number=1,
        name=f"FY{now.year}-P1",
        start_date=now.date().replace(month=1, day=1),
        end_date=now.date().replace(month=12, day=31),
        is_closed=False,
    )
    Budget.objects.create(
        cost_center=cc,
        fiscal_period=period,
        allocated_amount=Decimal("50000.00"),
    )

    requester = User.objects.create_user(
        email="requester.notif@hpe.com",
        password="Password123!",
        role=db_roles[Role.REQUESTER],
        organization=org,
        department=dept,
    )
    finance = User.objects.create_user(
        email="finance.notif@hpe.com",
        password="Password123!",
        role=db_roles[Role.FINANCE_AP],
        organization=org,
    )
    stores = User.objects.create_user(
        email="stores.notif@hpe.com",
        password="Password123!",
        role=db_roles[Role.STORES_RECEIVER],
        organization=org,
    )
    proc_exec = User.objects.create_user(
        email="proc_exec.notif@hpe.com",
        password="Password123!",
        role=db_roles[Role.PROC_EXEC],
        organization=org,
    )

    cat = VendorCategory.objects.create(name="Hardware", code="HW")
    vendor = register_vendor_service(
        legal_name="Apex Hardware Inc",
        tax_identification_number="TIN-APEX-01",
        category=cat,
        email="apex@vendor.com",
        address="Austin TX",
    )
    vendor.status = Vendor.STATUS_ACTIVE
    vendor.save()

    return {
        "org": org,
        "dept": dept,
        "cc": cc,
        "requester": requester,
        "finance": finance,
        "stores": stores,
        "proc_exec": proc_exec,
        "vendor": vendor,
    }


@pytest.mark.django_db
def test_finance_notifications_layout_and_receipt_detail(base_test_data):
    """
    Verify Finance dashboard has notification bell, sidebar link,
    and navigating to a receipt detail notification retains Finance navigation.
    """
    finance = base_test_data["finance"]
    client = Client()
    client.force_login(finance)

    # 1. Finance dashboard renders bell icon & notifications link
    res = client.get("/finance/")
    assert res.status_code == 200
    content = res.content.decode("utf-8")
    assert "/notifications/" in content
    assert "fa-bell" in content

    # 2. Notifications page renders under Finance layout
    res = client.get("/notifications/")
    assert res.status_code == 200
    content = res.content.decode("utf-8")
    assert "Finance &amp; AP" in content or "Finance & AP" in content
    assert "Stores Desk" not in content

    # 3. Create a PO and GRN, generate a notification pointing to GRN
    po = generate_purchase_order_service(
        vendor=base_test_data["vendor"],
        cost_center=base_test_data["cc"],
        line_items=[{"item_description": "Server", "quantity": 1, "unit_price": 500}],
        created_by_user=base_test_data["proc_exec"],
    )
    grn = GoodsReceipt.objects.create(
        grn_number="GRN-TEST-001",
        po=po,
        received_by=base_test_data["stores"],
        received_date=timezone.now(),
        delivery_note_number="DN-123",
    )

    notif = Notification.objects.create(
        recipient=finance,
        notification_type=Notification.TYPE_GOODS_RECEIVED,
        title=f"GRN Receipt Note Dispatched: {grn.grn_number}",
        message=f"Stores Receiver has dispatched Goods Receipt Note {grn.grn_number}.",
        target_url=f"/receipts/{grn.id}/",
    )

    # 4. Access GRN detail view as Finance user
    res = client.get(f"/receipts/{grn.id}/")
    assert res.status_code == 200
    grn_content = res.content.decode("utf-8")
    # Finance shell should be rendered, not warehouse actions
    assert "Back to Finance Dashboard" in grn_content
    assert "Invoices &amp; AP" in grn_content or "Invoices & AP" in grn_content
    assert "Match Exceptions" in grn_content


@pytest.mark.django_db
def test_dashboard_url_does_not_redirect_to_stores():
    """Verify /dashboard/ uses dashboard_redirect_view rather than hijacking to stores."""
    client = Client()
    res = client.get("/dashboard/")
    # Unauthenticated should redirect to login
    assert res.status_code == 302
    assert "/login/" in res.url


@pytest.mark.django_db
def test_pr_status_updates_on_sourcing_and_po(base_test_data):
    """
    Verify Requisition status transitions from APPROVED to SOURCING
    when a sourcing event is created, and to PO_ISSUED when a PO is generated.
    """
    requester = base_test_data["requester"]
    proc_exec = base_test_data["proc_exec"]
    vendor = base_test_data["vendor"]
    cc = base_test_data["cc"]
    dept = base_test_data["dept"]

    today = timezone.now()

    # 1. Create and approve PR
    pr = PurchaseRequisition.objects.create(
        pr_number="PR-TEST-NOTIF-01",
        title="Server Racks",
        justification="Project expansion",
        requester=requester,
        department=dept,
        cost_center=cc,
        status=PurchaseRequisition.STATUS_APPROVED,
        total_amount=Decimal("1000.00"),
        requested_delivery_date=today.date() + timedelta(days=14),
    )
    PRLine.objects.create(
        requisition=pr,
        item_description="Server Rack",
        quantity=Decimal("2.00"),
        unit_of_measure="EA",
        estimated_unit_price=Decimal("500.00"),
        estimated_total=Decimal("1000.00"),
    )

    client = Client()
    client.force_login(requester)

    # View PR detail in APPROVED state
    res = client.get(f"/requisitions/{pr.id}/")
    assert res.status_code == 200
    assert "Ready for Sourcing" in res.content.decode("utf-8")

    # 2. Create Sourcing Event linked to PR -> status moves to SOURCING
    event = create_sourcing_event_service(
        title="Server Racks RFQ",
        event_type=SourcingEvent.TYPE_RFQ,
        bid_start_date=today,
        bid_end_date=today + timedelta(days=7),
        description="Sourcing racks",
        requisition=pr,
        created_by_user=proc_exec,
    )
    pr.refresh_from_db()
    assert pr.status == PurchaseRequisition.STATUS_SOURCING

    # Detail page, requester dashboard, and PR list should reflect In Sourcing
    res = client.get(f"/requisitions/{pr.id}/")
    content = res.content.decode("utf-8")
    assert "In Sourcing" in content
    assert event.event_number in content

    res = client.get("/requester/")
    assert "In Sourcing" in res.content.decode("utf-8")

    res = client.get("/requisitions/")
    assert "In Sourcing" in res.content.decode("utf-8")

    # 3. Generate PO linked to PR -> status moves to PO_ISSUED
    po = generate_purchase_order_service(
        vendor=vendor,
        cost_center=cc,
        line_items=[{"item_description": "Server Rack", "quantity": 2, "unit_price": 500}],
        created_by_user=proc_exec,
        requisition=pr,
        sourcing_event=event,
    )
    pr.refresh_from_db()
    assert pr.status == PurchaseRequisition.STATUS_PO_ISSUED

    # Detail page, requester dashboard, and PR list should reflect PO Issued
    res = client.get(f"/requisitions/{pr.id}/")
    content = res.content.decode("utf-8")
    assert "PO Issued" in content
    assert po.po_number in content

    res = client.get("/requester/")
    assert "PO Issued" in res.content.decode("utf-8")

    res = client.get("/requisitions/")
    assert "PO Issued" in res.content.decode("utf-8")


@pytest.mark.django_db
def test_pr_status_backward_compatibility_with_existing_po(base_test_data):
    """
    Even if an existing PR in the database has status='APPROVED',
    if it has linked purchase orders, the UI displays 'PO Issued'.
    """
    requester = base_test_data["requester"]
    proc_exec = base_test_data["proc_exec"]
    vendor = base_test_data["vendor"]
    cc = base_test_data["cc"]
    dept = base_test_data["dept"]
    today = timezone.now()

    pr = PurchaseRequisition.objects.create(
        pr_number="PR-LEGACY-001",
        title="Office Chairs",
        justification="Ergonomic chairs",
        requester=requester,
        department=dept,
        cost_center=cc,
        status=PurchaseRequisition.STATUS_APPROVED,  # status is APPROVED in DB
        total_amount=Decimal("500.00"),
        requested_delivery_date=today.date() + timedelta(days=14),
    )
    # Manually attach a PO without updating pr.status
    PurchaseOrder.objects.create(
        po_number="PO-LEGACY-001",
        requisition=pr,
        vendor=vendor,
        cost_center=cc,
        status=PurchaseOrder.STATUS_ISSUED,
        total_amount=Decimal("500.00"),
    )

    client = Client()
    client.force_login(requester)

    res = client.get(f"/requisitions/{pr.id}/")
    content = res.content.decode("utf-8")
    assert "PO Issued" in content

    res = client.get("/requester/")
    assert "PO Issued" in res.content.decode("utf-8")

    res = client.get("/requisitions/")
    assert "PO Issued" in res.content.decode("utf-8")


@pytest.mark.django_db
def test_requester_isolated_from_stores_on_receipt_and_orders(base_test_data):
    """
    Verify that when a Requester views a Goods Receipt or Purchase Order:
    1. Base layout is Requester Desk (not Stores or Procurement shell).
    2. Back buttons point to Requisition / Requester Desk (not Store lists).
    3. Operational warehouse buttons (inspection, stock handoff, returns) are hidden.
    4. Navigating to /receipts/ or /purchase-orders/ redirects back to /requisitions/.
    5. Requisition detail displays the downstream linked PO card.
    """
    requester = base_test_data["requester"]
    proc_exec = base_test_data["proc_exec"]
    stores = base_test_data["stores"]
    vendor = base_test_data["vendor"]
    cc = base_test_data["cc"]
    dept = base_test_data["dept"]
    today = timezone.now()

    pr = PurchaseRequisition.objects.create(
        pr_number="PR-REQ-TEST-001",
        title="Engineering Laptops",
        justification="Hardware refresh",
        requester=requester,
        department=dept,
        cost_center=cc,
        status=PurchaseRequisition.STATUS_APPROVED,
        total_amount=Decimal("2500.00"),
        requested_delivery_date=today.date() + timedelta(days=14),
    )
    po = generate_purchase_order_service(
        vendor=vendor,
        cost_center=cc,
        line_items=[{"item_description": "Laptop", "quantity": 2, "unit_price": 1250}],
        created_by_user=proc_exec,
        requisition=pr,
    )
    grn = GoodsReceipt.objects.create(
        grn_number="GRN-REQ-TEST-001",
        po=po,
        received_by=stores,
        received_date=today,
    )

    client = Client()
    client.force_login(requester)

    # 1. Requester viewing /receipts/{grn.id}/
    res_grn = client.get(f"/receipts/{grn.id}/")
    assert res_grn.status_code == 200
    grn_html = res_grn.content.decode("utf-8")
    assert "Requester Desk" in grn_html
    assert f"Back to Requisition {pr.pr_number}" in grn_html
    assert f"/requisitions/{pr.id}/" in grn_html
    assert f"/receipts/{grn.id}/inspect/" not in grn_html
    assert f"/receipts/{grn.id}/stock-handoff/" not in grn_html
    assert "rejections_queue" not in grn_html
    assert "Proceed to Stock Handoff" not in grn_html
    assert "Correct Qty" not in grn_html
    assert "Dispatch Return" not in grn_html

    # 2. Requester viewing /orders/{po.id}/
    res_po = client.get(f"/orders/{po.id}/")
    assert res_po.status_code == 200
    po_html = res_po.content.decode("utf-8")
    assert "Requester Desk" in po_html
    assert f"Back to Requisition {pr.pr_number}" in po_html
    assert "Start Goods Receipt" not in po_html
    assert "Amend PO" not in po_html

    # 3. Requester visiting /receipts/ and /purchase-orders/
    res_receipts_list = client.get("/receipts/")
    assert res_receipts_list.status_code == 302
    assert res_receipts_list.url == "/requisitions/"

    res_orders_list = client.get("/purchase-orders/")
    assert res_orders_list.status_code == 302
    assert res_orders_list.url == "/requisitions/"

    # 4. Requester viewing PR detail displays linked PO card
    res_pr = client.get(f"/requisitions/{pr.id}/")
    assert res_pr.status_code == 200
    pr_html = res_pr.content.decode("utf-8")
    assert "Procurement Execution" in pr_html
    assert po.po_number in pr_html
    assert f"/purchase-orders/{po.id}/" in pr_html

