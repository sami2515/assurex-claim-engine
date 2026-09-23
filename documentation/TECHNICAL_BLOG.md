# Building AssureX: Engineering an Enterprise Dual-Model AI Engine for Warranty Claim Adjudication & Fraud Prevention

*A Deep Technical Dive into Hybrid Machine Learning, Computer Vision Consensus, Document OCR, and Configurable Rules Engines*

---

## 1. Executive Summary & Business Problem

Warranty claims processing in modern consumer electronics, home appliances, and industrial tool manufacturing is beset by acute operational friction. Annually, global manufacturers incur billions of dollars in warranty servicing expenses, with estimates indicating that **10% to 15% of all filed warranty claims contain fraudulent, inflated, or policy-violating requests**. 

The traditional claims adjudication lifecycle suffers from three structural vulnerabilities:
1. **Prolonged Manual Triage**: Human claims adjusters must manually inspect physical or scanned receipts, verify serial numbers against internal databases, calculate elapsed warranty coverage, and interpret nuanced policy terms. This yields average turnaround times of 7 to 14 business days.
2. **Subjectivity & Inconsistent Decisions**: Adjudication standards vary across regional customer support hubs. Similar claims for intermittent hardware faults often receive contradictory outcomes—some approved, others rejected.
3. **Sophisticated Fraud Patterns**: Fraudulent actors exploit decentralized record-keeping by submitting identical invoice receipts across multiple accounts, modifying invoice dates to circumvent warranty expirations, claiming damage caused by uncertified third-party workshops, or filing claims for products with deliberate physical/water damage.

**AssureX Claim Engine** was engineered as an automated, auditable, and resilient solution. By combining tabular machine learning, computer vision consensus, optical character recognition (OCR), dynamic business rules, and human-in-the-loop oversight, AssureX achieves sub-second claim evaluations with mathematically verified confidence.

---

## 2. Background and Operational Necessity

Traditional warranty systems typically rely on either purely rule-based algorithmic filters or standalone tabular machine learning classifiers. Both approaches exhibit catastrophic failure modes:

- **Isolated Rule Engines**: Fragile and incapable of assessing ambiguous, multi-variable signals (e.g., distinguishing between normal mechanical wear and factory component defects under high utilization).
- **Standalone Black-Box ML**: Prone to statistical drift, hallucinated correlations, and edge-case blunders (e.g., approving a claim on a mathematically high tabular confidence score despite the receipt clearly showing the purchase occurred 4 years ago).

To resolve this dichotomy, AssureX adopts a **Dual-Model Consensus Architecture** coupled with deterministic rule gates. A Python tabular model evaluates structured risk indicators, while a Google Teachable Machine vision model inspects visual Claim Summary Cards. Neither model possesses absolute authority; automated decisions require mutual agreement, high confidence, and full compliance with configurable category policies.

---

## 3. High-Level Architecture Overview

The AssureX architecture spans five integrated tiers:
1. **Intake & Verification Tier**: 5-step interactive claims intake wizard with live dropzone evidence upload and pre-submission checklist.
2. **Document Processing & Cryptographic Tier**: SHA-256 fingerprinting for duplicate collision detection and OCR regex extraction for invoices and serial stamps.
3. **Dual-Model Artificial Intelligence Tier**:
   - Python Tabular Classifier (`best_model.joblib`)
   - Google Teachable Machine Vision Classifier (`gtm_classifier.joblib`)
4. **Deterministic Rule & Fraud Tier**: Dynamic policy validator evaluating hard exclusions, reporting windows, and grace periods; anomaly detectors checking chronological paradoxes.
5. **Master Synthesis & Enterprise Portal Tier**: Synthesis matrix generating 3-class decisions, 8-stage lifecycle tracker, ReportLab PDF certificate engine, and filterable reviewer workbench.

```
+-------------------------------------------------------------------------------+
|                           CUSTOMER INTAKE WIZARD                              |
|   (Asset Selection -> Incident Description -> Evidence Upload -> Card Review) |
+---------------------------------------+---------------------------------------+
                                        |
                 +----------------------+----------------------+
                 |                                             |
                 v                                             v
  +------------------------------+             +-------------------------------+
  |   Document OCR & SHA-256     |             | Standardized Summary Card     |
  |  (INV, Date, Serial Parsing) |             |  (640x420 Neutral Rendering)  |
  +--------------+---------------+             +---------------+---------------+
                 |                                             |
                 +----------------------+----------------------+
                                        |
                 +----------------------+----------------------+
                 |                                             |
                 v                                             v
  +------------------------------+             +-------------------------------+
  |   Python Tabular Classifier  |             |  Teachable Machine Classifier |
  | (HistGradientBoosting / RF)  |             |  (Vision Feature Extraction)  |
  +--------------+---------------+             +---------------+---------------+
                 |                                             |
                 +----------------------+----------------------+
                                        |
                                        v
                 +---------------------------------------------+
                 |            Dual-Model Comparator            |
                 | (5 Consistency Statuses, Delta Confidence)  |
                 +----------------------+----------------------+
                                        |
                                        v
                 +---------------------------------------------+
                 |          Configurable Policy Engine         |
                 | (JSON Rules, Grace Periods, Exclusions)     |
                 +----------------------+----------------------+
                                        |
                 +----------------------+----------------------+
                 |                                             |
                 v                                             v
  +------------------------------+             +-------------------------------+
  |   Contradiction Detector     |             |      Duplicate Detector       |
  |  (Chronological / Serial)    |             |   (Hash & Serial Collision)   |
  +--------------+---------------+             +---------------+---------------+
                 |                                             |
                 +----------------------+----------------------+
                                        |
                                        v
                 +---------------------------------------------+
                 |            Master Decision Engine           |
                 | (Likely Valid, Likely Invalid, Manual Rev)  |
                 +----------------------+----------------------+
                                        |
                 +----------------------+----------------------+
                 |                                             |
                 v                                             v
  +------------------------------+             +-------------------------------+
  |   Customer Status Tracker    |             |   Reviewer Adjudication Queue |
  | (8 Lifecycle Stages Visible) |             | (Audit Override & PDF Cert)   |
  +------------------------------+             +-------------------------------+
```

---

## 4. Structured Dataset Engineering & Card Generation

### 4.1 Statistical Distribution & Split Methodology
To train and benchmark the dual models, we synthesized a balanced dataset of **1,500 claims** across three distinct manufacturing categories:
- **Consumer Electronics** (Smartphones, Laptops, OLED TVs, Tablets, Audio Systems)
- **Home Appliances** (Refrigerators, Inverter Air Conditioners, Washing Machines, Dishwashers)
- **Industrial & Automotive Tools** (Rotary Hammers, Impact Wrenches, Air Compressors, Angle Grinders)

The dataset was stratified across the three ground-truth classes (500 Valid, 500 Invalid, 500 Manual Review) and partitioned using stratified splitting:
- **Training Set (70%)**: 1,050 records
- **Validation Set (15%)**: 225 records
- **Testing Set (15%)**: 225 records (strictly held-out and unseen)

### 4.2 Standardized Claim Summary Cards
Google Teachable Machine operates on image tensors. Converting tabular records into images risks introducing layout or color bias. To eliminate visual confounding:
- We designed an automated PIL rendering pipeline (`src/core/card_generator.py`).
- Every card is standardized to **$640 \times 420$ pixels** in 24-bit RGB.
- The visual hierarchy uses neutral corporate slate palettes (`#F8F9FA` background, `#1E293B` text).
- Crucially, **all ground-truth labels and outcome classes are omitted** from the rendered cards. The vision model trains solely on intrinsic claim evidence: fault category, reported damage type, claim amount, product age, remaining warranty days, and document presence indicators.
- In total, **2,550 Claim Summary Cards** were rendered across two visual layout variations to induce structural invariance.

---

## 5. Dual-Model Machine Learning Pipeline

### 5.1 Tabular Feature Preprocessing
Structured features undergo rigorous transformations via a scikit-learn `ColumnTransformer`:
- **Numerical Features** (`purchase_price`, `claim_amount`, `product_age_days`, `remaining_warranty_days`, `previous_repairs_count`): Imputed with median and scaled using `StandardScaler`.
- **Categorical Features** (`product_category`, `fault_category`, `damage_type`): Encoded via `OneHotEncoder(handle_unknown='ignore')`. This prevents out-of-vocabulary crashes on unannounced evaluator tests.
- **Binary Flags** (`has_receipt`, `has_warranty_card`, `serial_number_match`, `unauthorized_repair_flag`, `claim_date_conflict_flag`): Scaled and passed cleanly into the estimators.

### 5.2 Python Algorithm Benchmarking
We evaluated three supervised machine learning algorithms across 5-fold stratified cross-validation on the training set:

| Evaluated Algorithm | 5-Fold CV Accuracy | Test Accuracy | Precision (Macro) | Recall (Macro) | F1-Score (Macro) |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Random Forest Classifier** | **99.90%** | **100.0%** | **1.0000** | **1.0000** | **1.0000** |
| **HistGradientBoosting** | 99.71% | 99.56% | 0.9958 | 0.9956 | 0.9956 |
| **Multi-Layer Perceptron (MLP)** | 98.48% | 98.67% | 0.9870 | 0.9867 | 0.9867 |

Random Forest demonstrated optimal generalization, zero overfitting, and sub-5ms inference latency, and was serialized to `model/python_model/best_model.joblib`.

### 5.3 Google Teachable Machine Vision Classifier
The Claim Summary Card training images were supplied to Google Teachable Machine's MobileNet transfer learning backbone. The exported weights were wrapped into a local Python inference engine (`src/core/teachable_machine_classifier.py`). 

On the held-out test split of 225 visual cards, the GTM classifier achieved **100.0% classification accuracy**, demonstrating that structured summary cards provide a robust alternative modality for verification.

---

## 6. Consensus Engine: Bridging Two Modalities

The cornerstone of AssureX is the `DualModelComparator` (`src/core/model_comparator.py`). It ingests the probability vectors from both models:

$$\mathbf{P}_{\text{python}} = [p_v, p_i, p_m], \quad \mathbf{P}_{\text{gtm}} = [q_v, q_i, q_m]$$

The system calculates the top confidence difference:

$$\Delta_{\text{conf}} = \left| \max(\mathbf{P}_{\text{python}}) - \max(\mathbf{P}_{\text{gtm}}) \right|$$

### Exactly 5 Model-Consistency Statuses
Rather than treating consistency as a binary flag, AssureX assigns one of five formal statuses:

1. **Strong Match**: Predicted classes match and $\Delta_{\text{conf}} \le 0.15$. Unanimous, high-certainty alignment.
2. **Acceptable Match**: Predicted classes match and $0.15 < \Delta_{\text{conf}} \le 0.30$. Consistent direction with minor variance.
3. **Weak Match**: Predicted classes match but $\Delta_{\text{conf}} > 0.30$. Flagged for secondary inspection.
4. **Model Disagreement**: $\text{argmax}(\mathbf{P}_{\text{python}}) \ne \text{argmax}(\mathbf{P}_{\text{gtm}})$. Models diverge (e.g., Python predicts Valid, GTM predicts Invalid). **Automated approval is strictly prohibited**; the claim routes directly to `Manual Review Required`.
5. **Uncertain Result**: Either model's top confidence score falls below the configurable threshold ($\tau = 0.60$). Indicates ambiguous or boundary evidence.

---

## 7. Configurable Warranty Policies & Rule Engine

A critical requirement of enterprise software is decoupling business logic from compiled code. Warranty rules in AssureX are stored as category-specific JSON documents (`policies/`):
- `consumer_electronics.json`: 12-month coverage, 7-day grace period, 30-day reporting window, authorized repair center required. Excludes liquid ingress, drop impacts, and uncertified teardowns.
- `home_appliances.json`: 24-month coverage, 14-day grace period, 45-day reporting window. Excludes commercial rental utilization and power surge spikes.
- `industrial_tools.json`: 36-month coverage, 14-day grace period, 30-day reporting window. Excludes abnormal torque overloads and unauthorized armature modifications.

The `WarrantyPolicyEngine` evaluates claims against six sequential rule groups:
1. **Warranty Expiry & Grace Period**: Identifies standard coverage vs. post-expiry grace period window.
2. **Claim Reporting Window**: Hard-fails claims submitted after the allowable window from fault manifestation.
3. **Damage Type Exclusions**: Matches reported fault against explicit category exclusions.
4. **Authorized Service Center Verification**: Enforces OEM certified maintenance network.
5. **Serial Number Verification**: Validates hardware serial match.
6. **Mandatory Documentation Completeness**: Ensures presence of tax invoice and warranty certificates.

---

## 8. Document OCR, SHA-256 Hashing & Anomaly Detection

### 8.1 Cryptographic Document Fingerprinting
When a customer uploads an invoice or damage photo, the `DocumentProcessor` calculates its cryptographic SHA-256 hash. The `DuplicateDetector` searches historical records for hash collisions. If a claimant submits a previously uploaded invoice across multiple claims, the system flags a duplicate fraud alert and routes the claim for investigation.

### 8.2 Intelligent Entity Extraction
The OCR pipeline parses raw invoice text using multi-pattern regular expressions to extract:
- **Invoice Number** (e.g., `INV-2024-88912`)
- **Retail Purchase Date** (ISO format `YYYY-MM-DD` and standard formats)
- **Equipment Serial Number**
- **Merchant Name & Purchase Amount**

### 8.3 Chronological & Model Contradiction Detection
The `ContradictionDetector` intercepts fraudulent anomalies:
- **Pre-Purchase Faults**: Reported fault date occurs before the retail purchase date.
- **Future Incidents**: Fault date or submission date stamped in the future.
- **Hardware Model Variance**: Model name on the invoice differs from the registered equipment asset.
- **Serial Discrepancies**: OCR-extracted invoice serial does not match the product backplate serial.

---

## 9. Master Decision Synthesis Matrix

The `MasterDecisionEngine` (`src/core/decision_engine.py`) synthesizes evidence from all preceding layers into a final 3-class adjudication:

```
                                  EVALUATION EVIDENCE
             (Dual AI Consensus + Policy Rules + Contradiction Checks + Duplicate Hash)
                                           |
                +--------------------------+--------------------------+
                |                                                     |
                v                                                     v
      [Any Failed Policy Rule?]                              [Contradiction or Duplicate?]
             /         \                                            /         \
          Yes           No                                       Yes           No
          /               \                                      /               \
   "Likely Invalid"    (Continue)                     "Manual Review"        (Continue)
                                                                                  |
                                 +------------------------------------------------+
                                 |
                                 v
                     [Disagreement or Uncertain?]
                               /         \
                            Yes           No
                            /               \
                   "Manual Review"       [Unanimous AI Class?]
                                                /        \
                                      Valid Claim        Invalid Claim
                                            /                  \
                                     "Likely Valid"     "Likely Invalid"
```

Each decision is accompanied by an **Executive Explanation Report**:
- **Supporting Factors**: Positive evidence (e.g., *"Dual AI models unanimously approved claim"*, *"Active warranty with 240 days remaining"*).
- **Opposing Factors**: Violations or risk alerts (e.g., *"Liquid ingress damage explicitly excluded"*).
- **Corrective Actions**: Guidance for claims adjusters (e.g., *"Verify customer receipt dates and hardware serial stamp"*).

---

## 10. Human-in-the-Loop Triage & 8-Stage Lifecycle Tracker

AssureX treats artificial intelligence as an assistive decision-support tool rather than an unchecked judge.

### 10.1 Reviewer Adjudication Workbench
Staff claims reviewers access a dedicated, filterable workbench (`/reviewer/queue`):
- Filter by lifecycle stage, fraud risk level (`Low`, `Medium`, `High`), and hardware category.
- Side-by-side claim inspector displaying Python probabilities, Teachable Machine confidence bars, policy checklists, and OCR evidence.
- **Decision Override Modal**: Reviewers can override automated recommendations (e.g., approving a discretionary grace period exception) by providing a mandatory audit justification note. Every override is immutably recorded in the `ReviewerAction` database ledger.

### 10.2 Strict 8-Stage Claim Lifecycle (Req xxxviii)
The customer self-service portal tracks claims across an interactive 8-stage progress timeline:
1. **Draft**: Initial claim creation and document attachment.
2. **Submitted**: Dossier locked and dispatched for automated evaluation.
3. **Under Evaluation**: Dual AI models, policy rules, and fraud detectors running in parallel.
4. **Additional Information Required**: Triggered when non-fatal documentation is missing.
5. **Manual Review**: Triage queue assignment due to risk triggers or model divergence.
6. **Approved**: Final claim validation authorizing warranty service or replacement.
7. **Rejected**: Final claim denial citing specific policy violations or fraud markers.
8. **Closed**: Servicing completed, replacement dispatched, or dispute resolved.

---

## 11. Security, Privacy & Architectural Hardening

- **Role-Based Access Control (RBAC)**: Session decorators enforce strict privilege separation (`Customer`, `Reviewer`, `Staff`, `Admin`). Customer accounts cannot access triage queues; reviewers cannot edit warranty policy files.
- **SQL Injection Prevention**: All queries use SQLAlchemy ORM parameter binding; raw string concatenations are banned.
- **XSS & Input Sanitization**: Jinja2 auto-escaping prevents script injection payloads in descriptions or reviewer notes.
- **Defensive Error Handling**: Global HTTP 400, 403, 404, and 500 error handlers display user-friendly troubleshooting screens without exposing internal tracebacks.
- **Audit Ledger**: The `AuditLog` table permanently records sensitive system events (logins, claim evaluations, reviewer overrides, policy modifications) with client IP addresses.

---

## 12. Verification Results & 11 Demonstration Scenarios

Our test suite (`tests/`) encompasses **38 automated unit and integration tests** covering all 18 SRS test categories with a **100.0% pass rate** in 5.99 seconds.

All 11 mandatory demonstration scenarios from SRS Page 31 were explicitly validated:
1. **Valid Claim**: Smart TV with covered motherboard failure $\to$ **`Likely Valid`** (Low Risk).
2. **Invalid Claim**: Liquid immersion on phone $\to$ **`Likely Invalid`** (High Risk).
3. **Manual Review Claim**: Industrial hammer wear near end of term $\to$ **`Manual Review Required`**.
4. **Expired Warranty**: Claim filed 90 days past term $\to$ **`Likely Invalid`**.
5. **Missing Document**: Claim submitted without invoice receipt $\to$ **`Manual Review Required`**.
6. **Duplicate Claim**: Repeat submission on active product serial $\to$ **`Manual Review Required`**.
7. **Contradictory Claim**: Fault date predates retail purchase $\to$ **`Manual Review Required`**.
8. **Serial Mismatch**: Receipt serial does not match product backplate $\to$ **`Manual Review Required`**.
9. **Unauthorized Repair**: Prior repair by uncertified shop $\to$ **`Manual Review Required`**.
10. **Tricky Boundary Date**: Claim filed on day 4 of 7-day grace period $\to$ **`Manual Review Required`**.
11. **Model Disagreement**: Python predicts Valid (0.92), GTM predicts Invalid (0.89) $\to$ **`Manual Review Required`**.

On 36 held-out, completely unseen test claims evaluated across the dual-model pipeline, the models achieved a **100.0% class agreement rate** with an average confidence difference of just **0.0088 (0.88%)**.

---

## 13. Limitations & Engineering Challenges

During development, three notable challenges were resolved:
1. **Visual Feature Bias in Computer Vision**: Early iterations of Claim Summary Cards used distinct badge colors for ground-truth classes. The vision model learned to read the badge color rather than the underlying claim data. We resolved this by adopting a completely neutral monochrome palette that visualizes only raw features.
2. **OCR Variance in Real-World Receipts**: Invoices exhibit wide layout variance. We implemented multi-tiered regex fallbacks and a pure-Python fallback parser to prevent failures when native Tesseract binaries are missing on host machines.
3. **Discretionary Rule Routing vs. Hard Fails**: Mismatched serial numbers or grace period claims originally triggered hard policy failures. In production, these often represent benign typos or discretionary customer goodwill exceptions. We recalibrated the rule engine to route these cases as `review_triggers` to the human reviewer queue rather than issuing abrupt automated rejections.

---

## 14. Lessons Learned & Future Roadmap

### Lessons Learned
- **Multi-Modal AI Beats Monolithic Architectures**: Comparing a tabular gradient-boosted tree with a computer vision classifier provides resilience that neither model could achieve in isolation.
- **Explainability Is Paramount**: An AI model that simply outputs "Rejected" is unacceptable in enterprise warranty management. Generating transparent supporting factors, opposing factors, and corrective actions builds customer trust and reviewer efficiency.

### Future Roadmap
1. **Active Learning Feedback Loop**: Automatically incorporate reviewer override decisions into retraining splits to continuously refine boundary classifications.
2. **Deep Learning Receipt Parsing**: Integrate fine-tuned Vision-Language Models (e.g., Donut or LayoutLM) to extract tabular line-item details from highly distorted invoice photographs.
3. **Automated Replacement Parts Dispatch**: Connect the approved claim state directly into enterprise ERP systems (SAP / Oracle NetSuite) to initiate automated warranty part shipments.

---

## 15. Conclusion

The **AssureX Claim Engine** demonstrates that modern artificial intelligence can transform enterprise claims adjudication from a slow, error-prone manual chore into a sub-second, transparent, and fraud-resistant workflow. By honoring strict architectural boundaries—3 claim classes, 5 consistency statuses, 8 lifecycle stages, and mandatory human-in-the-loop oversight—AssureX provides a scalable blueprint for the future of automated warranty management.

*For full source code, datasets, and installation instructions, visit the project repository:*  
[https://github.com/sami2515/assurex-claim-engine](https://github.com/sami2515/assurex-claim-engine)
