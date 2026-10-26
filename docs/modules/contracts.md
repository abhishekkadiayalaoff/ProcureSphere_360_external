# Module: Contracts

## Overview
Detailed documentation for the `contracts` module in ProcureSphere 360.

## Database Models
### Contract
Contract(id, created_at, updated_at, created_by, contract_number, title, version, vendor, sourcing_event, po, status, contract_value, start_date, end_date, renewal_notice_days, contract_owner)

| Field | Type | Attributes |
|-------|------|------------|
| `versions` | `ForeignKey` | null, to: ContractVersion |
| `milestones` | `ForeignKey` | null, to: ContractMilestone |
| `alerts` | `ForeignKey` | null, to: ContractAlert |
| `obligations` | `ForeignKey` | null, to: ContractObligation |
| `documents` | `ForeignKey` | null, to: ContractDocument |
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `contract_number` | `CharField` | unique |
| `title` | `CharField` | - |
| `version` | `PositiveIntegerField` | - |
| `vendor` | `ForeignKey` | to: Vendor |
| `sourcing_event` | `ForeignKey` | null, blank, to: SourcingEvent |
| `po` | `ForeignKey` | null, blank, to: PurchaseOrder |
| `status` | `CharField` | - |
| `contract_value` | `DecimalField` | - |
| `start_date` | `DateField` | - |
| `end_date` | `DateField` | - |
| `renewal_notice_days` | `PositiveIntegerField` | - |
| `contract_owner` | `ForeignKey` | to: User |

### ContractVersion
ContractVersion(id, created_at, updated_at, created_by, contract, version_number, amendment_summary, contract_value, start_date, end_date, approved_by)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `contract` | `ForeignKey` | to: Contract |
| `version_number` | `PositiveIntegerField` | - |
| `amendment_summary` | `TextField` | - |
| `contract_value` | `DecimalField` | - |
| `start_date` | `DateField` | - |
| `end_date` | `DateField` | - |
| `approved_by` | `ForeignKey` | to: User |

### ContractMilestone
ContractMilestone(id, created_at, updated_at, created_by, contract, title, due_date, amount, is_completed, completed_at)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `contract` | `ForeignKey` | to: Contract |
| `title` | `CharField` | - |
| `due_date` | `DateField` | - |
| `amount` | `DecimalField` | - |
| `is_completed` | `BooleanField` | - |
| `completed_at` | `DateTimeField` | null, blank |

### ContractAlert
ContractAlert(id, created_at, updated_at, created_by, contract, alert_type, message, triggered_at, is_processed)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `contract` | `ForeignKey` | to: Contract |
| `alert_type` | `CharField` | - |
| `message` | `TextField` | - |
| `triggered_at` | `DateTimeField` | blank |
| `is_processed` | `BooleanField` | - |

### ContractObligation
ContractObligation(id, created_at, updated_at, created_by, contract, title, responsible_party, due_date, is_fulfilled, fulfilled_at)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `contract` | `ForeignKey` | to: Contract |
| `title` | `CharField` | - |
| `responsible_party` | `CharField` | - |
| `due_date` | `DateField` | - |
| `is_fulfilled` | `BooleanField` | - |
| `fulfilled_at` | `DateTimeField` | null, blank |

### ContractDocument
ContractDocument(id, created_at, updated_at, created_by, contract, title, file, uploaded_by)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `contract` | `ForeignKey` | to: Contract |
| `title` | `CharField` | - |
| `file` | `FileField` | - |
| `uploaded_by` | `ForeignKey` | to: User |

## Business Logic & Services
### `activate_contract_service(*, contract: apps.contracts.models.Contract, user: apps.accounts.models.User) -> apps.contracts.models.Contract`
```text
Activates contract state from DRAFT / LEGAL_REVIEW to ACTIVE directly.
```

### `add_contract_milestone_service(*, contract: apps.contracts.models.Contract, title: str, due_date, amount: decimal.Decimal = Decimal('0.00')) -> apps.contracts.models.ContractMilestone`
```text
Adds a tracked milestone to a contract.
```

### `add_contract_obligation_service(*, contract: apps.contracts.models.Contract, title: str, responsible_party: str, due_date) -> apps.contracts.models.ContractObligation`
```text
Adds a legal obligation to a contract.
```

### `approve_business_service(*, contract: apps.contracts.models.Contract, user: apps.accounts.models.User, notes: str = '') -> apps.contracts.models.Contract`
```text
Business owner approves contract, moving status from BUSINESS_APPROVAL to ACTIVE.
```

### `approve_legal_review_service(*, contract: apps.contracts.models.Contract, user: apps.accounts.models.User, notes: str = '') -> apps.contracts.models.Contract`
```text
Approves legal review, moving contract to BUSINESS_APPROVAL state.
```

### `complete_contract_milestone_service(*, milestone: apps.contracts.models.ContractMilestone, user: apps.accounts.models.User) -> apps.contracts.models.ContractMilestone`
```text
Marks a milestone as completed.
```

### `create_contract_service(*, title: str, vendor: apps.vendors.models.Vendor, contract_value: decimal.Decimal, start_date, end_date, contract_owner: apps.accounts.models.User, renewal_notice_days: int = 30, sourcing_event=None, po=None) -> apps.contracts.models.Contract`
```text
Creates a new Contract in DRAFT status.
```

### `create_contract_version_service(*, contract: apps.contracts.models.Contract, user: apps.accounts.models.User, amendment_summary: str, contract_value: decimal.Decimal, start_date, end_date) -> apps.contracts.models.ContractVersion`
```text
Amends contract by incrementing version number, preserving prior version values,
and updating active contract values.
```

### `fulfill_contract_obligation_service(*, obligation: apps.contracts.models.ContractObligation, user: apps.accounts.models.User) -> apps.contracts.models.ContractObligation`
```text
Marks an obligation as fulfilled.
```

### `reject_legal_review_service(*, contract: apps.contracts.models.Contract, user: apps.accounts.models.User, reason: str) -> apps.contracts.models.Contract`
```text
Rejects legal review, returning contract to DRAFT state for corrections.
```

### `renew_contract_service(*, contract: apps.contracts.models.Contract, user: apps.accounts.models.User, new_end_date, new_value: decimal.Decimal = None, notes: str = '') -> apps.contracts.models.Contract`
```text
Renews an active or renewal-due contract, creating a new version.
```

### `scan_contract_expirations_and_milestones_service() -> int`
```text
Scans active contracts for upcoming expirations & milestones.
Executes scheduled Celery Beat task logic and logs alerts.
Returns count of generated alerts.
```

### `submit_for_legal_review_service(*, contract: apps.contracts.models.Contract, user: apps.accounts.models.User, notes: str = '') -> apps.contracts.models.Contract`
```text
Submits contract from DRAFT to LEGAL_REVIEW state.
```

### `terminate_contract_service(*, contract: apps.contracts.models.Contract, user: apps.accounts.models.User, reason: str) -> apps.contracts.models.Contract`
```text
Terminates a contract.
```

### `upload_contract_document_service(*, contract: apps.contracts.models.Contract, user: apps.accounts.models.User, title: str, file) -> apps.contracts.models.ContractDocument`
```text
Uploads a signed contract document or appendix.
```
