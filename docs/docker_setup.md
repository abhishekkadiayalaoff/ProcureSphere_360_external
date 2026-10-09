# ProcureSphere 360 — Complete Docker Setup & Developer Guide

This guide provides step-by-step instructions for setting up and running **ProcureSphere 360** using Docker and Docker Compose. 

---

## 1. System Architecture Overview

The Docker environment runs **5 containerized microservices**:

| Container Name | Service | Purpose | Port Binding |
|---|---|---|---|
| **`procuresphere_web`** | Django App | Web UI, REST APIs (`/api/v1/`), Swagger Docs | `http://localhost:8000/` |
| **`procuresphere_db`** | PostgreSQL 15 | Relational Database (Normalized Schema) | `5432:5432` |
| **`procuresphere_redis`** | Redis 7 | Message Broker & In-Memory Cache | `6379:6379` |
| **`procuresphere_worker`** | Celery Worker | Asynchronous Background Job Processing | Internal |
| **`procuresphere_beat`** | Celery Beat | Scheduled Task Trigger (SLA Expiry Alerts) | Internal |

---

## 2. Prerequisites

Before starting, ensure you have installed:
1. **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** (Ensure Docker Engine is active and running).
2. **[Git](https://git-scm.com/downloads)**.
3. *(Windows users)* **WSL 2** enabled for Docker Desktop engine integration.

---

## 3. Step-by-Step Setup Instructions

### Step 1: Clone the Repository

```bash
git clone https://github.com/VPDTechnologies/ProcureSphere_360_Internal.git
cd ProcureSphere_360_Internal
```

---

### Step 2: Configure Environment Variables

Create your local `.env` configuration file from the template:

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

**Mac / Linux:**
```bash
cp .env.example .env
```

> **Note:** The `docker-compose.yml` automatically routes container traffic to the internal database (`db`) and Redis service (`redis`), so your local `.env` can safely co-exist with cloud or local database credentials.

---

### Step 3: Build and Start Containers

Run the following command to build the Docker images and boot all 5 services in detached mode:

```bash
docker compose up --build -d
```

*Note: The initial build downloads base images (`python:3.11-slim`, `postgres:15-alpine`, `redis:7-alpine`) and installs dependencies from `requirements.txt`.*

---

### Step 4: Seed Demonstration Data & Create User Accounts

Populate the database with realistic demonstration dataset across all 10 system roles, organization units, cost centers, sample requisitions, purchase orders, invoices, and contracts:

```bash
docker exec procuresphere_web python manage.py seed_demo_data
```

---

### Step 5: Access the Web Application

Open your browser and navigate to:

- 🌐 **ERP Main Application**: [http://localhost:8000/](http://localhost:8000/)
- 🔑 **Sign-In Portal**: [http://localhost:8000/admin/login/](http://localhost:8000/admin/login/)
- 📚 **OpenAPI / Swagger API Docs**: [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/)
- 💚 **Health Endpoint**: [http://localhost:8000/health/](http://localhost:8000/health/)

---

## 4. Default Demonstration Login Credentials

> **Default Password for All Accounts:** `Password123!`

| Role Name | Email / Username | Password | Access Purpose |
|---|---|---|---|
| **Super Admin** | `admin@hpe.com` | `Password123!` | System Config, Governance & All Masters |
| **Requester** | `requester@hpe.com` | `Password123!` | Create & Track Purchase Requisitions |
| **Department Approver** | `approver@hpe.com` | `Password123!` | Review PRs & Department Budget Limits |
| **Procurement Executive** | `procexec@hpe.com` | `Password123!` | Sourcing Events, Bids & PO Operations |
| **Procurement Manager** | `procmgr@hpe.com` | `Password123!` | Award Approvals & Vendor Governance |
| **Finance / AP** | `finance@hpe.com` | `Password123!` | Budget Review, 3-Way Match & Invoice Exceptions |
| **Stores / Receiver** | `receiver@hpe.com` | `Password123!` | Goods Receipt Notes (GRN) & Inspections |
| **Legal / Contract Manager** | `legal@hpe.com` | `Password123!` | Contract Reviews & Expiry Milestones |
| **Compliance Auditor** | `auditor@hpe.com` | `Password123!` | Read-Only Audit Log & Traceability |
| **Vendor User** | `vendoruser@cisco.com` | `Password123!` | Vendor Self-Service & Bidding Portal |

---

## 5. Daily Development & Maintenance Commands

### Check Running Containers
```bash
docker ps
```

### View Live Application Logs
```bash
# Stream logs for all containers
docker compose logs -f

# Stream logs for Django web server only
docker compose logs -f web

# Stream logs for Celery background worker
docker compose logs -f celery_worker
```

### Run Django Management Commands
```bash
# Create a new custom superuser
docker exec -it procuresphere_web python manage.py createsuperuser

# Reset login lockout attempts (django-axes)
docker exec procuresphere_web python manage.py axes_reset

# Run automated test suite inside container
docker exec procuresphere_web pytest
```

### Stop Containers
```bash
# Stop containers (preserves database data volume)
docker compose down

# Stop containers and remove volumes (fresh database reset)
docker compose down -v
```

---

## 6. Troubleshooting Common Issues

### Issue 1: "Account Temporarily Locked" Screen
- **Cause**: Exceeded 5 consecutive failed login attempts (`django-axes` lockout).
- **Fix**: Run `docker exec procuresphere_web python manage.py axes_reset` to unlock all accounts/IPs immediately.

### Issue 2: "exec /app/scripts/entrypoint.sh: no such file or directory"
- **Cause**: File saved with Windows `CRLF` (`\r\n`) line endings instead of Unix `LF` (`\n`).
- **Fix**: The `Dockerfile` includes `RUN sed -i 's/\r$//' /app/scripts/entrypoint.sh`. Simply re-run `docker compose up --build -d`.

### Issue 3: Docker Engine Not Found / Failed Connection to Docker API
- **Cause**: Docker Desktop is not running on your machine.
- **Fix**: Open **Docker Desktop** application on Windows/Mac and ensure the status indicator at the bottom left is green ("Engine running").
