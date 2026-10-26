# Module: Approvals

## Overview
Detailed documentation for the `approvals` module in ProcureSphere 360.

## Database Models
### ApprovalPolicy
ApprovalPolicy(id, created_at, updated_at, created_by, name, module, department, min_amount, max_amount, is_active)

| Field | Type | Attributes |
|-------|------|------------|
| `steps` | `ForeignKey` | null, to: ApprovalStep |
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `name` | `CharField` | - |
| `module` | `CharField` | - |
| `department` | `ForeignKey` | null, blank, to: Department |
| `min_amount` | `DecimalField` | - |
| `max_amount` | `DecimalField` | null, blank |
| `is_active` | `BooleanField` | - |

### ApprovalStep
ApprovalStep(id, created_at, updated_at, created_by, policy, step_number, approver_role, specific_approver, description)

| Field | Type | Attributes |
|-------|------|------------|
| `approvalaction` | `ForeignKey` | null, to: ApprovalAction |
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `policy` | `ForeignKey` | to: ApprovalPolicy |
| `step_number` | `PositiveIntegerField` | - |
| `approver_role` | `ForeignKey` | to: Role |
| `specific_approver` | `ForeignKey` | null, blank, to: User |
| `description` | `CharField` | blank |

### ApprovalAction
ApprovalAction(id, created_at, updated_at, created_by, policy_step, target_object_id, target_model_name, actor, action, comments, previous_state, new_state)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `policy_step` | `ForeignKey` | null, blank, to: ApprovalStep |
| `target_object_id` | `UUIDField` | - |
| `target_model_name` | `CharField` | - |
| `actor` | `ForeignKey` | to: User |
| `action` | `CharField` | - |
| `comments` | `TextField` | blank |
| `previous_state` | `CharField` | - |
| `new_state` | `CharField` | - |

### ApprovalDelegate
ApprovalDelegate(id, created_at, updated_at, created_by, approver, delegate, start_date, end_date, is_active, reason)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `approver` | `ForeignKey` | to: User |
| `delegate` | `ForeignKey` | to: User |
| `start_date` | `DateField` | - |
| `end_date` | `DateField` | - |
| `is_active` | `BooleanField` | - |
| `reason` | `TextField` | blank |

## Business Logic & Services
### `add_approval_step_service(*, policy: apps.approvals.models.ApprovalPolicy, step_number: int, approver_role: apps.accounts.models.Role, specific_approver: apps.accounts.models.User = None, description: str = '') -> apps.approvals.models.ApprovalStep`
```text
Adds an ordered step to an Approval Policy.
```

### `create_approval_policy_service(*, name: str, module: str, min_amount: decimal.Decimal = Decimal('0.00'), max_amount=None, department=None) -> apps.approvals.models.ApprovalPolicy`
```text
Creates an Approval Policy configuration.
```

### `evaluate_approval_chain(*, module: str, amount: decimal.Decimal, department=None)`
```text
Evaluates server-side approval routing policies for a module & amount threshold.
Returns list of tuples: [(step, target_approver_role, effective_approver_user)]
```

### `process_approval_action_service(*, target_object, actor: apps.accounts.models.User, action: str, comments: str = '')`
```text
Processes an approval action (APPROVE or REJECT) on a target object (e.g. PurchaseRequisition).
```

### `record_approval_action_service(*, target_object_id, target_model_name: str, actor: apps.accounts.models.User, action: str, previous_state: str, new_state: str, policy_step: apps.approvals.models.ApprovalStep = None, comments: str = '') -> apps.approvals.models.ApprovalAction`
```text
Records an append-only ApprovalAction and corresponding AuditLog entry inside a transaction.
```

### `resolve_active_delegate(approver: apps.accounts.models.User) -> apps.accounts.models.User`
```text
Resolves if an approver has an active delegate for today's date.
If active delegate exists, returns the delegate user; otherwise returns the original approver.
```

### `set_approval_delegate_service(*, approver: apps.accounts.models.User, delegate: apps.accounts.models.User, start_date, end_date, reason: str = '') -> apps.approvals.models.ApprovalDelegate`
```text
Sets up a temporary delegate for an approver.
```
