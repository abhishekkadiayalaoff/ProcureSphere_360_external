# Module: Receipts

## Overview
Detailed documentation for the `receipts` module in ProcureSphere 360.

## Database Models
### GoodsReceipt
GoodsReceipt(id, created_at, updated_at, created_by, grn_number, po, received_by, received_date, delivery_note_number, remarks)

| Field | Type | Attributes |
|-------|------|------------|
| `lines` | `ForeignKey` | null, to: ReceiptLine |
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `grn_number` | `CharField` | unique |
| `po` | `ForeignKey` | to: PurchaseOrder |
| `received_by` | `ForeignKey` | to: User |
| `received_date` | `DateTimeField` | - |
| `delivery_note_number` | `CharField` | blank |
| `remarks` | `TextField` | blank |

### ReceiptLine
ReceiptLine(id, created_at, updated_at, created_by, receipt, po_line, quantity_received, quantity_accepted, quantity_rejected, notes)

| Field | Type | Attributes |
|-------|------|------------|
| `inspection` | `OneToOneField` | null, to: InspectionRecord |
| `rejections` | `ForeignKey` | null, to: RejectionRecord |
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `receipt` | `ForeignKey` | to: GoodsReceipt |
| `po_line` | `ForeignKey` | to: POLine |
| `quantity_received` | `DecimalField` | - |
| `quantity_accepted` | `DecimalField` | - |
| `quantity_rejected` | `DecimalField` | - |
| `notes` | `CharField` | blank |

### InspectionRecord
InspectionRecord(id, created_at, updated_at, created_by, receipt_line, inspected_by, passed, inspection_notes)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `receipt_line` | `OneToOneField` | unique, to: ReceiptLine |
| `inspected_by` | `ForeignKey` | to: User |
| `passed` | `BooleanField` | - |
| `inspection_notes` | `TextField` | - |

### RejectionRecord
RejectionRecord(id, created_at, updated_at, created_by, receipt_line, rejected_quantity, rejection_reason, returned_to_vendor)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `receipt_line` | `ForeignKey` | to: ReceiptLine |
| `rejected_quantity` | `DecimalField` | - |
| `rejection_reason` | `TextField` | - |
| `returned_to_vendor` | `BooleanField` | - |

## Business Logic & Services
### `create_goods_receipt_service(*, po: apps.orders.models.PurchaseOrder, received_by: apps.accounts.models.User, receipt_items: list, delivery_note_number: str = '', remarks: str = '') -> apps.receipts.models.GoodsReceipt`
```text
Records a Goods Receipt Note (GRN) against a Purchase Order.
Supports partial receipts and multiple GRNs against one PO.
Updates POLine.quantity_received and transitions PO status (PARTIAL_RECEIPT vs COMPLETED).
```

### `record_inspection_service(*, receipt: apps.receipts.models.GoodsReceipt, inspected_by: apps.accounts.models.User, inspection_items: list) -> apps.receipts.models.GoodsReceipt`
```text
Records or updates quality inspection and rejection records for a Goods Receipt Note (GRN).
Enforces server-side quantity validation, ownership verification, and updates PO line quantities.
```
