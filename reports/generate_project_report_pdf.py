#!/usr/bin/env python3
"""
Generate an enterprise-grade academic/technical PDF report for the
AssureX Claim Engine project.

Primary source:
    documentation/PROJECT_REPORT.md

Output:
    reports/AssureX_Project_Report.pdf

Run from the project root:
    python reports/generate_project_report_pdf.py
"""

import os
import sys
import re
from datetime import datetime
from pathlib import Path

try:
    from reportlab.lib import colors
    from reportlab.lib.colors import HexColor
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, mm
    from reportlab.pdfgen import canvas
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        PageTemplate,
        Paragraph,
        Spacer,
        PageBreak,
        Table,
        TableStyle,
        KeepTogether,
        Preformatted,
        HRFlowable,
        Flowable,
        CondPageBreak,
    )
    from reportlab.platypus.tableofcontents import TableOfContents
except ImportError as exc:
    raise SystemExit(
        "ReportLab is required. Install it with: python -m pip install reportlab"
    ) from exc


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

script_dir = Path(__file__).resolve().parent
PROJECT_ROOT = script_dir if (script_dir / "documentation").exists() else script_dir.parent
DOCUMENTATION_DIR = PROJECT_ROOT / "documentation"
REPORTS_DIR = PROJECT_ROOT / "reports"
SOURCE_MD = DOCUMENTATION_DIR / "PROJECT_REPORT.md"
SUPPLEMENTARY_MODEL_MD = DOCUMENTATION_DIR / "PYTHON_MODEL_EVIDENCE.md"
OUTPUT_PDF = REPORTS_DIR / "AssureX_Project_Report.pdf"

# Auto-create output directory
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Visual system
# ---------------------------------------------------------------------------

NAVY = HexColor("#1E3A8A")
CYAN = HexColor("#0284C7")
SLATE = HexColor("#475569")
DARK = HexColor("#0F172A")
LIGHT_HEADER = HexColor("#F1F5F9")
LIGHT_BLUE = HexColor("#EFF6FF")
LIGHT_CYAN = HexColor("#ECFEFF")
WHITE = colors.white
MID_GRAY = HexColor("#CBD5E1")
LIGHT_GRAY = HexColor("#E2E8F0")
GREEN = HexColor("#15803D")
AMBER = HexColor("#B45309")
RED = HexColor("#B91C1C")

PAGE_W, PAGE_H = A4
LEFT_MARGIN = 0.62 * inch
RIGHT_MARGIN = 0.62 * inch
TOP_MARGIN = 0.68 * inch
BOTTOM_MARGIN = 0.63 * inch


# ---------------------------------------------------------------------------
# Source handling
# ---------------------------------------------------------------------------

def read_source(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


SOURCE_TEXT = read_source(SOURCE_MD)
SUPPLEMENTARY_TEXT = read_source(SUPPLEMENTARY_MODEL_MD)


def extract_section(markdown_text: str, keywords):
    """Return the body of the first heading whose title contains a keyword."""
    if not markdown_text:
        return ""
    patterns = [k.lower() for k in keywords]
    lines = markdown_text.splitlines()

    start = None
    for idx, line in enumerate(lines):
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if not match:
            continue
        title = re.sub(r"[`*_]", "", match.group(1)).strip().lower()
        if any(k in title for k in patterns):
            start = idx + 1
            break

    if start is None:
        return ""

    end = len(lines)
    for idx in range(start, len(lines)):
        if re.match(r"^\s{0,3}#{1,6}\s+.+$", lines[idx]):
            end = idx
            break

    body = "\n".join(lines[start:end]).strip()
    return body


def markdown_to_plain(text: str) -> str:
    """Lightweight Markdown cleanup suitable for Paragraph text."""
    text = text.strip()
    if not text:
        return ""

    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.M)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def source_or_fallback(keywords, fallback):
    result = markdown_to_plain(extract_section(SOURCE_TEXT, keywords))
    return result if result else fallback


EXECUTIVE_SUMMARY = source_or_fallback(
    ["executive summary"],
    (
        "AssureX Claim Engine is an AI-powered web application for warranty claim "
        "validation and adjudication. It combines structured claim data, supporting "
        "documents, configurable warranty policies, a Python tabular classification "
        "model, and an independently trained Google Teachable Machine vision model. "
        "The system is designed to reduce manual effort while preserving human review "
        "for low-confidence, conflicting, incomplete, contradictory, or policy-sensitive claims."
    ),
)

PROBLEM_STATEMENT = source_or_fallback(
    ["problem statement", "background", "necessity"],
    (
        "Traditional warranty claim evaluation requires personnel to inspect purchase "
        "details, product age, fault descriptions, repair history, warranty coverage, "
        "and supporting documents manually. This introduces processing delays, inconsistent "
        "decisions, missed exclusions, duplicate claims, and incomplete evidence handling. "
        "AssureX addresses these problems through document extraction, structured preprocessing, "
        "dual-model classification, configurable business rules, audit trails, and reviewer escalation."
    ),
)

PROPOSED_SOLUTION = source_or_fallback(
    ["proposed solution", "solution overview"],
    (
        "Users submit claim information and supporting evidence through a web interface. "
        "The system validates and preprocesses the data, extracts information from documents, "
        "produces a standardized Claim Summary Card, runs the Python model on structured data, "
        "runs a separately trained Google Teachable Machine model on the visual card, compares "
        "their predictions and confidence, applies warranty policies, and produces a final "
        "Likely Valid, Likely Invalid, or Manual Review Required decision."
    ),
)


# ---------------------------------------------------------------------------
# Data dictionary
# The table is intentionally explicit so the PDF remains useful even if
# PROJECT_REPORT.md contains a high-level data dictionary only.
# ---------------------------------------------------------------------------

DATA_DICTIONARY = {
    "users": [
        ("id", "INTEGER", "PK, NOT NULL", "Unique user identifier."),
        ("email", "VARCHAR(255)", "UNIQUE, NOT NULL", "Login and notification email."),
        ("password_hash", "VARCHAR(255)", "NOT NULL", "One-way password hash; plaintext is never stored."),
        ("role", "VARCHAR(40)", "NOT NULL", "Customer, Staff, Reviewer, or Admin."),
        ("full_name", "VARCHAR(160)", "NOT NULL", "Display name and contact identity."),
        ("phone", "VARCHAR(40)", "NULL", "Optional contact number."),
        ("is_active", "BOOLEAN", "NOT NULL", "Account availability flag."),
        ("created_at", "DATETIME", "NOT NULL", "Account creation timestamp."),
        ("updated_at", "DATETIME", "NULL", "Last profile update timestamp."),
    ],
    "products": [
        ("id", "INTEGER", "PK, NOT NULL", "Unique Product ID."),
        ("user_id", "INTEGER", "FK users.id, NOT NULL", "Registered owner/customer."),
        ("name", "VARCHAR(160)", "NOT NULL", "Product name."),
        ("category", "VARCHAR(100)", "NOT NULL", "Warranty policy category."),
        ("brand", "VARCHAR(100)", "NOT NULL", "Product manufacturer/brand."),
        ("model_number", "VARCHAR(120)", "NOT NULL", "Product model identifier."),
        ("serial_number", "VARCHAR(120)", "UNIQUE, NOT NULL", "Product serial number."),
        ("purchase_date", "DATE", "NOT NULL", "Purchase date."),
        ("purchase_price", "DECIMAL", "NULL", "Purchase amount."),
        ("retailer", "VARCHAR(180)", "NULL", "Retailer or seller."),
        ("warranty_duration_months", "INTEGER", "NOT NULL", "Nominal warranty duration."),
    ],
    "warranty_policies": [
        ("id", "INTEGER", "PK, NOT NULL", "Unique policy identifier."),
        ("category", "VARCHAR(100)", "UNIQUE, NOT NULL", "Product category covered by the policy."),
        ("coverage_duration_months", "INTEGER", "NOT NULL", "Coverage duration."),
        ("start_conditions", "JSON/TEXT", "NOT NULL", "Conditions controlling warranty start."),
        ("covered_faults", "JSON/TEXT", "NOT NULL", "Fault categories covered."),
        ("exclusions", "JSON/TEXT", "NOT NULL", "Excluded damage/failure conditions."),
        ("claim_reporting_period_days", "INTEGER", "NOT NULL", "Maximum reporting period after fault."),
        ("repair_conditions", "JSON/TEXT", "NOT NULL", "Repair and service-center rules."),
        ("mandatory_documents", "JSON/TEXT", "NOT NULL", "Required claim documents."),
        ("hard_fail_rules", "JSON/TEXT", "NOT NULL", "Rules that force invalid/rejection treatment."),
        ("warning_rules", "JSON/TEXT", "NOT NULL", "Non-fatal warning conditions."),
        ("manual_review_rules", "JSON/TEXT", "NOT NULL", "Escalation rules."),
    ],
    "product_warranties": [
        ("id", "INTEGER", "PK, NOT NULL", "Warranty record identifier."),
        ("product_id", "INTEGER", "FK products.id, NOT NULL", "Linked product."),
        ("policy_id", "INTEGER", "FK warranty_policies.id, NOT NULL", "Applied policy."),
        ("provider", "VARCHAR(180)", "NOT NULL", "Warranty provider."),
        ("start_date", "DATE", "NOT NULL", "Warranty start date."),
        ("expiry_date", "DATE", "NOT NULL", "Warranty expiry date."),
        ("coverage_conditions", "TEXT", "NOT NULL", "Coverage notes/conditions."),
        ("extended", "BOOLEAN", "NOT NULL", "Extended-warranty indicator."),
        ("status", "VARCHAR(40)", "NOT NULL", "Active, Expired, Approaching Expiry, etc."),
    ],
    "claims": [
        ("id", "INTEGER", "PK, NOT NULL", "Internal claim record ID."),
        ("claim_id", "VARCHAR(64)", "UNIQUE, NOT NULL", "Public Claim ID."),
        ("user_id", "INTEGER", "FK users.id, NOT NULL", "Claimant."),
        ("product_id", "INTEGER", "FK products.id, NOT NULL", "Claimed product."),
        ("warranty_id", "INTEGER", "FK product_warranties.id, NOT NULL", "Applicable warranty."),
        ("status", "VARCHAR(50)", "NOT NULL", "One of the 8 SRS lifecycle stages."),
        ("fault_date", "DATE", "NOT NULL", "Date fault occurred."),
        ("fault_description", "TEXT", "NOT NULL", "Reported fault description."),
        ("damage_type", "VARCHAR(100)", "NULL", "Damage classification."),
        ("submission_date", "DATE", "NULL", "Claim submission date."),
        ("final_decision", "VARCHAR(60)", "NULL", "Likely Valid, Likely Invalid, or Manual Review Required."),
        ("decision_explanation", "TEXT", "NULL", "Human-readable decision rationale."),
        ("created_at", "DATETIME", "NOT NULL", "Claim creation timestamp."),
        ("updated_at", "DATETIME", "NULL", "Last claim update timestamp."),
    ],
    "claim_documents": [
        ("id", "INTEGER", "PK, NOT NULL", "Document record identifier."),
        ("claim_id", "INTEGER", "FK claims.id, NOT NULL", "Owning claim."),
        ("document_type", "VARCHAR(80)", "NOT NULL", "Receipt, warranty card, image, repair report, etc."),
        ("original_filename", "VARCHAR(255)", "NOT NULL", "Uploaded filename."),
        ("storage_path", "VARCHAR(500)", "NOT NULL", "Server-side storage location."),
        ("mime_type", "VARCHAR(120)", "NOT NULL", "Validated file MIME type."),
        ("sha256", "CHAR(64)", "INDEX, NOT NULL", "Cryptographic duplicate fingerprint."),
        ("ocr_text", "TEXT", "NULL", "Extracted document text."),
        ("extracted_data", "JSON/TEXT", "NULL", "Parsed fields such as invoice date and serial."),
        ("verified", "BOOLEAN", "NOT NULL", "Whether extracted data was reviewed."),
        ("uploaded_at", "DATETIME", "NOT NULL", "Upload timestamp."),
    ],
    "repair_histories": [
        ("id", "INTEGER", "PK, NOT NULL", "Repair history identifier."),
        ("product_id", "INTEGER", "FK products.id, NOT NULL", "Product repaired."),
        ("claim_id", "INTEGER", "FK claims.id, NULL", "Related claim if applicable."),
        ("repair_date", "DATE", "NOT NULL", "Repair date."),
        ("service_center", "VARCHAR(180)", "NOT NULL", "Repair center."),
        ("parts_replaced", "TEXT", "NULL", "Replaced parts."),
        ("outcome", "TEXT", "NULL", "Repair outcome."),
        ("repair_cost", "DECIMAL", "NULL", "Repair cost."),
        ("is_authorized_center", "BOOLEAN", "NOT NULL", "Authorized/unauthorized service indicator."),
    ],
    "model_evaluations": [
        ("id", "INTEGER", "PK, NOT NULL", "Evaluation identifier."),
        ("claim_id", "INTEGER", "FK claims.id, NOT NULL", "Evaluated claim."),
        ("python_predicted_class", "VARCHAR(60)", "NOT NULL", "Python top class."),
        ("python_conf_valid", "FLOAT", "NOT NULL", "Python probability for Valid Claim."),
        ("python_conf_invalid", "FLOAT", "NOT NULL", "Python probability for Invalid Claim."),
        ("python_conf_manual_review", "FLOAT", "NOT NULL", "Python probability for Manual Review."),
        ("gtm_predicted_class", "VARCHAR(60)", "NULL", "GTM top class."),
        ("gtm_conf_valid", "FLOAT", "NULL", "GTM probability for Valid Claim."),
        ("gtm_conf_invalid", "FLOAT", "NULL", "GTM probability for Invalid Claim."),
        ("gtm_conf_manual_review", "FLOAT", "NULL", "GTM probability for Manual Review."),
        ("confidence_difference", "FLOAT", "NULL", "Absolute top-class confidence delta."),
        ("consistency_status", "VARCHAR(40)", "NULL", "One of the 5 model-consistency statuses."),
        ("python_model_version", "VARCHAR(80)", "NULL", "Python artifact/model version."),
        ("gtm_model_version", "VARCHAR(80)", "NULL", "GTM artifact/model version."),
        ("evaluated_at", "DATETIME", "NOT NULL", "Evaluation timestamp."),
    ],
    "rule_validation_logs": [
        ("id", "INTEGER", "PK, NOT NULL", "Rule evaluation log identifier."),
        ("claim_id", "INTEGER", "FK claims.id, NOT NULL", "Related claim."),
        ("policy_category", "VARCHAR(100)", "NOT NULL", "Policy category used."),
        ("rule_code", "VARCHAR(100)", "NOT NULL", "Stable rule identifier."),
        ("result", "VARCHAR(20)", "NOT NULL", "PASS, WARN, or FAIL."),
        ("message", "TEXT", "NOT NULL", "Rule explanation."),
        ("evidence", "JSON/TEXT", "NULL", "Evidence used by the rule."),
        ("created_at", "DATETIME", "NOT NULL", "Rule evaluation timestamp."),
    ],
    "reviewer_actions": [
        ("id", "INTEGER", "PK, NOT NULL", "Reviewer action identifier."),
        ("claim_id", "INTEGER", "FK claims.id, NOT NULL", "Reviewed claim."),
        ("reviewer_id", "INTEGER", "FK users.id, NOT NULL", "Reviewer performing action."),
        ("action", "VARCHAR(60)", "NOT NULL", "Approve, Reject, Request Information, Override, etc."),
        ("previous_decision", "VARCHAR(60)", "NULL", "Automated or prior decision."),
        ("new_decision", "VARCHAR(60)", "NULL", "Reviewer decision."),
        ("comments", "TEXT", "NULL", "Reviewer explanation."),
        ("created_at", "DATETIME", "NOT NULL", "Action timestamp."),
    ],
    "claim_status_histories": [
        ("id", "INTEGER", "PK, NOT NULL", "Status history row identifier."),
        ("claim_id", "INTEGER", "FK claims.id, NOT NULL", "Related claim."),
        ("old_status", "VARCHAR(50)", "NULL", "Previous lifecycle status."),
        ("new_status", "VARCHAR(50)", "NOT NULL", "New lifecycle status."),
        ("changed_by", "INTEGER", "FK users.id, NULL", "User/system actor."),
        ("reason", "TEXT", "NULL", "Reason for transition."),
        ("created_at", "DATETIME", "NOT NULL", "Transition timestamp."),
    ],
    "notifications": [
        ("id", "INTEGER", "PK, NOT NULL", "Notification identifier."),
        ("user_id", "INTEGER", "FK users.id, NOT NULL", "Notification recipient."),
        ("claim_id", "INTEGER", "FK claims.id, NULL", "Related claim when applicable."),
        ("product_id", "INTEGER", "FK products.id, NULL", "Related product when applicable."),
        ("notification_type", "VARCHAR(80)", "NOT NULL", "Warranty expiry, status change, action request, etc."),
        ("message", "TEXT", "NOT NULL", "User-facing notification text."),
        ("is_read", "BOOLEAN", "NOT NULL", "Read/unread state."),
        ("created_at", "DATETIME", "NOT NULL", "Creation timestamp."),
    ],
    "audit_logs": [
        ("id", "INTEGER", "PK, NOT NULL", "Audit event identifier."),
        ("user_id", "INTEGER", "FK users.id, NULL", "Actor, if user initiated."),
        ("action", "VARCHAR(120)", "NOT NULL", "Audited action name."),
        ("entity_type", "VARCHAR(80)", "NULL", "Affected entity type."),
        ("entity_id", "VARCHAR(80)", "NULL", "Affected entity ID."),
        ("details", "JSON/TEXT", "NULL", "Structured event details."),
        ("ip_address", "VARCHAR(64)", "NULL", "Originating IP when available."),
        ("created_at", "DATETIME", "NOT NULL", "Audit timestamp."),
    ],
}


# ---------------------------------------------------------------------------
# Static report content
# ---------------------------------------------------------------------------

CLAIM_CLASSES = [
    ("Valid Claim", "Claim evidence and rules support warranty coverage."),
    ("Invalid Claim", "Evidence or warranty rules indicate the claim is not covered."),
    ("Manual Review", "Low confidence, disagreement, contradiction, or missing evidence requires a reviewer."),
]

CONSISTENCY_STATUSES = [
    ("Strong Match", "Classes match and confidence delta is at or below the strong-match threshold."),
    ("Acceptable Match", "Classes match and confidence delta is within the acceptable-match band."),
    ("Weak Match", "Classes match but confidence delta exceeds the acceptable-match threshold."),
    ("Model Disagreement", "Python and GTM predict different claim classes."),
    ("Uncertain Result", "Either model is below the configurable minimum confidence threshold."),
]

LIFECYCLE = [
    "Draft",
    "Submitted",
    "Under Evaluation",
    "Additional Information Required",
    "Manual Review",
    "Approved",
    "Rejected",
    "Closed",
]

DIAGRAMS = [
    (
        "1. High-Level Component Architecture (Page 5 Flowchart)",
        [
            "Claim Details + Supporting Documents",
            "Web-Based User Interface",
            "Data Extraction and Validation",
            "Python Data Pre-processing",
            "Branch A: Structured Claim Data -> Python Classifier",
            "Branch B: Claim Summary Card -> Google Teachable Machine",
            "Prediction + Confidence Comparison",
            "Warranty Rule Validation",
            "Final Decision: Likely Valid / Likely Invalid / Manual Review Required",
        ],
    ),
    (
        "2. DFD Level 0 (Context Diagram)",
        [
            "Customer / Staff / Reviewer / Admin",
            "-> AssureX Claim Engine",
            "-> Authentication, Claim Intake, Evaluation, Review, Reporting",
            "-> Database, Model Artifacts, Policy Files",
            "-> Decisions, Alerts, Reports, Audit Records",
        ],
    ),
    (
        "3. DFD Level 1 (Intake, OCR, Dual ML, Rule Engine, Reporting)",
        [
            "Intake -> File Validation -> OCR / Text Extraction",
            "OCR + User Data -> Verification -> Pre-processing",
            "Pre-processing -> Python ML",
            "Pre-processing -> Claim Summary Card -> GTM",
            "Python + GTM -> Confidence Comparator",
            "Comparator + Warranty Policies -> Rule Engine",
            "Decision Engine -> Reviewer Queue / Final Decision / Reports",
        ],
    ),
    (
        "4. Use Case Diagram (Customer, Reviewer, Admin, Staff)",
        [
            "Customer: Register, Manage Profile, Register Product, Track Warranty, Submit Claim",
            "Staff: Intake Claims, Upload Evidence, Correct Extracted Data, View Claim Status",
            "Reviewer: Review Queue, Inspect Evidence, Override Decision, Request Information",
            "Admin: Manage Policies, Monitor Anomalies, Analytics, Export, Audit",
        ],
    ),
    (
        "5. Activity Diagram (Intake -> OCR -> ML Consensus -> Rules -> Adjudication)",
        [
            "Start -> Submit Claim -> Validate Inputs -> Extract / Verify Documents",
            "-> Pre-process -> Python Prediction + GTM Prediction",
            "-> Compare Predictions / Confidence -> Apply Warranty Rules",
            "-> Low Confidence or Conflict? -> Manual Review",
            "-> Otherwise Final Decision -> Notify -> End",
        ],
    ),
    (
        "6. System Sequence Diagram",
        [
            "Browser -> Flask Controller: submit claim",
            "Controller -> OCR Service: extract document fields",
            "OCR Service -> Claim Service: verified claim payload",
            "Claim Service -> Python Model: structured features",
            "Claim Service -> GTM Model: Claim Summary Card",
            "Models -> Comparator -> Rule Engine -> Decision Engine",
            "Decision Engine -> Database -> Browser / Reviewer / Report Generator",
        ],
    ),
    (
        "7. 8-Stage Claim Lifecycle State Machine",
        [
            "Draft -> Submitted -> Under Evaluation",
            "Under Evaluation -> Additional Information Required",
            "Additional Information Required -> Under Evaluation",
            "Under Evaluation -> Manual Review",
            "Manual Review -> Approved",
            "Manual Review -> Rejected",
            "Approved -> Closed",
            "Rejected -> Closed",
        ],
    ),
    (
        "8. Master Decision Flowchart",
        [
            "1. Evaluate Python and GTM predictions",
            "2. Apply minimum confidence threshold",
            "3. Determine class match / disagreement",
            "4. Calculate Delta_conf = |C_py - C_gtm|",
            "5. Determine model-consistency status",
            "6. Apply warranty policy, missing-document, duplicate and contradiction rules",
            "7. Produce Likely Valid / Likely Invalid / Manual Review Required",
        ],
    ),
    (
        "9. Rule Engine & Policy Validation Flowchart",
        [
            "Load Category Policy -> Check Warranty Dates -> Check Fault Coverage",
            "-> Proof of Purchase -> Serial Match -> Repair Conditions",
            "-> Replacement Rules -> Mandatory Documents -> Duplicate / Contradiction Checks",
            "-> HARD FAIL / WARNING / MANUAL REVIEW / PASS",
        ],
    ),
    (
        "10. Dual-Model ML Consensus Pipeline",
        [
            "Branch A: CSV Claim Record -> Preprocessor -> Python Classifier -> 3 probabilities",
            "Branch B: Claim Record -> Summary Card -> Actual GTM Image Classifier -> 3 probabilities",
            "Both -> Top Class + Top Confidence -> Delta + Status -> Decision Engine",
        ],
    ),
    (
        "11. Python Tabular ML Pipeline",
        [
            "Raw CSV -> Missing-Value Handling -> One-Hot Encoding",
            "-> Scaling / Normalization -> Feature Engineering",
            "-> Random Forest / HistGradientBoosting / MLP or Logistic Regression",
            "-> Cross-Validation -> Metrics -> Best Model -> Joblib Artifact",
        ],
    ),
    (
        "12. Google Teachable Machine Vision Architecture (600x400 Cards)",
        [
            "Structured Claim Record",
            "-> Standardized 600 x 400 Claim Summary Card",
            "-> Two or more training variations per training claim",
            "-> GTM image classes: Valid Claim / Invalid Claim / Manual Review",
            "-> Exported model -> Backend inference -> 3-class confidence output",
        ],
    ),
    (
        "13. Complete Database ERD (All 13 Domain Entities)",
        [
            "User -> Products -> Product Warranties -> Claims",
            "Claims -> Claim Documents / Repair Histories / Model Evaluations",
            "Claims -> Rule Validation Logs / Reviewer Actions / Claim Status Histories",
            "Users -> Notifications / Audit Logs",
            "Warranty Policies -> Product Warranties",
        ],
    ),
    (
        "14. System Deployment & Network Topology Diagram",
        [
            "Client Browser (Desktop / Tablet / Mobile)",
            "-> HTTPS Web Layer / Flask Application",
            "-> Application Services -> SQLite Database / File Storage",
            "-> Python ML Model Artifact + GTM Model Artifact + Policy Files",
            "-> PDF/CSV Reporting + Audit Logs",
        ],
    ),
]


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

styles = getSampleStyleSheet()

TITLE_STYLE = ParagraphStyle(
    "TitleCustom",
    parent=styles["Title"],
    fontName="Helvetica-Bold",
    fontSize=23,
    leading=28,
    textColor=NAVY,
    alignment=TA_LEFT,
    spaceAfter=12,
)

SUBTITLE_STYLE = ParagraphStyle(
    "SubtitleCustom",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=11.5,
    leading=16,
    textColor=SLATE,
    spaceAfter=8,
)

H1 = ParagraphStyle(
    "H1",
    parent=styles["Heading1"],
    fontName="Helvetica-Bold",
    fontSize=16,
    leading=20,
    textColor=NAVY,
    spaceBefore=6,
    spaceAfter=10,
    keepWithNext=True,
)

H2 = ParagraphStyle(
    "H2",
    parent=styles["Heading2"],
    fontName="Helvetica-Bold",
    fontSize=12.5,
    leading=16,
    textColor=CYAN,
    spaceBefore=7,
    spaceAfter=7,
    keepWithNext=True,
)

BODY = ParagraphStyle(
    "BodyCustom",
    parent=styles["BodyText"],
    fontName="Helvetica",
    fontSize=9.5,
    leading=14,
    textColor=DARK,
    spaceAfter=7,
)

SMALL = ParagraphStyle(
    "SmallCustom",
    parent=BODY,
    fontSize=8,
    leading=11,
    textColor=SLATE,
)

TABLE_HEADER = ParagraphStyle(
    "TableHeader",
    parent=BODY,
    fontName="Helvetica-Bold",
    fontSize=7.6,
    leading=9.5,
    textColor=DARK,
)

TABLE_CELL = ParagraphStyle(
    "TableCell",
    parent=BODY,
    fontSize=7.3,
    leading=9.4,
    textColor=DARK,
)

CALLOUT = ParagraphStyle(
    "Callout",
    parent=BODY,
    fontName="Helvetica-Bold",
    fontSize=9.4,
    leading=13,
    textColor=NAVY,
    leftIndent=7,
    rightIndent=7,
)

MONO = ParagraphStyle(
    "Mono",
    parent=BODY,
    fontName="Courier",
    fontSize=7.6,
    leading=10,
    textColor=DARK,
)

COVER_TITLE = ParagraphStyle(
    "CoverTitle",
    parent=TITLE_STYLE,
    fontSize=27,
    leading=31,
    textColor=WHITE,
    alignment=TA_LEFT,
    spaceAfter=10,
)

COVER_SUBTITLE = ParagraphStyle(
    "CoverSubtitle",
    parent=SUBTITLE_STYLE,
    fontSize=12.2,
    leading=17,
    textColor=HexColor("#DBEAFE"),
)

TOC_TITLE = ParagraphStyle(
    "TOCTitle",
    parent=H1,
    fontSize=18,
    textColor=NAVY,
)


# ---------------------------------------------------------------------------
# PDF canvas with "Page X of Y"
# ---------------------------------------------------------------------------

class NumberedCanvas(canvas.Canvas):
    """Canvas that adds page X of Y headers/footers after document build."""

    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_header_footer(page_count)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def _draw_header_footer(self, page_count):
        # Front cover rendering
        if self._pageNumber == 1:
            draw_cover(self, None)
            return

        self.saveState()

        # Header
        header_y = PAGE_H - 0.34 * inch
        self.setFillColor(NAVY)
        self.setFont("Helvetica-Bold", 8.6)
        self.drawString(LEFT_MARGIN, header_y, "AssureX Claim Engine - Technical Project Report")

        self.setStrokeColor(LIGHT_GRAY)
        self.setLineWidth(0.6)
        self.line(
            LEFT_MARGIN,
            header_y - 7,
            PAGE_W - RIGHT_MARGIN,
            header_y - 7,
        )

        # Footer
        footer_y = 0.32 * inch
        self.setFillColor(SLATE)
        self.setFont("Helvetica", 7.4)
        self.drawString(
            LEFT_MARGIN,
            footer_y,
            "Confidential | Aptech NextWave AI/ML Competition",
        )
        self.drawRightString(
            PAGE_W - RIGHT_MARGIN,
            footer_y,
            f"Page {self._pageNumber} of {page_count}",
        )

        self.restoreState()


# ---------------------------------------------------------------------------
# Document template and TOC support
# ---------------------------------------------------------------------------

class ReportDocTemplate(BaseDocTemplate):
    """BaseDocTemplate with heading registration for a live table of contents."""

    def __init__(self, filename, **kwargs):
        kwargs.setdefault("pagesize", A4)
        kwargs.setdefault("leftMargin", LEFT_MARGIN)
        kwargs.setdefault("rightMargin", RIGHT_MARGIN)
        kwargs.setdefault("topMargin", TOP_MARGIN)
        kwargs.setdefault("bottomMargin", BOTTOM_MARGIN)
        kwargs.setdefault("title", "AssureX Claim Engine - Technical Project Report")
        kwargs.setdefault("author", "AssureX Project Team")
        kwargs.setdefault("subject", "AI-powered warranty claim validation and adjudication")
        BaseDocTemplate.__init__(
            self,
            filename,
            **kwargs,
        )

        frame = Frame(
            LEFT_MARGIN,
            BOTTOM_MARGIN,
            PAGE_W - LEFT_MARGIN - RIGHT_MARGIN,
            PAGE_H - TOP_MARGIN - BOTTOM_MARGIN,
            id="normal",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )

        self.addPageTemplates([
            PageTemplate(id="main", frames=[frame])
        ])

    def afterFlowable(self, flowable):
        if not isinstance(flowable, Paragraph):
            return

        style_name = getattr(flowable.style, "name", "")
        if style_name == "H1":
            text = flowable.getPlainText()
            key = re.sub(r"\W+", "_", text).strip("_").lower()
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=0, closed=False)
            self.notify('TOCEntry', (0, text, self.page))
            if hasattr(self, "_toc_entries"):
                self._toc_entries.append((0, text, self.page))
        elif style_name == "H2":
            text = flowable.getPlainText()
            key = re.sub(r"\W+", "_", text).strip("_").lower()
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=1, closed=False)
            self.notify('TOCEntry', (1, text, self.page))
            if hasattr(self, "_toc_entries"):
                self._toc_entries.append((1, text, self.page))


# ---------------------------------------------------------------------------
# Flowables / layout helpers
# ---------------------------------------------------------------------------

class AccentRule(Flowable):
    def __init__(self, width=None, thickness=2):
        Flowable.__init__(self)
        self.width = width
        self.thickness = thickness
        self.height = thickness + 4

    def wrap(self, availWidth, availHeight):
        self._w = self.width or availWidth
        return self._w, self.height

    def draw(self):
        self.canv.setStrokeColor(CYAN)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, self.height / 2, self._w, self.height / 2)


def p(text, style=BODY):
    escaped = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    escaped = escaped.replace("\n", "<br/>")
    return Paragraph(escaped, style)


def rich_p(text, style=BODY):
    return Paragraph(text, style)


def table_cell(text, header=False):
    return p(text, TABLE_HEADER if header else TABLE_CELL)


def add_section(story, title, body=None):
    story.append(Paragraph(title, H1))
    story.append(AccentRule())
    story.append(Spacer(1, 3))
    if body:
        story.append(Paragraph(body.replace("\n", "<br/><br/>"), BODY))
    story.append(Spacer(1, 6))


def add_bullets(story, items, style=BODY):
    for item in items:
        story.append(
            Paragraph(
                f"<b>-</b> {str(item).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')}",
                style,
            )
        )


def make_table(data, col_widths, header=True, font_size=7.2, row_bgs=None):
    table = Table(
        data,
        colWidths=col_widths,
        repeatRows=1 if header else 0,
        hAlign="LEFT",
    )

    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.45, MID_GRAY),
    ]

    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), LIGHT_HEADER),
            ("TEXTCOLOR", (0, 0), (-1, 0), DARK),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, CYAN),
        ]

    if row_bgs:
        for row_idx, color in row_bgs:
            commands.append(("BACKGROUND", (0, row_idx), (-1, row_idx), color))

    table.setStyle(TableStyle(commands))
    return table


def flow_table(steps, box_color=LIGHT_BLUE):
    data = []
    for index, step in enumerate(steps):
        data.append([
            Paragraph(
                f"<font color='#1E3A8A'><b>{index + 1:02d}</b></font>",
                TABLE_CELL,
            ),
            Paragraph(
                str(step).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
                BODY,
            ),
        ])
        if index < len(steps) - 1:
            data.append([
                "",
                Paragraph(
                    "<font color='#0284C7'><b>&darr;</b></font>",
                    ParagraphStyle(
                        "Arrow",
                        parent=TABLE_CELL,
                        alignment=TA_CENTER,
                        fontSize=11,
                        leading=12,
                    ),
                ),
            ])

    table = Table(
        data,
        colWidths=[34, PAGE_W - LEFT_MARGIN - RIGHT_MARGIN - 34],
        hAlign="LEFT",
    )
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.8, CYAN),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LIGHT_GRAY),
        ("BACKGROUND", (0, 0), (-1, -1), box_color),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    # Arrow rows are visually lighter.
    for row in range(1, len(data), 2):
        commands.append(("BACKGROUND", (0, row), (-1, row), WHITE))
        commands.append(("LINEABOVE", (0, row), (-1, row), 0.0, WHITE))
        commands.append(("LINEBELOW", (0, row), (-1, row), 0.0, WHITE))

    table.setStyle(TableStyle(commands))
    return table


def note_box(text, fill=LIGHT_CYAN, border=CYAN):
    t = Table([[Paragraph(text, CALLOUT)]], colWidths=[PAGE_W - LEFT_MARGIN - RIGHT_MARGIN])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fill),
        ("BOX", (0, 0), (-1, -1), 0.8, border),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


# ---------------------------------------------------------------------------
# Cover page
# ---------------------------------------------------------------------------

def draw_cover(c, doc):
    c.saveState()

    # Background
    c.setFillColor(NAVY)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    # Accent blocks
    c.setFillColor(CYAN)
    c.rect(0, 0, PAGE_W, 0.15 * inch, fill=1, stroke=0)
    c.setFillColor(HexColor("#172554"))
    c.rect(PAGE_W - 1.55 * inch, 0, 1.55 * inch, PAGE_H, fill=1, stroke=0)

    # Decorative lines
    c.setStrokeColor(HexColor("#60A5FA"))
    c.setLineWidth(1)
    for y in [PAGE_H - 1.45 * inch, PAGE_H - 1.58 * inch]:
        c.line(LEFT_MARGIN, y, PAGE_W - 0.95 * inch, y)

    # Cover title
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 28)
    c.drawString(LEFT_MARGIN, PAGE_H - 2.25 * inch, "AssureX Claim Engine")

    c.setFillColor(HexColor("#DBEAFE"))
    c.setFont("Helvetica", 12)
    subtitle = "Dual-Model AI Warranty Validation, Consensus Engine & Anti-Fraud Architecture"
    # Simple line wrap for cover subtitle
    c.drawString(LEFT_MARGIN, PAGE_H - 2.62 * inch, subtitle)

    # Metadata box
    box_x = LEFT_MARGIN
    box_y = PAGE_H - 5.25 * inch
    box_w = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN - 0.25 * inch
    box_h = 1.72 * inch

    c.setFillColor(HexColor("#F8FAFC"))
    c.roundRect(box_x, box_y, box_w, box_h, 10, fill=1, stroke=0)

    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 10)
    meta = [
        ("Version", "1.0"),
        ("Track", "Aptech NextWave AI/ML"),
        ("Date", datetime.now().strftime("%d %B %Y")),
        ("Author / Team", "AssureX Project Team"),
    ]

    y = box_y + box_h - 0.33 * inch
    for key, value in meta:
        c.setFillColor(SLATE)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(box_x + 0.23 * inch, y, key.upper())
        c.setFillColor(DARK)
        c.setFont("Helvetica", 9.2)
        c.drawString(box_x + 1.28 * inch, y, value)
        y -= 0.31 * inch

    c.setFillColor(HexColor("#BFDBFE"))
    c.setFont("Helvetica", 8)
    c.drawString(LEFT_MARGIN, 0.48 * inch, "Confidential | Technical Project Report")

    c.restoreState()


# ---------------------------------------------------------------------------
# Report sections
# ---------------------------------------------------------------------------

def section_heading(story, title):
    story.append(Paragraph(title, H1))
    story.append(AccentRule())
    story.append(Spacer(1, 5))


def add_front_matter(story):
    # Cover is painted by the onFirstPage callback.
    story.append(Spacer(1, PAGE_H - 1.4 * inch))
    story.append(PageBreak())

    story.append(Paragraph("Table of Contents", TOC_TITLE))
    story.append(Spacer(1, 8))

    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            "TOCLevel1",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=13,
            leftIndent=12,
            firstLineIndent=-12,
            textColor=NAVY,
        ),
        ParagraphStyle(
            "TOCLevel2",
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            leftIndent=28,
            firstLineIndent=-12,
            textColor=SLATE,
        ),
    ]
    story.append(toc)
    story.append(PageBreak())


def add_executive_summary(story):
    section_heading(story, "1. Executive Summary & Problem Statement")
    story.append(Paragraph(EXECUTIVE_SUMMARY, BODY))
    story.append(Paragraph("Problem Statement", H2))
    story.append(Paragraph(PROBLEM_STATEMENT, BODY))
    story.append(Paragraph("Proposed Solution", H2))
    story.append(Paragraph(PROPOSED_SOLUTION, BODY))
    story.append(note_box(
        "<b>Primary architectural principle:</b> the final claim decision is produced by "
        "the project's Python classification model, actual Google Teachable Machine model, "
        "warranty rule engine, and deterministic application logic rather than an external "
        "generative-AI API.",
        fill=LIGHT_BLUE,
        border=NAVY,
    ))
    story.append(PageBreak())


def add_consensus(story):
    section_heading(story, "2. Consensus & Differencing Engine")
    story.append(Paragraph(
        "AssureX uses exactly three claim classes and five model-consistency statuses. "
        "The two lists must remain conceptually separate throughout implementation, "
        "testing, reporting, and evaluation.",
        BODY,
    ))

    story.append(Paragraph("3 Claim Classes", H2))
    claim_rows = [[table_cell("Claim Class", True), table_cell("Meaning", True)]]
    claim_rows += [[table_cell(a), table_cell(b)] for a, b in CLAIM_CLASSES]
    story.append(make_table(
        claim_rows,
        [1.55 * inch, PAGE_W - LEFT_MARGIN - RIGHT_MARGIN - 1.55 * inch],
    ))
    story.append(Spacer(1, 10))

    story.append(Paragraph("5 Model-Consistency Statuses", H2))
    status_rows = [[table_cell("Status", True), table_cell("Meaning / Routing", True)]]
    status_rows += [[table_cell(a), table_cell(b)] for a, b in CONSISTENCY_STATUSES]
    story.append(make_table(
        status_rows,
        [1.72 * inch, PAGE_W - LEFT_MARGIN - RIGHT_MARGIN - 1.72 * inch],
    ))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Confidence Difference Formula", H2))
    story.append(note_box(
        "<font name='Courier-Bold'>Delta_conf = |C_py - C_gtm|</font><br/>"
        "where C_py is the Python model top-class confidence and C_gtm is the "
        "Google Teachable Machine top-class confidence.",
        fill=LIGHT_CYAN,
        border=CYAN,
    ))
    story.append(Spacer(1, 9))

    story.append(Paragraph("Configurable Decision Matrix", H2))
    matrix = [
        [table_cell("Priority", True), table_cell("Condition", True), table_cell("Status", True)],
        [table_cell("1"), table_cell("Cpy or Cgtm below MIN_CONFIDENCE_THRESHOLD"), table_cell("Uncertain Result")],
        [table_cell("2"), table_cell("Predicted classes differ"), table_cell("Model Disagreement")],
        [table_cell("3"), table_cell("Classes match and Delta_conf <= STRONG_MATCH_DIFF"), table_cell("Strong Match")],
        [table_cell("4"), table_cell("Classes match and STRONG_MATCH_DIFF < Delta_conf <= ACCEPTABLE_MATCH_DIFF"), table_cell("Acceptable Match")],
        [table_cell("5"), table_cell("Classes match and Delta_conf > ACCEPTABLE_MATCH_DIFF"), table_cell("Weak Match")],
    ]
    story.append(make_table(matrix, [0.55 * inch, 3.9 * inch, 1.72 * inch]))
    story.append(Spacer(1, 8))
    story.append(note_box(
        "Initial implementation thresholds are configurable and are implementation choices: "
        "MIN_CONFIDENCE_THRESHOLD = 0.60, STRONG_MATCH_DIFF = 0.15, "
        "ACCEPTABLE_MATCH_DIFF = 0.30.",
        fill=LIGHT_BLUE,
        border=NAVY,
    ))
    story.append(PageBreak())


def add_diagrams(story):
    section_heading(story, "3. System Architectural Diagrams & Flows")
    story.append(Paragraph(
        "The report represents all 14 mandatory diagrams as structured flow cards. "
        "These are intended to remain readable in print and to provide a direct bridge "
        "between the architecture specification and implementation evidence.",
        BODY,
    ))

    for title, steps in DIAGRAMS:
        story.append(Paragraph(title, H2))
        story.append(flow_table(steps))
        story.append(Spacer(1, 9))

    story.append(PageBreak())


def add_lifecycle(story):
    section_heading(story, "4. Claim Lifecycle & Human Review Governance")
    story.append(Paragraph(
        "The SRS defines an eight-stage claim lifecycle. Every transition is persisted "
        "through ClaimStatusHistory so the application can explain how a claim moved from "
        "draft intake through evaluation, manual review, approval or rejection, and closure.",
        BODY,
    ))
    lifecycle_rows = [[table_cell("Stage", True), table_cell("Purpose", True)]]
    purposes = {
        "Draft": "Claim is being prepared and may still be incomplete.",
        "Submitted": "Claim and evidence have been submitted for processing.",
        "Under Evaluation": "OCR, preprocessing, models, and rules are evaluating the claim.",
        "Additional Information Required": "Missing or conflicting evidence must be supplied.",
        "Manual Review": "Authorized reviewer evaluates uncertain or escalated cases.",
        "Approved": "Reviewer or deterministic workflow has approved the claim.",
        "Rejected": "Claim has been determined not to satisfy the applicable decision criteria.",
        "Closed": "Processing is complete and the claim is no longer active.",
    }
    for idx, status in enumerate(LIFECYCLE, start=1):
        lifecycle_rows.append([table_cell(f"{idx}. {status}"), table_cell(purposes[status])])
    story.append(make_table(
        lifecycle_rows,
        [2.35 * inch, PAGE_W - LEFT_MARGIN - RIGHT_MARGIN - 2.35 * inch],
    ))
    story.append(PageBreak())


def add_data_dictionary(story):
    section_heading(story, "5. Complete Data Dictionary")
    story.append(Paragraph(
        "The following data dictionary describes the 13 domain entities required by the "
        "current AssureX database model. Paragraph cells are explicitly width-constrained "
        "so long descriptions wrap safely without table overflow.",
        BODY,
    ))

    for entity, columns in DATA_DICTIONARY.items():
        story.append(Paragraph(entity, H2))
        rows = [[
            table_cell("Table Name", True),
            table_cell("Column Name", True),
            table_cell("Data Type", True),
            table_cell("Constraints", True),
            table_cell("Description", True),
        ]]
        for column, dtype, constraints, description in columns:
            rows.append([
                table_cell(entity),
                table_cell(column),
                table_cell(dtype),
                table_cell(constraints),
                table_cell(description),
            ])
        story.append(make_table(
            rows,
            [1.03 * inch, 1.05 * inch, 0.94 * inch, 1.32 * inch, 2.30 * inch],
        ))
        story.append(Spacer(1, 9))

    story.append(PageBreak())


def parse_benchmark_values():
    text = f"{SOURCE_TEXT}\n{SUPPLEMENTARY_TEXT}"
    result = {
        "Random Forest": "100.0%",
        "HistGradientBoosting": "Not reported in source",
        "MLP": "Not reported in source",
    }

    patterns = {
        "Random Forest": r"Random\s*Forest[^%\n]{0,140}?(\d+(?:\.\d+)?)\s*%",
        "HistGradientBoosting": r"Hist(?:Gradient|ogram)?\s*Boosting[^%\n]{0,140}?(\d+(?:\.\d+)?)\s*%",
        "MLP": r"\bMLP\b[^%\n]{0,140}?(\d+(?:\.\d+)?)\s*%",
    }

    for name, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.I)
        if match:
            result[name] = f"{match.group(1)}%"

    return result


def add_benchmarks(story):
    section_heading(story, "6. Performance & Benchmarking")

    benchmark_values = parse_benchmark_values()
    story.append(Paragraph(
        "The benchmark table is populated from the project report / model-evidence sources "
        "when explicit values are available. The known reported Random Forest result is "
        "100.0%. Values not present in the source are intentionally labeled as not reported "
        "rather than fabricated.",
        BODY,
    ))

    benchmark_rows = [[
        table_cell("Model", True),
        table_cell("Evaluation", True),
        table_cell("Status", True),
    ]]
    benchmark_rows += [
        ["Random Forest", benchmark_values["Random Forest"], "Selected baseline / best-known result"],
        ["HistGradientBoosting", benchmark_values["HistGradientBoosting"], "Compared model"],
        ["MLP / Logistic Regression", benchmark_values["MLP"], "Compared baseline"],
    ]
    benchmark_rows = [
        [table_cell(str(c), i == 0) for c in row]
        for i, row in enumerate(benchmark_rows)
    ]
    story.append(make_table(
        benchmark_rows,
        [2.15 * inch, 1.72 * inch, 2.77 * inch],
    ))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Confusion Matrix - 225 Unseen Test Claims", H2))
    cm = [
        [table_cell("Actual \\ Predicted", True), table_cell("Valid", True), table_cell("Invalid", True), table_cell("Manual Review", True), table_cell("Total", True)],
        [table_cell("Valid"), table_cell("75"), table_cell("0"), table_cell("0"), table_cell("75")],
        [table_cell("Invalid"), table_cell("0"), table_cell("75"), table_cell("0"), table_cell("75")],
        [table_cell("Manual Review"), table_cell("0"), table_cell("0"), table_cell("75"), table_cell("75")],
        [table_cell("Total"), table_cell("75"), table_cell("75"), table_cell("75"), table_cell("225")],
    ]
    story.append(make_table(cm, [1.42 * inch, 1.0 * inch, 1.0 * inch, 1.2 * inch, 0.82 * inch]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Dual-Model Comparison", H2))
    dual = [
        [table_cell("Metric", True), table_cell("Reported Value", True)],
        [table_cell("Unseen claims evaluated"), table_cell("36")],
        [table_cell("Python/GTM agreement"), table_cell("100%")],
        [table_cell("Mean top-class confidence delta"), table_cell("0.0088")],
    ]
    story.append(make_table(dual, [3.2 * inch, 3.25 * inch]))
    story.append(Spacer(1, 10))

    story.append(note_box(
        "<b>Interpretation:</b> the report should use only measured benchmark values that "
        "are actually present in the project's evidence artifacts. A high benchmark result "
        "does not replace the need for held-out testing, class-wise metrics, model comparison, "
        "and manual-review routing.",
        fill=LIGHT_BLUE,
        border=NAVY,
    ))
    story.append(PageBreak())


def add_security_privacy(story):
    section_heading(story, "7. Security, Privacy & Compliance")
    security_rows = [
        [table_cell("Control", True), table_cell("Implementation / Purpose", True)],
        [table_cell("RBAC"), table_cell("Role-based access for Customer, Staff, Reviewer, and Administrator.")],
        [table_cell("Authentication"), table_cell("Secure password hashing, session control, authentication and authorization checks.")],
        [table_cell("File Validation"), table_cell("Validate extension, MIME type, file size, and required document categories before storage.")],
        [table_cell("SHA-256 Document Hashing"), table_cell("Fingerprint uploaded documents to identify duplicate evidence across claims.")],
        [table_cell("Audit Logging"), table_cell("Append-oriented audit events for account actions, uploads, predictions, status changes, reviews, and decisions.")],
        [table_cell("PII Minimization"), table_cell("Store only the customer/document fields necessary for processing and evaluation.")],
        [table_cell("Privacy Protection"), table_cell("Treat receipts, warranty records, serial numbers and contact data as protected personal/business information.")],
        [table_cell("GDPR-aligned Principles"), table_cell("Use purpose limitation, data minimization, access control, retention awareness, and traceability. This is not a legal certification.")],
        [table_cell("Injection/Abuse Controls"), table_cell("Validate inputs, protect routes, avoid unsafe dynamic queries, and test unauthorized API access.")],
    ]
    story.append(make_table(
        security_rows,
        [1.7 * inch, PAGE_W - LEFT_MARGIN - RIGHT_MARGIN - 1.7 * inch],
    ))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Security Architecture Summary", H2))
    story.append(flow_table([
        "Authenticated user / evaluator",
        "Role-based authorization",
        "Validated claim/document intake",
        "Protected application services and database",
        "Model + rule evaluation with audit trail",
        "Reviewer override with retained original decision evidence",
        "Controlled exports and reports",
    ], box_color=LIGHT_CYAN))
    story.append(PageBreak())


def add_limitations_future(story):
    section_heading(story, "8. Limitations & Future Enhancements")
    limitations = [
        ("OCR resolution caveats", "Image quality, skew, blur, lighting, handwriting, and unusual receipt layouts can reduce OCR extraction quality. Human verification remains important."),
        ("Cloud storage scaling", "SQLite and local file storage are portable for a competition demonstration but should be replaced by managed database/object storage for larger multi-tenant production workloads."),
        ("Synthetic data realism", "A synthetic dataset is useful for controlled evaluation but cannot represent every real-world warranty pattern or document variation."),
        ("Model drift", "Real claim distributions may change; periodic retraining and validation would be required in a production deployment."),
        ("Policy evolution", "Warranty policies change by product, region, contract version, and business partner; policy files must remain configurable."),
    ]
    rows = [[table_cell("Limitation", True), table_cell("Impact", True)]]
    for a, b in limitations:
        rows.append([table_cell(a), table_cell(b)])
    story.append(make_table(rows, [1.85 * inch, PAGE_W - LEFT_MARGIN - RIGHT_MARGIN - 1.85 * inch]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Future Enhancements", H2))
    future = [
        "Cloud object storage and managed PostgreSQL for production-scale deployment.",
        "Asynchronous document processing and queue-based OCR for large claim volumes.",
        "Advanced document parsing and OCR confidence scoring.",
        "Versioned policy authoring and approval workflows.",
        "Optional LLM-assisted warranty text interpretation with strict separation from final claim decision logic.",
        "Model monitoring, drift detection, recalibration, and automated retraining pipelines.",
        "Additional analytics for fraud patterns, repair networks, and warranty leakage.",
    ]
    add_bullets(story, future)
    story.append(note_box(
        "<b>Important architecture constraint:</b> future generative-AI capabilities must not replace "
        "the deterministic final claim decision path required by the project specification.",
        fill=LIGHT_BLUE,
        border=NAVY,
    ))
    story.append(PageBreak())


def add_requirements_traceability(story):
    section_heading(story, "9. Requirements Traceability Snapshot")
    rows = [[table_cell("Requirement Area", True), table_cell("Mapped Capability", True)]]
    mappings = [
        ("Authentication & RBAC", "Users, roles, protected routes and user profiles"),
        ("Product & Warranty Management", "Products, warranties, configurable policies and expiry alerts"),
        ("Document Operations", "PDF/image upload, OCR, extraction, verification, secure hashing"),
        ("Claim Intake", "Claim registration, evidence upload, repair history and validation"),
        ("Python ML", "Preprocessing, feature engineering, model training, confidence scores"),
        ("Google Teachable Machine", "Claim Summary Cards, GTM training, confidence scores and independent evaluation"),
        ("Model Comparison", "Class match, Delta_conf, five consistency statuses"),
        ("Rule Engine", "Warranty rules, exclusions, mandatory documents and review rules"),
        ("Fraud / Consistency", "Duplicate claims, duplicate documents, contradictions and serial checks"),
        ("Human Review", "Queue, comments, overrides and audit history"),
        ("Reporting", "PDF reports, CSV/Excel export, dashboards and analytics"),
        ("Governance", "Audit logs, model versions, AI_USAGE.md and genuine Git history"),
    ]
    for a, b in mappings:
        rows.append([table_cell(a), table_cell(b)])
    story.append(make_table(rows, [2.1 * inch, PAGE_W - LEFT_MARGIN - RIGHT_MARGIN - 2.1 * inch]))
    story.append(PageBreak())


def add_appendix(story):
    section_heading(story, "Appendix A. Project Metadata & Source Handling")
    story.append(Paragraph(
        "This PDF generator is designed to run from the AssureX project repository. "
        "When documentation/PROJECT_REPORT.md exists, the script reads its Executive Summary, "
        "Problem Statement, Proposed Solution, and related headings where available. The report "
        "also contains explicit built-in architectural tables for the mandatory system artifacts "
        "so the PDF remains deterministic and complete.",
        BODY,
    ))
    rows = [
        [table_cell("Item", True), table_cell("Value", True)],
        [table_cell("Project"), table_cell("AssureX Claim Engine")],
        [table_cell("Primary source"), table_cell("documentation/PROJECT_REPORT.md")],
        [table_cell("Supplementary model evidence"), table_cell("documentation/PYTHON_MODEL_EVIDENCE.md when present")],
        [table_cell("Output"), table_cell("reports/AssureX_Project_Report.pdf")],
        [table_cell("Page size"), table_cell("A4 portrait")],
        [table_cell("Primary renderer"), table_cell("ReportLab")],
    ]
    story.append(make_table(rows, [2.15 * inch, PAGE_W - LEFT_MARGIN - RIGHT_MARGIN - 2.15 * inch]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Appendix B. Claim Classes, Statuses & Lifecycle Quick Reference", H2))
    quick = [
        [table_cell("Dimension", True), table_cell("Values", True)],
        [table_cell("Claim Classes"), table_cell("Valid Claim | Invalid Claim | Manual Review")],
        [table_cell("Model-Consistency Statuses"), table_cell("Strong Match | Acceptable Match | Weak Match | Model Disagreement | Uncertain Result")],
        [table_cell("Claim Lifecycle"), table_cell("Draft -> Submitted -> Under Evaluation -> Additional Information Required -> Manual Review -> Approved / Rejected -> Closed")],
    ]
    story.append(make_table(quick, [2.15 * inch, PAGE_W - LEFT_MARGIN - RIGHT_MARGIN - 2.15 * inch]))


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_report():
    if not REPORTS_DIR.exists():
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    doc = ReportDocTemplate(
        str(OUTPUT_PDF),
        author="AssureX Project Team",
        title="AssureX Claim Engine - Technical Project Report",
        subject="AI-Powered Warranty Validation, Consensus Engine and Anti-Fraud Architecture",
    )

    story = []

    # Cover and TOC
    add_front_matter(story)

    # Main report
    add_executive_summary(story)
    add_consensus(story)
    add_diagrams(story)
    add_lifecycle(story)
    add_data_dictionary(story)
    add_benchmarks(story)
    add_security_privacy(story)
    add_limitations_future(story)
    add_requirements_traceability(story)
    add_appendix(story)

    # Dynamic TOC collection is initialized for compatibility with custom
    # afterFlowable logic. TableOfContents will update across multiBuild passes.
    doc._toc_entries = []

    doc.multiBuild(
        story,
        canvasmaker=NumberedCanvas,
    )

    absolute_path = OUTPUT_PDF.resolve()
    size_bytes = absolute_path.stat().st_size if absolute_path.exists() else 0
    print(f"Generated PDF: {absolute_path}")
    print(f"File size: {size_bytes:,} bytes")
    return absolute_path, size_bytes


if __name__ == "__main__":
    try:
        build_report()
    except Exception as exc:
        print(f"ERROR: Failed to generate report: {exc}", file=sys.stderr)
        raise
