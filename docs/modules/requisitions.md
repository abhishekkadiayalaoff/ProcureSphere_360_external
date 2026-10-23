# Module: Requisitions

## Overview
Detailed documentation for the `requisitions` module in ProcureSphere 360.

## Database Models
### PurchaseRequisition
PurchaseRequisition(id, created_at, updated_at, created_by, pr_number, title, justification, requester, department, cost_center, status, total_amount, requested_delivery_date)

| Field | Type | Attributes |
|-------|------|------------|
| `lines` | `ForeignKey` | null, to: PRLine |
| `attachments` | `ForeignKey` | null, to: PRAttachment |
| `sourcing_events` | `ForeignKey` | null, to: SourcingEvent |
| `purchase_orders` | `ForeignKey` | null, to: PurchaseOrder |
| `budget_reservations` | `ForeignKey` | null, to: BudgetReservation |
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `pr_number` | `CharField` | unique |
| `title` | `CharField` | - |
| `justification` | `TextField` | - |
| `requester` | `ForeignKey` | to: User |
| `department` | `ForeignKey` | to: Department |
| `cost_center` | `ForeignKey` | to: CostCenter |
| `status` | `CharField` | - |
| `total_amount` | `DecimalField` | - |
| `requested_delivery_date` | `DateField` | - |

### PRLine
PRLine(id, created_at, updated_at, created_by, requisition, item_description, quantity, unit_of_measure, estimated_unit_price, estimated_total, specifications)

| Field | Type | Attributes |
|-------|------|------------|
| `bidline` | `ForeignKey` | null, to: BidLine |
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `requisition` | `ForeignKey` | to: PurchaseRequisition |
| `item_description` | `CharField` | - |
| `quantity` | `DecimalField` | - |
| `unit_of_measure` | `CharField` | - |
| `estimated_unit_price` | `DecimalField` | - |
| `estimated_total` | `DecimalField` | - |
| `specifications` | `TextField` | blank |

### PRAttachment
PRAttachment(id, created_at, updated_at, created_by, requisition, uploaded_by, title, file, file_size)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `requisition` | `ForeignKey` | to: PurchaseRequisition |
| `uploaded_by` | `ForeignKey` | null, blank, to: User |
| `title` | `CharField` | - |
| `file` | `FileField` | - |
| `file_size` | `PositiveIntegerField` | - |

## Business Logic & Services
### `approve_purchase_requisition_service(*, requisition: apps.requisitions.models.PurchaseRequisition, approver: apps.accounts.models.User, comments: str = '') -> apps.requisitions.models.PurchaseRequisition`
```text
Approves a PR and transitions state to APPROVED.
```

### `create_purchase_requisition_service(*, title: str, justification: str, requester: apps.accounts.models.User, department: apps.organization.models.Department, cost_center: apps.organization.models.CostCenter, requested_delivery_date, line_items: list, attachments: list = None) -> apps.requisitions.models.PurchaseRequisition`
```text
Creates a new PurchaseRequisition in DRAFT status with atomic document number generation.
```

### `reject_purchase_requisition_service(*, requisition: apps.requisitions.models.PurchaseRequisition, approver: apps.accounts.models.User, comments: str) -> apps.requisitions.models.PurchaseRequisition`
```text
Rejects a PR and transitions state to REJECTED.
```

### `submit_purchase_requisition_service(*, requisition: apps.requisitions.models.PurchaseRequisition, user: apps.accounts.models.User) -> apps.requisitions.models.PurchaseRequisition`
```text
Submits a PR for approval:
1. Evaluates server-side approval chain.
2. Runs pre-approval budget check & locks reservation.
3. Transitions PR status to SUBMITTED / MANAGER_REVIEW.
```
