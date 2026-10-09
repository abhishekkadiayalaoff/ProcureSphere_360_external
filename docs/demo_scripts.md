# Day-90 Acceptance Demonstration Scripts — ProcureSphere 360

PRD Reference: HPE-PRD-2026-PROC01 / Section 14  
These scripts document the step-by-step end-to-end execution paths required for the seven Day-90 technical acceptance demonstrations on real PostgreSQL data.

---

## Demo 1: Vendor Onboarding & KYC Governance
- **Goal**: Onboard a new vendor with uploaded KYC documents, conduct review, approve vendor, and verify append-only audit trail.
- **Roles Involved**: Vendor User (`vendor@acme.com`), Procurement Executive (`proc_exec@hpe.com`), Procurement Manager (`proc_mgr@hpe.com`).
- **Steps**:
  1. Vendor submits registration form via portal (`/api/v1/vendors/register/` or UI) with tax ID, bank details, and attachments (Certificate of Inc, Tax Clearance).
  2. Status moves from `DRAFT` to `SUBMITTED`.
  3. Procurement Executive reviews KYC documents and marks checklist verified -> Status transitions to `KYC_REVIEW`.
  4. Procurement Manager approves vendor -> Status transitions to `APPROVED` and then `ACTIVE`.
  5. Audit log query confirms records for creation, submission, document verification, and approval with actor IDs and timestamps.

---

## Demo 2: Purchase Requisition, Budget Reservation & Multi-Level Approval
- **Goal**: Create PR exceeding $50,000 threshold, verify automatic multi-level approval routing, and confirm PostgreSQL budget reservation.
- **Roles Involved**: Requester (`requester@eng.hpe.com`), Department Manager (`dept_mgr@eng.hpe.com`), Procurement Manager (`proc_mgr@hpe.com`), Finance (`finance@hpe.com`).
- **Steps**:
  1. Requester creates PR with line items totaling $75,000 against Cost Center `CC-ENG-101`.
  2. System evaluates approval policy: requires Step 1 (Dept Manager) and Step 2 (Procurement Manager / Finance).
  3. Pre-approval budget check confirms available budget and creates `BudgetReservation` in `RESERVED` state.
  4. Dept Manager approves -> Step 1 completes.
  5. Procurement Manager approves -> PR transitions to `APPROVED`.
  6. Verify budget ledger shows reserved amount locked against `CC-ENG-101`.

---

## Demo 3: Sealed RFQ/RFP Sourcing Event, Sealed Bids & Evaluation
- **Goal**: Publish RFQ, receive ≥3 sealed vendor bids, enforce bid privacy before close, execute technical/commercial evaluation, and award contract.
- **Roles Involved**: Procurement Executive, Vendor 1, Vendor 2, Vendor 3, Sourcing Committee.
- **Steps**:
  1. Procurement Executive creates RFQ `RFQ-2026-001` and invites 3 vendors. Event state moves to `PUBLISHED` -> `BID_WINDOW`.
  2. Vendors submit bids independently. Reviewers attempting to read bid details before window closes receive `403 Forbidden` / sealed view.
  3. Bid window closes -> Event transitions to `TECHNICAL_REVIEW`.
  4. Committee submits technical scores -> Event transitions to `COMMERCIAL_REVIEW`.
  5. System generates commercial comparison matrix -> Winner selected -> Award decision recorded with audit hash.

---

## Demo 4: PO Execution, Amendment Versioning & Goods Receipt
- **Goal**: Issue PO from awarded bid, issue change order (amendment), record partial and final receipts (GRN), and verify historical PO versions.
- **Roles Involved**: Procurement Executive, Vendor, Stores Receiver.
- **Steps**:
  1. PO `PO-2026-0089` generated from award. Vendor acknowledges PO.
  2. Procurement Executive submits Change Order (price update) -> Creates PO Version 2; Version 1 remains immutably preserved in `POAmendment` / version store.
  3. Stores Receiver creates Goods Receipt `GRN-2026-0042` for partial quantity (60 of 100 units). PO state moves to `PARTIAL_RECEIPT`.
  4. Stores Receiver creates second GRN for remaining 40 units -> PO state moves to `COMPLETED`.
  5. Querying PO version history yields both original V1 and amended V2 records intact.

---

## Demo 5: Invoice Capture, 3-Way Matching, Tolerance Exception & Payment Readiness
- **Goal**: Submit supplier invoice, execute automated 3-way match against PO & GRN, trigger tolerance exception, resolve exception, and transition to payment-ready.
- **Roles Involved**: Vendor, AP Specialist, AP Manager.
- **Steps**:
  1. Vendor submits invoice `INV-ACME-901` referencing `PO-2026-0089`.
  2. Automated 3-way match compares PO line prices, GRN received quantities, and Invoice billed amounts.
  3. Unit price on invoice exceeds PO by 4% (configured tolerance is 2%) -> System creates `MatchException` record (type: `PRICE_VARIANCE`, status: `OPEN`).
  4. AP Specialist inspects exception details, inputs variance justification, and routes for AP Manager approval.
  5. AP Manager approves exception -> Invoice state transitions from `EXCEPTION` to `READY_FOR_PAYMENT`.

---

## Demo 6: Contract Governance, Milestone Alerts & Celery Scheduled Execution
- **Goal**: Register enterprise contract with milestones and expiration date, execute Celery Beat task, and confirm scheduled notification & audit records.
- **Roles Involved**: Legal Manager, System Celery Beat Scheduler.
- **Steps**:
  1. Legal Manager registers Contract `CON-2026-0012` with expiration date set to 30 days in future and SLA milestone.
  2. Trigger Celery Beat scheduled task `contracts.tasks.scan_contract_expirations_and_milestones`.
  3. Task evaluates active contracts, detects upcoming expiration, creates `ContractAlert` notification record, and dispatches in-app/email alert.
  4. Verification of Celery task execution log confirms scheduled job run and alert delivery evidence.

---

## Demo 7: Spend Analytics, Supplier Scorecards & Immutable Audit Export
- **Goal**: View spend dashboard by cost center/category, view calculated vendor performance scorecard, and export full audited transaction lifecycle report.
- **Roles Involved**: Procurement Manager, Compliance Auditor.
- **Steps**:
  1. Open Spend Analytics dashboard showing interactive spend distribution across vendors and categories.
  2. Open Supplier Scorecard for Acme Corp: system calculates composite score based on delivery timeliness (GRN dates), quality (rejection rate), and price competitiveness.
  3. Compliance Auditor triggers Audit Export for `PO-2026-0089` lifecycle.
  4. System queues `ExportJob`, generates PDF/XLSX report detailing every transaction step (PR creation -> Approval -> RFQ -> Award -> PO -> GRN -> Invoice -> Payment), and logs an append-only `AuditLog` entry for the export event.
