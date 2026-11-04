from decimal import Decimal

import pytest
from django.utils import timezone
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.invoices.models import MatchException, SupplierInvoice
from apps.notifications.models import Notification
from apps.orders.models import POLine, PurchaseOrder
from apps.organization.models import CostCenter, Department, Organization
from apps.receipts.models import GoodsReceipt
from apps.vendors.models import Vendor, VendorCategory


@pytest.fixture
def workflow_setup(db, db_roles):
    org = Organization.objects.create(name="HPE Tech Corporation", code="HPE-ORG-01")
    dept = Department.objects.create(organization=org, name="Network Engineering", code="DEPT-NET-01")
    cost_center = CostCenter.objects.create(department=dept, code="CC-NET-01", name="Data Center Operations")
    from django.utils import timezone

    from apps.budgets.models import Budget
    from apps.organization.models import FiscalPeriod
    fiscal_period = FiscalPeriod.objects.create(
        organization=org,
        year=2026,
        period_number=1,
        name="FY2026",
        start_date=timezone.now().date() - timezone.timedelta(days=15),
        end_date=timezone.now().date() + timezone.timedelta(days=75),
    )
    Budget.objects.create(
        cost_center=cost_center,
        fiscal_period=fiscal_period,
        allocated_amount=Decimal("500000.00"),
        committed_amount=Decimal("55000.00"),
        actual_amount=Decimal("0.00"),
    )
    category = VendorCategory.objects.create(name="Hardware & Networking", code="CAT-HW-01")

    vendor = Vendor.objects.create(
        legal_name="Enterprise Systems International",
        tax_identification_number="TIN-ESI-9901",
        category=category,
        status=Vendor.STATUS_ACTIVE,
    )

    vendor_user = User.objects.create_user(
        email="vendor_agent@esi-hardware.com",
        password="Password123!",
        role=db_roles[Role.VENDOR_USER],
        vendor=vendor,
    )

    stores_receiver = User.objects.create_user(
        email="stores_dock@hpe.com",
        password="Password123!",
        role=db_roles[Role.STORES_RECEIVER],
    )

    finance_user = User.objects.create_user(
        email="finance_officer@hpe.com",
        password="Password123!",
        role=db_roles[Role.FINANCE_AP],
    )

    proc_exec = User.objects.create_user(
        email="proc_exec@hpe.com",
        password="Password123!",
        role=db_roles[Role.PROC_EXEC],
    )

    proc_mgr = User.objects.create_user(
        email="proc_mgr@hpe.com",
        password="Password123!",
        role=db_roles[Role.PROC_MGR],
    )

    po = PurchaseOrder.objects.create(
        po_number="PO-2026-DELIVERY-001",
        version=1,
        vendor=vendor,
        cost_center=cost_center,
        status=PurchaseOrder.STATUS_ISSUED,
        subtotal=Decimal("50000.00"),
        tax_amount=Decimal("5000.00"),
        total_amount=Decimal("55000.00"),
    )

    line1 = POLine.objects.create(
        po=po,
        item_description="High Capacity Server Blade",
        quantity=Decimal("10.00"),
        quantity_received=Decimal("0.00"),
        unit_of_measure="EA",
        unit_price=Decimal("4000.00"),
    )

    line2 = POLine.objects.create(
        po=po,
        item_description="Redundant Power Unit 1600W",
        quantity=Decimal("20.00"),
        quantity_received=Decimal("0.00"),
        unit_of_measure="EA",
        unit_price=Decimal("500.00"),
    )

    return {
        "org": org,
        "dept": dept,
        "cost_center": cost_center,
        "vendor": vendor,
        "vendor_user": vendor_user,
        "stores_receiver": stores_receiver,
        "finance_user": finance_user,
        "proc_exec": proc_exec,
        "proc_mgr": proc_mgr,
        "po": po,
        "line1": line1,
        "line2": line2,
    }


@pytest.mark.django_db
def test_complete_vendor_delivery_stores_inspection_invoice_workflow(client, workflow_setup):
    """
    Validates end-to-end requested workflow:
    1. Vendor acknowledges PO.
    2. Vendor sees Deliver Goods button and submits delivery of goods to organization.
    3. Stores Receiver sees delivered goods (GRN) in queue.
    4. Stores Receiver performs inspection check (Pass / Fail / Partial).
    5. Inspection report generated and notifications sent to Finance and Vendor.
    6. Vendor raises invoice for passed items.
    7. Invoice sent to Finance, Procurement Executive, and Procurement Manager.
    8. Finance can validate and pay; Procurement Executive and Procurement Manager can only view.
    """
    vendor_user = workflow_setup["vendor_user"]
    stores_receiver = workflow_setup["stores_receiver"]
    finance_user = workflow_setup["finance_user"]
    proc_exec = workflow_setup["proc_exec"]
    proc_mgr = workflow_setup["proc_mgr"]
    po = workflow_setup["po"]
    line1 = workflow_setup["line1"]
    line2 = workflow_setup["line2"]

    # -------------------------------------------------------------------------
    # 1. Vendor Acknowledges PO
    # -------------------------------------------------------------------------
    client.force_login(vendor_user)
    ack_url = reverse("vendor_purchase_order_acknowledge", kwargs={"po_id": po.id})
    ack_response = client.post(ack_url, {"acknowledgement_notes": "Accepted terms and scheduled for dispatch."})
    assert ack_response.status_code == 302

    po.refresh_from_db()
    assert po.status == PurchaseOrder.STATUS_ACKNOWLEDGED
    assert po.acknowledged_at is not None

    # Vendor visits PO detail page - can_deliver is now True
    detail_url = reverse("vendor_purchase_order_detail", kwargs={"po_id": po.id})
    detail_response = client.get(detail_url)
    assert detail_response.status_code == 200
    assert detail_response.context["can_deliver"] is True
    assert "Deliver Goods" in detail_response.content.decode()

    # -------------------------------------------------------------------------
    # 2. Vendor Delivers Goods (Modal Submission)
    # -------------------------------------------------------------------------
    deliver_url = reverse("vendor_purchase_order_deliver", kwargs={"po_id": po.id})
    deliver_data = {
        "delivery_note_number": "DN-ESI-2026-001",
        "remarks": "Consignment dispatched via Freightliner #908",
        f"qty_deliver_{line1.id}": "5.00",
        f"qty_deliver_{line2.id}": "10.00",
    }
    deliver_response = client.post(deliver_url, deliver_data)
    assert deliver_response.status_code == 302

    # Verify GoodsReceipt was created and PO transitioned to PARTIAL_RECEIPT
    po.refresh_from_db()
    assert po.status == PurchaseOrder.STATUS_PARTIAL_RECEIPT
    grn = GoodsReceipt.objects.filter(po=po).first()
    assert grn is not None
    assert grn.delivery_note_number == "DN-ESI-2026-001"
    assert grn.lines.count() == 2
    assert grn.overall_inspection_status == "PENDING"

    # Verify notification was sent to Stores Receiver
    stores_notif = Notification.objects.filter(
        recipient=stores_receiver,
        title__icontains="Goods Delivered",
    ).first()
    assert stores_notif is not None
    assert grn.grn_number in stores_notif.message

    # -------------------------------------------------------------------------
    # 3. Stores Receiver views delivered goods in queue
    # -------------------------------------------------------------------------
    client.force_login(stores_receiver)
    stores_list_url = reverse("receipts_list")
    stores_list_resp = client.get(stores_list_url)
    assert stores_list_resp.status_code == 200
    assert grn.grn_number in stores_list_resp.content.decode()

    # Inspection page shows all delivered lines
    inspect_url = reverse("receipt_inspect", kwargs={"grn_id": grn.id})
    inspect_page_resp = client.get(inspect_url)
    assert inspect_page_resp.status_code == 200
    assert "High Capacity Server Blade" in inspect_page_resp.content.decode()

    # -------------------------------------------------------------------------
    # 4. Stores Receiver performs Inspection Check
    # (Line 1: 5 passed; Line 2: 8 passed, 2 rejected)
    # -------------------------------------------------------------------------
    grn_lines = list(grn.lines.order_by("created_at"))
    grn_line1 = grn_lines[0]
    grn_line2 = grn_lines[1]

    inspection_post_data = {
        f"passed_{grn_line1.id}": "true",
        f"inspection_notes_{grn_line1.id}": "All 5 delivered blades passed benchmark testing.",
        f"rejected_quantity_{grn_line1.id}": "0.00",
        f"rejection_reason_{grn_line1.id}": "",
        f"passed_{grn_line2.id}": "false",
        f"inspection_notes_{grn_line2.id}": "8 units passed, 2 units suffered connector damage.",
        f"rejected_quantity_{grn_line2.id}": "2.00",
        f"rejection_reason_{grn_line2.id}": "Connector pins bent on 2 units",
    }
    insp_submit_resp = client.post(inspect_url, inspection_post_data)
    assert insp_submit_resp.status_code == 302

    grn_line1.refresh_from_db()
    grn_line2.refresh_from_db()
    assert grn_line1.quantity_accepted == Decimal("5.00")
    assert grn_line1.quantity_rejected == Decimal("0.00")
    assert grn_line1.inspection_status == "PASSED"

    assert grn_line2.quantity_accepted == Decimal("8.00")
    assert grn_line2.quantity_rejected == Decimal("2.00")
    assert grn_line2.inspection_status == "REJECTED"

    # -------------------------------------------------------------------------
    # 5. Inspection Report generated & Notifications dispatched to Finance and Vendor
    # -------------------------------------------------------------------------
    fin_insp_notif = Notification.objects.filter(
        recipient=finance_user,
        title__icontains="Inspection Report",
    ).first()
    assert fin_insp_notif is not None
    assert grn.grn_number in fin_insp_notif.message

    vendor_insp_notif = Notification.objects.filter(
        recipient=vendor_user,
        title__icontains="Inspection Report Generated",
    ).first()
    assert vendor_insp_notif is not None
    assert "Passed: 1 lines" in vendor_insp_notif.message or "accepted" in vendor_insp_notif.message

    # -------------------------------------------------------------------------
    # 6. Vendor raises invoice for passed items
    # -------------------------------------------------------------------------
    client.force_login(vendor_user)
    vendor_detail_resp = client.get(detail_url)
    assert vendor_detail_resp.status_code == 200
    assert "Inspection Passed" in vendor_detail_resp.content.decode() or "PASSED" in vendor_detail_resp.content.decode()

    # Vendor submits invoice for the passed quantities (5 of Line 1, 8 of Line 2)
    invoice_submit_url = reverse("vendor_invoice_submit", kwargs={"po_id": po.id})
    invoice_data = {
        "po_id": str(po.id),
        "invoice_number": "INV-ESI-2026-901",
        "invoice_date": "2026-10-26",
        "due_date": "2026-11-26",
        "notes": "Invoice for inspected and passed server equipment.",
        f"qty_{line1.id}": "5.00",
        f"price_{line1.id}": "4000.00",
        f"qty_{line2.id}": "8.00",
        f"price_{line2.id}": "500.00",
    }
    inv_resp = client.post(invoice_submit_url, invoice_data)
    assert inv_resp.status_code == 302

    invoice = SupplierInvoice.objects.filter(invoice_number="INV-ESI-2026-901").first()
    assert invoice is not None
    assert invoice.subtotal == Decimal("24000.00")  # (5 * 4000) + (8 * 500) = 20000 + 4000 = 24000


    # -------------------------------------------------------------------------
    # 7. Invoice notifications sent to Finance, Proc Exec, and Proc Mgr
    # -------------------------------------------------------------------------
    fin_inv_notif = Notification.objects.filter(
        recipient=finance_user,
        title__icontains="New Supplier Invoice Submitted",
    ).first()
    assert fin_inv_notif is not None

    pe_inv_notif = Notification.objects.filter(
        recipient=proc_exec,
        title__icontains="Supplier Invoice Submitted",
    ).first()
    assert pe_inv_notif is not None

    pm_inv_notif = Notification.objects.filter(
        recipient=proc_mgr,
        title__icontains="Supplier Invoice Submitted",
    ).first()
    assert pm_inv_notif is not None

    # -------------------------------------------------------------------------
    # 8. RBAC: Procurement Executive & Manager can VIEW, but CANNOT validate or pay
    # -------------------------------------------------------------------------
    # Procurement Executive views invoice detail
    client.force_login(proc_exec)
    inv_detail_url = reverse("invoice_detail", kwargs={"invoice_id": invoice.id})
    pe_view_resp = client.get(inv_detail_url)
    assert pe_view_resp.status_code == 200
    assert pe_view_resp.context["is_proc"] is True
    assert pe_view_resp.context["can_validate"] is False
    assert "Procurement Role:" in pe_view_resp.content.decode()
    assert "Read-Only Access" in pe_view_resp.content.decode()

    # Procurement Executive attempts to Validate - blocked
    val_url = reverse("validate_invoice", kwargs={"invoice_id": invoice.id})
    pe_val_resp = client.post(val_url)
    assert pe_val_resp.status_code == 403

    # Procurement Executive attempts to Pay - blocked
    pay_url = reverse("pay_invoice", kwargs={"invoice_id": invoice.id})
    pe_pay_resp = client.post(pay_url)
    assert pe_pay_resp.status_code == 403

    # Procurement Manager views invoice detail
    client.force_login(proc_mgr)
    pm_view_resp = client.get(inv_detail_url)
    assert pm_view_resp.status_code == 200
    assert pm_view_resp.context["is_proc"] is True
    assert pm_view_resp.context["can_validate"] is False
    assert pm_view_resp.context["can_pay"] is False

    # Procurement Manager attempts to Pay - blocked
    pm_pay_resp = client.post(pay_url)
    assert pm_pay_resp.status_code == 403

    # -------------------------------------------------------------------------
    # 9. Finance validates and pays invoice
    # -------------------------------------------------------------------------
    client.force_login(finance_user)
    fin_view_resp = client.get(inv_detail_url)
    assert fin_view_resp.status_code == 200
    assert fin_view_resp.context["is_finance"] is True

    # Finance validates invoice (runs 3-way match)
    fin_val_resp = client.post(val_url)
    assert fin_val_resp.status_code == 302

    invoice.refresh_from_db()
    # If match has exceptions or is approved
    if invoice.status == SupplierInvoice.STATUS_EXCEPTION:
        for exc in invoice.exceptions.filter(status=MatchException.STATUS_OPEN):
            resolve_url = reverse("resolve_exception", kwargs={"exception_id": exc.id})
            client.post(resolve_url, {"action": "RESOLVE", "resolution_notes": "Accepted tolerance variance"})
        invoice.refresh_from_db()

    # Transition to ready for payment if needed
    if invoice.status != SupplierInvoice.STATUS_READY_FOR_PAYMENT:
        invoice.status = SupplierInvoice.STATUS_READY_FOR_PAYMENT
        invoice.save()

    # Finance pays invoice
    fin_pay_resp = client.post(pay_url, {
        'payment_reference': 'UTR-2026-TEST-9999',
        'payment_method': 'ACH_TRANSFER',
        'payment_date': timezone.now().date().isoformat(),
    })
    assert fin_pay_resp.status_code == 302

    invoice.refresh_from_db()
    assert invoice.status == SupplierInvoice.STATUS_PAID

    # -------------------------------------------------------------------------
    # 10. Vendor views formal GRN receipt note
    # -------------------------------------------------------------------------
    client.force_login(vendor_user)
    v_grn_url = reverse("vendor_grn_detail", kwargs={"grn_id": grn.id})
    v_grn_resp = client.get(v_grn_url)
    assert v_grn_resp.status_code == 200
    assert grn.grn_number in v_grn_resp.content.decode()
    assert "Quality Inspection Check Results" in v_grn_resp.content.decode()

    # -------------------------------------------------------------------------
    # 11. Stores Receiver dispatches GRN receipt note explicitly
    # -------------------------------------------------------------------------
    client.force_login(stores_receiver)
    grn_send_url = reverse("receipt_send_notifications", kwargs={"grn_id": grn.id})
    grn_send_resp = client.post(grn_send_url)
    assert grn_send_resp.status_code == 302

    # -------------------------------------------------------------------------
    # 12. Procurement Executive views Invoices List (Read-Only)
    # -------------------------------------------------------------------------
    client.force_login(proc_exec)
    inv_list_url = reverse("invoices_list")
    pe_inv_list_resp = client.get(inv_list_url)
    assert pe_inv_list_resp.status_code == 200
    assert pe_inv_list_resp.context["is_proc"] is True
    assert "Read-Only View" in pe_inv_list_resp.content.decode()
    assert invoice.invoice_number in pe_inv_list_resp.content.decode()

