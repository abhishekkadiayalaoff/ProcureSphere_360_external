# OWASP Top 10 Security Checklist & Baseline — ProcureSphere 360

PRD Reference: HPE-PRD-2026-PROC01 / Section 2.1 & Section 12  
Application Target: Production Enterprise Deployment

---

## Security Verification Checklist

| OWASP Risk Category | Security Requirement / Control | Implementation Details | Status |
|---|---|---|---|
| A01: Broken Access Control | Backend RBAC enforcement & object scoping | Django REST Framework permission classes + Object-level queryset selectors. No frontend-only security. Positive and negative tests for every endpoint. | Planned / Baseline |
| A02: Cryptographic Failures | Password hashing, HTTPS, token security | Argon2 / PBKDF2 Django password hashing. HTTPS cookies (`SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`). JWT secret isolated in env vars. | Planned / Baseline |
| A03: Injection | ORM parameterization & command safety | 100% Django ORM parameterization. No raw SQL formatting (`cursor.execute(f"...")` prohibited). Input sanitization for exports. | Planned / Baseline |
| A04: Insecure Design | Business rule validation & state machines | Server-side state machine guards in `services.py`. Multi-level approval thresholds, budget locking, sealed bid window enforcement. | Planned / Baseline |
| A05: Security Misconfiguration | Secure headers & CORS restriction | Django Security Middleware enabled (`SECURE_BROWSER_XSS_FILTER`, `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS='DENY'`). Strict CORS origin whitelist. | Planned / Baseline |
| A06: Vulnerable Components | Pinned dependencies & scanner | `requirements.txt` with exact version pins. Automated vulnerability check & secret scan in CI workflow. | Planned / Baseline |
| A07: Identification & Auth | Throttling & multi-tenant isolation | `django-axes` login throttling (max 5 failed attempts per IP/user before temporary lockout). DRF API rate limiting. | Planned / Baseline |
| A08: Software & Data Integrity | Immutable audit log & non-destructive history | Append-only `AuditLog` records (create, update, delete, approval, login, export). Version preservation on POs and Contracts. | Planned / Baseline |
| A09: Security Logging | Correlation IDs & audit tracking | `RequestIDMiddleware` attaches unique `X-Request-ID` to every HTTP request and log record. Audit logs record actor, IP, timestamp, user agent. | Planned / Baseline |
| A10: Server-Side Request Forgery | Upload validation & restricted fetches | Strictly validated file uploads (extension, magic bytes MIME check, maximum size 10MB, randomized file storage path outside root). | Planned / Baseline |

---

## Secret Scanning & Compliance Confirmation
- `.env` excluded in `.gitignore`
- `.env.example` committed with placeholder values only
- Secret scan runner integrated into GitHub Actions CI
