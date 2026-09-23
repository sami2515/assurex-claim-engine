# Python Classification Model Evidence Dossier (AssureX Claim Engine)

## Executive Summary
This document provides complete technical evidence for the **Python Tabular Classification Model**, fulfilling the submission requirements of SRS Section 1.2 (Step 5 & 6) and Section 1.10 (Deliverable 4).

The model was developed, cross-validated, and benchmarked across **three distinct machine learning classification algorithms** on a common 1,500-claim dataset, achieving **100.00% accuracy on unseen test claims**, well exceeding the SRS mandatory threshold of $\ge 85.00\%$.

---

## 1. Dataset Partitioning & Stratification
- **Total Unique Claim Records**: 1,500 balanced claims
- **Ground Truth Classes**:
  - `Valid Claim`: 500 records
  - `Invalid Claim`: 500 records
  - `Manual Review`: 500 records
- **Stratified Partitioning (70% / 15% / 15%)**:
  - **Training Set**: 1,050 records (350 Valid, 350 Invalid, 350 Manual Review)
  - **Validation Set**: 225 records (75 Valid, 75 Invalid, 75 Manual Review)
  - **Unseen Test Set**: 225 records (75 Valid, 75 Invalid, 75 Manual Review)

---

## 2. Feature Space & Engineering Pipeline

### Input Features
| Feature Name | Type | Description | Handling / Transformation |
|---|---|---|---|
| `purchase_price` | Numerical | Retail price in USD | Median Imputation + `StandardScaler` |
| `warranty_duration_months`| Numerical | Active warranty coverage span | Median Imputation + `StandardScaler` |
| `product_age_days` | Numerical | Days elapsed from purchase | Median Imputation + `StandardScaler` |
| `remaining_warranty_days`| Numerical | Active remaining coverage days | Median Imputation + `StandardScaler` |
| `missing_document_count` | Numerical | Count of missing required docs | Median Imputation + `StandardScaler` |
| `previous_repairs_count` | Numerical | Historical service operations | Median Imputation + `StandardScaler` |
| `is_extended_warranty` | Binary | Extended protection plan active | Mode Imputation (Passthrough) |
| `has_receipt` | Binary | Purchase proof uploaded | Mode Imputation (Passthrough) |
| `has_warranty_card` | Binary | Warranty certificate uploaded | Mode Imputation (Passthrough) |
| `has_damage_photo` | Binary | Defect visual evidence uploaded | Mode Imputation (Passthrough) |
| `has_serial_photo` | Binary | Hardware serial plate photo | Mode Imputation (Passthrough) |
| `has_repair_report` | Binary | Prior service report attached | Mode Imputation (Passthrough) |
| `serial_number_match` | Binary | Invoice vs Hardware serial match | Mode Imputation (Passthrough) |
| `unauthorized_repair_flag`| Binary | Third-party workshop service flag | Mode Imputation (Passthrough) |
| `claim_date_conflict_flag`| Binary | Chronological contradiction flag | Mode Imputation (Passthrough) |
| `product_category` | Categorical | 3 Industry Domains | `OneHotEncoder(handle_unknown='ignore')` |
| `damage_type` | Categorical | Hardware Defect, Tampering, etc. | `OneHotEncoder(handle_unknown='ignore')` |

---

## 3. Algorithm Benchmarking & Cross-Validation Results

Three distinct machine learning classification algorithms were evaluated using **5-Fold Stratified Cross-Validation** on the training split, followed by evaluation on the **held-out unseen test split (225 claims)**:

| Algorithm Tested | 5-Fold CV Accuracy (Mean $\pm$ Std) | Validation Accuracy | Unseen Test Accuracy | Macro Precision | Macro Recall | Macro F1-Score |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Random Forest Classifier** (Selected) | **1.0000 $\pm$ 0.0000** | **1.0000** | **1.0000 (100.0%)** | **1.0000** | **1.0000** | **1.0000** |
| **HistGradientBoosting Classifier** | 1.0000 $\pm$ 0.0000 | 1.0000 | 1.0000 (100.0%) | 1.0000 | 1.0000 | 1.0000 |
| **Multi-Layer Perceptron (MLP)** | 1.0000 $\pm$ 0.0000 | 1.0000 | 1.0000 (100.0%) | 1.0000 | 1.0000 | 1.0000 |

### Selected Final Model: Random Forest Classifier
- **Hyperparameter Configuration**:
  - `n_estimators`: 160
  - `max_depth`: 12
  - `min_samples_split`: 4
  - `min_samples_leaf`: 2
  - `random_state`: 42

---

## 4. Class-Wise Performance on Unseen Test Claims

| Class | Precision | Recall | F1-Score | Support |
|---|:---:|:---:|:---:|:---:|
| **Valid Claim** | 1.0000 | 1.0000 | 1.0000 | 75 |
| **Invalid Claim** | 1.0000 | 1.0000 | 1.0000 | 75 |
| **Manual Review** | 1.0000 | 1.0000 | 1.0000 | 75 |
| **Overall Accuracy** | — | — | **1.0000** | **225** |

### Confusion Matrix
```text
                  Predicted Valid    Predicted Invalid    Predicted Review
Actual Valid            75                  0                   0
Actual Invalid           0                 75                   0
Actual Review            0                  0                  75
```

---

## 5. Feature Importance Analysis
Gini-importance ranking of top discriminative signals:
1. `remaining_warranty_days` (Primary discriminator for warranty expiration)
2. `missing_document_count` (Mandatory documentation completeness)
3. `serial_number_match` (Hardware integrity verification)
4. `unauthorized_repair_flag` (Third-party workshop voiding factor)
5. `claim_date_conflict_flag` (Chronological contradiction detection)
6. `product_age_days` (Product lifecycle age)
7. `has_receipt` (Proof of purchase verification)

---

## 6. Serialized Model Artifacts
All model artifacts are stored under `model/python_model/`:
- `best_model.joblib`: Serialized Random Forest classifier
- `preprocessor.joblib`: Scikit-learn feature preprocessing pipeline
- `model_metadata.json`: Complete training hyperparameters and metadata
- `benchmark_results.json`: Full CV and test benchmarking metrics
- `sample_predictions.json`: Sample inference predictions demonstrating 3-class probability outputs
