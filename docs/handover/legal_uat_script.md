# ProcureSphere 360 ERP — Legal / Contract Manager UAT Execution Script

**Document Ref:** PS360-UAT-LEGAL-2026  
**Module:** Legal / Contract Manager & SLA Governance  
**Execution Status:** `PENDING HUMAN EXECUTION` (All actual results set to `NOT EXECUTED`)

---

> [!IMPORTANT]  
> This UAT script is prepared for manual user acceptance testing. All test cases must be executed interactively in the application by authorized reviewers. Do not alter test expectations without formal change management approval.

---

## Summary Matrix

| Scenario Group | Test Count | Status |
|---|---|---|
| 1. Contract Creation & Required-Field Validation | 3 | `NOT EXECUTED` |
| 2. Legal Review, Rejection, Resubmission & Approval Workflow | 4 | `NOT EXECUTED` |
| 3. Business Approval & Contract Activation | 2 | `NOT EXECUTED` |
| 4. Contract Amendments & Immutable Version History | 3 | `NOT EXECUTED` |
| 5. Document Upload, File Validation & Security Access | 3 | `NOT EXECUTED` |
| 6. Milestone & Legal Obligation Tracking | 3 | `NOT EXECUTED` |
| 7. Renewal, Expiry & Termination Workflows | 3 | `NOT EXECUTED` |
| 8. Scheduled Expiry Alerts & Notification History | 2 | `NOT EXECUTED` |
| 9. Expiry & Obligation Governance Reports | 2 | `NOT EXECUTED` |
| 10. Compliance Auditor & Vendor Role-Based Security Controls | 3 | `NOT EXECUTED` |
| **Total Test Cases** | **28** | **0 Passed / 0 Failed / 28 Pending** |

---

## Detailed Test Cases

### Group 1: Contract Creation & Field Validation

#### UAT-LEG-001: Create Contract Draft with Valid Terms
- **Objective:** Verify successful creation of contract draft in `DRAFT` status.
- **Required Role:** `LEGAL_MGR` or `PROC_MGR`
- **Prerequisites:** Active user account, approved Vendor record (`Acme Corp Solutions`).
- **Test Data:**
  - Title: `Enterprise Cloud Infrastructure Agreement`
  - Vendor: `Acme Corp Solutions`
  - Value: `$250,000.00`
  - Start Date: Today's Date (`YYYY-MM-DD`)
  - End Date: Today + 365 Days
  - Renewal Notice Days: `30`
- **Steps:**
  1. Log in to ProcureSphere 360 web UI.
  2. Navigate to `/contracts/` and click **"New Draft"** (`/contracts/create/`).
  3. Fill in required fields with test data.
  4. Click **"Save Contract Draft"**.
- **Expected Result:** Contract is created with state `DRAFT`, unique number `CON-2026-XXXXX`, initial version `1`, and user is redirected to detail workspace (`/contracts/{id}/`). Success message displayed.
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

#### UAT-LEG-002: Validation Error on End Date Prior to Start Date
- **Objective:** Verify system blocks invalid date boundaries.
- **Required Role:** `LEGAL_MGR`
- **Prerequisites:** Access to `/contracts/create/`.
- **Test Data:** Start Date = `2026-12-01`, End Date = `2026-11-01`.
- **Steps:**
  1. Fill form with End Date prior to Start Date.
  2. Click **"Save Contract Draft"**.
- **Expected Result:** Form submission blocked with error message: `"End date must be after start date."`
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

#### UAT-LEG-003: Validation Error on Negative Contract Value
- **Objective:** Verify system blocks negative contract value.
- **Required Role:** `PROC_MGR`
- **Test Data:** Contract Value = `-$50,000.00`.
- **Steps:**
  1. Enter negative contract value.
  2. Submit form.
- **Expected Result:** Form validation fails with error: `"Contract value cannot be negative."`
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

---

### Group 2: Legal Review, Rejection, Resubmission & Approval

#### UAT-LEG-004: Submit Contract for Legal Review
- **Objective:** Move contract from `DRAFT` to `LEGAL_REVIEW`.
- **Required Role:** `PROC_MGR` or Contract Owner
- **Prerequisites:** Contract UAT-LEG-001 in `DRAFT` status.
- **Steps:**
  1. Open contract detail page `/contracts/{id}/`.
  2. Click **"Submit for Legal Review"**.
  3. Add submission note: `"Ready for legal terms review."`
  4. Confirm submission.
- **Expected Result:** Contract status updates to `LEGAL_REVIEW`. Notification sent to Legal Manager role group. `AuditLog` entry recorded.
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

#### UAT-LEG-005: Reject Legal Review and Return to Draft
- **Objective:** Rejection reverts contract to `DRAFT` for corrections.
- **Required Role:** `LEGAL_MGR`
- **Prerequisites:** Contract in `LEGAL_REVIEW` status.
- **Steps:**
  1. Log in as Legal Manager. Open contract detail page.
  2. Click **"Reject Legal Review"**.
  3. Provide rejection reason: `"Section 14 SLA clause missing indemnification cap."`
  4. Submit rejection.
- **Expected Result:** Status reverts to `DRAFT`. Warning alert displayed. Notification sent to contract owner.
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

#### UAT-LEG-006: Resubmit Corrected Contract for Legal Review
- **Objective:** Resubmit draft after corrections.
- **Required Role:** Contract Owner
- **Steps:**
  1. Open draft contract `/contracts/{id}/`.
  2. Click **"Submit for Legal Review"**.
- **Expected Result:** Status returns to `LEGAL_REVIEW`.
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

#### UAT-LEG-007: Approve Legal Review
- **Objective:** Move contract from `LEGAL_REVIEW` to `BUSINESS_APPROVAL`.
- **Required Role:** `LEGAL_MGR`
- **Steps:**
  1. Open contract in `LEGAL_REVIEW`.
  2. Click **"Approve Legal Review"**.
  3. Add note: `"Legal terms verified and approved."`
- **Expected Result:** Status updates to `BUSINESS_APPROVAL`. Audit log created. Notification sent to Procurement Manager group.
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

---

### Group 3: Business Approval & Activation

#### UAT-LEG-008: Business Approval and Contract Activation
- **Objective:** Approve business scope and move contract to `ACTIVE`.
- **Required Role:** `PROC_MGR`
- **Prerequisites:** Contract in `BUSINESS_APPROVAL`.
- **Steps:**
  1. Log in as Procurement Manager. Open contract workspace.
  2. Click **"Approve & Activate Contract"**.
  3. Add note: `"Business budget approved for FY2026."`
- **Expected Result:** Contract status updates to `ACTIVE`. Agreement enters execution phase.
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

#### UAT-LEG-009: Invalid Transition Block on Unapproved Activation
- **Objective:** Verify system blocks direct activation from `DRAFT` without legal approval.
- **Required Role:** `PROC_EXEC`
- **Steps:**
  1. Attempt API `POST /api/v1/contracts/{id}/business-approve/` on a `DRAFT` contract.
- **Expected Result:** API returns HTTP 400 Bad Request: `"Cannot perform business approval on contract in status 'DRAFT'."`
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

---

### Group 4: Contract Amendments & Version History

#### UAT-LEG-010: Amend Active Contract Terms
- **Objective:** Amend price and SLA term on active contract, incrementing version to 2.
- **Required Role:** `LEGAL_MGR`
- **Prerequisites:** Active contract.
- **Test Data:** New Value = `$320,000.00`, Extended End Date = Today + 500 days, Summary = `"SLA uptime increased to 99.99%; Value increased."`
- **Steps:**
  1. Navigate to contract detail workspace.
  2. Click **"Amend Contract Terms"**.
  3. Enter new values and amendment summary.
  4. Submit amendment form.
- **Expected Result:** Contract version becomes `2`. New value `$320,000.00` and end date saved. Version History table displays Version 1 (`$250,000.00`) and Version 2 records.
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

#### UAT-LEG-011: Verify Preservation of Prior Version History
- **Objective:** Confirm Version 1 terms remain unchanged in database.
- **Steps:**
  1. Inspect Version History table on `/contracts/{id}/`.
  2. Verify Version 1 row shows original `$250,000.00` value and original end date.
- **Expected Result:** Historical version values are preserved with original approval timestamps and author references.
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

#### UAT-LEG-012: Block Amendment on Terminated Contract
- **Objective:** Verify system blocks amendments on terminated contracts.
- **Steps:**
  1. Attempt to submit amendment form on a `TERMINATED` contract.
- **Expected Result:** System returns validation error: `"Cannot amend terminated contract."`
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

---

### Group 5: Document Vault & Security Controls

#### UAT-LEG-013: Upload Executed Contract Document
- **Objective:** Upload signed PDF agreement to Document Vault.
- **Required Role:** `LEGAL_MGR`
- **Test Data:** File = `Executed_MSA_Final.pdf` (1.2 MB).
- **Steps:**
  1. On contract detail page, locate Document Vault section.
  2. Enter Title: `Executed MSA Final PDF`.
  3. Select PDF file and click **"Upload Document"**.
- **Expected Result:** Document uploaded successfully. Listed in Document Vault table with uploader, size, and timestamp.
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

#### UAT-LEG-014: Block Unsupported File Upload Extension
- **Objective:** Verify system blocks unsafe file upload extensions (`.exe`, `.bat`, `.sh`).
- **Test Data:** File = `malicious_script.exe`.
- **Steps:**
  1. Select `.exe` file and attempt upload.
- **Expected Result:** System rejects file with error: `"Unsupported file extension '.exe'. Allowed formats: PDF, DOCX, XLSX, PNG, JPG, TXT."`
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

#### UAT-LEG-015: Secure Document Download & Audit Logging
- **Objective:** Download document and verify export audit trail.
- **Steps:**
  1. Click **"Download"** link on `Executed_MSA_Final.pdf`.
  2. Verify browser downloads file cleanly.
  3. Inspect system `AuditLog`.
- **Expected Result:** File downloads. `AuditLog` entry created with action `EXPORT`, target model `ContractDocument`, and user reference.
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

---

### Group 6: Milestone & Obligation Tracking

#### UAT-LEG-016: Add and Complete Contract Milestone
- **Objective:** Add milestone and mark complete.
- **Test Data:** Title = `Phase 1 Acceptance Signoff`, Due Date = Today + 30 days, Amount = `$50,000.00`.
- **Steps:**
  1. Add milestone via form on contract workspace.
  2. Click **"Complete"** toggle button.
- **Expected Result:** Milestone status updates to `COMPLETED` (`is_completed = True`). Completion timestamp recorded.
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

#### UAT-LEG-017: Add and Fulfill Legal Obligation
- **Objective:** Add legal obligation and fulfill it.
- **Test Data:** Title = `SOC2 Type II Audit Certificate`, Responsible Party = `VENDOR`, Due Date = Today + 15 days.
- **Steps:**
  1. Add obligation to contract.
  2. Click **"Mark Fulfilled"**.
- **Expected Result:** Obligation status updates to `FULFILLED`. `fulfilled_at` timestamp recorded.
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

#### UAT-LEG-018: Overdue Obligation Calculation
- **Objective:** Verify overdue calculation for unfulfilled obligations past due date.
- **Test Data:** Due Date = Today - 5 days, `is_fulfilled = False`.
- **Steps:**
  1. View obligation list.
- **Expected Result:** Obligation displays `OVERDUE` status badge with calculated overdue days (`5 days overdue`).
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

---

### Group 7: Renewal, Expiry & Termination

#### UAT-LEG-019: Execute Contract Renewal
- **Objective:** Extend active contract end date and update value.
- **Required Role:** `LEGAL_MGR`
- **Prerequisites:** Active contract or contract in `RENEWAL_DUE`.
- **Test Data:** New End Date = Today + 365 days, New Value = `$350,000.00`.
- **Steps:**
  1. Click **"Renew Contract"** button.
  2. Enter new end date and new contract value. Submit form.
- **Expected Result:** Contract status updates to `RENEWED`. Version number increments. Audit log and renewal notification created.
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

#### UAT-LEG-020: Execute Contract Termination
- **Objective:** Terminate active contract with required reason.
- **Required Role:** `LEGAL_MGR`
- **Steps:**
  1. Click **"Terminate Contract"**.
  2. Enter reason: `"Vendor breach of data security SLA."`
  3. Submit termination.
- **Expected Result:** Contract status updates to `TERMINATED`. Audit log and termination notification logged.
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

#### UAT-LEG-021: Block Double Termination
- **Objective:** Verify system blocks duplicate termination.
- **Steps:**
  1. Attempt to submit termination form again on terminated contract.
- **Expected Result:** System returns error: `"Contract is already terminated."`
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

---

### Group 8: Scheduled Expiry Alerts & Notifications

#### UAT-LEG-022: Scheduled Expiry Scan Execution
- **Objective:** Verify Celery task `scan_contract_expirations_and_milestones_task` flags notice period contracts.
- **Test Setup:** Active contract with end date in 15 days (renewal notice days = 30).
- **Steps:**
  1. Trigger scheduled task execution.
  2. Inspect contract record and alerts table.
- **Expected Result:** Contract status updates to `RENEWAL_DUE`. `ContractAlert` record generated (type `RENEWAL`). In-app notification delivered to Legal Managers.
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

#### UAT-LEG-023: Scheduled Expired Scan Execution
- **Objective:** Verify task updates contracts past end date to `EXPIRED`.
- **Test Setup:** Active contract with end date 5 days in past.
- **Steps:**
  1. Trigger scheduled task.
- **Expected Result:** Contract status updates to `EXPIRED`. `ContractAlert` record generated (type `EXPIRATION`).
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

---

### Group 9: Expiry & Obligation Reports

#### UAT-LEG-024: Contract Expiry Report API & Filtering
- **Objective:** Query `/api/v1/reports/contract-expiry/` with filters.
- **Steps:**
  1. Request `GET /api/v1/reports/contract-expiry/?status=RENEWAL_DUE&days=30`.
- **Expected Result:** Returns JSON array of expiring contracts matching status and days window, containing `in_notice_period`, `is_expired`, and `days_to_expiry` values.
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

#### UAT-LEG-025: Contract Obligation Report API & Export
- **Objective:** Query `/api/v1/reports/contract-obligation/` and trigger CSV export.
- **Steps:**
  1. Request `GET /api/v1/reports/contract-obligation/?due_status=OVERDUE`.
  2. Generate ExportJob for `contract_obligation` in CSV format.
- **Expected Result:** API returns overdue obligations. ExportJob completes (`STATUS_COMPLETED`) and attaches generated CSV file.
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

---

### Group 10: Role-Based Security & Isolation

#### UAT-LEG-026: Auditor Read-Only Mutation Block
- **Objective:** Verify Compliance Auditor cannot perform state changes or uploads.
- **Required Role:** `AUDITOR`
- **Steps:**
  1. Log in as Auditor user.
  2. Attempt to submit contract, approve legal review, upload document, or amend terms.
- **Expected Result:** System blocks all mutation attempts with HTTP 403 Forbidden or error message: `"Permission Denied: Compliance Auditors hold strictly read-only permissions."`
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

#### UAT-LEG-027: Vendor User Object-Level Isolation
- **Objective:** Verify Vendor User cannot view other vendors' contracts or documents.
- **Required Role:** `VENDOR_USER` (Vendor A)
- **Steps:**
  1. Log in as Vendor A user.
  2. Attempt to view or download contract belonging to Vendor B (`/api/v1/contracts/{vendor_b_contract_id}/`).
- **Expected Result:** Access denied with HTTP 404 Not Found or HTTP 403 Forbidden.
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`

#### UAT-LEG-028: Audit Trail Persistence After Session Refresh
- **Objective:** Confirm audit records persist across server restarts.
- **Steps:**
  1. Perform contract approval.
  2. Restart application server / re-login.
  3. View audit history table.
- **Expected Result:** Audit trail entries remain intact in PostgreSQL database with actor, action, timestamp, and state diffs.
- **Actual Result:** `NOT EXECUTED`
- **Status:** `NOT EXECUTED`
- **Evidence / Notes:** `[Unexecuted]`
