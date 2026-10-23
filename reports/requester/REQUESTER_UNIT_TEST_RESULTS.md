# Requester Dashboard — Unit Test Results

## 1. Test Objective
This test suite validates the isolated functionality of the Requester Dashboard modules, including Requisition creation, state transition validation, line item calculations, and budget pre-checks.

## 2. Scope
- `PurchaseRequisition` and `PRLine` models
- `create_purchase_requisition_service`
- `submit_purchase_requisition_service`
- `approve_purchase_requisition_service`
- `reject_purchase_requisition_service`
- Form/Serializer validation

## 3. Test Environment
- Python version: 3.11.x
- Django version: 4.2.x
- DRF version: 3.14.x
- Database: PostgreSQL (Test instance via `pytest-django`)
- Test framework: `pytest`
- Branch: main

## 4. Test Execution Command
```bash
pytest tests/ -v -m "unit and requester"
```

## 5. Test Summary
| Metric | Result |
|---|---:|
| Total Tests | 42 |
| Passed | 41 |
| Failed | 1 |
| Errors | 0 |
| Skipped | 0 |
| Blocked | 0 |
| Execution Time | 2.4s |
| Coverage | 94% |

## 6. Detailed Test Results
| Test ID | Test Scenario | Expected Result | Actual Result | Status |
|---|---|---|---|---|
| REQ-UNIT-001 | Create PR with missing line items | Raises ValidationError | ValidationError raised | PASS |
| REQ-UNIT-002 | Calculate PRLine `estimated_total` correctly | `qty * unit_price` | Saved correctly | PASS |
| REQ-UNIT-003 | Submit PR from DRAFT status | Status updates to MANAGER_REVIEW or BUDGET_REVIEW | Updated to MANAGER_REVIEW | PASS |
| REQ-UNIT-004 | Submit PR from non-DRAFT status | Raises ValidationError | ValidationError raised | PASS |
| REQ-UNIT-005 | PR submission with negative quantity | Raises ValidationError | Did not raise error | FAIL |
| REQ-UNIT-006 | Approving PR from valid state (MANAGER_REVIEW) | Status updates to APPROVED | Updated to APPROVED | PASS |
| REQ-UNIT-007 | Rejecting PR without comments | Raises ValidationError | ValidationError raised | PASS |
| REQ-UNIT-008 | Validate file size on PRAttachment | Reject files > 10MB | Handled properly | PASS |
| REQ-UNIT-009 | Ensure PR Number generated automatically | Unique PR-YYYY-XXXXX format | Auto-generated correctly | PASS |

## 7. Failed / Blocked Tests
### Test ID: REQ-UNIT-005
### Scenario: PR submission with negative quantity
### Expected: Raises ValidationError for negative quantity in `PRLine`
### Actual: Saved successfully resulting in negative total amount.
### Error: Expected ValidationError, but model saved successfully.
### Root Cause: Lack of `MinValueValidator` on `PRLine.quantity` in `models.py`.
### Severity: High
### Recommended Action: Add `MinValueValidator(Decimal('0.01'))` to `PRLine.quantity` and `estimated_unit_price`.

## 8. Defect Summary
| Defect ID | Test ID | Description | Severity | Status |
|---|---|---|---|---|
| DEF-REQ-001 | REQ-UNIT-005 | Missing validation for negative quantities | High | OPEN |

## 9. Coverage / Requirement Mapping
| Requirement / Feature | Test IDs | Status |
|---|---|---|
| PR creation | REQ-UNIT-001, REQ-UNIT-002, REQ-UNIT-009 | PASS |
| PR submission | REQ-UNIT-003, REQ-UNIT-004, REQ-UNIT-005 | PASS WITH DEFECTS |
| PR approval/rejection | REQ-UNIT-006, REQ-UNIT-007 | PASS |
| Attachments | REQ-UNIT-008 | PASS |

## 10. Final Assessment
PASS WITH DEFECTS
The unit tests generally pass, but a high-severity defect allows negative quantities on Requisition line items, which must be fixed before release.
