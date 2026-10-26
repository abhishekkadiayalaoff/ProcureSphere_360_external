# ProcureSphere 360 ERP — Legal / Contract Manager Knowledge-Transfer (KT) Handover

**Document Ref:** PS360-KT-LEGAL-2026  
**Module:** Legal / Contract Manager & SLA Governance  
**Author / Assigned Engineer:** Preetham  
**Target Audience:** Technical Lead, Peer Engineers, Receiving Maintenance / QA Team  
**Handover Date:** November 2026 (Day 30 Scope Completion)

---

## 1. Module Overview & Implemented Scope

The **Legal / Contract Manager Module** (`src/apps/contracts/`) is a core enterprise domain module in ProcureSphere 360. It governs the end-to-end lifecycle of corporate supplier agreements, sourcing awards, purchase order contracts, version amendments, legal obligations, delivery milestones, renewal notice windows, expiry scanning, and document evidence registers.

### Completed Feature Set (Days 6–30)
1. **Contract Master & Terms Management:** Full schema for contracts, versions, milestones, obligations, alerts, and document vault.
2. **Controlled Lifecycle State Machine:**
   $$\text{DRAFT} \rightarrow \text{LEGAL\_REVIEW} \rightarrow \text{BUSINESS\_APPROVAL} \rightarrow \text{ACTIVE} \rightarrow \text{RENEWAL\_DUE} \rightarrow \text{RENEWED} \mid \text{EXPIRED} \mid \text{TERMINATED}$$
3. **Legal Review & Approval Engine:** Multi-step submission, legal approval/rejection with notes, and business approval for activation.
4. **Immutable Versioning & Amendment Workflow:** Increments contract version ($v \rightarrow v + 1$) while preserving exact historical version records in `ContractVersion`.
5. **Renewal, Expiry & Notice Period Engine:** Renewal extension service, scheduled Celery Beat expiry scan (`scan_contract_expirations_and_milestones_task`), alert generation (`ContractAlert`), and termination handling.
6. **Milestone & Obligation SLA Tracking:** Real-time due status calculations (`OVERDUE`, `UPCOMING`, `FULFILLED`) and fulfillment timestamps (`fulfilled_at`).
7. **Secure Document Vault:** File upload with extension/size validation, secure download routes with export audit logging (`AuditLog.ACTION_EXPORT`).
8. **Reports & Dashboards:** Executive Legal & SLA Governance Desk (`/contracts/dashboard/`), contract expiry reporting API (`/api/v1/reports/contract-expiry/`), obligation reporting API (`/api/v1/reports/contract-obligation/`), and background CSV/XLSX/PDF export jobs.
9. **Role-Based Access Control & Object Scoping:** Full RBAC enforcement across web views, REST APIs, and background services (`LEGAL_MGR`, `PROC_MGR`, `SUPER_ADMIN`, `AUDITOR` read-only, `VENDOR_USER` vendor-scoped).

---

## 2. Architecture & Primary Code Locations

```
src/apps/contracts/
├── models.py          # Contract, ContractVersion, ContractMilestone, ContractObligation, ContractAlert, ContractDocument
├── services.py        # Business logic & workflow state transitions (all @transaction.atomic)
├── selectors.py       # Optimized read queries, dashboard metrics & obligation filters
├── api_views.py       # DRF ViewSet (/api/v1/contracts/...) & REST action endpoints
├── views.py           # Web views for Contract Register, Workspace, Forms, Downloads & Dashboard
├── forms.py           # Django forms for Create, Amendment, Milestone, Obligation, Renewal, Document
├── permissions.py     # DRF permission classes (CanViewContract, CanManageContract, IsLegalManager, IsNotAuditor)
├── urls.py            # Web URL routes (/contracts/...)
├── api_urls.py        # DRF Router & API endpoint mappings
└── tasks.py           # Celery Beat scheduled tasks (contracts.tasks.scan_contract_expirations_and_milestones)
```

### Key Supporting Components
- **Reports Module:** `src/apps/reports/services.py` (`get_contract_expiry_report`, `get_contract_obligation_report`, `REPORT_DISPATCHER`), `src/apps/reports/api_urls.py`.
- **Audit Module:** `src/apps/audit/models.py` (`AuditLog`), `services.py`.
- **Notifications Module:** `src/apps/notifications/models.py` (`Notification`), `services.py` (`notify_role_users`, `notify_users`).
- **Templates:** `templates/pages/contracts/` (`list.html`, `detail.html`, `create.html`), `templates/pages/dashboards/legal_dashboard.html`, `templates/layouts/legal_base.html`.
- **Automated Tests:** `tests/test_contracts_workflow.py` (22 suite tests), `tests/test_demo_6_contract_celery_alerts.py`.

---

## 3. Main Models & Database Schemas

| Model Name | Table Name | Key Fields | Purpose |
|---|---|---|---|
| `Contract` | `contracts_contract` | `contract_number`, `title`, `vendor`, `sourcing_event`, `po`, `status`, `contract_value`, `start_date`, `end_date`, `renewal_notice_days`, `version`, `contract_owner` | Primary contract register record. |
| `ContractVersion` | `contracts_contractversion` | `contract`, `version_number`, `amendment_summary`, `contract_value`, `start_date`, `end_date`, `approved_by` | Immutable version history snapshot. |
| `ContractMilestone` | `contracts_contractmilestone` | `contract`, `title`, `due_date`, `amount`, `is_completed`, `completed_at` | Financial sign-offs & delivery phases. |
| `ContractObligation` | `contracts_contractobligation` | `contract`, `title`, `responsible_party`, `due_date`, `is_fulfilled`, `fulfilled_at` | Legal & compliance deliverables. |
| `ContractAlert` | `contracts_contractalert` | `contract`, `alert_type`, `message`, `triggered_at`, `is_processed` | Expiry, milestone, obligation warning alerts. |
| `ContractDocument` | `contracts_contractdocument` | `contract`, `title`, `file`, `uploaded_by` | Signed agreement files & addenda. |

---

## 4. Lifecycle State Machine & Business Rules

```
+-------+     Submit Legal     +--------------+     Legal Approve     +-------------------+     Business Approve     +--------+
| DRAFT | -------------------> | LEGAL_REVIEW | --------------------> | BUSINESS_APPROVAL | -----------------------> | ACTIVE |
+-------+                      +--------------+                       +-------------------+                          +--------+
    ^                                 |                                                                                  |
    |          Legal Reject           |                                                                  Renewal Due /   |
    +---------------------------------+                                                                  Expiry Scan     v
                                                                                                           +--------------------+
                                                                                                           | RENEWAL_DUE        |
                                                                                                           | (Notice Window)    |
                                                                                                           +--------------------+
                                                                                                                     |
                                                                                    Renew Contract /                 |
                                                                                    Past End Date                    v
                                                                                           +----------------------------------+
                                                                                           | RENEWED / EXPIRED / TERMINATED   |
                                                                                           +----------------------------------+
```

### Non-Negotiable Business Rules
1. **No Frontend-Only Security:** Every web view and DRF API endpoint checks RBAC permissions (`CanViewContract`, `IsLegalManager`, `IsNotAuditor`).
2. **Immutable History:** Prior versions (`ContractVersion`), receipts, amendments, and audit logs are append-only.
3. **Controlled Transitions:** State changes occur exclusively via `@transaction.atomic` service functions (`submit_for_legal_review_service`, `approve_legal_review_service`, `renew_contract_service`, `terminate_contract_service`).
4. **Notice Period Calculations:** Renewal notice date = $\text{end\_date} - \text{renewal\_notice\_days}$.
5. **Auditor Restriction:** Compliance Auditors have strictly read-only access.
6. **Vendor Scoping:** Vendor users can access only their own vendor's contracts, obligations, and documents.

---

## 5. Environment & Configuration Prerequisites

- **Python Version:** Python 3.11+ (running on Python 3.12).
- **Django Version:** Django 4.2+ LTS.
- **Database:** PostgreSQL 15+ (or SQLite local development fallback).
- **Redis & Celery:** Redis 7+, Celery 5+.
- **Environment Variables (`.env`):**
  - `DEBUG=True` (dev) / `False` (prod)
  - `SECRET_KEY=<secret>`
  - `DATABASE_URL=postgres://...`
  - `CELERY_BROKER_URL=redis://localhost:6379/0`
  - `MEDIA_ROOT=media/`

---

## 6. Testing & Quality Verification Commands

Run all automated quality checks before merging code or deploying:

```powershell
# 1. Django System Configuration Check
.\.venv\Scripts\python manage.py check

# 2. Migration Integrity Check
.\.venv\Scripts\python manage.py makemigrations --check

# 3. Ruff Code Linter
.\.venv\Scripts\ruff check .

# 4. Black Code Formatter
.\.venv\Scripts\black --check .

# 5. Automated Legal Test Suite
.\.venv\Scripts\python -m pytest tests/test_contracts_workflow.py tests/test_demo_6_contract_celery_alerts.py
```

### Test Suite Summary
- **Total Suite Tests:** 23
- **Test Status:** 23 Passed, 0 Failed, 0 Skipped.

---

## 7. Troubleshooting Common Workflow Issues

| Issue / Symptom | Possible Cause | Troubleshooting Action |
|---|---|---|
| Celery alert task not triggering notice alerts | Celery worker or Celery Beat scheduler not running. | Run `celery -A config worker -l info -P solo` and `celery -A config beat -l info` or trigger `scan_contract_expirations_and_milestones_service()` directly. |
| Vendor user receiving 404/403 on contract detail | `user.vendor` is not linked to vendor record, or contract belongs to another vendor. | Verify `user.vendor` foreign key in database; ensure `contract.vendor` matches. |
| File upload failing with 400 Bad Request | Uploaded file size exceeds 10MB or has disallowed extension. | Check file size and extension (allowed: PDF, DOCX, XLSX, PNG, JPG, TXT). |
| Document download returns 404 File Not Found | Document metadata exists in DB but media file is missing on storage path. | Verify file path in `MEDIA_ROOT` storage directory (`media/contract_documents/`). |

---

## 8. Known Limitations & Technical Risks

1. **Manual UAT Execution Pending:** All 28 manual UAT test cases in `docs/handover/legal_uat_script.md` are marked `NOT EXECUTED` awaiting interactive browser verification after Day 30.
2. **File Storage Backend:** Local filesystem storage (`MEDIA_ROOT`) is configured by default. For cloud production deployment (AWS S3 / GCS), configure `django-storages`.

---

## 9. Handover Verification Checklist

- [x] All 7 Day-90 PRD acceptance demonstrations supported in contract domain code.
- [x] All 23 automated pytest cases passing cleanly.
- [x] Zero Django system check errors (`python manage.py check`).
- [x] Zero pending unapplied migrations (`python manage.py makemigrations --check`).
- [x] Clean Ruff and Black code formatting.
- [x] Legal User Guide (`docs/handover/legal_user_guide.md`) created.
- [x] Manual UAT Execution Script (`docs/handover/legal_uat_script.md`) created with 28 structured test cases.
- [x] Knowledge-Transfer Handover (`docs/handover/legal_kt_handover.md`) created.
- [ ] Interactive manual UAT execution by QA / receiving team.
