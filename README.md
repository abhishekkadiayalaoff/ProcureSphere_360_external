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

For complete step-by-step instructions, see the **[Docker Setup & Troubleshooting Guide](docs/docker_setup.md)**.

```powershell
# 1. Build and boot all 5 containers
docker compose up --build -d

# 2. Seed realistic demonstration dataset & 10 role accounts
docker exec procuresphere_web python manage.py seed_demo_data
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

- [`docs/docker_setup.md`](docs/docker_setup.md): Complete Docker Setup & Troubleshooting Guide
- [`docs/assumptions.md`](docs/assumptions.md): Clarification & Query Register
- [`docs/rbac_matrix.md`](docs/rbac_matrix.md): System Roles & Access Matrix
- [`docs/security_checklist.md`](docs/security_checklist.md): OWASP Top 10 Security Controls
- [`docs/demo_scripts.md`](docs/demo_scripts.md): Day-90 Technical Acceptance Demonstrations
- [`docs/architecture.md`](docs/architecture.md): Architecture & Data Model Topology
- [`docs/PROGRESS.md`](docs/PROGRESS.md): Delivery Progress Tracker
