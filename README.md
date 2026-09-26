# AssureX Claim Engine

> **Dual-Model Warranty Claim Adjudication & Fraud Detection Platform**  
> *NextWave AI & ML — Aptech Limited*

---

## Project Overview

**AssureX Claim Engine** is an automated warranty claims processing system that combines **Python Tabular Machine Learning** (Random Forest / Gradient Boosting) with **Google Teachable Machine Vision Models** to evaluate warranty claims in real time.

The system handles fraud detection, OCR receipt extraction, SHA-256 document hashing, configurable warranty policies, and an 8-stage claims lifecycle tracker with manual review support.

```
       +--------------------------------------------------------------+
       |                  Customer Claim Submission                   |
       +------------------------------+-------------------------------+
                                      |
                      +---------------+---------------+
                      |                               |
                      v                               v
        +---------------------------+   +---------------------------+
        |   Python Tabular Model    |   |    GTM Summary Card AI    |
        | (Features & Risk Metrics) |   | (640x420 Visual Card OCR) |
        +-------------+-------------+   +-------------+-------------+
                      |                               |
                      +---------------+---------------+
                                      |
                                      v
                        +---------------------------+
                        |   Dual-Model Comparator   |
                        | (5 Consistency Statuses)  |
                        +-------------+-------------+
                                      |
                                      v
                        +---------------------------+
                        |  Warranty Rules & Fraud   |
                        |  (Policy + Contradiction) |
                        +-------------+-------------+
                                      |
                                      v
                        +---------------------------+
                        |   Master Decision Engine  |
                        | (3-Class Final Decision)  |
                        +---------------------------+
```

---

## Key Architectural Standards

### 3 Claim Classes
1. **`Valid Claim`** — Covered fault, active warranty, verified serial, model consensus.
2. **`Invalid Claim`** — Policy violation, excluded damage, expired warranty, or fraud flag.
3. **`Manual Review`** — Borderline conditions, model disagreement, low confidence, or date discrepancy.

### 5 Model-Consistency Statuses
1. **`Strong Match`** — Both models predict identical class with $|\Delta\text{conf}| \le 0.15$.
2. **`Acceptable Match`** — Both models predict identical class with $0.15 < |\Delta\text{conf}| \le 0.30$.
3. **`Weak Match`** — Both models predict identical class with $|\Delta\text{conf}| > 0.30$.
4. **`Model Disagreement`** — Conflicting class predictions between models; routes to Manual Review.
5. **`Uncertain Result`** — Either model confidence falls below configurable threshold ($0.60$).

### 8 Claim Lifecycle Stages
`Draft` $\to$ `Submitted` $\to$ `Under Evaluation` $\to$ `Additional Information Required` $\to$ `Manual Review` $\to$ `Approved` $\to$ `Rejected` $\to$ `Closed`

---

## Quick-Start Login Credentials

| Role | Email | Password | Access Scope |
|:---|:---|:---|:---|
| **System Administrator** | `admin@assurex.local` | `AdminPass123!` | Admin Portal, User Management (RBAC), Policies, Analytics, Audit Trail |
| **Claims Reviewer** | `reviewer@assurex.local` | `ReviewerPass123!` | Reviewer Queue, Claim Inspection, Adjudication Decision Overrides |
| **Customer / Claimant** | `customer@assurex.local` | `CustomerPass123!` | Customer Portal, Product Fleet, Intake Wizard, Tracking |
| **Service Center Staff** | `staff@assurex.local` | `StaffPass123!` | Service Hub Maintenance Records, Repair Logging |

---

## Role-Based Access Control (RBAC) & Security Architecture

AssureX Claim Engine enforces an enterprise-grade, defense-in-depth Role-Based Access Control (RBAC) framework strictly compliant with **Aptech SRS Sections 1.6.i, 1.6.ii, 1.6.xlvii (Audit Trail), and 1.6.l (Monitoring & Anomaly Alerts)**.

### Canonical Roles & Privileges
1. **`administrator`** (`Config.ROLE_ADMIN`): Full governance over user accounts (`/admin/users`), policy configurations, system thresholds, analytics, and immutable audit logs.
2. **`claim_reviewer`** (`Config.ROLE_REVIEWER`): Specialized adjudication access to the manual review queue, forensic evidence review, and decision overrides (`/reviewer/`).
3. **`service_center_staff`** (`Config.ROLE_STAFF`): Technical service hub operations, repair record creation, and authorized service center updates.
4. **`customer`** (`Config.ROLE_CUSTOMER`): Restricted self-service portal for product registration, claim intake wizard, status tracking, and personal document management.

### Security Invariants & Defensive Controls
- **Deterministic Public Registration**: Public `/register` deterministically provisions accounts with `customer` role only. Any client-submitted role parameters or form injections are completely ignored.
- **Enterprise Account Provisioning**: Elevated accounts (`staff`, `reviewer`, `administrator`) can exclusively be provisioned by authenticated Administrators via `/admin/users/create`.
- **Database-Backed Single Source of Truth**: Route authorization `@role_required` and `@login_required` resolve fresh user identity, role, and active status directly from the database on every HTTP request. Session cookie tampering is completely rejected.
- **Account Deactivation & Lockout Defense**: Deactivated accounts (`is_active = False`) are strictly blocked from logging in with zero auto-reactivation loopholes. Active sessions for deactivated accounts are terminated immediately.
- **Administrative Lockout Safeguards**:
  - *Self-Demotion Blocked*: Administrators cannot remove their own administrator privileges.
  - *Self-Deactivation Blocked*: Administrators cannot deactivate their own active accounts.
  - *Last Active Administrator Protection*: Demoting or deactivating the last remaining active administrator is strictly prohibited (`active_admins > 1` invariant).
- **Object-Level Access Control (IDOR Isolation)**: Multi-tenant tenant boundaries are enforced across all resources. Customers cannot view, modify, or download claims, products, repair records, documents, or PDF certificates belonging to other claimants.
- **Cross-Site Request Forgery (CSRF) Protection**: Cryptographically secure CSRF tokens validate all state-changing `POST`, `PUT`, `DELETE`, and `PATCH` requests.
- **Immutable Audit Logging**: All security-critical lifecycle events (`ACCOUNT_CREATED`, `RBAC_ROLE_CHANGE`, `ACCOUNT_ACTIVATED`, `ACCOUNT_DEACTIVATED`, `USER_LOGIN_SUCCESS`, `LOGIN_FAILED`, `USER_LOGOUT`) are permanently recorded in `AuditLog` with actor ID, target entity, role transitions, client IP, and timestamps.

---

## Installation & Local Setup

### Prerequisites
- Python 3.10+
- Git

### Setup Steps
```bash
# 1. Clone repository
git clone https://github.com/sami2515/assurex-claim-engine.git
cd assurex-claim-engine

# 2. Create and activate virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\Activate.ps1
# macOS / Linux:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Initialize and seed SQLite database
python database/seed.py

# 5. Start the web application
python src/app.py
```
Open **`http://127.0.0.1:5000`** in your browser.

---

## Test Suite

```bash
# Run full test suite (109 tests)
python -m unittest discover -s tests

# Run dedicated RBAC security, CSRF & IDOR suite (24 tests)
python -m unittest tests/test_rbac_security.py

# Run SRS test categories
python -m unittest tests/test_srs_18_categories.py

# Run demonstration cases
python -m unittest tests/test_srs_demonstration_cases.py

# Generate model comparison report
python reports/generate_comparison_report.py
```

---

## Live Deployment

- **Live URL:** [https://assurexai.pythonanywhere.com](https://assurexai.pythonanywhere.com)
- **Hosting:** PythonAnywhere

---

## Dataset & Models

- **Dataset:** 1,500 claims across 3 product categories (`Consumer Electronics`, `Home Appliances`, `Industrial Tools`).
- **Splits:** 70% Train (1,050) / 15% Val (225) / 15% Test (225).
- **Claim Summary Cards:** $640 \times 420$ claim cards for vision model training.
- **Python Model:** Random Forest Classifier.
- **Teachable Machine:** Vision classifier trained on summary card images.

---

## Repository Structure

```
assurex-claim-engine/
├── config/                  # Configuration settings
├── data/                    # CSV datasets, splits, and summary cards
├── database/                # SQLite database and seed scripts
├── documentation/           # Project documentation and test cases
├── model/                   # Trained ML models (python_model, teachable_machine)
├── policies/                # JSON warranty policies per category
├── reports/                 # Model comparison and project reports
├── sample_claims/           # Sample claim JSON files
├── screenshots/             # UI screenshots and diagrams
├── src/                     # Application source code
│   ├── api/                 # Flask routes (auth, products, claims, reviewer, admin, reports)
│   ├── core/                # Preprocessor, classifiers, comparator, decision engine
│   ├── models/              # SQLAlchemy database models
│   ├── ocr/                 # OCR document processor and SHA-256 hashing
│   ├── rules/               # Policy engine, duplicate and contradiction checks
│   └── services/            # PDF generator, alerts, analytics, CSV export
├── static/                  # CSS, JS, and images
├── templates/               # HTML templates
├── tests/                   # Unit and integration tests
├── LICENSE                  # MIT License
└── README.md                # Project documentation
```

---

## Technical Blog

- **Medium Link:** [https://medium.com/@samikhan031027/building-assurex-a-dual-model-warranty-claim-evaluation-system-8a30d3684111](https://medium.com/@samikhan031027/building-assurex-a-dual-model-warranty-claim-evaluation-system-8a30d3684111)
- **Local Copy:** [`documentation/TECHNICAL_BLOG.md`](file:///c:/Users/sami/Desktop/techwiz%207/documentation/TECHNICAL_BLOG.md)

---

## License

Developed for the **NextWave AI and ML** project evaluation at **Aptech Limited**.
