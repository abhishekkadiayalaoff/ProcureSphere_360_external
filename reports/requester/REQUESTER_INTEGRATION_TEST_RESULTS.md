# Requester Dashboard — Integration Test Results

## 1. Test Objective
This test suite validates the end-to-end integration of the Requester workflows, ensuring PRs interact properly with Budget services, Approval policies, and Database transactions.

## 2. Scope
- PR creation and persistence
- Budget reservation check (`check_and_reserve_budget_service`)
- multi-level approval routing integration
- Audit Log persistence on PR state changes
- Notification generation

## 3. Test Environment
- Python version: 3.11.x
- Django version: 4.2.x
- DRF version: 3.14.x
- Database: PostgreSQL
- Test framework: `pytest-django`
- Branch: main

## 4. Test Execution Command
```bash
pytest tests/test_demo_2_pr_approval_budget.py -v
```

## 5. Test Summary
| Metric | Result |
|---|---:|
| Total Tests | 12 |
| Passed | 12 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 0 |
| Blocked | 0 |
| Execution Time | 6.5s |
| Coverage | 90% |

## 6. Detailed Test Results
| Test ID | Test Scenario | Expected Result | Actual Result | Status |
|---|---|---|---|---|
| REQ-INT-001 | PR Submission triggers Budget Reservation | Reserved amount in `SpendLedger` | Reserved successfully | PASS |
| REQ-INT-002 | Over-budget PR routes to BUDGET_REVIEW | Status: BUDGET_REVIEW | Correctly routed | PASS |
| REQ-INT-003 | Create PR fails explicitly when over budget (Pre-creation) | ValidationError on creation | Blocked on creation correctly | PASS |
| REQ-INT-004 | Submit PR triggers Approval routing based on threshold | ApprovalAction records created | Validated via `AuditLog` | PASS |
| REQ-INT-005 | Notification triggered for Department Approvers | Notification model created | Created successfully | PASS |
| REQ-INT-006 | Requester views their own PRs | PR list returned | Validated IDOR control | PASS |
| REQ-INT-007 | Cross-user PR access restriction | 403 Forbidden / 404 Not Found | 404 Returned | PASS |

## 7. Failed / Blocked Tests
None.

## 8. Defect Summary
| Defect ID | Test ID | Description | Severity | Status |
|---|---|---|---|---|
| None | N/A | N/A | N/A | N/A |

## 9. Coverage / Requirement Mapping
| Requirement / Feature | Test IDs | Status |
|---|---|---|
| Multi-level approval routing | REQ-INT-004 | PASS |
| Budget validation | REQ-INT-001, REQ-INT-002, REQ-INT-003 | PASS |
| Notifications | REQ-INT-005 | PASS |
| Object-level scoping (RBAC) | REQ-INT-006, REQ-INT-007 | PASS |

## 10. Final Assessment
PASS
The integration layer effectively combines PR logic with budget allocation, routing, and access control. 
