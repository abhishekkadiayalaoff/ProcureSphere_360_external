# Module: Orders

## Overview
Detailed documentation for the `orders` module in ProcureSphere 360.

## Database Models
### PurchaseOrder
PurchaseOrder(id, created_at, updated_at, created_by, po_number, version, vendor, requisition, sourcing_event, cost_center, status, subtotal, tax_amount, total_amount, terms_and_conditions, acknowledged_at, acknowledged_by, acknowledgement_notes)

| Field | Type | Attributes |
|-------|------|------------|
| `lines` | `ForeignKey` | null, to: POLine |
| `amendments` | `ForeignKey` | null, to: POAmendment |
| `delivery_schedules` | `ForeignKey` | null, to: DeliverySchedule |
| `receipts` | `ForeignKey` | null, to: GoodsReceipt |
| `invoices` | `ForeignKey` | null, to: SupplierInvoice |
| `contracts` | `ForeignKey` | null, to: Contract |
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `po_number` | `CharField` | unique |
| `version` | `PositiveIntegerField` | - |
| `vendor` | `ForeignKey` | to: Vendor |
| `requisition` | `ForeignKey` | null, blank, to: PurchaseRequisition |
| `sourcing_event` | `ForeignKey` | null, blank, to: SourcingEvent |
| `cost_center` | `ForeignKey` | to: CostCenter |
| `status` | `CharField` | - |
| `subtotal` | `DecimalField` | - |
| `tax_amount` | `DecimalField` | - |
| `total_amount` | `DecimalField` | - |
| `terms_and_conditions` | `TextField` | blank |
| `acknowledged_at` | `DateTimeField` | null, blank |
| `acknowledged_by` | `ForeignKey` | null, blank, to: User |
| `acknowledgement_notes` | `TextField` | blank |

### POLine
POLine(id, created_at, updated_at, created_by, po, item_description, quantity, quantity_received, unit_of_measure, unit_price, line_total)

| Field | Type | Attributes |
|-------|------|------------|
| `schedules` | `ForeignKey` | null, to: DeliverySchedule |
| `receipt_lines` | `ForeignKey` | null, to: ReceiptLine |
| `invoiceline` | `ForeignKey` | null, to: InvoiceLine |
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `po` | `ForeignKey` | to: PurchaseOrder |
| `item_description` | `CharField` | - |
| `quantity` | `DecimalField` | - |
| `quantity_received` | `DecimalField` | - |
| `unit_of_measure` | `CharField` | - |
| `unit_price` | `DecimalField` | - |
| `line_total` | `DecimalField` | - |

### POAmendment
POAmendment(id, created_at, updated_at, created_by, po, amendment_number, reason, previous_version_snapshot, requested_by)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `po` | `ForeignKey` | to: PurchaseOrder |
| `amendment_number` | `PositiveIntegerField` | - |
| `reason` | `TextField` | - |
| `previous_version_snapshot` | `JSONField` | - |
| `requested_by` | `ForeignKey` | to: User |

### DeliverySchedule
DeliverySchedule(id, created_at, updated_at, created_by, po, po_line, expected_delivery_date, quantity_expected, destination_address, status)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `po` | `ForeignKey` | to: PurchaseOrder |
| `po_line` | `ForeignKey` | to: POLine |
| `expected_delivery_date` | `DateField` | - |
| `quantity_expected` | `DecimalField` | - |
| `destination_address` | `TextField` | blank |
| `status` | `CharField` | - |

## Business Logic & Services
### `acknowledge_purchase_order_service(*, po: apps.orders.models.PurchaseOrder, vendor_user: apps.accounts.models.User, acknowledgement_notes: str = '') -> apps.orders.models.PurchaseOrder`
```text
Vendor acknowledges an issued PO. Transitions status to ACKNOWLEDGED.
```

### `amend_purchase_order_service(*, po: apps.orders.models.PurchaseOrder, reason: str, updated_line_items: list, requested_by_user: apps.accounts.models.User, tax_rate: decimal.Decimal = Decimal('0.10')) -> apps.orders.models.POAmendment`
```text
Creates a PO Change Order / Amendment:
- Captures immutable JSON snapshot of prior PO state.
- Increments PO version counter (e.g. V1 -> V2).
- Preserves prior POLine history in POAmendment record.
```

### `generate_purchase_order_service(*, vendor: apps.vendors.models.Vendor, cost_center: apps.organization.models.CostCenter, line_items: list, created_by_user: apps.accounts.models.User, requisition=None, sourcing_event=None, terms_and_conditions: str = 'Standard HPE Enterprise Procurement Terms & Conditions', tax_rate: decimal.Decimal = Decimal('0.10')) -> apps.orders.models.PurchaseOrder`
```text
Generates a new Purchase Order in ISSUED status from requisition/award.
Moves BudgetReservation to SpendLedger COMMITMENT.
```
