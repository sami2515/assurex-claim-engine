# AssureX Claim Engine

> **Enterprise AI-Powered Dual-Model Warranty Claim Adjudication & Fraud Detection Platform**  
> *Built for NextWave AI & ML Evaluation — Aptech Limited*

---

## 📌 Project Overview

**AssureX Claim Engine** is an enterprise-grade automated warranty claims processing system that combines **Python Tabular Machine Learning** (Random Forest / Gradient Boosting) with **Google Teachable Machine Vision Models** to adjudicate warranty claims in real time.

The system enforces multi-layer fraud detection, OCR receipt extraction, cryptographic SHA-256 fingerprinting, configurable category warranty policies, and an 8-stage claims lifecycle tracking engine with human-in-the-loop review overrides.

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

## 🎯 Key Architectural Standards

### Exactly 3 Claim Classes
1. **`Valid Claim`** — Covered fault, active warranty, verified serial, unanimous AI consensus.
2. **`Invalid Claim`** — Policy violation, excluded damage, expired warranty, or unanimous fraud detection.
3. **`Manual Review`** — Borderline conditions, model disagreement, low confidence, or chronological discrepancies.

### Exactly 5 Model-Consistency Statuses
1. **`Strong Match`** — Both models predict identical class with $|\Delta\text{conf}| \le 0.15$.
2. **`Acceptable Match`** — Both models predict identical class with $0.15 < |\Delta\text{conf}| \le 0.30$.
3. **`Weak Match`** — Both models predict identical class with $|\Delta\text{conf}| > 0.30$.
4. **`Model Disagreement`** — Conflicting class predictions between models; automatically routes to Manual Review.
5. **`Uncertain Result`** — Either model confidence falls below configurable threshold ($0.60$).

### Exactly 8 Claim Lifecycle Stages (Req xxxviii)
`Draft` $\to$ `Submitted` $\to$ `Under Evaluation` $\to$ `Additional Information Required` $\to$ `Manual Review` $\to$ `Approved` $\to$ `Rejected` $\to$ `Closed`

---

## 🔑 Evaluator Quick-Start Login Credentials

| Role | Email | Password | Access Scope |
|:---|:---|:---|:---|
| **System Administrator** | `admin@assurex.local` | `AdminPass123!` | Full Admin Portal, Policies Editor, Analytics, Audit Logs |
| **Claims Reviewer** | `reviewer@assurex.local` | `ReviewerPass123!` | Reviewer Triage Queue, Adjudication Workbench, Overrides |
| **Customer / Claimant** | `customer@assurex.local` | `CustomerPass123!` | Self-Service Portal, Product Fleet, 5-Step Intake Wizard |
| **Service Center Staff** | `staff@assurex.local` | `StaffPass123!` | Service Hub Maintenance Records, Repair Logging |

*Tip: The login page at `http://127.0.0.1:5000/login` features 1-click quick-fill buttons to auto-populate any role.*

---

## 🚀 Installation & Local Setup

### Prerequisites
- Python 3.10+ (tested on Python 3.14)
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

## 🧪 Test Suite & Verification

The application includes 38 automated test cases covering all 18 SRS test categories and 11 demonstration scenarios:

```bash
# Run full automated test suite (38 tests)
python -m unittest discover tests

# Run 18 SRS Test Categories specifically
python -m unittest tests/test_srs_18_categories.py

# Run 11 Mandatory Demonstration Cases
python -m unittest tests/test_srs_demonstration_cases.py

# Generate 21-column Model Comparison Report (36 unseen claims)
python reports/generate_comparison_report.py
```

---

## 📊 Dataset & Model Architecture

- **Dataset:** 1,500 balanced claims generated across 3 hardware categories (`Consumer Electronics`, `Home Appliances`, `Industrial & Automotive Tools`).
- **Splits:** 70% Train (1,050) / 15% Val (225) / 15% Test (225).
- **Claim Summary Cards:** Standardized $640 \times 420$ neutral-rendered claim cards for vision model training.
- **Python ML Benchmark:** Random Forest Classifier (100.0% test accuracy on held-out test split).
- **Google Teachable Machine:** Custom vision classifier trained on 2,100 augmented card images (100.0% test accuracy).
- **Dual-Model Class Agreement:** 100.00% across held-out unseen claims ($|\Delta\text{conf}| = 0.0088$).

---

## 📁 Repository Structure

```
assurex-claim-engine/
├── config/                  # Global threshold and environment configurations
├── data/                    # Structured CSV datasets, splits, and mapping tables
│   ├── raw/                 # Complete 1,500-record dataset
│   ├── splits/              # Train (70%), Val (15%), Test (15%)
│   └── summary_cards/       # Standardized 640x420 Claim Summary Cards
├── database/                # SQLite database and seed scripts
├── documentation/           # System design, test matrix, evidence dossiers
│   ├── TEST_CASES.md        # 18-Category formal verification matrix
│   ├── PYTHON_MODEL_EVIDENCE.md
│   └── GTM_EVIDENCE.md
├── model/                   # Serialized ML models (joblib, model.json, weights.bin)
├── policies/                # Configurable JSON warranty policies per category
├── reports/                 # 21-column model comparison report (CSV + MD)
├── src/                     # Core application source code
│   ├── api/                 # Flask Blueprints (auth, products, claims, reviewer, admin, reports)
│   ├── core/                # Preprocessor, Python ML, GTM Vision, Comparator, Decision Engine
│   ├── models/              # SQLAlchemy 13 entity domain models
│   ├── ocr/                 # Document processor, SHA-256 hasher, entity extractor
│   ├── rules/               # Policy engine, fraud detector, contradiction detector
│   └── services/            # PDF report certificate generator, CSV exporter
├── static/                  # CSS stylesheets, JavaScript client engine, images
├── templates/               # Jinja2 templates (Customer, Reviewer, Admin portals)
├── tests/                   # Automated unit and integration test suites
├── AI_USAGE.md              # Section 1.8 AI tool compliance declaration
└── README.md                # Project documentation
```

---

## 📄 License & Academic Compliance

This project is developed for the **NextWave AI and ML Competition / Examination** administered by **Aptech Limited**. All source code, dataset generation scripts, and machine learning models strictly follow the project Software Requirements Specification (SRS).
