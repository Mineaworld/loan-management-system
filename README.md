# Sovanaphum Microfinance Loan Management System (LMS)
### Dual-Portal Cambodian Microfinance & Commercial Lending Platform (NBC Standard)

[![Django](https://img.shields.io/badge/Django-5.2%2B-092E20?logo=django)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql)](https://www.postgresql.org/)
[![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?logo=bootstrap)](https://getbootstrap.com/)
[![Tests](https://img.shields.io/badge/Tests-79%20Passed-brightgreen)](#automated-testing)

---

## 📌 Project Overview

An institutional, bilingual (Khmer-first with English toggle) Loan Management System modeling **Sovanaphum Microfinance Plc. (SMP)** (គ្រឹះស្ថានមីក្រូហិរញ្ញវត្ថុ សុវណ្ណភូមិ ភីអិលស៊ី), a licensed Deposit-Taking Microfinance Institution (MDI) operating under National Bank of Cambodia (NBC) regulatory standards.

The system implements strict Role-Based Access Control (RBAC) across two dedicated operational portals:
- **Borrower Portal** (`/borrower/`): Loan application intake with live reducing-balance monthly installment (EMI) estimate, dedicated servicing Credit Officer contact card, 24-month amortization schedule, Bakong KHQR instant payment simulation, and bank transfer receipt slip upload.
- **Credit Officer Dashboard** (`/officer/`): Underwriting review queues with multi-tab coverage ("My Covered Borrowers", "Unassigned Applications", "All Branch Applications"), Simulated Credit Bureau Cambodia (CBC) scorecard widget with Debt-to-Income (DTI) and Collateral Coverage Ratio (CCR) calculations, atomic loan disbursal, payment slip verification, and statutory NBC 5-Tier Asset Quality Classification reports with one-click CSV export.

---

## 🏗️ System Architecture

The platform is structured into modular Django applications following domain-driven design:

- **`apps.accounts`**: Custom User model (`AbstractUser`), multi-role RBAC (`BORROWER`, `OFFICER`, `ADMIN`), Branch network entities (Head Office + 4 Provincial Branches), staff management, and profile extensions.
- **`apps.loans`**: 6 Cambodian loan products (SME, Personal, Agriculture, Auto, Housing, Education), application lifecycle state machine, collateral appraisal, Simulated CBC credit scoring engine, and atomic disbursal with amortization schedule generation.
- **`apps.repayments`**: Persistent database installment tracking, Bakong KHQR digital payment simulation, payment slip upload, and officer verification workflows.
- **`apps.reports`**: NBC 5-Tier Asset Quality Classification, Portfolio-at-Risk (PAR 30 / PAR 90) metrics, and UTF-8 BOM statutory CSV export.

---

## 🚀 Quick Start (Running Locally)

### 1. Clone & Set Up Virtual Environment

```bash
git clone https://github.com/Mineaworld/loan-management-system.git
cd loan-management-system

python -m venv venv
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Linux / macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment

Copy the provided environment template:

```bash
cp .env.example .env
```

### 3. Database Setup & Migrations

**Option A: PostgreSQL via Docker (Recommended)**
```bash
docker compose up -d db
python manage.py migrate
```

**Option B: SQLite Fallback (No Docker Required)**
Set `USE_SQLITE=True` in your `.env` file, then:
```bash
python manage.py migrate
```

### 4. Seed Demo Data

Provision demo accounts, loan products, collaterals, active loan schedules, and sample receipts:

```bash
python manage.py seed_demo_data
```

### 5. Launch Development Server

```bash
python manage.py runserver 127.0.0.1:8000
```

Access the system at **`http://127.0.0.1:8000/`** (automatically redirects to `/accounts/auth/`).

---

## 🔑 Pre-Configured Demo Credentials

| Role | Username | Password | Default Redirect | Highlights |
| :--- | :--- | :--- | :--- | :--- |
| **Active Borrower** | `borrower1` | `pass123` | `/borrower/` | Has an active $12,000 SME loan with 24-month schedule, upcoming due installment #1 ($556.51), and Bakong KHQR card. |
| **Fresh Applicant** | `borrower2` | `pass123` | `/borrower/` | Has a submitted $2,000 personal loan application; ideal for testing intake and underwriting. |
| **Credit Officer** | `officer1` | `pass123` | `/officer/` | Credit Underwriting Department officer; can access CBC scores, approve/reject applications, disburse loans, and verify payment slips. |
| **Super Admin** | `admin` | `pass123` | `/officer/` | Superuser account with full staff management modal and Django admin access (`/admin/`). |

---

## 🧪 Automated Testing

The codebase includes comprehensive unit and integration test coverage across financial calculation formulas, permissions, and atomic workflows:

```bash
python manage.py test apps.accounts apps.loans
```

```text
Ran 79 tests in 347.662s
OK
System check identified no issues (0 silenced).
```

---

## 🏛️ Academic Context

Developed as a Year 4 Semester 1 Advanced Python / Django Capstone Project at **SETEC Institute**, Phnom Penh, Cambodia (Academic Year 2026).
