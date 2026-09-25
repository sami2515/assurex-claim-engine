import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Config:
    """Central configuration class for AssureX Claim Engine."""

    # Core Application Settings
    SECRET_KEY = os.environ.get("SECRET_KEY", "assurex-secure-secret-key-2026-production")
    DEBUG = os.environ.get("DEBUG", "False").lower() in ("true", "1")
    TESTING = False

    # Directory Paths
    BASE_DIR = BASE_DIR
    DATA_DIR = BASE_DIR / "data"
    UPLOAD_DIR = DATA_DIR / "uploads"
    MODEL_DIR = BASE_DIR / "model"
    PYTHON_MODEL_DIR = MODEL_DIR / "python_model"
    GTM_MODEL_DIR = MODEL_DIR / "teachable_machine"
    POLICY_DIR = BASE_DIR / "policies"
    REPORT_DIR = BASE_DIR / "reports"
    DATABASE_DIR = BASE_DIR / "database"

    # Database Configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", 
        f"sqlite:///{DATABASE_DIR / 'assurex.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Upload Rules
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload
    ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
    ALLOWED_MEDIA_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "mp4"}

    # =========================================================================
    # EXACT SRS DOMAIN CONSTANTS
    # =========================================================================

    # Exactly 3 Claim Classes
    CLAIM_CLASS_VALID = "Valid Claim"
    CLAIM_CLASS_INVALID = "Invalid Claim"
    CLAIM_CLASS_MANUAL_REVIEW = "Manual Review"
    ALL_CLAIM_CLASSES = [
        CLAIM_CLASS_VALID,
        CLAIM_CLASS_INVALID,
        CLAIM_CLASS_MANUAL_REVIEW
    ]

    # Exactly 5 Model-Consistency Statuses
    CONSISTENCY_STRONG = "Strong Match"
    CONSISTENCY_ACCEPTABLE = "Acceptable Match"
    CONSISTENCY_WEAK = "Weak Match"
    CONSISTENCY_DISAGREEMENT = "Model Disagreement"
    CONSISTENCY_UNCERTAIN = "Uncertain Result"
    ALL_CONSISTENCY_STATUSES = [
        CONSISTENCY_STRONG,
        CONSISTENCY_ACCEPTABLE,
        CONSISTENCY_WEAK,
        CONSISTENCY_DISAGREEMENT,
        CONSISTENCY_UNCERTAIN
    ]

    # Exactly 8 Claim Status Lifecycle Stages (Req xxxviii)
    STATUS_DRAFT = "Draft"
    STATUS_SUBMITTED = "Submitted"
    STATUS_UNDER_EVALUATION = "Under Evaluation"
    STATUS_ADDITIONAL_INFO = "Additional Information Required"
    STATUS_MANUAL_REVIEW = "Manual Review"
    STATUS_APPROVED = "Approved"
    STATUS_REJECTED = "Rejected"
    STATUS_CLOSED = "Closed"
    ALL_CLAIM_STATUSES = [
        STATUS_DRAFT,
        STATUS_SUBMITTED,
        STATUS_UNDER_EVALUATION,
        STATUS_ADDITIONAL_INFO,
        STATUS_MANUAL_REVIEW,
        STATUS_APPROVED,
        STATUS_REJECTED,
        STATUS_CLOSED
    ]

    # Role-Based Access Control
    ROLE_CUSTOMER = "customer"
    ROLE_STAFF = "service_center_staff"
    ROLE_REVIEWER = "claim_reviewer"
    ROLE_ADMIN = "administrator"
    ALL_ROLES = [
        ROLE_CUSTOMER,
        ROLE_STAFF,
        ROLE_REVIEWER,
        ROLE_ADMIN
    ]

    # =========================================================================
    # CONFIGURABLE THRESHOLDS & MODEL PARAMETERS
    # =========================================================================
    # All thresholds are configurable and can be reconfigured dynamically for surprise modifications
    MIN_CONFIDENCE_THRESHOLD = float(os.environ.get("MIN_CONFIDENCE_THRESHOLD", "0.60"))
    STRONG_MATCH_DIFF = float(os.environ.get("STRONG_MATCH_DIFF", "0.15"))
    ACCEPTABLE_MATCH_DIFF = float(os.environ.get("ACCEPTABLE_MATCH_DIFF", "0.30"))

    # Expiry alert window in days
    WARRANTY_EXPIRY_ALERT_DAYS = int(os.environ.get("WARRANTY_EXPIRY_ALERT_DAYS", "30"))

    # Active Model Versions
    PYTHON_MODEL_VERSION = "v1.0.0"
    GTM_MODEL_VERSION = "v1.0.0"

    # Notification Event Types
    NOTIF_TYPE_WARRANTY_EXPIRY = "warranty_expiry"
    NOTIF_TYPE_CLAIM_SUBMISSION = "claim_submission"
    NOTIF_TYPE_MISSING_DOCUMENTS = "missing_documents"
    NOTIF_TYPE_ADDITIONAL_INFO = "additional_info_required"
    NOTIF_TYPE_STATUS_CHANGE = "status_change"
    NOTIF_TYPE_REVIEW_COMPLETE = "review_complete"
    NOTIF_TYPE_APPROVAL = "claim_approval"
    NOTIF_TYPE_REJECTION = "claim_rejection"
    NOTIF_TYPE_ANOMALY_ALERT = "anomaly_alert"


class TestConfig(Config):
    """Configuration for automated test execution."""
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
