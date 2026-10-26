# Module: Budgets

## Overview
Detailed documentation for the `budgets` module in ProcureSphere 360.

## Database Models
### Budget
Budget(id, created_at, updated_at, created_by, cost_center, fiscal_period, allocated_amount, reserved_amount, committed_amount, actual_amount, allow_overspend)

| Field | Type | Attributes |
|-------|------|------------|
| `reservations` | `ForeignKey` | null, to: BudgetReservation |
| `ledger_entries` | `ForeignKey` | null, to: SpendLedger |
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `cost_center` | `ForeignKey` | to: CostCenter |
| `fiscal_period` | `ForeignKey` | to: FiscalPeriod |
| `allocated_amount` | `DecimalField` | - |
| `reserved_amount` | `DecimalField` | - |
| `committed_amount` | `DecimalField` | - |
| `actual_amount` | `DecimalField` | - |
| `allow_overspend` | `BooleanField` | - |

### BudgetReservation
BudgetReservation(id, created_at, updated_at, created_by, budget, requisition, amount, status)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `budget` | `ForeignKey` | to: Budget |
| `requisition` | `ForeignKey` | to: PurchaseRequisition |
| `amount` | `DecimalField` | - |
| `status` | `CharField` | - |

### SpendLedger
SpendLedger(id, created_at, updated_at, created_by, budget, entry_type, amount, reference_number, description)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `budget` | `ForeignKey` | to: Budget |
| `entry_type` | `CharField` | - |
| `amount` | `DecimalField` | - |
| `reference_number` | `CharField` | - |
| `description` | `CharField` | - |

## Business Logic & Services
### `allocate_budget_service(*, cost_center: apps.organization.models.CostCenter, fiscal_period: apps.organization.models.FiscalPeriod, allocated_amount: decimal.Decimal, allow_overspend: bool = False) -> apps.budgets.models.Budget`
```text
Allocates budget to a CostCenter for a FiscalPeriod inside an atomic transaction.
```

### `check_and_reserve_budget_service(*, requisition, requested_by_user) -> apps.budgets.models.BudgetReservation`
```text
Checks available budget for a PurchaseRequisition's cost center.
If available, locks a BudgetReservation in RESERVED status and writes a SpendLedger entry.
```

### `convert_commitment_to_actual_service(*, po, invoice, user) -> apps.budgets.models.SpendLedger`
```text
Moves spend from COMMITMENT to ACTUAL when an invoice is approved/paid.
```

### `validate_budget_availability_service(*, cost_center: apps.organization.models.CostCenter, amount: decimal.Decimal, today=None)`
```text
Validates if a cost center has sufficient available budget for an amount.
Raises ValidationError if insufficient budget.
```
