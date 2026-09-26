import json
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, session, redirect, url_for, flash, jsonify, render_template, Response, abort
from config.config import Config
from database.db import db
from src.models.entities import Claim, Product, User, WarrantyPolicy, ModelEvaluation, AuditLog, ProductWarranty, SystemSetting
from src.api.auth import login_required, role_required, get_current_user, csrf_protect
from src.services.export_service import DataExportService
from src.services.alert_service import (
    get_alert_threshold_days,
    set_alert_threshold_days,
    scan_and_generate_warranty_alerts,
    get_approaching_warranties,
    get_system_anomalies,
    scan_and_generate_anomaly_alerts
)

from src.services.analytics_service import AnalyticsService

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/dashboard", methods=["GET"])
@login_required
@role_required(Config.ROLE_ADMIN)
def dashboard():
    """Administrator dashboard with high-level analytics, disagreement metrics, duplicate alerts, and trends."""
    total_claims = Claim.query.count()
    valid_claims = Claim.query.filter(Claim.status == Config.STATUS_APPROVED).count()
    invalid_claims = Claim.query.filter(Claim.status == Config.STATUS_REJECTED).count()
    manual_review_claims = Claim.query.filter(Claim.status == Config.STATUS_MANUAL_REVIEW).count()
    pending_claims = Claim.query.filter(Claim.status.in_([Config.STATUS_SUBMITTED, Config.STATUS_UNDER_EVALUATION])).count()

    total_products = Product.query.count()
    total_users = User.query.count()

    # Duplicate alerts count
    duplicate_alerts = Claim.query.filter(Claim.is_duplicate_flag == True).count()

    # Model evaluation metrics & average confidence scores
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

    # Claim trends over time
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

    # Warranty Alert Metrics
    alert_threshold_days = get_alert_threshold_days()
    approaching_warranties = get_approaching_warranties(threshold_days=alert_threshold_days)

    # ML Benchmark & Common Dataset Telemetry
    benchmark_path = Path(Config.BASE_DIR) / "model" / "python_model" / "benchmark_results.json"
    benchmark_data = {}
    if benchmark_path.exists():
        try:
            benchmark_data = json.loads(benchmark_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    dataset_stats_path = Path(Config.BASE_DIR) / "data" / "dataset_statistics.json"
    dataset_stats = {}
    if dataset_stats_path.exists():
        try:
            dataset_stats = json.loads(dataset_stats_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Anomaly Monitoring & Alerts Telemetry
    anomalies = get_system_anomalies()

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
        dataset_stats=dataset_stats,
        anomalies=anomalies,
        anomalies_count=len(anomalies)
    )


@admin_bp.route("/anomalies/dispatch", methods=["POST"])
@login_required
@role_required(Config.ROLE_ADMIN)
def dispatch_anomaly_alerts():
    """Dispatches real-time anomaly alerts to administrators."""
    created = scan_and_generate_anomaly_alerts()
    if created:
        flash(f"Successfully dispatched {len(created)} anomaly notification(s) to system administrators.", "success")
    else:
        flash("Anomaly scan complete: All current anomalies have already been notified.", "info")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/analytics", methods=["GET"])
@login_required
@role_required(Config.ROLE_ADMIN)
def analytics_dashboard():
    """Comprehensive Data Analysis & Reporting on 8 core warranty dimensions."""
    analytics = AnalyticsService.get_comprehensive_analytics()
    return render_template("admin/analytics.html", analytics=analytics)


@admin_bp.route("/analytics/export-json", methods=["GET"])
@login_required
@role_required(Config.ROLE_ADMIN)
def export_analytics_json():
    """Download JSON summary report of analytics."""
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
    """Alias redirect for claims & warranty search and filtering."""
    return redirect(url_for("claims.search_records", **request.args))


@admin_bp.route("/policies", methods=["GET", "POST"])
@login_required
@role_required(Config.ROLE_ADMIN)
def manage_policies():
    """Dynamic policy editor allowing live adjustments to rules and thresholds."""
    if request.method == "POST":
        category = (request.form.get("category") or "").strip()
        policy_name = (request.form.get("policy_name") or "").strip()
        try:
            duration = int(request.form.get("duration", 12) or 12)
            grace = int(request.form.get("grace", 7) or 7)
            reporting = int(request.form.get("reporting", 30) or 30)
        except ValueError:
            flash("Duration, grace period, and reporting window must be valid whole numbers.", "danger")
            return redirect(url_for("admin.manage_policies"))

        if duration < 1 or grace < 0 or reporting < 1:
            flash("Duration and reporting period must be positive numbers, and grace period cannot be negative.", "warning")
            return redirect(url_for("admin.manage_policies"))

        rules_text = request.form.get("rules_json")

        policy = WarrantyPolicy.query.filter_by(category=category).first()
        if not policy:
            policy = WarrantyPolicy(category=category)
            db.session.add(policy)

        policy.policy_name = policy_name or f"{category} Standard Policy"
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

    # Configurable model consistency thresholds
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
    """Configure confidence-difference and minimum-confidence thresholds for Model Consistency Status."""
    user = get_current_user()
    try:
        current_min_conf = SystemSetting.get_val("min_confidence_threshold", "0.60")
        current_strong_diff = SystemSetting.get_val("strong_match_diff", "0.15")
        current_acceptable_diff = SystemSetting.get_val("acceptable_match_diff", "0.30")

        min_conf = float(request.form.get("min_confidence", current_min_conf).strip())
        strong_diff = float(request.form.get("strong_diff", current_strong_diff).strip())
        acceptable_diff = float(request.form.get("acceptable_diff", current_acceptable_diff).strip())

        if not (0.0 < min_conf <= 1.0):
            flash("Minimum confidence threshold must be between 0.01 and 1.00.", "warning")
            return redirect(url_for("admin.manage_policies"))
        if not (0.0 < strong_diff < acceptable_diff <= 1.0):
            flash("Strong match diff must be less than acceptable match diff (between 0.01 and 1.00).", "warning")
            return redirect(url_for("admin.manage_policies"))

        SystemSetting.set_val("min_confidence_threshold", f"{min_conf:.2f}", description="Minimum confidence threshold")
        SystemSetting.set_val("strong_match_diff", f"{strong_diff:.2f}", description="Strong match confidence difference threshold")
        SystemSetting.set_val("acceptable_match_diff", f"{acceptable_diff:.2f}", description="Acceptable match confidence difference threshold")

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
    except Exception:
        db.session.rollback()
        flash("An error occurred while saving thresholds. Please try again.", "danger")

    return redirect(url_for("admin.manage_policies"))


@admin_bp.route("/settings/warranty-alerts", methods=["POST"])
@login_required
@role_required(Config.ROLE_ADMIN)
def configure_warranty_alerts():
    """Configure the number of days before expiry when an alert should be generated."""
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
    """Manually trigger a fleet-wide scan and dispatch warranty expiry alerts."""
    generated = scan_and_generate_warranty_alerts()
    flash(f"Fleet-wide scan complete: {len(generated)} warranty expiry alert notification(s) dispatched to affected users.", "info")
    return redirect(url_for("admin.manage_policies"))



@admin_bp.route("/audit-logs", methods=["GET"])
@login_required
@role_required(Config.ROLE_ADMIN)
def audit_logs():
    """Immutable system audit logs viewer."""
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(100).all()
    return render_template("admin/audit_logs.html", logs=logs)


@admin_bp.route("/export/<string:export_type>", methods=["GET"])
@login_required
@role_required(Config.ROLE_ADMIN)
def export_data(export_type):
    """CSV exporter for selected claims, products, warranties, analytics records, and audit logs."""
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
    """Alias for warranties CSV export."""
    return export_data("warranties")


@admin_bp.route("/export-analytics", methods=["GET"])
@login_required
@role_required(Config.ROLE_ADMIN)
def export_analytics():
    """Alias for analytics CSV export."""
    return export_data("analytics")


# ==============================================================================
# ROLE-BASED ACCESS CONTROL (RBAC) USER MANAGEMENT
# ==============================================================================

ROLE_NORMALIZATION_MAP = {
    "admin": Config.ROLE_ADMIN,
    "administrator": Config.ROLE_ADMIN,
    "reviewer": Config.ROLE_REVIEWER,
    "claim_reviewer": Config.ROLE_REVIEWER,
    "staff": Config.ROLE_STAFF,
    "service_center_staff": Config.ROLE_STAFF,
    "customer": Config.ROLE_CUSTOMER,
}

ADMIN_ROLES = [Config.ROLE_ADMIN, "Admin", "administrator"]


def is_admin_role(role_name):
    if not role_name:
        return False
    return role_name in ADMIN_ROLES or role_name.lower() in ["admin", "administrator"]


@admin_bp.route("/users", methods=["GET"])
@login_required
@role_required(Config.ROLE_ADMIN)
def users_directory():
    """
    Administrator User Directory and Access Management console.
    Provides filtering across roles (Customer, Staff, Reviewer, Admin),
    status (Active/Inactive), and text search across names, emails, and IDs.
    """
    q = request.args.get("q", "").strip()
    role_filter = request.args.get("role", "").strip()
    status_filter = request.args.get("status", "").strip()

    query = User.query

    if q:
        search_pattern = f"%{q}%"
        query = query.filter(
            (User.full_name.ilike(search_pattern)) |
            (User.email.ilike(search_pattern)) |
            (User.user_id.ilike(search_pattern))
        )

    if role_filter and role_filter != "all":
        canonical_role = ROLE_NORMALIZATION_MAP.get(role_filter.lower(), role_filter)
        query = query.filter(
            (User.role == canonical_role) |
            (User.role == role_filter)
        )

    if status_filter == "active":
        query = query.filter(User.is_active == True)
    elif status_filter == "inactive":
        query = query.filter(User.is_active == False)

    users = query.order_by(User.id.desc()).all()

    # Active admin count for last-admin safety rules
    active_admin_count = User.query.filter(
        User.role.in_(ADMIN_ROLES),
        User.is_active == True
    ).count()

    total_users_count = User.query.count()
    customer_count = User.query.filter(User.role.in_([Config.ROLE_CUSTOMER, "Customer", "customer"])).count()
    staff_count = User.query.filter(User.role.in_([Config.ROLE_STAFF, "Staff", "service_center_staff"])).count()
    reviewer_count = User.query.filter(User.role.in_([Config.ROLE_REVIEWER, "Reviewer", "claim_reviewer"])).count()

    current_user = get_current_user()

    role_options = [
        {"val": Config.ROLE_CUSTOMER, "label": "Customer"},
        {"val": Config.ROLE_STAFF, "label": "Service Staff"},
        {"val": Config.ROLE_REVIEWER, "label": "Claim Reviewer"},
        {"val": Config.ROLE_ADMIN, "label": "Administrator"}
    ]

    return render_template(
        "admin/users.html",
        users=users,
        q=q,
        role_filter=role_filter,
        status_filter=status_filter,
        active_admin_count=active_admin_count,
        total_users_count=total_users_count,
        customer_count=customer_count,
        staff_count=staff_count,
        reviewer_count=reviewer_count,
        current_user=current_user,
        role_options=role_options
    )


@admin_bp.route("/users/create", methods=["POST"])
@login_required
@role_required(Config.ROLE_ADMIN)
@csrf_protect
def create_user():
    """
    Admin endpoint to provision elevated roles (Staff, Reviewer, Admin) or Customer accounts.
    Strictly validates email uniqueness, required fields, password length, and logs audit event.
    """
    email = request.form.get("email", "").strip().lower()
    full_name = request.form.get("full_name", "").strip()
    role_raw = request.form.get("role", "").strip()
    password = request.form.get("password", "")
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()

    role = ROLE_NORMALIZATION_MAP.get(role_raw.lower())

    if not email or not full_name or not password or not role_raw:
        flash("Full name, email address, role, and temporary password are required.", "warning")
        return redirect(url_for("admin.users_directory"))

    if not role:
        flash(f"Invalid role '{role_raw}'.", "danger")
        return redirect(url_for("admin.users_directory"))

    if "@" not in email or "." not in email.split("@")[-1]:
        flash("Please enter a valid email address.", "warning")
        return redirect(url_for("admin.users_directory"))

    if len(password) < 8:
        flash("Password must be at least 8 characters long.", "warning")
        return redirect(url_for("admin.users_directory"))

    if User.query.filter_by(email=email).first():
        flash(f"A user account with email '{email}' already exists.", "danger")
        return redirect(url_for("admin.users_directory"))

    if phone:
        digits_only = ''.join(c for c in phone if c.isdigit())
        if len(digits_only) < 7 or len(digits_only) > 15:
            flash("Phone number must contain between 7 and 15 digits.", "warning")
            return redirect(url_for("admin.users_directory"))

    new_user = User(
        email=email,
        full_name=full_name,
        role=role,
        phone_number=phone or None,
        address=address or None,
        is_active=True
    )
    new_user.set_password(password)

    try:
        db.session.add(new_user)
        db.session.flush()

        current_user = get_current_user()
        audit = AuditLog(
            user_id=current_user.id if current_user else session.get("user_id"),
            user_role=current_user.role if current_user else session.get("role"),
            action="ACCOUNT_CREATED",
            entity_type="USER",
            entity_id=new_user.user_id,
            ip_address=request.remote_addr,
            details_json=json.dumps({
                "actor_id": current_user.id if current_user else None,
                "target_id": new_user.id,
                "target_user_id": new_user.id,
                "target_user_code": new_user.user_id,
                "email": new_user.email,
                "assigned_role": new_user.role,
                "provisioned_by": current_user.email if current_user else "admin",
                "ip": request.remote_addr
            })
        )
        db.session.add(audit)
        db.session.commit()
        flash(f"Account for '{new_user.full_name}' ({new_user.role}) successfully provisioned with ID {new_user.user_id}.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to create account: {str(e)}", "danger")

    return redirect(url_for("admin.users_directory"))


@admin_bp.route("/users/<int:user_id>/role", methods=["POST"])
@login_required
@role_required(Config.ROLE_ADMIN)
@csrf_protect
def update_user_role(user_id):
    """
    Admin endpoint to change a user's role.
    Safeguards:
    1. Prevents administrator self-demotion.
    2. Prevents demoting the last active administrator.
    Records RBAC_ROLE_CHANGE event to immutable audit log.
    """
    target_user = db.session.get(User, user_id)
    if not target_user:
        flash("Target user not found.", "danger")
        return redirect(url_for("admin.users_directory"))

    new_role_raw = request.form.get("role", "").strip()
    new_role = ROLE_NORMALIZATION_MAP.get(new_role_raw.lower())

    if not new_role:
        flash(f"Invalid role selection: '{new_role_raw}'.", "danger")
        return redirect(url_for("admin.users_directory"))

    if target_user.role == new_role:
        flash(f"User '{target_user.full_name}' already possesses the role '{new_role}'.", "info")
        return redirect(url_for("admin.users_directory"))

    current_user = get_current_user()

    # Safeguard 1: Administrator cannot self-demote
    if current_user and current_user.id == target_user.id and not is_admin_role(new_role):
        flash("Self-demotion is prohibited. You cannot remove your own Administrator role.", "danger")
        return redirect(url_for("admin.users_directory"))

    # Safeguard 2: Last active administrator protection
    if is_admin_role(target_user.role) and not is_admin_role(new_role):
        active_admin_count = User.query.filter(
            User.role.in_(ADMIN_ROLES),
            User.is_active == True
        ).count()
        if active_admin_count <= 1:
            flash("Action blocked: Cannot demote the last active Administrator in the system.", "danger")
            return redirect(url_for("admin.users_directory"))

    old_role = target_user.role
    target_user.role = new_role

    try:
        audit = AuditLog(
            user_id=current_user.id if current_user else session.get("user_id"),
            user_role=current_user.role if current_user else session.get("role"),
            action="RBAC_ROLE_CHANGE",
            entity_type="USER",
            entity_id=target_user.user_id,
            ip_address=request.remote_addr,
            details_json=json.dumps({
                "actor_id": current_user.id if current_user else None,
                "target_id": target_user.id,
                "target_user_id": target_user.id,
                "target_user_code": target_user.user_id,
                "old_role": old_role,
                "new_role": new_role,
                "changed_by": current_user.email if current_user else "admin",
                "ip": request.remote_addr
            })
        )
        db.session.add(audit)
        db.session.commit()
        flash(f"Role for '{target_user.full_name}' successfully updated from {old_role} to {new_role}.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to update user role: {str(e)}", "danger")

    return redirect(url_for("admin.users_directory"))


@admin_bp.route("/users/<int:user_id>/toggle-status", methods=["POST"])
@login_required
@role_required(Config.ROLE_ADMIN)
@csrf_protect
def toggle_user_status(user_id):
    """
    Admin endpoint for soft activation and deactivation of user accounts.
    Safeguards:
    1. Administrator cannot deactivate their own account.
    2. Cannot deactivate the last active administrator.
    Records ACCOUNT_ACTIVATED or ACCOUNT_DEACTIVATED in audit log.
    """
    target_user = db.session.get(User, user_id)
    if not target_user:
        flash("Target user not found.", "danger")
        return redirect(url_for("admin.users_directory"))

    current_user = get_current_user()

    if target_user.is_active:
        # Attempting deactivation
        # Safeguard 1: Administrator cannot self-deactivate
        if current_user and current_user.id == target_user.id:
            flash("Self-deactivation is prohibited. You cannot deactivate your own account.", "danger")
            return redirect(url_for("admin.users_directory"))

        # Safeguard 2: Last active administrator protection
        if is_admin_role(target_user.role):
            active_admin_count = User.query.filter(
                User.role.in_(ADMIN_ROLES),
                User.is_active == True
            ).count()
            if active_admin_count <= 1:
                flash("Action blocked: Cannot deactivate the last active Administrator in the system.", "danger")
                return redirect(url_for("admin.users_directory"))

        target_user.is_active = False
        action_name = "ACCOUNT_DEACTIVATED"
        flash_msg = f"Account '{target_user.full_name}' has been deactivated. The user is now blocked from logging in."
    else:
        # Activating
        target_user.is_active = True
        action_name = "ACCOUNT_ACTIVATED"
        flash_msg = f"Account '{target_user.full_name}' has been reactivated. The user can now log in."

    try:
        audit = AuditLog(
            user_id=current_user.id if current_user else session.get("user_id"),
            user_role=current_user.role if current_user else session.get("role"),
            action=action_name,
            entity_type="USER",
            entity_id=target_user.user_id,
            ip_address=request.remote_addr,
            details_json=json.dumps({
                "actor_id": current_user.id if current_user else None,
                "target_id": target_user.id,
                "target_user_id": target_user.id,
                "target_user_code": target_user.user_id,
                "target_email": target_user.email,
                "new_status": target_user.is_active,
                "performed_by": current_user.email if current_user else "admin",
                "ip": request.remote_addr
            })
        )
        db.session.add(audit)
        db.session.commit()
        flash(flash_msg, "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to update account status: {str(e)}", "danger")

    return redirect(url_for("admin.users_directory"))
