# Module: Organization

## Overview
Detailed documentation for the `organization` module in ProcureSphere 360.

## Database Models
### Organization
Organization(id, created_at, updated_at, created_by, name, code, tax_identifier, address, is_active)

| Field | Type | Attributes |
|-------|------|------------|
| `departments` | `ForeignKey` | null, to: Department |
| `fiscal_periods` | `ForeignKey` | null, to: FiscalPeriod |
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `name` | `CharField` | - |
| `code` | `CharField` | unique |
| `tax_identifier` | `CharField` | blank |
| `address` | `TextField` | blank |
| `is_active` | `BooleanField` | - |

### Department
Department(id, created_at, updated_at, created_by, organization, name, code, description)

| Field | Type | Attributes |
|-------|------|------------|
| `users` | `ForeignKey` | null, to: User |
| `cost_centers` | `ForeignKey` | null, to: CostCenter |
| `approval_policies` | `ForeignKey` | null, to: ApprovalPolicy |
| `requisitions` | `ForeignKey` | null, to: PurchaseRequisition |
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `organization` | `ForeignKey` | to: Organization |
| `name` | `CharField` | - |
| `code` | `CharField` | unique |
| `description` | `TextField` | blank |

### CostCenter
CostCenter(id, created_at, updated_at, created_by, department, code, name, manager)

| Field | Type | Attributes |
|-------|------|------------|
| `requisitions` | `ForeignKey` | null, to: PurchaseRequisition |
| `purchase_orders` | `ForeignKey` | null, to: PurchaseOrder |
| `budgets` | `ForeignKey` | null, to: Budget |
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `department` | `ForeignKey` | to: Department |
| `code` | `CharField` | unique |
| `name` | `CharField` | - |
| `manager` | `ForeignKey` | null, blank, to: User |

### FiscalPeriod
FiscalPeriod(id, created_at, updated_at, created_by, organization, year, period_number, name, start_date, end_date, is_closed)

| Field | Type | Attributes |
|-------|------|------------|
| `budgets` | `ForeignKey` | null, to: Budget |
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `organization` | `ForeignKey` | to: Organization |
| `year` | `PositiveIntegerField` | - |
| `period_number` | `PositiveIntegerField` | - |
| `name` | `CharField` | - |
| `start_date` | `DateField` | - |
| `end_date` | `DateField` | - |
| `is_closed` | `BooleanField` | - |

## Business Logic & Services
### `create_cost_center_service(*, department: apps.organization.models.Department, code: str, name: str, manager=None) -> apps.organization.models.CostCenter`
```text
Service layer function to create a Cost Center linked to a Department.
```

### `create_department_service(*, organization: apps.organization.models.Organization, name: str, code: str, description: str = '') -> apps.organization.models.Department`
```text
Service layer function to create a Department inside an Organization.
```

### `create_fiscal_period_service(*, organization: apps.organization.models.Organization, year: int, period_number: int, name: str, start_date, end_date) -> apps.organization.models.FiscalPeriod`
```text
Service layer function to define a Fiscal Period.
```

### `create_organization_service(*, name: str, code: str, tax_identifier: str = '', address: str = '') -> apps.organization.models.Organization`
```text
Service layer function to create an Organization entity inside a database transaction.
```
