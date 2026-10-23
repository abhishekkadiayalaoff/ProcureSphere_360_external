# Module: Accounts

## Overview
Detailed documentation for the `accounts` module in ProcureSphere 360.

## Database Models
### Role
System RBAC Role (Super Admin, Requester, Dept Approver, Procurement Exec, etc.)

| Field | Type | Attributes |
|-------|------|------------|
| `users` | `ForeignKey` | null, to: User |
| `approval_steps` | `ForeignKey` | null, to: ApprovalStep |
| `id` | `UUIDField` | unique |
| `code` | `CharField` | unique |
| `name` | `CharField` | - |
| `description` | `TextField` | blank |
| `created_at` | `DateTimeField` | blank |

### User
Custom User model for ProcureSphere 360.
    Uses UUID primary key and links to primary Role and Department.

| Field | Type | Attributes |
|-------|------|------------|
| `logentry` | `ForeignKey` | null, to: LogEntry |
| `organization_created` | `ForeignKey` | null, to: Organization |
| `department_created` | `ForeignKey` | null, to: Department |
| `costcenter_created` | `ForeignKey` | null, to: CostCenter |
| `managed_cost_centers` | `ForeignKey` | null, to: CostCenter |
| `fiscalperiod_created` | `ForeignKey` | null, to: FiscalPeriod |
| `approvalpolicy_created` | `ForeignKey` | null, to: ApprovalPolicy |
| `approvalstep_created` | `ForeignKey` | null, to: ApprovalStep |
| `assigned_approval_steps` | `ForeignKey` | null, to: ApprovalStep |
| `approvalaction_created` | `ForeignKey` | null, to: ApprovalAction |
| `approval_actions` | `ForeignKey` | null, to: ApprovalAction |
| `approvaldelegate_created` | `ForeignKey` | null, to: ApprovalDelegate |
| `delegator_records` | `ForeignKey` | null, to: ApprovalDelegate |
| `delegated_records` | `ForeignKey` | null, to: ApprovalDelegate |
| `vendorcategory_created` | `ForeignKey` | null, to: VendorCategory |
| `vendor_created` | `ForeignKey` | null, to: Vendor |
| `vendorcontact_created` | `ForeignKey` | null, to: VendorContact |
| `vendordocument_created` | `ForeignKey` | null, to: VendorDocument |
| `verified_vendor_docs` | `ForeignKey` | null, to: VendorDocument |
| `vendorriskrecord_created` | `ForeignKey` | null, to: VendorRiskRecord |
| `assessed_vendor_risks` | `ForeignKey` | null, to: VendorRiskRecord |
| `purchaserequisition_created` | `ForeignKey` | null, to: PurchaseRequisition |
| `requisitions` | `ForeignKey` | null, to: PurchaseRequisition |
| `prline_created` | `ForeignKey` | null, to: PRLine |
| `prattachment_created` | `ForeignKey` | null, to: PRAttachment |
| `pr_attachments_uploaded` | `ForeignKey` | null, to: PRAttachment |
| `sourcingevent_created` | `ForeignKey` | null, to: SourcingEvent |
| `bidinvite_created` | `ForeignKey` | null, to: BidInvite |
| `vendorbid_created` | `ForeignKey` | null, to: VendorBid |
| `bidversion_created` | `ForeignKey` | null, to: BidVersion |
| `bidattachment_created` | `ForeignKey` | null, to: BidAttachment |
| `bidline_created` | `ForeignKey` | null, to: BidLine |
| `awarddecision_created` | `ForeignKey` | null, to: AwardDecision |
| `approved_awards` | `ForeignKey` | null, to: AwardDecision |
| `bidevaluation_created` | `ForeignKey` | null, to: BidEvaluation |
| `evaluations` | `ForeignKey` | null, to: BidEvaluation |
| `clarification_created` | `ForeignKey` | null, to: Clarification |
| `clarification` | `ForeignKey` | null, to: Clarification |
| `purchaseorder_created` | `ForeignKey` | null, to: PurchaseOrder |
| `acknowledged_pos` | `ForeignKey` | null, to: PurchaseOrder |
| `poline_created` | `ForeignKey` | null, to: POLine |
| `poamendment_created` | `ForeignKey` | null, to: POAmendment |
| `requested_po_amendments` | `ForeignKey` | null, to: POAmendment |
| `deliveryschedule_created` | `ForeignKey` | null, to: DeliverySchedule |
| `goodsreceipt_created` | `ForeignKey` | null, to: GoodsReceipt |
| `received_grns` | `ForeignKey` | null, to: GoodsReceipt |
| `receiptline_created` | `ForeignKey` | null, to: ReceiptLine |
| `inspectionrecord_created` | `ForeignKey` | null, to: InspectionRecord |
| `inspections` | `ForeignKey` | null, to: InspectionRecord |
| `rejectionrecord_created` | `ForeignKey` | null, to: RejectionRecord |
| `supplierinvoice_created` | `ForeignKey` | null, to: SupplierInvoice |
| `invoiceline_created` | `ForeignKey` | null, to: InvoiceLine |
| `matchexception_created` | `ForeignKey` | null, to: MatchException |
| `resolved_exceptions` | `ForeignKey` | null, to: MatchException |
| `matchresult_created` | `ForeignKey` | null, to: MatchResult |
| `performed_matches` | `ForeignKey` | null, to: MatchResult |
| `paymentstatus_created` | `ForeignKey` | null, to: PaymentStatus |
| `processed_payments` | `ForeignKey` | null, to: PaymentStatus |
| `contract_created` | `ForeignKey` | null, to: Contract |
| `owned_contracts` | `ForeignKey` | null, to: Contract |
| `contractversion_created` | `ForeignKey` | null, to: ContractVersion |
| `approved_contract_versions` | `ForeignKey` | null, to: ContractVersion |
| `contractmilestone_created` | `ForeignKey` | null, to: ContractMilestone |
| `contractalert_created` | `ForeignKey` | null, to: ContractAlert |
| `contractobligation_created` | `ForeignKey` | null, to: ContractObligation |
| `contractdocument_created` | `ForeignKey` | null, to: ContractDocument |
| `uploaded_contract_docs` | `ForeignKey` | null, to: ContractDocument |
| `budget_created` | `ForeignKey` | null, to: Budget |
| `budgetreservation_created` | `ForeignKey` | null, to: BudgetReservation |
| `spendledger_created` | `ForeignKey` | null, to: SpendLedger |
| `vendorscorecard_created` | `ForeignKey` | null, to: VendorScorecard |
| `evaluated_scorecards` | `ForeignKey` | null, to: VendorScorecard |
| `notification_created` | `ForeignKey` | null, to: Notification |
| `notifications` | `ForeignKey` | null, to: Notification |
| `exportjob_created` | `ForeignKey` | null, to: ExportJob |
| `export_jobs` | `ForeignKey` | null, to: ExportJob |
| `audit_logs` | `ForeignKey` | null, to: AuditLog |
| `password` | `CharField` | - |
| `last_login` | `DateTimeField` | null, blank |
| `is_superuser` | `BooleanField` | - |
| `username` | `CharField` | unique |
| `first_name` | `CharField` | blank |
| `last_name` | `CharField` | blank |
| `is_staff` | `BooleanField` | - |
| `is_active` | `BooleanField` | - |
| `date_joined` | `DateTimeField` | - |
| `id` | `UUIDField` | unique |
| `email` | `CharField` | unique |
| `phone_number` | `CharField` | blank |
| `role` | `ForeignKey` | null, blank, to: Role |
| `department` | `ForeignKey` | null, blank, to: Department |
| `vendor` | `ForeignKey` | null, blank, to: Vendor |
| `groups` | `ManyToManyField` | blank, to: Group |
| `user_permissions` | `ManyToManyField` | blank, to: Permission |

## Business Logic & Services
### `create_user_service(*, email, password, first_name='', last_name='', role=None, department=None, vendor=None)`
```text
Service layer function to create a new user with proper password hashing and atomic transaction.
```

### `update_user_role_service(*, user: apps.accounts.models.User, new_role: apps.accounts.models.Role)`
```text
Updates user assigned role safely within a database transaction.
```
