from src.api.auth import auth_bp
from src.api.products import product_bp
from src.api.claims import claim_bp
from src.api.reviewer import reviewer_bp
from src.api.admin import admin_bp
from src.api.reports import report_bp

__all__ = [
    "auth_bp",
    "product_bp",
    "claim_bp",
    "reviewer_bp",
    "admin_bp",
    "report_bp"
]
