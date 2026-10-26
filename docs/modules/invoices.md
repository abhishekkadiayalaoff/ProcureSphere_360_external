# Module: Invoices

## Overview
Detailed documentation for the `invoices` module in ProcureSphere 360.

## Database Models
### SupplierInvoice
SupplierInvoice(id, created_at, updated_at, created_by, invoice_number, vendor, po, invoice_date, due_date, status, subtotal, tax_amount, total_amount, notes)

| Field | Type | Attributes |
|-------|------|------------|
| `lines` | `ForeignKey` | null, to: InvoiceLine |
| `exceptions` | `ForeignKey` | null, to: MatchException |
| `match_results` | `ForeignKey` | null, to: MatchResult |
| `payment_record` | `OneToOneField` | null, to: PaymentStatus |
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `invoice_number` | `CharField` | - |
| `vendor` | `ForeignKey` | to: Vendor |
| `po` | `ForeignKey` | to: PurchaseOrder |
| `invoice_date` | `DateField` | - |
| `due_date` | `DateField` | - |
| `status` | `CharField` | - |
| `subtotal` | `DecimalField` | - |
| `tax_amount` | `DecimalField` | - |
| `total_amount` | `DecimalField` | - |
| `notes` | `TextField` | blank |

### InvoiceLine
InvoiceLine(id, created_at, updated_at, created_by, invoice, po_line, item_description, quantity, unit_price, line_total)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `invoice` | `ForeignKey` | to: SupplierInvoice |
| `po_line` | `ForeignKey` | null, blank, to: POLine |
| `item_description` | `CharField` | - |
| `quantity` | `DecimalField` | - |
| `unit_price` | `DecimalField` | - |
| `line_total` | `DecimalField` | - |

### MatchException
MatchException(id, created_at, updated_at, created_by, invoice, exception_type, status, description, variance_amount, resolution_notes, resolved_by)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `invoice` | `ForeignKey` | to: SupplierInvoice |
| `exception_type` | `CharField` | - |
| `status` | `CharField` | - |
| `description` | `TextField` | - |
| `variance_amount` | `DecimalField` | - |
| `resolution_notes` | `TextField` | blank |
| `resolved_by` | `ForeignKey` | null, blank, to: User |

### MatchResult
MatchResult(id, created_at, updated_at, created_by, invoice, is_matched, price_variance_percentage, quantity_variance, tolerance_applied_percentage, performed_by)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `invoice` | `ForeignKey` | to: SupplierInvoice |
| `is_matched` | `BooleanField` | - |
| `price_variance_percentage` | `DecimalField` | - |
| `quantity_variance` | `DecimalField` | - |
| `tolerance_applied_percentage` | `DecimalField` | - |
| `performed_by` | `ForeignKey` | to: User |

### PaymentStatus
PaymentStatus(id, created_at, updated_at, created_by, invoice, payment_reference, payment_date, amount_paid, payment_method, paid_by)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `invoice` | `OneToOneField` | unique, to: SupplierInvoice |
| `payment_reference` | `CharField` | unique |
| `payment_date` | `DateField` | - |
| `amount_paid` | `DecimalField` | - |
| `payment_method` | `CharField` | - |
| `paid_by` | `ForeignKey` | to: User |

## Business Logic & Services
### `create_supplier_invoice_service(*, vendor, po: apps.orders.models.PurchaseOrder, invoice_number: str, invoice_date, due_date, line_items: list, notes: str = '', created_by_user=None, tax_rate: decimal.Decimal = Decimal('0.10')) -> apps.invoices.models.SupplierInvoice`
```text
Creates a new Supplier Invoice in RECEIVED status with line items.
Enforces unique invoice_number per vendor (duplicate detection).
```

### `mark_invoice_paid_service(*, invoice: apps.invoices.models.SupplierInvoice, user) -> apps.invoices.models.SupplierInvoice`
```text
Marks invoice as PAID and transitions SpendLedger from COMMITMENT to ACTUAL.
```

### `resolve_match_exception_service(*, match_exception: apps.invoices.models.MatchException, resolved_by_user, resolution_notes: str, action: str = 'RESOLVE') -> apps.invoices.models.MatchException`
```text
Finance exception resolution workflow for 3-way match variances.
```

### `run_3_way_match_service(*, invoice: apps.invoices.models.SupplierInvoice, price_tolerance_pct: decimal.Decimal = Decimal('0.05'), qty_tolerance_pct: decimal.Decimal = Decimal('0.05'), user=None) -> tuple[apps.invoices.models.SupplierInvoice, list[apps.invoices.models.MatchException]]`
```text
Executes automated 3-way match: PO line vs Goods Receipt line vs Supplier Invoice line.
Generates explicit MatchException records if variance exceeds tolerance thresholds.
```
