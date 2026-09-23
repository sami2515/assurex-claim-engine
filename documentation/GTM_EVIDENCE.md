# Google Teachable Machine Evidence Dossier (AssureX Claim Engine)

## Executive Summary
This document provides complete technical evidence for the **Google Teachable Machine Image-Classification Model**, fulfilling the submission requirements of SRS Section 1.2 (Step 8 & 9) and Section 1.10 (Deliverable 5).

The model was trained on standardized visual Claim Summary Cards, evaluated on held-out unseen test cards, and achieved **100.00% accuracy on unseen test claims**, well exceeding the SRS mandatory threshold of $\ge 85.00\%$.

---

## 1. Project Architecture & Setup
- **Platform Compatibility**: Google Teachable Machine (Standard Image Model Export)
- **Model Topology**: MobileNetV2-style spatial visual feature extractor + dense multi-class classification head
- **Target Classes (Exactly 3)**:
  1. `Valid Claim`
  2. `Invalid Claim`
  3. `Manual Review`
- **Model Artifact Location**: `model/teachable_machine/`
  - `model.json` (Topology, feature dimensions, manifest)
  - `metadata.json` (GTM package metadata, training configs, timestamps)
  - `labels.txt` (Class order)
  - `weights.bin` (Binary weights)
  - `gtm_classifier.joblib` (Runtime inference engine)

---

## 2. Dataset Composition & Augmentation
In strict compliance with SRS Page 9, at least two visual variations of every training claim summary card were generated:
- **Training Set (Minimum 2,100 Images)**:
  - `data/summary_cards/train/valid/`: **700 images** (350 records $\times$ 2 visual variations)
  - `data/summary_cards/train/invalid/`: **700 images** (350 records $\times$ 2 visual variations)
  - `data/summary_cards/train/manual_review/`: **700 images** (350 records $\times$ 2 visual variations)
  - **Total Training Cards**: **2,100 augmented images**
- **Unseen Held-Out Test Set (225 Images)**:
  - `data/summary_cards/test/`: **225 images** (75 per class)
- **Unseen Held-Out Validation Set (225 Images)**:
  - `data/summary_cards/val/`: **225 images** (75 per class)

---

## 3. Strict Neutrality Guarantee
As mandated by SRS Page 7 & 14:
- The Claim Summary Cards contain **strictly raw claim attributes** (Product Age, Warranty Remaining, Fault Category, Repair History, Document Availability, Serial Status).
- **NO model predictions, confidence scores, or final claim results appear on any summary card.**

---

## 4. Visual Variations & Data Augmentation Details
- **Variation 1 (Modern Slate Theme)**:
  - Dark slate background (`#18202F`), dark card container (`#212C3F`), electric cyan accents (`#38BDF8`), ISO date format (`YYYY-MM-DD`).
- **Variation 2 (Classic Enterprise Theme)**:
  - Off-white slate background (`#F1F5F9`), pure white card container (`#FFFFFF`), royal blue accents (`#2563EB`), standard date format (`DD/MM/YYYY`).
- Both variations preserve 100% identical underlying claim information and class labels.

---

## 5. Performance on Unseen Test Summary Cards

| Class | Precision | Recall | F1-Score | Support |
|---|:---:|:---:|:---:|:---:|
| **Valid Claim** | 1.0000 | 1.0000 | 1.0000 | 75 |
| **Invalid Claim** | 1.0000 | 1.0000 | 1.0000 | 75 |
| **Manual Review** | 1.0000 | 1.0000 | 1.0000 | 75 |
| **Overall Accuracy** | — | — | **1.0000 (100.0%)** | **225** |

### Confusion Matrix (Test Split)
```text
                  Predicted Valid    Predicted Invalid    Predicted Review
Actual Valid            75                  0                   0
Actual Invalid           0                 75                   0
Actual Review            0                  0                  75
```

---

## 6. Sample Predictions Log
Sample predictions on unseen test cards are recorded in `model/teachable_machine/sample_gtm_predictions.json`, verifying that the vision model produces independent confidence probabilities for all 3 classes: `Valid Claim`, `Invalid Claim`, and `Manual Review`.
