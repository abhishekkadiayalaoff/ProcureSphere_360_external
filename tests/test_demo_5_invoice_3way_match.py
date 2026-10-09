from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.budgets.models import SpendLedger
from apps.budgets.services import allocate_budget_service, check_and_reserve_budget_service
from apps.invoices.models import MatchException, SupplierInvoice
from apps.invoices.services import (
    create_supplier_invoice_service,
    mark_invoice_paid_service,
    resolve_match_exception_service,
    run_3_way_match_service,
)
from apps.orders.services import acknowledge_purchase_order_service, generate_purchase_order_service
from apps.organization.models import CostCenter, Department, FiscalPeriod, Organization
from apps.receipts.services import create_goods_receipt_service
from apps.requisitions.services import create_purchase_requisition_service
from apps.vendors.models import VendorCategory
from apps.vendors.services import register_vendor_service


@pytest.mark.django_db
def test_demo_5_invoice_3way_match_and_exception_resolution():
    """
    Day-90 Acceptance Demonstration #5:
    Submit an invoice -> 3-way match -> trigger tolerance exception -> resolve -> payment-ready -> paid.
    """
    # 1. Setup Users, Org, Department, Cost Center, Fiscal Period, Budget
    org = Organization.objects.create(name="HPE Tech Corp", code="HPE-ORG")
    dept = Department.objects.create(organization=org, name="Operations", code="OPS")
    cost_center = CostCenter.objects.create(department=dept, code="CC-OPS-01", name="Ops Tech")
    fiscal_period = FiscalPeriod.objects.create(
        organization=org,
        year=2026,
        period_number=1,
        name="FY2026-Q1",
        start_date=timezone.now().date() - timezone.timedelta(days=10),
        end_date=timezone.now().date() + timezone.timedelta(days=90),
    )
    budget = allocate_budget_service(
        cost_center=cost_center,
        fiscal_period=fiscal_period,
        allocated_amount=Decimal("50000.00"),
    )

    req_role, _ = Role.objects.get_or_create(code=Role.REQUESTER, defaults={"name": "Requester"})
    fin_role, _ = Role.objects.get_or_create(code=Role.FINANCE_AP, defaults={"name": "Finance"})
    stores_role, _ = Role.objects.get_or_create(
        code=Role.STORES_RECEIVER, defaults={"name": "Stores"}
    )

    requester = User.objects.create_user(
        email="requester.d5@hpe.com", password="password123", role=req_role
    )
    finance_user = User.objects.create_user(
        email="finance.d5@hpe.com", password="password123", role=fin_role
    )
    receiver_user = User.objects.create_user(
        email="receiver.d5@hpe.com", password="password123", role=stores_role
    )

    # 2. Register Vendor & Issue PO
    category = VendorCategory.objects.create(name="Hardware D5", code="CAT-HW-D5")
    vendor = register_vendor_service(
        legal_name="Apex Hardware Supplies",
        tax_identification_number="TAX-APEX-99",
        category=category,
        email="billing@apex.com",
        address="100 Apex St",
    )

    pr = create_purchase_requisition_service(
        title="Server Racks Purchase",
        justification="Server hardware expansion for ops datacenter.",
        requester=requester,
        department=dept,
        cost_center=cost_center,
        requested_delivery_date=timezone.now().date() + timezone.timedelta(days=30),
        line_items=[
            {
                "item_description": "Standard Server Rack",
                "quantity": 10,
                "estimated_unit_price": 100.00,
            }
        ],
    )
    check_and_reserve_budget_service(requisition=pr, requested_by_user=requester)

    po = generate_purchase_order_service(
        vendor=vendor,
        cost_center=cost_center,
        requisition=pr,
        line_items=[
            {"item_description": "Standard Server Rack", "quantity": 10, "unit_price": 100.00}
        ],
        created_by_user=requester,
    )
    acknowledge_purchase_order_service(po=po, vendor_user=requester)
    po_line = po.lines.first()

    # 3. Record Goods Receipt (10 units accepted)
    grn = create_goods_receipt_service(
        po=po,
        received_by=receiver_user,
        receipt_items=[{"po_line": po_line, "quantity_received": 10, "quantity_accepted": 10}],
    )
    assert grn.lines.first().quantity_accepted == Decimal("10.00")

    # 4. Supplier submits invoice with price variance ($120 vs PO price $100 -> +20% > 5% tolerance)
    invoice = create_supplier_invoice_service(
        vendor=vendor,
        po=po,
        invoice_number="INV-APEX-2026-001",
        invoice_date=timezone.now().date(),
        due_date=timezone.now().date() + timezone.timedelta(days=30),
        line_items=[
            {
                "po_line": po_line,
                "item_description": "Standard Server Rack",
                "quantity": 10,
                "unit_price": 120.00,
            }
        ],
        created_by_user=requester,
    )

    # 5. Run Automated 3-Way Match Engine
    invoice, exceptions = run_3_way_match_service(invoice=invoice, user=finance_user)

    assert invoice.status == SupplierInvoice.STATUS_EXCEPTION
    assert len(exceptions) == 1
    exc = exceptions[0]
    assert exc.exception_type == MatchException.TYPE_PRICE_VARIANCE
    assert exc.status == MatchException.STATUS_OPEN

    # 6. Finance approves resolution note for price variance exception
    resolved_exc = resolve_match_exception_service(
        match_exception=exc,
        resolved_by_user=finance_user,
        resolution_notes="Approved 20% price increase due to emergency freight fee.",
        action="RESOLVE",
    )

    assert resolved_exc.status == MatchException.STATUS_RESOLVED
    invoice.refresh_from_db()
    assert invoice.status == SupplierInvoice.STATUS_READY_FOR_PAYMENT

    # 7. Execute payment and verify Spend Ledger actual spend transition
    paid_invoice = mark_invoice_paid_service(invoice=invoice, user=finance_user)
    assert paid_invoice.status == SupplierInvoice.STATUS_PAID

    budget.refresh_from_db()
    actual_ledger = SpendLedger.objects.filter(
        budget=budget, entry_type=SpendLedger.ENTRY_ACTUAL
    ).first()
    assert actual_ledger is not None
    assert actual_ledger.amount == paid_invoice.total_amount
