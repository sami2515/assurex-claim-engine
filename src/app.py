import os
import sys
from pathlib import Path

# Ensure workspace root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from flask import Flask, render_template, redirect, url_for, session
from config.config import Config
from database.db import init_db, db
from src.models.entities import User

# Import Blueprints
from src.api.auth import auth_bp, get_current_user
from src.api.products import product_bp
from src.api.claims import claim_bp
from src.api.reviewer import reviewer_bp
from src.api.admin import admin_bp
from src.api.reports import report_bp


def create_app(config_class=Config):
    """Application factory for AssureX Claim Engine."""
    app = Flask(
        __name__,
        template_folder=str(Path(config_class.BASE_DIR) / "templates"),
        static_folder=str(Path(config_class.BASE_DIR) / "static")
    )
    app.config.from_object(config_class)

    # Initialize Database & Models
    init_db(app)

    # Register API / UI Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(product_bp)
    app.register_blueprint(claim_bp)
    app.register_blueprint(reviewer_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(report_bp)

    # Global Context Processors for Jinja Templates
    @app.context_processor
    def inject_global_vars():
        return {
            "current_user": get_current_user(),
            "app_config": Config,
            "claim_classes": Config.ALL_CLAIM_CLASSES,
            "consistency_statuses": Config.ALL_CONSISTENCY_STATUSES,
            "claim_statuses": Config.ALL_CLAIM_STATUSES
        }

    # Root Route
    @app.route("/")
    def index():
        if session.get("user_id"):
            return redirect(url_for("auth.portal_redirect"))
        return redirect(url_for("auth.login"))

    # Custom Error Handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("components/error.html", error_code=404, message="The requested resource was not found on this server."), 404

    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template("components/error.html", error_code=403, message="Access forbidden. You do not possess the required permissions."), 403

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template("components/error.html", error_code=500, message="An internal application anomaly occurred. Our engineers have been alerted."), 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)
