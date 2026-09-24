import json
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, session, redirect, url_for, flash, jsonify, render_template, Response
from config.config import Config
from database.db import db
from src.models.entities import Claim, Product, User, WarrantyPolicy, ModelEvaluation, AuditLog, ProductWarranty
from src.api.auth import login_required, role_required, get_current_user
from src.services.export_service import DataExportService
from src.services.alert_service import (
    get_alert_threshold_days,
    set_alert_threshold_days,
    scan_and_generate_warranty_alerts,
    get_approaching_warranties
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/dashboard", methods=["GET"])
@login_required
@role_required(Config.ROLE_ADMIN)
def dashboard():
    """Req xli: Administrator dashboard with high-level analytics, disagreement metrics, and trends."""
    total_claims = Claim.query.count()
    valid_claims = Claim.query.filter(Claim.status == Config.STATUS_APPROVED).count()
    invalid_claims = Claim.query.filter(Claim.status == Config.STATUS_REJECTED).count()
    manual_review_claims = Claim.query.filter(Claim.status == Config.STATUS_MANUAL_REVIEW).count()
    pending_claims = Claim.query.filter(Claim.status.in_([Config.STATUS_SUBMITTED, Config.STATUS_UNDER_EVALUATION])).count()

    total_products = Product.query.count()
    total_users = User.query.count()

    # Model evaluation metrics
    evaluations = ModelEvaluation.query.all()
    disagreements = sum(1 for e in evaluations if not e.is_class_match)
    disagreement_rate = (disagreements / len(evaluations) * 100) if evaluations else 0.0

    avg_conf_diff = (
        sum(e.top_confidence_difference for e in evaluations) / len(evaluations)
    ) if evaluations else 0.0

    # Recent Audit Events
    recent_audits = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(10).all()

    # Category Breakdown
    cat_counts = {}
    for p in Product.query.all():
        cat_counts[p.category] = cat_counts.get(p.category, 0) + 1

    # Warranty Alert Metrics (Req 1.6.ix)
    alert_threshold_days = get_alert_threshold_days()
    approaching_warranties = get_approaching_warranties(threshold_days=alert_threshold_days)

    return render_template(
        "admin/dashboard.html",
        total_claims=total_claims,
        valid_claims=valid_claims,
        invalid_claims=invalid_claims,
        manual_review_claims=manual_review_claims,
        pending_claims=pending_claims,
        total_products=total_products,
        total_users=total_users,
        disagreements=disagreements,
        disagreement_rate=round(disagreement_rate, 2),
        avg_conf_diff=round(avg_conf_diff, 4),
        recent_audits=recent_audits,
        category_breakdown=cat_counts,
        alert_threshold_days=alert_threshold_days,
        approaching_warranties_count=len(approaching_warranties)
    )


@admin_bp.route("/policies", methods=["GET", "POST"])
@login_required
@role_required(Config.ROLE_ADMIN)
def manage_policies():
    """Req xxvi: Dynamic policy editor allowing live adjustments to rules and thresholds."""
    if request.method == "POST":
        category = request.form.get("category")
        policy_name = request.form.get("policy_name")
        duration = int(request.form.get("duration", 12))
        grace = int(request.form.get("grace", 7))
        reporting = int(request.form.get("reporting", 30))
        rules_text = request.form.get("rules_json")

        policy = WarrantyPolicy.query.filter_by(category=category).first()
        if not policy:
            policy = WarrantyPolicy(category=category)
            db.session.add(policy)

        policy.policy_name = policy_name
        policy.coverage_duration_months = duration
        policy.grace_period_days = grace
        policy.claim_reporting_period_days = reporting
        try:
            # Validate JSON
            parsed = json.loads(rules_text)
            policy.policy_rules_json = json.dumps(parsed, indent=2)
        except Exception:
            flash("Invalid JSON formatted rules text.", "danger")
            return redirect(url_for("admin.manage_policies"))

        db.session.commit()
        flash(f"Policy for '{category}' updated successfully!", "success")
        return redirect(url_for("admin.manage_policies"))

    policies = WarrantyPolicy.query.all()
    alert_threshold_days = get_alert_threshold_days()
    approaching_warranties = get_approaching_warranties(threshold_days=alert_threshold_days)

    return render_template(
        "admin/policies.html",
        policies=policies,
        alert_threshold_days=alert_threshold_days,
        approaching_warranties_count=len(approaching_warranties)
    )


@admin_bp.route("/settings/warranty-alerts", methods=["POST"])
@login_required
@role_required(Config.ROLE_ADMIN)
def configure_warranty_alerts():
    """Req 1.6.ix: Configure the number of days before expiry when an alert should be generated."""
    user = get_current_user()
    alert_days = request.form.get("alert_days", "30").strip()
    try:
        days = int(alert_days)
        if days < 1 or days > 365:
            flash("Alert window must be between 1 and 365 days.", "warning")
            return redirect(url_for("admin.manage_policies"))
    except ValueError:
        flash("Invalid alert window entered.", "danger")
        return redirect(url_for("admin.manage_policies"))

    set_alert_threshold_days(days, actor_user=user)
    generated = scan_and_generate_warranty_alerts()
    flash(f"Warranty expiry alert window configured to {days} days! {len(generated)} new notification(s) generated.", "success")
    return redirect(url_for("admin.manage_policies"))


@admin_bp.route("/alerts/dispatch", methods=["POST"])
@login_required
@role_required(Config.ROLE_ADMIN)
def dispatch_warranty_alerts():
    """Req 1.6.ix: Manually trigger a fleet-wide scan and dispatch warranty expiry alerts."""
    generated = scan_and_generate_warranty_alerts()
    flash(f"Fleet-wide scan complete: {len(generated)} warranty expiry alert notification(s) dispatched to affected users.", "info")
    return redirect(url_for("admin.manage_policies"))



@admin_bp.route("/audit-logs", methods=["GET"])
@login_required
@role_required(Config.ROLE_ADMIN)
def audit_logs():
    """Req xlvii: Immutable system audit logs viewer."""
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(100).all()
    return render_template("admin/audit_logs.html", logs=logs)


@admin_bp.route("/export/<string:export_type>", methods=["GET"])
@login_required
@role_required(Config.ROLE_ADMIN)
def export_data(export_type):
    """Req xlv: CSV exporter for claims, products, and audit trail."""
    service = DataExportService()
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    if export_type == "claims":
        claims = Claim.query.all()
        csv_data = service.export_claims_csv(claims)
        filename = f"assurex_claims_export_{timestamp_str}.csv"
    elif export_type == "products":
        products = Product.query.all()
        csv_data = service.export_products_csv(products)
        filename = f"assurex_products_export_{timestamp_str}.csv"
    elif export_type == "audit":
        logs = AuditLog.query.all()
        csv_data = service.export_audit_logs_csv(logs)
        filename = f"assurex_audit_logs_{timestamp_str}.csv"
    else:
        flash("Unsupported export dataset type.", "warning")
        return redirect(url_for("admin.dashboard"))

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )


@admin_bp.route("/policy-editor", methods=["GET"])
@login_required
@role_required(Config.ROLE_ADMIN)
def policy_editor():
    """Alias for policy editor."""
    return redirect(url_for("admin.manage_policies"))


@admin_bp.route("/export-claims", methods=["GET"])
@login_required
@role_required(Config.ROLE_ADMIN)
def export_claims():
    """Alias for claims CSV export."""
    return export_data("claims")
