# Module: Scorecards

## Overview
Detailed documentation for the `scorecards` module in ProcureSphere 360.

## Database Models
### VendorScorecard
VendorScorecard(id, created_at, updated_at, created_by, vendor, evaluation_period, delivery_score, quality_score, price_score, compliance_score, composite_score, evaluator_comments, evaluated_by)

| Field | Type | Attributes |
|-------|------|------------|
| `id` | `UUIDField` | unique |
| `created_at` | `DateTimeField` | blank |
| `updated_at` | `DateTimeField` | blank |
| `created_by` | `ForeignKey` | null, blank, to: User |
| `vendor` | `ForeignKey` | to: Vendor |
| `evaluation_period` | `CharField` | - |
| `delivery_score` | `DecimalField` | - |
| `quality_score` | `DecimalField` | - |
| `price_score` | `DecimalField` | - |
| `compliance_score` | `DecimalField` | - |
| `composite_score` | `DecimalField` | - |
| `evaluator_comments` | `TextField` | blank |
| `evaluated_by` | `ForeignKey` | to: User |

## Business Logic & Services
### `calculate_vendor_scorecard_service(*, vendor: apps.vendors.models.Vendor, evaluation_period: str, evaluated_by_user, comments: str = '') -> apps.scorecards.models.VendorScorecard`
```text
Computes performance scorecard for a Vendor using transactional indicators:
- Delivery score (30%): Delivery timeliness across GRNs.
- Quality score (30%): Acceptance rate (quantity_accepted / quantity_received).
- Price score (20%): Budget & contract price adherence.
- Compliance score (20%): KYC & regulatory status.
```
