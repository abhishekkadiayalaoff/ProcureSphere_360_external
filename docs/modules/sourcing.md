# Module: Sourcing

## Overview
Detailed documentation for the `sourcing` module in ProcureSphere 360.

## Database Models
### SourcingEvent
SourcingEvent(id, created_at, updated_at, created_by, event_number, title, event_type, requisition, status, bid_start_date, bid_end_date, is_sealed, description, technical_requirements, commercial_requirements, required_documents)

| Field | Type | Attributes |
|-------|------|------------|
| `invitations` | `ForeignKey` | null, to: BidInvite |
| `bids` | `ForeignKey` | null, to: VendorBid |
| `award_decision` | `OneToOneField` | null, to: AwardDecision |
| `evaluations` | `ForeignKey` | null, to: BidEvaluation |
| `clarifications` | `ForeignKey` | null, to: Clarification |
| `purchase_orders` | `ForeignKey` | null, to: PurchaseOrder |
| `contracts` | `ForeignKey` | null, to: Contract |
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `event_number` | `CharField` | unique |
| `title` | `CharField` | - |
| `event_type` | `CharField` | - |
| `requisition` | `ForeignKey` | null, blank, to: PurchaseRequisition |
| `status` | `CharField` | - |
| `bid_start_date` | `DateTimeField` | - |
| `bid_end_date` | `DateTimeField` | - |
| `is_sealed` | `BooleanField` | - |
| `description` | `TextField` | - |
| `technical_requirements` | `TextField` | blank |
| `commercial_requirements` | `TextField` | blank |
| `required_documents` | `TextField` | blank |

### BidInvite
BidInvite(id, created_at, updated_at, created_by, event, vendor, is_responded)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `event` | `ForeignKey` | to: SourcingEvent |
| `vendor` | `ForeignKey` | to: Vendor |
| `is_responded` | `BooleanField` | - |

### VendorBid
VendorBid(id, created_at, updated_at, created_by, event, vendor, bid_number, version, total_bid_amount, status, proposal_summary, technical_proposal, commercial_proposal, submitted_at)

| Field | Type | Attributes |
|-------|------|------------|
| `versions` | `ForeignKey` | null, to: BidVersion |
| `attachments` | `ForeignKey` | null, to: BidAttachment |
| `lines` | `ForeignKey` | null, to: BidLine |
| `awards` | `ForeignKey` | null, to: AwardDecision |
| `evaluations` | `ForeignKey` | null, to: BidEvaluation |
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `event` | `ForeignKey` | to: SourcingEvent |
| `vendor` | `ForeignKey` | to: Vendor |
| `bid_number` | `CharField` | unique |
| `version` | `PositiveIntegerField` | - |
| `total_bid_amount` | `DecimalField` | - |
| `status` | `CharField` | - |
| `proposal_summary` | `TextField` | blank |
| `technical_proposal` | `TextField` | blank |
| `commercial_proposal` | `TextField` | blank |
| `submitted_at` | `DateTimeField` | null, blank |

### BidVersion
Immutable historical snapshot of each submitted and amended bid version.

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `bid` | `ForeignKey` | to: VendorBid |
| `version_number` | `PositiveIntegerField` | - |
| `status` | `CharField` | - |
| `total_bid_amount` | `DecimalField` | - |
| `proposal_summary` | `TextField` | blank |
| `technical_proposal` | `TextField` | blank |
| `commercial_proposal` | `TextField` | blank |
| `amendment_reason` | `TextField` | blank |
| `submitted_at` | `DateTimeField` | null, blank |
| `snapshot_data` | `JSONField` | blank |

### BidAttachment
Documents / attachments uploaded by vendor as part of technical or commercial bid submission.

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `bid` | `ForeignKey` | to: VendorBid |
| `title` | `CharField` | - |
| `document_type` | `CharField` | - |
| `file` | `FileField` | - |
| `file_size` | `PositiveIntegerField` | - |

### BidLine
BidLine(id, created_at, updated_at, created_by, bid, pr_line, item_description, quantity, quoted_unit_price, quoted_total_price)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `bid` | `ForeignKey` | to: VendorBid |
| `pr_line` | `ForeignKey` | null, blank, to: PRLine |
| `item_description` | `CharField` | - |
| `quantity` | `DecimalField` | - |
| `quoted_unit_price` | `DecimalField` | - |
| `quoted_total_price` | `DecimalField` | - |

### AwardDecision
AwardDecision(id, created_at, updated_at, created_by, event, winning_bid, award_reason, approved_by)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `event` | `OneToOneField` | unique, to: SourcingEvent |
| `winning_bid` | `ForeignKey` | to: VendorBid |
| `award_reason` | `TextField` | - |
| `approved_by` | `ForeignKey` | to: User |

### BidEvaluation
BidEvaluation(id, created_at, updated_at, created_by, event, bid, evaluator, technical_score, commercial_score, weighted_total_score, comments)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `event` | `ForeignKey` | to: SourcingEvent |
| `bid` | `ForeignKey` | to: VendorBid |
| `evaluator` | `ForeignKey` | to: User |
| `technical_score` | `DecimalField` | - |
| `commercial_score` | `DecimalField` | - |
| `weighted_total_score` | `DecimalField` | - |
| `comments` | `TextField` | blank |

### Clarification
Clarification(id, created_at, updated_at, created_by, event, vendor, question, answer, answered_by, answered_at, status)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `event` | `ForeignKey` | to: SourcingEvent |
| `vendor` | `ForeignKey` | to: Vendor |
| `question` | `TextField` | - |
| `answer` | `TextField` | blank |
| `answered_by` | `ForeignKey` | null, blank, to: User |
| `answered_at` | `DateTimeField` | null, blank |
| `status` | `CharField` | - |

## Business Logic & Services
### `amend_vendor_bid_service(*, bid: apps.sourcing.models.VendorBid, vendor_user: apps.accounts.models.User, amendment_reason: str, line_items: list, proposal_summary: str = '', technical_proposal: str = '', commercial_proposal: str = '') -> apps.sourcing.models.VendorBid`
```text
Amends a submitted bid while the event is still open.
Preserves prior version as an immutable BidVersion snapshot, creates new version, and audits.
Rejects amendment if deadline has passed or event is not in BID_WINDOW.
```

### `ask_clarification_service(*, event: apps.sourcing.models.SourcingEvent, vendor: apps.vendors.models.Vendor, user: apps.accounts.models.User, question: str) -> apps.sourcing.models.Clarification`
```text
Submits a clarification question from an invited vendor for a sourcing event.
```

### `create_sourcing_event_service(*, title: str, event_type: str, bid_start_date, bid_end_date, description: str, technical_requirements: str = '', commercial_requirements: str = '', required_documents: str = '', requisition=None, created_by_user: apps.accounts.models.User = None) -> apps.sourcing.models.SourcingEvent`
```text
Creates a new RFQ/RFP sourcing event in DRAFT status.
```

### `evaluate_and_award_sourcing_event_service(*, event: apps.sourcing.models.SourcingEvent, winning_bid: apps.sourcing.models.VendorBid, award_reason: str, approved_by_user: apps.accounts.models.User) -> apps.sourcing.models.AwardDecision`
```text
Executes technical/commercial evaluation completion and records AwardDecision.
Transitions event status to AWARDED.
```

### `invite_vendors_to_event_service(*, event: apps.sourcing.models.SourcingEvent, vendor_ids: list, invited_by: apps.accounts.models.User) -> list`
```text
Invites active eligible vendors to participate in a sourcing event.
Blocks suspended/blacklisted vendors.
```

### `publish_sourcing_event_service(*, event: apps.sourcing.models.SourcingEvent, user: apps.accounts.models.User) -> apps.sourcing.models.SourcingEvent`
```text
Publishes a sourcing event and opens the bid window.
```

### `save_draft_bid_service(*, event: apps.sourcing.models.SourcingEvent, vendor: apps.vendors.models.Vendor, user: apps.accounts.models.User, line_items: list = None, proposal_summary: str = '', technical_proposal: str = '', commercial_proposal: str = '') -> apps.sourcing.models.VendorBid`
```text
Saves or updates a vendor's bid in DRAFT status.
```

### `submit_vendor_bid_service(*, event: apps.sourcing.models.SourcingEvent, vendor: apps.vendors.models.Vendor, line_items: list, proposal_summary: str = '', technical_proposal: str = '', commercial_proposal: str = '', submitted_by_user: apps.accounts.models.User = None) -> apps.sourcing.models.VendorBid`
```text
Submits a sealed bid for a vendor during the BID_WINDOW.
Enforces server-side deadline, authorization, atomic transaction, versioning, and audit log.
```

### `upload_bid_attachment_service(*, bid: apps.sourcing.models.VendorBid, user: apps.accounts.models.User, file, title: str = '', document_type: str = 'TECHNICAL') -> apps.sourcing.models.BidAttachment`
```text
Attaches a validated document to a vendor bid.
```

### `validate_bid_service(*, bid: apps.sourcing.models.VendorBid) -> dict`
```text
Authoritative server-side bid validation.
Checks authorization, status, deadline, completeness, line item pricing, and attachments.
```
