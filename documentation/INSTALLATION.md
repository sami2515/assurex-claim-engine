# AssureX Claim Engine — Installation & Deployment Manual

**Standard:** AssureX Claim Engine NextWave AI and ML SRS (Section 3.3, Pages 31–32)  
**Target Operating Systems:** Windows 10/11, Ubuntu 22.04 LTS+, macOS Sonoma+  
**Target Python Version:** Python 3.10 – 3.14  

---

## 1. Prerequisites & Environment

Ensure the following foundational software packages are installed on your workstation:

| Prerequisite | Recommended Version | Verification Command |
|:---|:---|:---|
| **Python** | 3.10.x to 3.14.x | `python --version` |
| **pip** | 24.0+ | `pip --version` |
| **Git** | 2.40+ | `git --version` |
| **Tesseract OCR (Optional)** | 5.0+ | `tesseract --version` *(optional fallback engine included)* |

---

## 2. Step-by-Step Installation

### Step 1: Clone Repository
```bash
git clone https://github.com/sami2515/assurex-claim-engine.git
cd assurex-claim-engine
```

### Step 2: Virtual Environment Creation
Create an isolated Python virtual environment to avoid dependency collisions:

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Linux / macOS (Bash):**
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Dependency Installation
Install all required libraries including Flask, scikit-learn, ReportLab, pandas, and Pillow:
```bash
pip install -r requirements.txt
```

### Step 4: Environment Variables (Optional)
The system operates out-of-the-box with production-ready defaults in `config/config.py`. To configure custom secret keys or ports, create a `.env` file in the project root:
```env
SECRET_KEY=your-secure-random-secret-key-here
FLASK_ENV=development
MIN_CONFIDENCE_THRESHOLD=0.60
STRONG_MATCH_DIFF=0.15
ACCEPTABLE_MATCH_DIFF=0.30
```

### Step 5: Database Initialization & Seeding
Create the SQLite database schema and seed the baseline users, warranty policies, sample equipment, and past claims:
```bash
python database/seed.py
```
*Expected Output:*
```text
-> Initializing database tables...
-> Database tables created.
-> Seeding core users...
-> Seeding warranty policies...
-> Seeding products and warranties...
-> Seeding sample claims and documents...
[✓] AssureX Claim Engine database seeded successfully!
```

---

## 3. Machine Learning Models Placement

The system models are pre-packaged and pre-trained in the repository:

1. **Python Tabular Model:**
   - Preprocessor: `model/python_model/preprocessor.joblib`
   - Benchmark Model: `model/python_model/best_model.joblib`
   - Benchmark Results: `model/python_model/benchmark_results.json`

2. **Google Teachable Machine Model:**
   - Architecture JSON: `model/teachable_machine/model.json`
   - Metadata JSON: `model/teachable_machine/metadata.json`
   - Labels File: `model/teachable_machine/labels.txt`
   - Weights Binary: `model/teachable_machine/weights.bin`
   - Standalone Classifier: `model/teachable_machine/gtm_classifier.joblib`

*Note: If models need to be retrained from scratch at any time, run:*
```bash
python -c "from src.core.card_generator import generate_all_cards; generate_all_cards()"
python -c "from src.core.preprocessor import train_and_save_python_model; train_and_save_python_model()"
```

---

## 4. Running the Application

Launch the Flask web server:
```bash
python src/app.py
```

*Expected Terminal Output:*
```text
 * Serving Flask app 'app'
 * Debug mode: on
 * Running on http://127.0.0.1:5000
```

Open **`http://127.0.0.1:5000`** in any web browser.

---

## 5. Evaluator User Accounts

The login interface features **1-Click Quick Fill** buttons for immediate evaluator testing:

| Role | Email | Password | Access Scope |
|:---|:---|:---|:---|
| **System Administrator** | `admin@assurex.local` | `AdminPass123!` | Executive dashboard, dynamic JSON policy editor, audit trail |
| **Claims Reviewer** | `reviewer@assurex.local` | `ReviewerPass123!` | Multi-filter review queue, adjudication workbench, decision override |
| **Customer** | `customer@assurex.local` | `CustomerPass123!` | Self-service claims portal, product fleet, 5-step intake wizard |
| **Service Staff** | `staff@assurex.local` | `StaffPass123!` | Service center maintenance and repair record logs |

---

## 6. Verification & Automated Test Execution

Execute the full verification suite (all 38 tests):
```bash
python -m unittest discover tests
```

Execute the 18 SRS Category verification test suite:
```bash
python -m unittest tests/test_srs_18_categories.py
```

Execute the 11 Mandatory Demonstration Cases:
```bash
python -m unittest tests/test_srs_demonstration_cases.py
```

Re-generate the 21-column Model Comparison Report on 36 unseen claims:
```bash
python reports/generate_comparison_report.py
```

---

## 7. Troubleshooting & FAQ

- **Port 5000 Already in Use:**
  In `src/app.py`, change line 75: `app.run(port=5001)` or run `flask run --port 5001`.
- **PowerShell Script Execution Policy Error:**
  If `.\venv\Scripts\Activate.ps1` gives an execution policy error, run:
  `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
- **Missing OCR Tesseract Binary:**
  The `DocumentProcessor` includes a built-in pure-Python fallback extraction engine that parses text, receipts, and invoices even without the native Tesseract binary installed.
