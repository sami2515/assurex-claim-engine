# Building AssureX: A Dual-Model Warranty Claim Evaluation System

*Technical overview of machine learning, OCR, visual classification, and configurable warranty rules*

> **SRS Deliverable #14 Compliance**: This technical blog addresses all 23 mandatory discussion topics specified in Aptech NextWave Software Requirements Specification (SRS Version 1.0, Page 35–36).

---

## Table of Contents

1. [Business Problem](#1-business-problem)
2. [Background and Necessity](#2-background-and-necessity)
3. [Proposed Solution](#3-proposed-solution)
4. [Application Architecture](#4-application-architecture)
5. [Dataset Creation](#5-dataset-creation)
6. [Dataset Challenges](#6-dataset-challenges)
7. [Python Model Development](#7-python-model-development)
8. [Algorithms Compared](#8-algorithms-compared)
9. [Google Teachable Machine Training](#9-google-teachable-machine-training)
10. [Claim Summary Card Generation](#10-claim-summary-card-generation)
11. [Python Integration](#11-python-integration)
12. [Model Prediction Comparison](#12-model-prediction-comparison)
13. [Confidence-Score Comparison](#13-confidence-score-comparison)
14. [Warranty-Rule Design](#14-warranty-rule-design)
15. [OCR and Document Processing](#15-ocr-and-document-processing)
16. [Difficulties Encountered](#16-difficulties-encountered)
17. [Model Errors](#17-model-errors)
18. [Model Disagreement Cases](#18-model-disagreement-cases)
19. [Testing Results](#19-testing-results)
20. [Security Considerations](#20-security-considerations)
21. [Limitations](#21-limitations)
22. [Lessons Learned](#22-lessons-learned)
23. [Future Enhancements](#23-future-enhancements)

---

AssureX Claim Engine is a web-based system for evaluating warranty claims using structured claim data, document processing, two independent model paths, and configurable warranty rules. The project was developed around the requirements of the AssureX Software Requirements Specification. It includes three claim classes: **Valid Claim, Invalid Claim, and Manual Review**. It also compares the outputs of a Python machine learning model and a Google Teachable Machine model before applying warranty policies and making the final application decision. This article explains how the system was designed, how the dataset and models were prepared, the main problems encountered during development, and how the completed application was tested.

---

## 1. Business Problem

Warranty claim processing involves several manual steps. A support or warranty team may need to inspect invoices, verify product serial numbers, check warranty dates, review repair history, and determine whether the reported fault is covered by the policy. This process becomes more difficult when claims contain incomplete documents, inconsistent information, duplicate submissions, or cases that are close to a warranty boundary.

Three common problems were identified during the design of AssureX:

### 1. Manual claim processing
A reviewer may have to inspect receipts, warranty cards, serial numbers, repair records, and other documents before reaching a decision. Repeating these checks for a large number of claims increases the amount of manual work and creates backlog delays.

### 2. Inconsistent decisions
Two claims with similar information may not always be handled in the same way when different reviewers interpret the available evidence differently. A system that follows the same validation process can help make the evaluation more consistent across different service hubs.

### 3. Duplicate and policy-violating claims
Warranty systems also need to handle repeated submissions, expired warranties, unauthorized repairs, serial mismatches, and other policy-related issues. Submitting the same invoice multiple times or claiming damage caused by uncertified third-party workshops are recurring operational issues.

AssureX was designed to address these problems by combining structured data processing, machine learning, OCR, configurable rules, and human manual review.

---

## 2. Background and Necessity

A warranty system based only on fixed business rules can handle clear cases well, but it may struggle with claims that contain several variables at the same time. For example, a claim may have:
- an active warranty,
- a high repair cost,
- a previous repair,
- a missing document,
- or information that does not completely agree across different records.

On the other hand, a machine learning model can identify patterns in structured data, but it should not be the only source of the final decision. Relying solely on a black-box model creates risk when ambiguous edge cases arise.

This led to the design of a **Dual-Model Consensus Architecture** in AssureX. The system uses two model paths:
- A **Python tabular classification model** works with structured claim information.
- A **Google Teachable Machine model** works with visual Claim Summary Cards.

The system then compares the two model outputs. Warranty policies and validation checks are applied after the model comparison. Claims that do not satisfy the required conditions or show model disagreement can be routed to manual review. This approach keeps machine learning and deterministic business rules as separate parts of the overall workflow.

---

## 3. Proposed Solution

The AssureX application is built around several connected components:

### 1. Document ingestion and OCR
Users can upload invoices, warranty documents, repair records, and supporting evidence. OCR and document parsing are used to extract information such as invoice numbers, purchase dates, and serial codes so they can be checked by the application.

### 2. Dual-model classification
The application uses two independent model paths:
- **Branch A:** Python tabular classifier (Random Forest)
- **Branch B:** Google Teachable Machine visual classifier (MobileNet vision transfer learning)

Both models classify the claim into the same three classes:
- **Valid Claim**
- **Invalid Claim**
- **Manual Review**

### 3. Configurable warranty policies
Warranty rules are stored separately from application code in JSON policy files. Policies can define:
- warranty duration,
- grace periods,
- reporting windows,
- covered faults,
- exclusions,
- repair requirements,
- replacement conditions,
- mandatory documents,
- and review triggers.

### 4. Human review workbench
Claims that require manual handling are placed in a reviewer queue. Reviewers can inspect the evidence, see the model comparison and confidence delta, and record an override decision together with an audit reason.

### 5. Claim lifecycle tracking
The application tracks claims through eight lifecycle stages:
1. Draft
2. Submitted
3. Under Evaluation
4. Additional Information Required
5. Manual Review
6. Approved
7. Rejected
8. Closed

The system also generates a downloadable PDF adjudication certificate containing the decision information, cryptographic QR verification, and rule breakdown.

---

## 4. Application Architecture

The application follows a modular processing pipeline based directly on the official system architecture diagram.

![Figure 1: Official 9-Stage System Architecture & Dual-Branch Consensus Pipeline (Aptech NextWave SRS Page 5)](/static/img/page-05-architecture-diagram.jpg)

*Figure 1: Official 9-Stage System Architecture & Dual-Branch Consensus Pipeline (Aptech NextWave SRS Page 5).*

The main idea is to keep data extraction, machine learning, model comparison, policy validation, and final decision handling as separate modules:
1. **Intake Tier**: Captures claim attributes, product selection, and uploaded documents.
2. **Extraction & Card Generation Tier**: Parses receipt text with regex while simultaneously generating a standardized 640x420 neutral Claim Summary Card.
3. **Dual Model Inference Tier**: Executes Branch A (tabular model) and Branch B (Teachable Machine) concurrently.
4. **Comparison & Rules Tier**: Evaluates prediction agreement, computes absolute confidence delta $|\Delta_{\text{conf}}|$, and verifies category JSON policy rules.
5. **Master Decision Tier**: Assigns the final outcome (Likely Valid, Likely Invalid, or Manual Review) and directs claims to the appropriate role workbench.

---

## 5. Dataset Creation

The project uses a synthetic warranty claims dataset containing **1,500 unique records** generated using `dataset_generator/generate_dataset.py`.

The dataset is balanced across the three claim classes:

### 500 Valid Claim records
- covered faults,
- valid purchase dates within warranty terms,
- active warranty coverage,
- matching product serial numbers,
- authorized service history.

### 500 Invalid Claim records
- expired warranty periods beyond grace allowances,
- excluded damage types (liquid damage, physical drop impact),
- unauthorized third-party modifications,
- unsupported claims without valid purchase proof.

### 500 Manual Review records
- boundary purchase dates within grace periods,
- missing non-critical documents,
- minor serial number typographical differences,
- conflicting incident descriptions requiring human assessment.

The dataset was partitioned using a stratified 70/15/15 distribution:

| Dataset Split | Percentage | Number of Records |
|:---|:---:|:---:|
| **Training Set** | 70% | 1,050 |
| **Validation Set** | 15% | 225 |
| **Testing Set** | 15% | 225 |
| **Total** | **100%** | **1,500** |

The same class definitions are used across the dataset files and the visual Claim Summary Cards.

---

## 6. Dataset Challenges

Creating a synthetic dataset was not only a matter of generating 1,500 rows. The records also needed to contain enough variation so that the models would not simply learn one obvious feature.

### 1. Avoiding trivial separation
Early data patterns allowed the model to rely heavily on `product_age_days`. To reduce this issue, the dataset included cases where older products could still be valid because of longer industrial policies (e.g., 36 months), while newer products could be invalid because of damage exclusions (such as liquid spill).

### 2. Multiple product categories
The dataset covers three distinct equipment categories:
- **Consumer Electronics** (Smartphones, Laptops, Tablets, Smart TVs)
- **Home Appliances** (Refrigerators, Washing Machines, Microwaves, Air Conditioners)
- **Industrial Tools** (Rotary Hammers, Angle Grinders, Air Compressors, Demolition Drills)

Each category has different warranty durations, cost structures, failure types, and claim conditions.

### 3. Document variation
Invoice data was also varied using different date formats (`YYYY-MM-DD`, `DD/MM/YYYY`, `MM/DD/YYYY`), merchant names, and text variations. This was useful for testing the OCR and parsing components instead of assuming that every document would follow exactly the same structure.

---

## 7. Python Model Development

The Python classification branch is implemented in `src/core/python_classifier.py`. The model receives structured claim features extracted from the application.

### Feature preprocessing
A scikit-learn `ColumnTransformer` is used for preprocessing.

#### Numerical features
The following numeric values are processed:
- `purchase_price`
- `claim_amount`
- `product_age_days`
- `remaining_warranty_days`
- `previous_repairs_count`

Missing values are median-imputed and the features are scaled using `StandardScaler`.

#### Categorical features
The following categorical fields are encoded using `OneHotEncoder(handle_unknown='ignore')`:
- `product_category`
- `fault_category`
- `damage_type`

Using `handle_unknown='ignore'` prevents unseen evaluator categories from breaking the preprocessing pipeline during live testing.

#### Binary evidence flags
Several boolean indicators are passed through directly:
- `has_receipt`
- `has_warranty_card`
- `serial_number_match`
- `unauthorized_repair_flag`
- `claim_date_conflict_flag`

The resulting feature pipeline is then supplied to the classification algorithms.

---

## 8. Algorithms Compared

Three supervised learning algorithms were evaluated using 5-fold stratified cross-validation on the 1,050 training records.

| Algorithm | 5-Fold CV Accuracy | Test Split Accuracy | Precision (Macro) | Recall (Macro) | F1-Score (Macro) |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Random Forest Classifier** | **99.90%** | **100.0%** | **1.0000** | **1.0000** | **1.0000** |
| **HistGradientBoosting** | 99.71% | 99.56% | 0.9958 | 0.9956 | 0.9956 |
| **Multi-Layer Perceptron (MLP)** | 98.48% | 98.67% | 0.9870 | 0.9867 | 0.9867 |

In the current project test run, Random Forest produced the highest measured results among the three evaluated algorithms. It showed stable decision paths, quick training, and inference latency under 5 milliseconds.

The selected model was serialized and saved as `model/python_model/best_model.joblib`.

*Note: These results apply to the generated project dataset and test setup used during development. They should not be interpreted as a general commercial production benchmark.*

---

## 9. Google Teachable Machine Training

The second model path uses Google Teachable Machine. Instead of using raw claim data directly, the system generates standardized Claim Summary Cards and uses those cards as visual input.

- **Training Volume**: At least two visual variations were created for each training card, producing **2,100 training images**.
- **Visual Variations**: The visual variations changed presentation details such as card margins, font sizing, background canvas appearance, spacing, and layout padding. The underlying claim information itself remained identical.
- **Evaluation**: For evaluation, the held-out test cards were kept strictly separate from training data. In the project test run, the model recorded **100.0% accuracy** on 225 held-out test cards.

The local inference runtime is implemented in `src/core/teachable_machine_classifier.py`.

---

## 10. Claim Summary Card Generation

Claim Summary Cards are generated programmatically by `src/core/card_generator.py`. The cards are rendered as 640x420 PNG images using the Python Pillow (PIL) library.

A card contains information such as:
- product metadata (name, category, serial),
- serial status and receipt match,
- purchase dates and incident date,
- fault description and repair count,
- document availability flags.

**Strict Neutral Formatting**: The card does **not** contain:
- the ground-truth claim class,
- Python model predictions,
- GTM model predictions,
- or the final claim decision.

This separation is important because the visual model should work from the claim information shown on the card rather than simply reading an already-written answer. The card design uses a structured typography layout so that important fields can be detected consistently by the vision model.

---

## 11. Python Integration

The Python classifier and the Teachable Machine classifier are connected through the application's comparison and decision modules:
- `ModelComparator` (`src/core/comparator.py`)
- `DecisionEngine` (`src/core/decision_engine.py`)

When a claim is submitted:
1. Structured claim data is prepared and fed to the Python model.
2. A Claim Summary Card is generated in parallel.
3. The visual card is evaluated by the Teachable Machine classifier.
4. Both models return class probabilities across the three classes:
   - $P(\text{Valid})$
   - $P(\text{Invalid})$
   - $P(\text{Manual Review})$
5. The outputs are passed to the comparison layer.
6. Warranty rules and other validation checks are then applied.

The implementation records execution latency and performance information for the entire inference pipeline.

---

## 12. Model Prediction Comparison

The system compares the highest-probability class from each model:

$$\hat{y}_{\text{py}} = \arg\max(\mathbf{P}_{\text{py}}), \quad \hat{y}_{\text{gtm}} = \arg\max(\mathbf{P}_{\text{gtm}})$$

There are two primary cases:

### Agreement
If $\hat{y}_{\text{py}} = \hat{y}_{\text{gtm}}$, both models have selected the same class. The claim can continue to the warranty rule validation stage.

### Disagreement
If $\hat{y}_{\text{py}} \neq \hat{y}_{\text{gtm}}$, the system assigns the status **`Model Disagreement`**. The claim is immediately sent for manual review rather than being automatically approved. This prevents one model from overriding a conflicting result from the second model.

---

## 13. Confidence-Score Comparison

AssureX also compares the confidence associated with the top prediction from each model. The confidence difference is computed as:

$$\Delta_{\text{conf}} = \left| \max(\mathbf{P}_{\text{py}}) - \max(\mathbf{P}_{\text{gtm}}) \right|$$

Three configurable thresholds are defined:
- `MIN_CONFIDENCE = 0.60`
- `STRONG_MATCH_DIFF = 0.15`
- `ACCEPTABLE_MATCH_DIFF = 0.30`

The system uses **five consistency statuses**:

1. **Strong Match**: The predicted classes match and $\Delta_{\text{conf}} \le 0.15$. High certainty alignment.
2. **Acceptable Match**: The predicted classes match and $0.15 < \Delta_{\text{conf}} \le 0.30$. Consistent direction with minor variance.
3. **Weak Match**: The predicted classes match but $\Delta_{\text{conf}} > 0.30$. Flagged with confidence variance warning.
4. **Model Disagreement**: The two models predict different classes ($\hat{y}_{\text{py}} \neq \hat{y}_{\text{gtm}}$). Automated approval is barred; routed to Manual Review.
5. **Uncertain Result**: Either model has a top-class confidence below $0.60$. This indicates that the model output is not confident enough for an automated decision.

The five consistency statuses are separate from the three claim classes. The claim classes describe the classification category, while the consistency statuses describe the relationship between the two model outputs.

---

## 14. Warranty-Rule Design

Warranty rules are stored separately from the core application logic in the `policies/` directory. The project contains three configurable policy categories:

### Consumer Electronics (`consumer_electronics.json`)
- 12-month coverage duration,
- 7-day grace period,
- 30-day incident reporting window,
- authorized repair center requirement.
- *Exclusions*: liquid ingress, screen drops, uncertified disassembly.

### Home Appliances (`home_appliances.json`)
- 24-month coverage duration,
- 14-day grace period,
- 45-day reporting window.
- *Exclusions*: commercial rental usage, electrical power surge damage.

### Industrial Tools (`industrial_tools.json`)
- 36-month coverage duration,
- 14-day grace period,
- 30-day reporting window.
- *Exclusions*: abnormal torque overload, unauthorized motor modifications.

The `WarrantyPolicyEngine` evaluates the claim using six main validation groups:
1. **Expiry**: Validates elapsed purchase age against coverage term plus grace days.
2. **Reporting Window**: Verifies that the fault was reported within the policy window.
3. **Exclusions**: Checks reported damage against policy exclusion lists.
4. **Authorized Service**: Validates repair facility history.
5. **Serial Verification**: Checks product serial match between invoice and device.
6. **Document Completeness**: Verifies mandatory receipt and warranty card presence.

Because policies are stored as JSON files, changes can be made without altering or recompiling the Python application code.

---

## 15. OCR and Document Processing

The document-processing layer is implemented in `src/ocr/document_processor.py`. The system processes uploaded claim documents and extracts useful information:

### SHA-256 fingerprinting
Each uploaded file is hashed using cryptographic SHA-256. The resulting hash is stored and used by the duplicate detector to identify identical files appearing across different claims or user accounts.

### Regex-based extraction
Regular expressions extract structured entities from uploaded text:
- Invoice numbers (`INV-\d{4}-\d{5}`)
- Purchase dates (ISO and localized formats)
- Merchant names and payment totals
- Hardware serial numbers

The extracted information is compared with the user-entered claim details to verify consistency. OCR and extraction are treated as evidence validation steps, not as the sole decision mechanism.

---

## 16. Difficulties Encountered

Several practical issues appeared during development and were resolved:

### 1. Visual feature bias
Early Claim Summary Cards contained colored status badges. The visual model started relying on those colors instead of learning from the underlying claim fields. The solution was to simplify the cards to a neutral monochrome presentation focused purely on claim data attributes.

### 2. OCR layout variation
Real-world documents do not always have the same layout. Invoices use different date formats, field alignments, or text arrangements. To handle this, the document parser uses multiple regex patterns and also includes a Python fallback parser for environments where native Tesseract binaries are not installed.

### 3. Discretionary rule routing vs. hard failures
Some cases are not suitable for an immediate automated rejection. For example, a serial mismatch might be a simple typographical error by the customer, while a claim close to the warranty boundary may warrant customer goodwill. Instead of treating every such case as an automatic failure, the application routes these cases through `review_triggers` to the reviewer queue for manual evaluation.

---

## 17. Model Errors

Testing exposed a few model-related issues that were subsequently addressed:

- **False Invalid predictions on industrial claims**: High repair costs initially affected some industrial claims because cost-related features were strongly associated with rejection in the initial training splits. The addition of a normalized `claim_to_price_ratio` feature helped resolve this bias.
- **Vision errors on dense layouts**: Some Claim Summary Cards had long fault descriptions that reduced the spacing and visibility of adjacent serial fields. In response, the card generator was adjusted to improve line spacing, vertical padding, and field separation.

---

## 18. Model Disagreement Cases

Model disagreement occurs when structured features and visual card evidence point in different directions.

A demonstration scenario involves an industrial rotary hammer (Demo Case 11):
- The claim had an active warranty, a valid receipt, and one previous repair by an uncertified service center.
- In the recorded test run:
  - The Python model predicted **Valid Claim (92.4% confidence)** because all core numerical metrics were healthy.
  - The GTM model predicted **Invalid Claim (88.7% confidence)** by detecting the visual warning flag in the repair history section.
- Because the predicted classes differed, the system assigned **`Model Disagreement`**.
- The confidence difference was $|0.924 - 0.887| = 0.037$.
- Even though confidence values were close, the class predictions did not match. Therefore, the Master Decision Engine barred automated approval and routed the claim to the human reviewer queue.

---

## 19. Testing Results

The project contains automated unit and integration tests under `tests/`. The current test run reports:
- **38 automated tests** covering all 18 SRS test categories,
- **100.0% pass rate**,
- approximately 6 seconds execution time.

The project also includes the 11 mandatory demonstration scenarios:
1. **Valid Claim**: Smart TV with covered motherboard fault $\to$ **`Likely Valid`**.
2. **Invalid Claim**: Phone with liquid damage $\to$ **`Likely Invalid`**.
3. **Manual Review Claim**: Industrial hammer with borderline wear near end of term $\to$ **`Manual Review Required`**.
4. **Expired Warranty**: Claim submitted past warranty period $\to$ **`Likely Invalid`**.
5. **Missing Document**: Claim submitted without required invoice $\to$ **`Manual Review Required`**.
6. **Duplicate Claim**: Repeated submission on active product serial $\to$ **`Manual Review Required`**.
7. **Contradictory Claim**: Reported fault date occurs before purchase date $\to$ **`Manual Review Required`**.
8. **Serial Mismatch**: Receipt serial does not match product serial $\to$ **`Manual Review Required`**.
9. **Unauthorized Repair**: Previous repair performed by uncertified service provider $\to$ **`Manual Review Required`**.
10. **Boundary Date**: Claim filed on day 4 of 7-day grace period $\to$ **`Manual Review Required`**.
11. **Model Disagreement**: Python predicts Valid while GTM predicts Invalid $\to$ **`Manual Review Required`**.

---

## 20. Security Considerations

Security was implemented at both the application and data levels:
- **Role-Based Access Control (RBAC)**: Enforced boundaries between Customer, Reviewer, Staff, and Administrator using decorators (`@login_required`, `@role_required`).
- **SQL Injection Protection**: Database operations use SQLAlchemy ORM parameterized queries instead of manual SQL string concatenation.
- **Template Escaping**: Jinja2 template auto-escaping prevents cross-site scripting (XSS) in user comments and reviewer notes.
- **Password Hashing & Audit Records**: Passwords are saved using Werkzeug PBKDF2/SHA-256 password hashing. Important actions such as reviewer decisions and administrative policy updates are recorded in the immutable `AuditLog` database table.

---

## 21. Limitations

AssureX operates under several defined constraints:
1. **Visual card input**: The Teachable Machine model evaluates generated Claim Summary Cards rather than raw photographs of defective products.
2. **OCR limitations**: Highly distorted, handwritten, or unusual invoices require human verification in the reviewer queue.
3. **Fixed product categories**: The current configuration covers Consumer Electronics, Home Appliances, and Industrial Tools. Adding more categories requires new JSON policy schemas.
4. **Synthetic dataset**: The machine learning models are evaluated on the project's generated dataset; commercial deployment would require additional field testing on real warranty records.

---

## 22. Lessons Learned

Building AssureX highlighted several practical software engineering lessons:
- **Two model paths provide an additional validation step**: Comparing tabular structured data against a visual card representation catches edge cases that a single model might miss.
- **Explainability matters during review**: A human reviewer needs supporting factors, opposing factors, and rule details rather than a raw prediction score.
- **Decoupled policies simplify maintenance**: Keeping warranty rules in JSON configuration files allows adjusting grace periods or exclusions without rewriting the Python engine.
- **Dataset quality directly impacts evaluation**: Avoiding trivial features and injecting realistic noise ensures that models learn meaningful relationships.

---

## 23. Future Enhancements

Potential improvements for future versions of AssureX include:
1. **Vision-Language Document Models**: Exploring models such as LayoutLM or Donut for deeper document parsing of complex receipts.
2. **Active Learning**: Collecting reviewer override cases as training examples to refine model performance around difficult boundary cases.
3. **ERP Integration**: Connecting approved claim states directly into ERP systems like SAP or Oracle NetSuite to initiate replacement part logistics.
4. **Additional Document Formats**: Expanding document processing to support multi-page warranty contracts and service center invoices.

---

## Conclusion

AssureX Claim Engine was developed as a warranty claim evaluation system combining structured machine learning, visual classification, document OCR, configurable policies, and human review.

The architecture maintains clear boundaries across:
- **3 claim classes**: Valid Claim, Invalid Claim, Manual Review
- **5 model-consistency statuses**: Strong Match, Acceptable Match, Weak Match, Model Disagreement, Uncertain Result
- **8 claim lifecycle stages**: Draft, Submitted, Under Evaluation, Info Required, Manual Review, Approved, Rejected, Closed

The primary takeaway from this project is that practical warranty adjudication is not simply a classification problem. A reliable system requires document verification, business rule engines, model consensus, immutable audit logging, and a dedicated human review path when automated components do not agree.

---

### Project Links
- **Published Live on Medium**: [https://medium.com/@samikhan031027/building-assurex-a-dual-model-warranty-claim-evaluation-system-8a30d3684111](https://medium.com/@samikhan031027/building-assurex-a-dual-model-warranty-claim-evaluation-system-8a30d3684111)
- **Source Code Repository**: [https://github.com/sami2515/assurex-claim-engine](https://github.com/sami2515/assurex-claim-engine)
- **Publication Record**: [`documentation/BLOG_PUBLICATION.md`](file:///c:/Users/sami/Desktop/techwiz%207/documentation/BLOG_PUBLICATION.md)
- **Local Interactive Reader**: [http://127.0.0.1:5000/blog](http://127.0.0.1:5000/blog)
