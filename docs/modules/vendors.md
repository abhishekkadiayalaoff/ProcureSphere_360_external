# Module: Vendors

## Overview
Detailed documentation for the `vendors` module in ProcureSphere 360.

## Database Models
### VendorCategory
VendorCategory(id, created_at, updated_at, created_by, name, code, description)

| Field | Type | Attributes |
|-------|------|------------|
| `vendors` | `ForeignKey` | null, to: Vendor |
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `name` | `CharField` | - |
| `code` | `CharField` | unique |
| `description` | `TextField` | blank |

### Vendor
Vendor(id, created_at, updated_at, created_by, legal_name, trade_name, vendor_number, tax_identification_number, registration_number, category, status, bank_name, bank_account_number, bank_routing_code, email, phone, address, status_notes)

| Field | Type | Attributes |
|-------|------|------------|
| `vendor_users` | `ForeignKey` | null, to: User |
| `contacts` | `ForeignKey` | null, to: VendorContact |
| `documents` | `ForeignKey` | null, to: VendorDocument |
| `risk_records` | `ForeignKey` | null, to: VendorRiskRecord |
| `bid_invitations` | `ForeignKey` | null, to: BidInvite |
| `bids` | `ForeignKey` | null, to: VendorBid |
| `clarifications` | `ForeignKey` | null, to: Clarification |
| `purchase_orders` | `ForeignKey` | null, to: PurchaseOrder |
| `invoices` | `ForeignKey` | null, to: SupplierInvoice |
| `contracts` | `ForeignKey` | null, to: Contract |
| `scorecards` | `ForeignKey` | null, to: VendorScorecard |
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `legal_name` | `CharField` | - |
| `trade_name` | `CharField` | blank |
| `vendor_number` | `CharField` | unique |
| `tax_identification_number` | `CharField` | unique |
| `registration_number` | `CharField` | blank |
| `category` | `ForeignKey` | to: VendorCategory |
| `status` | `CharField` | - |
| `bank_name` | `CharField` | blank |
| `bank_account_number` | `CharField` | blank |
| `bank_routing_code` | `CharField` | blank |
| `email` | `CharField` | - |
| `phone` | `CharField` | blank |
| `address` | `TextField` | - |
| `status_notes` | `TextField` | blank |

### VendorContact
VendorContact(id, created_at, updated_at, created_by, vendor, first_name, last_name, email, phone, designation, is_primary)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `vendor` | `ForeignKey` | to: Vendor |
| `first_name` | `CharField` | - |
| `last_name` | `CharField` | - |
| `email` | `CharField` | - |
| `phone` | `CharField` | blank |
| `designation` | `CharField` | blank |
| `is_primary` | `BooleanField` | - |

### VendorDocument
VendorDocument(id, created_at, updated_at, created_by, vendor, document_type, title, file, expiry_date, is_verified, verified_by)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `vendor` | `ForeignKey` | to: Vendor |
| `document_type` | `CharField` | - |
| `title` | `CharField` | - |
| `file` | `FileField` | - |
| `expiry_date` | `DateField` | null, blank |
| `is_verified` | `BooleanField` | - |
| `verified_by` | `ForeignKey` | null, blank, to: User |

### VendorRiskRecord
VendorRiskRecord(id, created_at, updated_at, created_by, vendor, risk_level, assessment_notes, assessed_by)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `vendor` | `ForeignKey` | to: Vendor |
| `risk_level` | `CharField` | - |
| `assessment_notes` | `TextField` | - |
| `assessed_by` | `ForeignKey` | to: User |

## Business Logic & Services
### `approve_vendor_service(*, vendor: apps.vendors.models.Vendor, manager: apps.accounts.models.User, notes: str = '') -> apps.vendors.models.Vendor`
```text
Approves Vendor and transitions state from KYC_REVIEW to APPROVED and ACTIVE.
```

### `register_vendor_service(*, legal_name: str, tax_identification_number: str, category: apps.vendors.models.VendorCategory, email: str, address: str, trade_name: str = '', registration_number: str = '', phone: str = '', bank_name: str = '', bank_account_number: str = '', bank_routing_code: str = '', created_by_user: apps.accounts.models.User = None) -> apps.vendors.models.Vendor`
```text
Registers a new vendor in DRAFT status with unique vendor number.
```

### `set_vendor_status_governance_service(*, vendor: apps.vendors.models.Vendor, actor: apps.accounts.models.User, new_status: str, notes: str) -> apps.vendors.models.Vendor`
```text
Governance service to set vendor status (HOLD, SUSPENDED, ACTIVE, REJECTED).
```

### `start_kyc_review_service(*, vendor: apps.vendors.models.Vendor, reviewer: apps.accounts.models.User) -> apps.vendors.models.Vendor`
```text
Transitions Vendor state to KYC_REVIEW.
```

### `submit_vendor_kyc_service(*, vendor: apps.vendors.models.Vendor, user: apps.accounts.models.User) -> apps.vendors.models.Vendor`
```text
Transitions Vendor state from DRAFT to SUBMITTED.
```

### `update_vendor_profile_service(*, vendor: apps.vendors.models.Vendor, user: apps.accounts.models.User, data: dict) -> apps.vendors.models.Vendor`
```text
Vendor self-service profile update: updates trade name, address, phone, and banking info.
Legal name, TIN, vendor number, and category are locked and require governance approval.
```

### `upload_vendor_document_service(*, vendor: apps.vendors.models.Vendor, user: apps.accounts.models.User, file, document_type: str, title: str = '', expiry_date=None) -> apps.vendors.models.VendorDocument`
```text
Uploads a KYC or compliance document for a vendor.
```

### `verify_vendor_document_service(*, document: apps.vendors.models.VendorDocument, verifier: apps.accounts.models.User) -> apps.vendors.models.VendorDocument`
```text
Marks a KYC document as verified.
```
