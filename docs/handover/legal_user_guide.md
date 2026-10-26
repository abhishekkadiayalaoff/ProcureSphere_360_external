# ProcureSphere 360 ERP — Legal / Contract Manager User Guide

**Document Ref:** PS360-UG-LEGAL-2026  
**Module:** Legal / Contract Manager & SLA Governance  
**Target Roles:** Legal Manager (`LEGAL_MGR`), Procurement Manager (`PROC_MGR`), Procurement Executive (`PROC_EXEC`), Super Admin (`SUPER_ADMIN`), Compliance Auditor (`AUDITOR`), Vendor User (`VENDOR_USER`).

---

## 1. Overview & Supported Roles

The **Legal / Contract Manager Module** in ProcureSphere 360 manages the full lifecycle of enterprise supplier agreements, sourcing contracts, purchase order links, obligations, milestones, version amendments, renewal notices, and document evidence.

### Primary Roles & Responsibilities

| Role Code | Role Name | System Access & Operations |
|---|---|---|
| `LEGAL_MGR` | Legal / Contract Manager | Draft, submit, perform legal review (approve/reject), amend terms, renew, terminate contracts, fulfill obligations, manage milestones, upload/download documents, view dashboards & reports. |
| `PROC_MGR` | Procurement Manager | Draft contracts, submit for legal review, perform business approval for active contract execution, view dashboard & reporting. |
| `PROC_EXEC` | Procurement Executive | Draft contracts linked to sourcing events & POs, upload supporting documents, track milestone delivery. |
| `SUPER_ADMIN` | System Administrator | Full administrative override across all contract workflows, role assignments, policy configuration, and audit logs. |
| `AUDITOR` | Compliance Auditor | **Strictly read-only access.** Can view contract details, version history, document registers, download evidence, and view compliance reports. Cannot draft, approve, reject, amend, upload, renew, or terminate contracts. |
| `VENDOR_USER` | Vendor User | **Restricted self-service scope.** Can view only contracts where `vendor` matches their assigned vendor account, track obligations & milestones assigned to vendor, upload requested compliance documents. |

---

## 2. Contract Creation & Initial Terms Entry

### Navigation & Entry Points
- **Web UI:** Navigate to `/contracts/` (Contract Register) $\rightarrow$ Click **"New Draft"** (`/contracts/create/`).
- **REST API:** `POST /api/v1/contracts/`

### Input Fields & Validation Rules
- **Contract Title (`title`):** Required text string describing the agreement scope.
- **Vendor (`vendor`):** Required selection from approved Vendor Master records (`status=ACTIVE` or `APPROVED`).
- **Contract Value (`contract_value`):** Non-negative numeric decimal (`Decimal`).
- **Start Date (`start_date`):** Required ISO Date (`YYYY-MM-DD`).
- **End Date (`end_date`):** Required ISO Date (`YYYY-MM-DD`). Must be after `start_date`.
- **Renewal Notice Days (`renewal_notice_days`):** Positive integer (default: `30` days). Defines notice window prior to `end_date`.
- **Sourcing Event (`sourcing_event`):** Optional link to awarded RFQ/RFP event.
- **Purchase Order (`po`):** Optional link to associated execution Purchase Order.

### State Transition
Upon creation, the contract is assigned a unique system document number (`CON-YYYY-XXXXX`), initial `version = 1`, and initial state `DRAFT`.

---

## 3. Legal Review, Rejection, Resubmission & Business Approval

The contract lifecycle enforces strict server-side state transitions:

$$\text{DRAFT} \xrightarrow{\text{Submit Legal}} \text{LEGAL\_REVIEW} \xrightarrow{\text{Legal Approve}} \text{BUSINESS\_APPROVAL} \xrightarrow{\text{Business Approve}} \text{ACTIVE}$$

```
+-------+     Submit Legal     +--------------+     Legal Approve     +-------------------+     Business Approve     +--------+
| DRAFT | -------------------> | LEGAL_REVIEW | --------------------> | BUSINESS_APPROVAL | -----------------------> | ACTIVE |
+-------+                      +--------------+                       +-------------------+                          +--------+
    ^                                 |
    |          Legal Reject           |
    +---------------------------------+
```

### Step 1: Submission for Legal Review
- **Role:** Contract Owner, Procurement Manager, Legal Manager.
- **Action:** Web View button **"Submit for Legal Review"** or API `POST /api/v1/contracts/{id}/submit-legal/`.
- **Result:** Status changes to `LEGAL_REVIEW`. Generates `AuditLog` entry and sends in-app/email notification to `LEGAL_MGR` role group.

### Step 2: Legal Review & Disposition
- **Role:** Legal Manager (`LEGAL_MGR`) or `SUPER_ADMIN`.
- **Approval Path:** Click **"Approve Legal Review"** or API `POST /api/v1/contracts/{id}/legal-approve/`. Status changes to `BUSINESS_APPROVAL`. Generates `AuditLog` and notifies `PROC_MGR` role group.
- **Rejection Path:** Click **"Reject Legal Review"** with required `reason` string or API `POST /api/v1/contracts/{id}/legal-reject/`. Status reverts to `DRAFT`. Generates `AuditLog` and notifies contract owner.

### Step 3: Business Approval & Activation
- **Role:** Procurement Manager (`PROC_MGR`), Legal Manager, or `SUPER_ADMIN`.
- **Action:** Click **"Approve & Activate"** or API `POST /api/v1/contracts/{id}/business-approve/`.
- **Result:** Status changes to `ACTIVE`. The agreement enters active execution.

---

## 4. Contract Amendments & Immutable Version History

ProcureSphere 360 enforces non-destructive versioning. Prior contract terms are never overwritten.

### Creating an Amendment
- **Prerequisite:** Contract must be in `ACTIVE`, `RENEWAL_DUE`, or `RENEWED` state.
- **Action:** Web View amendment modal or API `POST /api/v1/contracts/{id}/amend/`.
- **Required Fields:** `amendment_summary`, `contract_value`, `start_date`, `end_date`.

### System Behavior
1. Active `Contract` object's version number increments ($v \rightarrow v + 1$).
2. Updated terms (`contract_value`, `start_date`, `end_date`) are saved to the active contract.
3. An immutable `ContractVersion` record is created containing the prior version number, exact historical terms, `amendment_summary`, and `approved_by` user reference.
4. An `AuditLog` entry with action `UPDATE` records previous state vs new state.

---

## 5. Contract Renewal, Expiry & Termination Workflows

### Expiry Scanning & Renewal Notice (`scan_contract_expirations_and_milestones_task`)
- A Celery Beat scheduled job runs periodically to scan active contracts.
- **Renewal Due Trigger:** If $\text{today} \ge (\text{end\_date} - \text{renewal\_notice\_days})$ and contract is `ACTIVE`, status automatically updates to `RENEWAL_DUE`, generating a `ContractAlert` (type `RENEWAL`) and notifying Legal and Procurement Managers.
- **Expired Trigger:** If $\text{today} > \text{end\_date}$, status automatically updates to `EXPIRED`, generating a `ContractAlert` (type `EXPIRATION`).

### Executing a Renewal
- **Roles:** `LEGAL_MGR`, `PROC_MGR`, `SUPER_ADMIN`.
- **Action:** Web view **"Renew Contract"** modal or API `POST /api/v1/contracts/{id}/renew/`.
- **Fields:** `new_end_date` (required, must be after start date), `new_value` (optional decimal), `notes` (optional).
- **Result:** Status updates to `RENEWED`, end date is extended, contract version increments, and an amendment version record is logged.

### Terminating a Contract
- **Action:** Web view **"Terminate Contract"** modal or API `POST /api/v1/contracts/{id}/terminate/`.
- **Required Field:** `reason` string.
- **Result:** Status updates to `TERMINATED`. Further amendments, renewals, or duplicate terminations are blocked.

---

## 6. Managing Obligations, Milestones & SLA Tracking

### Contract Milestones
- Track financial sign-offs or delivery phases.
- Add via Web view or API `POST /api/v1/contracts/{id}/add-milestone/` (`title`, `due_date`, `amount`).
- Mark completed via Web view toggle or API `POST /api/v1/contracts/{id}/complete-milestone/{milestone_id}/`.

### Legal Obligations
- Track deliverables and compliance obligations assigned to `VENDOR` or `BUYER`.
- Add via Web view or API `POST /api/v1/contracts/{id}/add-obligation/` (`title`, `responsible_party`, `due_date`).
- Fulfill via Web view toggle or API `POST /api/v1/contracts/{id}/fulfill-obligation/{obligation_id}/`.
- **Status Categories:**
  - `OVERDUE`: Unfulfilled and $\text{due\_date} < \text{today}$.
  - `UPCOMING`: Unfulfilled and $\text{due\_date} \ge \text{today}$.
  - `FULFILLED`: `is_fulfilled = True` with saved `fulfilled_at` timestamp.

---

## 7. Document Vault & Evidence Retrieval

### Uploading Documents
- Upload signed agreements, addenda, or compliance certificates via Web view or API `POST /api/v1/contracts/{id}/upload-document/`.
- **Validation:** Enforces maximum size (10MB) and allowed file extensions (`.pdf`, `.docx`, `.doc`, `.xlsx`, `.xls`, `.png`, `.jpg`, `.jpeg`, `.txt`).
- **Security:** Compliance Auditors are blocked from uploading.

### Document Retrieval & Audit
- Download via `/contracts/{id}/document/{doc_id}/download/` or API `/api/v1/contracts/{id}/documents/{doc_id}/download/`.
- Enforces RBAC permissions and vendor object-level scoping.
- **Audit Logging:** Every file download generates an `AuditLog` entry with action `EXPORT`.

---

## 8. Reports & Governance Dashboards

### Legal & SLA Governance Desk (`/contracts/dashboard/`)
Provides real-time visibility into contract portfolio performance:
- Total portfolio contract value ($)
- Count of contracts in `PENDING_LEGAL_REVIEW`, `ACTIVE`, and `EXPIRING_SOON` (<30 days)
- Interactive Status Breakdown Doughnut Chart
- Pending Legal Review Action Queue
- Renewal Notice Schedule
- Pending Legal Obligations list

### Reports Module Integration (`/reports/` & `/api/v1/reports/`)
- **Contract Expiry Report (`/api/v1/reports/contract-expiry/`):** Supports filtering by `status`, `days` window, `start_date`, `end_date`, with notice period calculation (`in_notice_period`, `is_expired`).
- **Contract Obligation Report (`/api/v1/reports/contract-obligation/`):** Supports filtering by `due_status` (`OVERDUE`, `UPCOMING`, `FULFILLED`), `responsible_party`, and date ranges.
- **Export Jobs:** Reports can be exported as CSV, Excel (`XLSX`), or PDF documents via the background export engine.

---

## 9. Validation Errors & Troubleshooting

| Error Code / Message | Root Cause | Solution |
|---|---|---|
| `Cannot renew contract in status 'DRAFT'` | Attempted renewal on contract not yet active or renewal-due. | Complete legal and business approval before renewing. |
| `Unsupported file extension '.exe'` | File upload extension failed MIME/extension whitelist check. | Upload file in allowed format (PDF, DOCX, XLSX, PNG, JPG, TXT). |
| `Permission Denied: Compliance Auditors hold strictly read-only permissions` | Auditor attempted state transition or document upload. | Switch to authorized role (`LEGAL_MGR` or `PROC_MGR`). |
| `Contract is already terminated` | Attempted secondary termination or amendment on a terminated contract. | Terminated contracts are immutable. Create a new contract draft if required. |
| `Renewal end date must be after contract start date` | Invalid end date provided in renewal form. | Select a renewal end date greater than the contract start date. |
