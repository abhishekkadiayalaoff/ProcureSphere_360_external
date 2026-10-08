# ProcureSphere 360

> **Enterprise Procurement, Vendor & Contract Management ERP (Source-to-Pay + AP Workflow)**  
> **PRD Ref:** HPE-PRD-2026-PROC01 (VER-1.0-DRAFT)  
> **Issuing Authority:** HPE Team — Enterprise Technology Solutions & Delivery Oversight  
> **Development Partner:** VPD Technologies Pvt. Ltd.

---

## 1. Project Overview

ProcureSphere 360 is a fully traceable, database-backed enterprise ERP replacing email/spreadsheet procurement workflows. Every requisition, sourcing event, sealed vendor bid, purchase order, receipt note, invoice, contract, and approval is traceable to actor, state, timestamp, and supporting evidence in PostgreSQL.

---

## 2. Tech Stack

- **Backend:** Python 3.11+, Django 4.2+ LTS, Django REST Framework 3.14+
- **Database:** PostgreSQL 15+ (normalized schema, check constraints, FKs, index optimization)
- **Async & Scheduling:** Redis 7+, Celery 5+ (Worker + Celery Beat)
- **Frontend:** Django Templates + HTMX, HTML5/CSS3/ES6+, Bootstrap 5
- **API & Docs:** Versioned REST (`/api/v1/`), OpenAPI/Swagger via `drf-spectacular`
- **Security:** `django-axes` login throttling, SimpleJWT API auth, append-only `AuditLog`, role-based access control (RBAC)
- **Containerization:** Docker & Docker Compose

---

## 3. Local Development Setup

### Quickstart (PowerShell on Windows)

```powershell
# 1. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Environment configuration
copy .env.example .env

# 4. Run database migrations
python manage.py migrate

# 5. Seed realistic demonstration data
python manage.py seed_demo_data

# 6. Start development server
python manage.py runserver
```

### Async Worker & Scheduler

```powershell
# Run Celery Worker (Windows pool: solo)
celery -A config worker -l info -P solo

# Run Celery Beat Scheduler
celery -A config beat -l info
```

### Docker Setup

```powershell
docker compose up --build
```

---

## 4. Testing & Quality Commands

```powershell
# Run full test suite with coverage
pytest --cov=src

# Run linter and code style checks
ruff check .
black --check .
```

---

## 5. Documentation Map

- [`docs/assumptions.md`](file:///C:/Users/Dell/Desktop/ProcureSphere_360/docs/assumptions.md): Clarification & Query Register
- [`docs/rbac_matrix.md`](file:///C:/Users/Dell/Desktop/ProcureSphere_360/docs/rbac_matrix.md): System Roles & Access Matrix
- [`docs/security_checklist.md`](file:///C:/Users/Dell/Desktop/ProcureSphere_360/docs/security_checklist.md): OWASP Top 10 Security Controls
- [`docs/demo_scripts.md`](file:///C:/Users/Dell/Desktop/ProcureSphere_360/docs/demo_scripts.md): Day-90 Technical Acceptance Demonstrations
- [`docs/architecture.md`](file:///C:/Users/Dell/Desktop/ProcureSphere_360/docs/architecture.md): Architecture & Data Model Topology
- [`docs/PROGRESS.md`](file:///C:/Users/Dell/Desktop/ProcureSphere_360/docs/PROGRESS.md): Delivery Progress Tracker
