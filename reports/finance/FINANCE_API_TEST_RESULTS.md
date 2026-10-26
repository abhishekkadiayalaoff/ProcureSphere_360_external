# Finance Dashboard — API Test Results

## 1. Test Objective
This suite verifies the API endpoints for the Finance Dashboard, ensuring proper role-based access control, payload validation, and correct endpoint functionality for invoices and matching.

## 2. Scope
- `/api/v1/invoices/` (GET, POST)
- `/api/v1/invoices/{id}/` (GET)
- `/api/v1/invoices/{id}/match/` (POST)
- `/api/v1/invoices/{id}/exceptions/` (GET, PATCH)

## 3. Test Environment
- Python version: 3.11.x
- Django / DRF: 4.2.x / 3.14.x
- API Client: `APIClient` from `rest_framework.test`
- Branch: main

## 4. Test Execution Command
```bash
pytest tests/ -v -m "api and finance"
```

## 5. Test Summary
| Metric | Result |
|---|---:|
| Total Tests | 22 |
| Passed | 0 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 0 |
| Blocked | 22 |
| Execution Time | 0.0s |
| Coverage | Not measured |

## 6. Detailed Test Results
| Test ID | Test Scenario | Expected Result | Actual Result | Status |
|---|---|---|---|---|
| FIN-API-001 | Unauthenticated access to `/invoices/` | 401 Unauthorized | N/A | BLOCKED |
| FIN-API-002 | Access by non-Finance role | 403 Forbidden | N/A | BLOCKED |
| FIN-API-003 | Access by Finance role | 200 OK | N/A | BLOCKED |
| FIN-API-004 | POST `/invoices/` with valid payload | 201 Created | N/A | BLOCKED |
| FIN-API-005 | POST `/invoices/{id}/match/` | 200 OK, triggers match | N/A | BLOCKED |
| FIN-API-006 | PATCH `/exceptions/{id}/` to resolve | 200 OK | N/A | BLOCKED |

## 7. Failed / Blocked Tests
### Test ID: All API Tests
### Scenario: API Test Execution
### Expected: API tests run successfully.
### Actual: Tests failed to start.
### Error: `The type initializer for 'System.Management.Automation.TypeAccelerators' threw an exception.`
### Root Cause: Windows PowerShell environment error preventing pytest execution.
### Severity: High (Blocker for CI/CD)
### Recommended Action: Fix PowerShell environment or run inside Docker container.

## 8. Defect Summary
| Defect ID | Test ID | Description | Severity | Status |
|---|---|---|---|---|
| ENV-001 | All | Pytest execution fails due to PowerShell TypeAccelerators exception | Critical | OPEN |

## 9. Coverage / Requirement Mapping
| Requirement / Feature | Test IDs | Status |
|---|---|---|
| API Auth / Roles | FIN-API-001 - 003 | BLOCKED |
| Invoice Match Endpoint | FIN-API-005 | BLOCKED |

## 10. Final Assessment
BLOCKED
Unable to verify API due to environment execution failures.
