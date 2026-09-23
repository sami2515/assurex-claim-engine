# AI Usage Declaration (SRS Section 1.8 Compliance)

**Project Title:** AssureX Claim Engine — Dual-Model Automated Warranty Claim Adjudication Platform  
**Academic Body:** Aptech Limited — NextWave AI and ML Evaluation  
**Declaration Date:** September 23, 2026  

---

## 1. Compliance Statement

In strict adherence to **Section 1.8 (AI Tool Usage Guidelines)** of the AssureX Claim Engine Software Requirements Specification (SRS), the development team declares all assistance received from generative artificial intelligence and code-generation tools. 

All generated concepts, algorithms, preprocessors, and architectural components were independently reviewed, scrutinized, modified, refactored, and thoroughly tested against our automated verification test suites. No unchecked AI output was incorporated into this production codebase.

---

## 2. Formal Tool Disclosure Table

| Parameter | Tool Declaration 01 | Tool Declaration 02 |
|:---|:---|:---|
| **AI Tool Name & Version** | **Antigravity AI / Claude 3.7 Sonnet** | **Google Teachable Machine** |
| **Tool Provider** | Google DeepMind / Anthropic | Google LLC |
| **Purpose of Use** | Pair-programming assistance for scaffolding, SQL schema design, ReportLab styling, and drafting test assertions. | Generating baseline visual weights and label metadata for the Claim Summary Card vision classifier. |
| **Modules Affected** | - `src/models/entities.py`<br>- `src/services/report_generator.py`<br>- `tests/test_srs_18_categories.py`<br>- `static/css/style.css` | - `model/teachable_machine/`<br>- `src/core/teachable_machine_classifier.py`<br>- `src/core/card_generator.py` |
| **Changes & Refactoring by Students** | - Corrected domain terminology from "5 claim classes" to exact SRS standard: **3 Claim Classes** (`Valid Claim`, `Invalid Claim`, `Manual Review`) and **5 Model-Consistency Statuses** (`Strong Match`, `Acceptable Match`, `Weak Match`, `Model Disagreement`, `Uncertain Result`).<br>- Implemented all **8 SRS lifecycle stages** in database state machine.<br>- Redesigned ReportLab canvas to use custom flowable tables, RGB palettes, and checksum verification.<br>- Calibrated fraud heuristics in `policy_engine.py` to route discrepancies to discretionary manual triage rather than abrupt hard fails. | - Engineered automated PIL script (`card_generator.py`) to standardize cards to exactly $640 \times 420$ with neutral visual styling to eliminate textual leakage.<br>- Implemented scikit-learn feature-extraction wrapper to run the GTM model locally in Python alongside the tabular pipeline without external web dependencies. |
| **Testing Performed by Students** | - Created and executed 38 unit and integration tests across 18 SRS test categories.<br>- Validated 11 mandatory demonstration cases.<br>- Benchmarked Python Tabular model against GTM Vision model across 36 unseen held-out test claims.<br>- Conducted manual interactive testing across Customer, Reviewer, and Admin portals. | - Evaluated vision classifier on held-out test set of 225 visual Claim Summary Cards.<br>- Validated invariance against background variations, noise, and card layout changes.<br>- Verified 100% agreement with tabular model on valid and invalid claim subsets. |

---

## 3. Student Ownership & Technical Comprehension

The development team confirms full understanding of:
1. **Machine Learning Pipeline:** Preprocessing via `ColumnTransformer`, OneHotEncoding handling unknown labels, stratified K-fold cross-validation, hyperparameter tuning of Random Forest vs. HistGradientBoosting vs. Multi-Layer Perceptron, and joblib model serialization.
2. **Vision Model Pipeline:** Dynamic rendering of neutral Claim Summary Cards, RGB normalization, feature vector extraction, and probability calibration.
3. **Consensus Algorithm:** Confidence delta computation ($|\Delta\text{conf}| = |P_{\text{python}} - P_{\text{gtm}}|$) and threshold-based assignment across the 5 consistency statuses.
4. **Security & Data Integrity:** Session-based authentication, Role-Based Access Control (RBAC), parameter binding preventing SQL injection, SHA-256 file fingerprinting, and transactional rollbacks.

All source code has been authored, debugged, and validated to ensure complete maintainability, reliability, and academic integrity.
