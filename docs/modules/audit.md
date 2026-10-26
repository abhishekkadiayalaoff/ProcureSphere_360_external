# Module: Audit

## Overview
Detailed documentation for the `audit` module in ProcureSphere 360.

## Database Models
### AuditLog
Append-only immutable audit trail capturing state changes across ProcureSphere 360.
    Enforces strict immutability by preventing modifications and deletions.

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `timestamp` | `DateTimeField` | blank |
| `actor` | `ForeignKey` | null, blank, to: User |
| `action` | `CharField` | - |
| `target_model` | `CharField` | - |
| `target_object_id` | `CharField` | - |
| `previous_state` | `JSONField` | null, blank |
| `new_state` | `JSONField` | null, blank |
| `ip_address` | `GenericIPAddressField` | null, blank |
| `request_id` | `CharField` | blank |
| `user_agent` | `TextField` | blank |

## Business Logic & Services
### `create_audit_log_service(actor: Optional[apps.accounts.models.User] = None, action: str = 'UPDATE', target_model: str = '', target_object_id: Any = '', previous_state: Optional[Dict[str, Any]] = None, new_state: Optional[Dict[str, Any]] = None, ip_address: Optional[str] = None, request_id: Optional[str] = None, user_agent: str = '') -> apps.audit.models.AuditLog`
```text
Centralized service to append an immutable AuditLog record across ProcureSphere 360.
Automatically retrieves thread-local actor, request_id, and client IP if omitted.
```

### `detect_entity_type(identifier: str) -> str`
```text
Infers entity domain type from prefix or format.
```

### `export_auditor_data_service(export_type: str, export_format: str = 'csv', filters: Optional[Dict[str, Any]] = None, actor: Optional[Any] = None) -> Dict[str, Any]`
```text
Generates structured export data (CSV or JSON) for Auditor Dashboard domains,
and creates an immutable ACTION_EXPORT audit log record.
```

### `get_transaction_lifecycle_service(entity_type: Optional[str] = None, entity_identifier: str = '') -> Dict[str, Any]`
```text
Constructs an end-to-end Source-to-Pay (S2P) lifecycle graph from any starting node:
Requisition -> Approvals -> Budget -> Sourcing -> Bids -> Evaluation -> Award ->
Purchase Order -> Receipts -> Inspections -> Invoice -> 3-Way Match -> Payment ->
Contract -> Vendor Governance & Complete Immutable Audit Trail.
```
