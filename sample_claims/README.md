# AssureX Sample Claims - Mandatory Demonstration Suite

This folder fulfills **SRS Deliverable #2 & Deliverable #8 (Pages 25 & 31)** by providing comprehensive demonstration dossiers for each of the 11 mandatory edge and lifecycle scenarios specified in the AssureX Software Requirements Specification.

---

## 11 Mandatory Demonstration Cases Mapping Table

| Case | Filename | Scenario Description | Core Engine Layers Triggered | Expected SRS Decision | Risk Level |
|---|---|---|---|---|---|
| **01** | [`01_valid_claim.json`](./01_valid_claim.json) | Genuine hardware failure, active warranty, verified invoice & serial | Python Tabular ML + GTM Vision Consensus | **Likely Valid** | Low |
| **02** | [`02_invalid_claim.json`](./02_invalid_claim.json) | Accidental drop & liquid damage violating policy exclusion | Policy Hard Fail + Dual-Model Consensus | **Likely Invalid** | High |
| **03** | [`03_manual_review_claim.json`](./03_manual_review_claim.json) | Intermittent surge damage with missing warranty card | Triage Rule Engine + Low-Margin Confidence | **Manual Review Required** | Medium |
| **04** | [`04_expired_warranty_claim.json`](./04_expired_warranty_claim.json) | Defect date 2.5 years after purchase (policy expired) | Policy Rule: `COVERAGE_DURATION_EXPIRED` | **Likely Invalid** | High |
| **05** | [`05_missing_document_claim.json`](./05_missing_document_claim.json) | Customer lost original purchase receipt | Integrity Layer: `MANDATORY_DOC_MISSING` | **Manual Review Required** | Medium |
| **06** | [`06_duplicate_claim.json`](./06_duplicate_claim.json) | Same hardware serial resubmitted under another claim code | Duplicate Detector: `SERIAL_COLLISION` | **Manual Review Required** | High |
| **07** | [`07_contradictory_claim.json`](./07_contradictory_claim.json) | Defect occurrence date 5 months *before* purchase date | Contradiction Detector: `CHRONOLOGY_CONFLICT` | **Manual Review Required** | High |
| **08** | [`08_serial_mismatch_claim.json`](./08_serial_mismatch_claim.json) | OCR extracted invoice serial differs from chassis serial | Contradiction Detector: `OCR_SERIAL_MISMATCH` | **Manual Review Required** | High |
| **09** | [`09_unauthorized_repair_claim.json`](./09_unauthorized_repair_claim.json) | Chassis opened by uncertified third-party street technician | Policy Rule: `UNAUTHORIZED_SERVICE_CENTER` | **Manual Review Required** | High |
| **10** | [`10_boundary_date_claim.json`](./10_boundary_date_claim.json) | Defect occurred 3 days after nominal expiry (within 7d grace) | Policy Engine: `GRACE_PERIOD_DISCRETIONARY` | **Manual Review Required** | Medium |
| **11** | [`11_model_disagreement_claim.json`](./11_model_disagreement_claim.json) | Python model predicts Valid (0.94), GTM predicts Invalid (0.91) | Consensus Layer: `MODEL_DISAGREEMENT` | **Manual Review Required** | Medium |

---

## Automated Verification

All 11 cases are programmatically asserted and verified by the automated test suite in [`tests/test_srs_demonstration_cases.py`](../tests/test_srs_demonstration_cases.py):

```bash
python -m unittest tests/test_srs_demonstration_cases.py
```
