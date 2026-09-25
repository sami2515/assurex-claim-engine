from flask import Blueprint, send_file, flash, redirect, url_for, Response, session
from config.config import Config
from src.models.entities import Claim
from src.api.auth import login_required, get_current_user
from src.services.report_generator import get_pdf_generator

report_bp = Blueprint("reports", __name__, url_prefix="/reports")


@report_bp.route("/claim/<string:claim_id>/pdf", methods=["GET"])
@login_required
def download_claim_pdf(claim_id):
    """
    Generates and streams official downloadable PDF claim evaluation certificate.
    """
    claim = Claim.query.filter_by(claim_id=claim_id).first_or_404()
    curr_user = get_current_user()
    if session.get("role") == Config.ROLE_CUSTOMER and curr_user and claim.user_id != curr_user.id:
        flash("Access denied: You can only download reports for your own warranty claims.", "danger")
        return redirect(url_for("claims.customer_dashboard"))
    pdf_generator = get_pdf_generator()
    pdf_bytes = pdf_generator.generate_pdf(claim)

    filename = f"AssureX_Claim_Report_{claim.claim_id}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
