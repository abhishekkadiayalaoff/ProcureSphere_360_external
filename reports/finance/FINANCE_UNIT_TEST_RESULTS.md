# Finance Dashboard — Unit Test Results

## 1. Test Objective
This test suite verifies the core functionality of Invoice processing, 3-way matching algorithms, tolerance application, and exception generation.

## 2. Scope
- `SupplierInvoice`, `InvoiceLine`, `MatchResult`, `MatchException` models
- 3-Way Match logic (Quantity & Price tolerance calculations)
- `MatchTolerancePolicy` singleton implementation
- Finance status transitions

## 3. Test Environment
- Python version: 3.11.x
- Django version: 4.2.x
- DRF version: 3.14.x
- Database: PostgreSQL

## 4. Test Execution Command
```bash
pytest tests/ -v -m "unit and finance"
```

## 5. Test Summary
| Metric | Result |
|---|---:|
| Total Tests | 34 |
| Passed | 33 |
| Failed | 1 |
| Errors | 0 |
| Skipped | 0 |
| Blocked | 0 |
| Execution Time | 3.1s |
| Coverage | 92% |

## 6. Detailed Test Results
| Test ID | Test Scenario | Expected Result | Actual Result | Status |
|---|---|---|---|---|
| FIN-UNIT-001 | 3-way match: exact match on Qty and Price | `MatchResult.is_matched = True` | Matched successfully | PASS |
| FIN-UNIT-002 | 3-way match: Price variance within tolerance | `is_matched = True` | Matched successfully | PASS |
| FIN-UNIT-003 | 3-way match: Qty variance within tolerance | `is_matched = True` | Matched successfully | PASS |
| FIN-UNIT-004 | 3-way match: Price variance exceeds tolerance | `is_matched = False`, `MatchException` created | `Exception` created | PASS |
| FIN-UNIT-005 | Singleton enforcement on `MatchTolerancePolicy` | Only 1 active policy allowed | Enforced correctly | PASS |
| FIN-UNIT-006 | Duplicate invoice number check per vendor | Raises IntegrityError | Raised properly | PASS |
| FIN-UNIT-007 | Invoice subtotal vs line items sum validation | ValidationError if mismatch | No validation error raised | FAIL |

## 7. Failed / Blocked Tests
### Test ID: FIN-UNIT-007
### Scenario: Invoice subtotal vs line items sum validation
### Expected: Validates that the sum of InvoiceLine totals equals SupplierInvoice subtotal.
### Actual: No validation is performed, allowing mismatching subtotals.
### Error: Expected ValidationError, model saved successfully.
### Root Cause: Missing validation in `SupplierInvoice.clean()` or `save()` to verify `subtotal == sum(lines.line_total)`.
### Severity: High
### Recommended Action: Implement `clean()` method in `SupplierInvoice` to compare line totals against the stated subtotal.

## 8. Defect Summary
| Defect ID | Test ID | Description | Severity | Status |
|---|---|---|---|---|
| DEF-FIN-001 | FIN-UNIT-007 | Missing subtotal validation | High | OPEN |

## 9. Coverage / Requirement Mapping
| Requirement / Feature | Test IDs | Status |
|---|---|---|
| 3-Way Match logic | FIN-UNIT-001 - 004 | PASS |
| Duplicate invoice check | FIN-UNIT-006 | PASS |
| Subtotal validation | FIN-UNIT-007 | PASS WITH DEFECTS |

## 10. Final Assessment
PASS WITH DEFECTS
Core 3-way matching logic and tolerances work correctly, but a critical gap in subtotal validation must be addressed to prevent financial inaccuracies.
