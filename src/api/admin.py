import json
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, session, redirect, url_for, flash, jsonify, render_template, Response
from config.config import Config
from database.db import db
from src.models.entities import Claim, Product, User, WarrantyPolicy, ModelEvaluation, AuditLog, ProductWarranty, SystemSetting
from src.api.auth import login_required, role_required, get_current_user
from src.services.export_service import DataExportService
from src.services.alert_service import (
    get_alert_threshold_days,
    set_alert_threshold_days,
    scan_and_generate_warranty_alerts,
    get_approaching_warranties
)

from src.services.analytics_service import AnalyticsService

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/dashboard", methods=["GET"])
@login_required
@role_required(Config.ROLE_ADMIN)
def dashboard():
    """Req xli: Administrator dashboard with high-level analytics, disagreement metrics, duplicate alerts, and trends."""
    total_claims = Claim.query.count()
    valid_claims = Claim.query.filter(Claim.status == Config.STATUS_APPROVED).count()
    invalid_claims = Claim.query.filter(Claim.status == Config.STATUS_REJECTED).count()
    manual_review_claims = Claim.query.filter(Claim.status == Config.STATUS_MANUAL_REVIEW).count()
    pending_claims = Claim.query.filter(Claim.status.in_([Config.STATUS_SUBMITTED, Config.STATUS_UNDER_EVALUATION])).count()

    total_products = Product.query.count()
    total_users = User.query.count()

    # Duplicate alerts count (Req xli)
    duplicate_alerts = Claim.query.filter(Claim.is_duplicate_flag == True).count()

    # Model evaluation metrics & average confidence scores (Req xli)
    evaluations = ModelEvaluation.query.all()
    disagreements = sum(1 for e in evaluations if not e.is_class_match)
    disagreement_rate = (disagreements / len(evaluations) * 100) if evaluations else 0.0

    avg_conf_diff = (
        sum(e.top_confidence_difference for e in evaluations) / len(evaluations)
    ) if evaluations else 0.0

    if evaluations:
        python_confs = [max(e.python_conf_valid, e.python_conf_invalid, e.python_conf_manual) for e in evaluations]
        gtm_confs = [max(e.gtm_conf_valid, e.gtm_conf_invalid, e.gtm_conf_manual) for e in evaluations]
        avg_python_conf = sum(python_confs) / len(python_confs)
        avg_gtm_conf = sum(gtm_confs) / len(gtm_confs)
        avg_confidence_score = (avg_python_conf + avg_gtm_conf) / 2.0
    else:
        avg_python_conf = 0.0
        avg_gtm_conf = 0.0
        avg_confidence_score = 0.0

    # Claim trends over time (Req xli)
    trends_map = {}
    claims_chronological = Claim.query.order_by(Claim.claim_submission_date.asc(), Claim.created_at.asc()).all()
    for c in claims_chronological:
        month_key = c.claim_submission_date.strftime("%b %Y") if c.claim_submission_date else (
            c.created_at.strftime("%b %Y") if c.created_at else "Unknown"
        )
        if month_key not in trends_map:
            trends_map[month_key] = {"total": 0, "approved": 0, "rejected": 0, "manual": 0}
        trends_map[month_key]["total"] += 1
        if c.status == Config.STATUS_APPROVED:
            trends_map[month_key]["approved"] += 1
        elif c.status == Config.STATUS_REJECTED:
            trends_map[month_key]["rejected"] += 1
        elif c.status == Config.STATUS_MANUAL_REVIEW:
            trends_map[month_key]["manual"] += 1

    if not trends_map:
        current_m = datetime.now().strftime("%b %Y")
        trends_map = {current_m: {"total": total_claims, "approved": valid_claims, "rejected": invalid_claims, "manual": manual_review_claims}}

    trend_labels = list(trends_map.keys())
    trend_totals = [trends_map[k]["total"] for k in trend_labels]
    trend_approved = [trends_map[k]["approved"] for k in trend_labels]
    trend_rejected = [trends_map[k]["rejected"] for k in trend_labels]
    trend_manual = [trends_map[k]["manual"] for k in trend_labels]

    # Recent Audit Events
    recent_audits = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(10).all()

    # Category Breakdown
    cat_counts = {}
    for p in Product.query.all():
        cat_counts[p.category] = cat_counts.get(p.category, 0) + 1

    # Warranty Alert Metrics (Req 1.6.ix)
    alert_threshold_days = get_alert_threshold_days()
    approaching_warranties = get_approaching_warranties(threshold_days=alert_threshold_days)

    # ML Benchmark & Common Dataset Telemetry (Req 1.6.xvii, xviii, xix)
    benchmark_path = Path("model/python_model/benchmark_results.json")
    benchmark_data = {}
    if benchmark_path.exists():
        try:
            benchmark_data = json.loads(benchmark_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    dataset_stats_path = Path("data/dataset_statistics.json")
    dataset_stats = {}
    if dataset_stats_path.exists():
        try:
            dataset_stats = json.loads(dataset_stats_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    return render_template(
        "admin/dashboard.html",
        total_claims=total_claims,
        valid_claims=valid_claims,
        invalid_claims=invalid_claims,
        manual_review_claims=manual_review_claims,
        pending_claims=pending_claims,
        total_products=total_products,
        total_users=total_users,
        duplicate_alerts=duplicate_alerts,
        disagreements=disagreements,
        disagreement_rate=round(disagreement_rate, 2),
        avg_conf_diff=round(avg_conf_diff, 4),
        avg_confidence_score=round(avg_confidence_score * 100, 2),
        avg_python_conf=round(avg_python_conf * 100, 2),
        avg_gtm_conf=round(avg_gtm_conf * 100, 2),
        trend_labels=trend_labels,
        trend_totals=trend_totals,
        trend_approved=trend_approved,
        trend_rejected=trend_rejected,
        trend_manual=trend_manual,
        recent_audits=recent_audits,
        category_breakdown=cat_counts,
        alert_threshold_days=alert_threshold_days,
        approaching_warranties_count=len(approaching_warranties),
        benchmark_data=benchmark_data,
        dataset_stats=dataset_stats
    )


@admin_bp.route("/analytics", methods=["GET"])
@login_required
@role_required(Config.ROLE_ADMIN)
def analytics_dashboard():
    """Req xliii: Comprehensive Data Analysis & Reporting on 8 core warranty dimensions."""
    analytics = AnalyticsService.get_comprehensive_analytics()
    return render_template("admin/analytics.html", analytics=analytics)


@admin_bp.route("/analytics/export-json", methods=["GET"])
@login_required
@role_required(Config.ROLE_ADMIN)
def export_analytics_json():
    """Req xliii: Download JSON summary report of analytics."""
    analytics = AnalyticsService.get_comprehensive_analytics()
    return Response(
        json.dumps(analytics, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=assurex_analytics_report.json"}
    )


@admin_bp.route("/claims-search", methods=["GET"])
@login_required
@role_required(Config.ROLE_ADMIN)
def claims_search():
    """Alias redirect for claims & warranty search and filtering (Req xlii)."""
    return redirect(url_for("claims.search_records", **request.args))


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

    # Req 1.6.xxiv: Configurable model consistency thresholds
    try:
        min_conf_val = float(SystemSetting.get_val("min_confidence_threshold", str(Config.MIN_CONFIDENCE_THRESHOLD)))
        strong_diff_val = float(SystemSetting.get_val("strong_match_diff", str(Config.STRONG_MATCH_DIFF)))
        acceptable_diff_val = float(SystemSetting.get_val("acceptable_match_diff", str(Config.ACCEPTABLE_MATCH_DIFF)))
    except Exception:
        min_conf_val = Config.MIN_CONFIDENCE_THRESHOLD
        strong_diff_val = Config.STRONG_MATCH_DIFF
        acceptable_diff_val = Config.ACCEPTABLE_MATCH_DIFF

    return render_template(
        "admin/policies.html",
        policies=policies,
        alert_threshold_days=alert_threshold_days,
        approaching_warranties_count=len(approaching_warranties),
        min_conf_val=min_conf_val,
        strong_diff_val=strong_diff_val,
        acceptable_diff_val=acceptable_diff_val
    )


@admin_bp.route("/settings/model-thresholds", methods=["POST"])
@login_required
@role_required(Config.ROLE_ADMIN)
def configure_model_thresholds():
    """Req 1.6.xxiv: Configure confidence-difference and minimum-confidence thresholds for Model Consistency Status."""
    user = get_current_user()
    try:
        min_conf = float(request.form.get("min_confidence", "0.60").strip())
        strong_diff = float(request.form.get("strong_diff", "0.15").strip())
        acceptable_diff = float(request.form.get("acceptable_diff", "0.30").strip())

        if not (0.0 < min_conf <= 1.0):
            flash("Minimum confidence threshold must be between 0.01 and 1.00.", "warning")
            return redirect(url_for("admin.manage_policies"))
        if not (0.0 < strong_diff < acceptable_diff <= 1.0):
            flash("Strong match diff must be less than acceptable match diff (between 0.01 and 1.00).", "warning")
            return redirect(url_for("admin.manage_policies"))

        SystemSetting.set_val("min_confidence_threshold", f"{min_conf:.2f}", description="Req xxiv: Minimum confidence threshold")
        SystemSetting.set_val("strong_match_diff", f"{strong_diff:.2f}", description="Req xxiv: Strong match confidence difference threshold")
        SystemSetting.set_val("acceptable_match_diff", f"{acceptable_diff:.2f}", description="Req xxiv: Acceptable match confidence difference threshold")

        AuditLog.log_event(
            action="UPDATE_MODEL_THRESHOLDS",
            user_id=user.id if user else None,
            user_role=user.role if user else None,
            entity_type="SystemSetting",
            details={
                "min_confidence_threshold": min_conf,
                "strong_match_diff": strong_diff,
                "acceptable_match_diff": acceptable_diff
            }
        )
        db.session.commit()
        flash(f"Model consistency thresholds updated: Min Conf={min_conf:.2f}, Strong Diff<={strong_diff:.2f}, Acceptable Diff<={acceptable_diff:.2f}.", "success")
    except ValueError:
        flash("Invalid numerical values entered for model thresholds.", "danger")

    return redirect(url_for("admin.manage_policies"))


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
    """Req xlv: CSV exporter for selected claims, products, warranties, analytics records, and audit logs."""
    service = DataExportService()
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    if export_type == "claims":
        selected_ids = request.args.get("ids") or request.args.get("claim_ids")
        if selected_ids:
            id_list = [i.strip() for i in selected_ids.split(",") if i.strip()]
            claims = Claim.query.filter(Claim.claim_id.in_(id_list)).all()
        else:
            claims = Claim.query.all()
        csv_data = service.export_claims_csv(claims)
        filename = f"assurex_claims_export_{timestamp_str}.csv"
    elif export_type == "products":
        products = Product.query.all()
        csv_data = service.export_products_csv(products)
        filename = f"assurex_products_export_{timestamp_str}.csv"
    elif export_type == "warranties":
        warranties = ProductWarranty.query.all()
        csv_data = service.export_warranties_csv(warranties)
        filename = f"assurex_warranties_export_{timestamp_str}.csv"
    elif export_type == "analytics":
        analytics_payload = AnalyticsService.get_comprehensive_analytics()
        csv_data = service.export_analytics_csv(analytics_payload)
        filename = f"assurex_analytics_export_{timestamp_str}.csv"
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


@admin_bp.route("/export-warranties", methods=["GET"])
@login_required
@role_required(Config.ROLE_ADMIN)
def export_warranties():
    """Alias for warranties CSV export (Req xlv)."""
    return export_data("warranties")


@admin_bp.route("/export-analytics", methods=["GET"])
@login_required
@role_required(Config.ROLE_ADMIN)
def export_analytics():
    """Alias for analytics CSV export (Req xlv)."""
    return export_data("analytics")
