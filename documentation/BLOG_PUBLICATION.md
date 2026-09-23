# AssureX Technical Blog Publication Record
> **Aptech NextWave AI and ML Competition Deliverable #14**  
> *Software Requirements Specification (SRS Version 1.0) — Page 35–36 Compliance*

---

## 📌 Publication Metadata

| Field | Official Record Details |
|:---|:---|
| **Article Title** | **Building AssureX: A Dual-Model Warranty Claim Evaluation System** |
| **Subtitle** | *Technical overview of machine learning, OCR, visual classification, and configurable warranty rules* |
| **Platform** | **Medium** |
| **Live Article URL** | [https://medium.com/@samikhan031027/building-assurex-a-dual-model-warranty-claim-evaluation-system-8a30d3684111](https://medium.com/@samikhan031027/building-assurex-a-dual-model-warranty-claim-evaluation-system-8a30d3684111) |
| **Author** | Sami Khan &middot; AssureX Engineering Team |
| **Publication Date** | September 2026 |
| **Official Word Count** | **3,794+ Words** *(Exceeds mandatory $\ge 2,000$ words requirement)* |
| **Local Source File** | [`documentation/TECHNICAL_BLOG.md`](file:///c:/Users/sami/Desktop/techwiz%207/documentation/TECHNICAL_BLOG.md) |
| **In-App Reader Route**| `http://127.0.0.1:5000/blog` |

---

## 📋 Comprehensive 23-Topic SRS Coverage Checklist

Per SRS Section 1.10 (Deliverable 14, Page 35–36), the technical blog covers all 23 discussion topics:

| # | SRS Discussion Topic | Addressed in Section | Word Count / Coverage Status |
|:---:|:---|:---|:---:|
| 1 | **Business problem** | Section 1: Executive Summary & Business Problem | ✅ Covered in detail |
| 2 | **Background and necessity** | Section 2: Background and Operational Necessity | ✅ Covered in detail |
| 3 | **Proposed solution** | Section 1 & Section 3: Proposed Solution | ✅ Covered in detail |
| 4 | **Application architecture** | Section 3: High-Level Architecture Overview & Flowchart | ✅ Covered in detail |
| 5 | **Dataset creation** | Section 4.1: Statistical Distribution & Stratified Split | ✅ Covered in detail |
| 6 | **Dataset challenges** | Section 4.1: Edge cases, Class Balance & Noise Injection | ✅ Covered in detail |
| 7 | **Python model development** | Section 5.1 & 5.2: Tabular Feature Preprocessing & Training | ✅ Covered in detail |
| 8 | **Algorithms compared** | Section 5.2: Random Forest, HistGradientBoosting, MLP Benchmarking | ✅ Covered in detail |
| 9 | **Google Teachable Machine training** | Section 5.3: GTM MobileNet Backbone & Transfer Learning | ✅ Covered in detail |
| 10 | **Claim Summary Card generation** | Section 4.2: Standardized 640x420 Visual Summary Cards | ✅ Covered in detail |
| 11 | **Python integration** | Section 5.3 & 6.0: Local Runtime Engine & Pipeline Coupling | ✅ Covered in detail |
| 12 | **Model prediction comparison** | Section 6.0: Dual-Model Prediction Matrix | ✅ Covered in detail |
| 13 | **Confidence-score comparison** | Section 6.0: Absolute Delta Formula $\|\max(P_{\text{py}}) - \max(P_{\text{gtm}})\|$ | ✅ Covered in detail |
| 14 | **Warranty-rule design** | Section 7.0: Configurable JSON Policy Engine (3 Categories) | ✅ Covered in detail |
| 15 | **OCR and document processing** | Section 8.1 & 8.2: SHA-256 Fingerprinting & Regex Extraction | ✅ Covered in detail |
| 16 | **Difficulties encountered** | Section 13.0: Dual-modality latency & OCR entity variance | ✅ Covered in detail |
| 17 | **Model errors** | Section 13.0: False positive analysis & ambiguous borderline cases | ✅ Covered in detail |
| 18 | **Model disagreement cases** | Section 6.0 & 12.0: Demonstration Case 11 (Disagreement Handling) | ✅ Covered in detail |
| 19 | **Testing results** | Section 12.0: Unit, Integration, Boundary & Security Tests (38/38) | ✅ Covered in detail |
| 20 | **Security considerations** | Section 11.0: Cryptographic Hashing, RBAC, CSRF, Audit Logs | ✅ Covered in detail |
| 21 | **Limitations** | Section 13.0: Constraints of static card generation & OCR limits | ✅ Covered in detail |
| 22 | **Lessons learned** | Section 14.1: Key takeaways from multi-modal consensus | ✅ Covered in detail |
| 23 | **Future enhancements** | Section 14.2: Multimodal LLM integration, Mobile SDK & Edge AI | ✅ Covered in detail |

---

## 🚀 Publishing Instructions for Team Members

To republish or update the live blog on Medium or another free blogging platform:
1. Open the in-app blog at `http://127.0.0.1:5000/blog` and click **"Copy Markdown for Medium / Blogger"**, or copy directly from [`documentation/TECHNICAL_BLOG.md`](file:///c:/Users/sami/Desktop/techwiz%207/documentation/TECHNICAL_BLOG.md).
2. Log into your [Medium](https://medium.com/) or [Blogger](https://blogger.com/) account.
3. Create a **New Story** and paste the formatted article.
4. Add tags: `Machine Learning`, `Artificial Intelligence`, `Computer Vision`, `Python`, `Document Ops`.
5. Publish as a public story and update the **Primary Live URL** in this file and in `README.md`.
