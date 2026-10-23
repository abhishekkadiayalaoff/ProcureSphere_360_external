# Module: Reports

## Overview
Detailed documentation for the `reports` module in ProcureSphere 360.

## Database Models
### ExportJob
ExportJob(id, created_at, updated_at, created_by, report_type, export_format, status, requested_by, result_file, error_message)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `report_type` | `CharField` | - |
| `export_format` | `CharField` | - |
| `status` | `CharField` | - |
| `requested_by` | `ForeignKey` | to: User |
| `result_file` | `FileField` | null, blank |
| `error_message` | `TextField` | blank |

## Business Logic & Services
### `generate_export_job_service(export_job_id: int) -> apps.reports.models.ExportJob`
```text
Processes an ExportJob, generates CSV, XLSX, or PDF file, attaches result file, and logs audit event.
```

### `get_audit_log_report()`
```text
9. User / approval audit export with filters and immutable references
```

### `get_contract_expiry_report()`
```text
7. Contract expiry / renewal / obligation
```

### `get_invoice_exception_aging_report()`
```text
6. Invoice match-exception aging
```

### `get_po_status_report()`
```text
4. PO open / partial / closed status
```

### `get_pr_aging_report()`
```text
1. PR aging and approval-bottleneck report
```

### `get_receipt_rejection_report()`
```text
5. Receipt / rejection and delivery performance
```

### `get_sourcing_cycle_time_report()`
```text
3. Sourcing cycle time and bid participation
```

### `get_spend_analytics_report()`
```text
2. Spend by vendor / category / department / cost center / period
```

### `get_supplier_performance_report()`
```text
8. Supplier performance scorecard and trend
```
