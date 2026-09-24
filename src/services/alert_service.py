"""
AssureX Warranty Alert & Notification Service (Req 1.6.ix)
Monitors registered equipment warranty lifecycles, detects approaching expirations
against administrator-configured thresholds, and dispatches real-time user notifications.
"""
from datetime import datetime, timezone
from database.db import db
from config.config import Config
from src.models.entities import Product, ProductWarranty, Notification, SystemSetting, AuditLog


def get_alert_threshold_days() -> int:
    """Retrieve administrator-configured expiry alert window in days (default: Config.WARRANTY_EXPIRY_ALERT_DAYS)."""
    try:
        return SystemSetting.get_int("warranty_expiry_alert_days", Config.WARRANTY_EXPIRY_ALERT_DAYS)
    except Exception:
        return Config.WARRANTY_EXPIRY_ALERT_DAYS


def set_alert_threshold_days(days: int, actor_user=None) -> int:
    """Set the system-wide warranty expiry alert window in days and log audit event."""
    days = max(1, min(int(days), 365))
    SystemSetting.set_val(
        "warranty_expiry_alert_days",
        str(days),
        "Threshold days before warranty expiration to trigger automated user alerts (Req 1.6.ix)"
    )

    if actor_user:
        AuditLog.log_event(
            action="WARRANTY_ALERT_THRESHOLD_UPDATED",
            user_id=actor_user.id if hasattr(actor_user, "id") else None,
            user_role=getattr(actor_user, "role", Config.ROLE_ADMIN),
            entity_type="SystemSetting",
            entity_id="warranty_expiry_alert_days",
            details={
                "new_threshold_days": days,
                "configured_by": getattr(actor_user, "email", "Administrator")
            }
        )
        db.session.commit()

    return days


def get_approaching_warranties(threshold_days=None, user_id=None) -> list:
    """Query active warranties approaching expiration within the alert window."""
    if threshold_days is None:
        threshold_days = get_alert_threshold_days()

    query = ProductWarranty.query.join(Product)
    if user_id:
        query = query.filter(Product.user_id == user_id)

    warranties = query.all()
    return [w for w in warranties if w.is_approaching_expiry(threshold_days=threshold_days)]


def scan_and_generate_warranty_alerts(user_id=None) -> list:
    """
    Req 1.6.ix: Warranty Expiry Alerts Engine
    Scans active warranties nearing expiration against the admin-configured threshold.
    Dispatches automated Notification records to corresponding users if not already notified.
    """
    threshold_days = get_alert_threshold_days()
    approaching = get_approaching_warranties(threshold_days=threshold_days, user_id=user_id)
    created_notifications = []

    for w in approaching:
        product = w.product
        if not product:
            continue

        rem_days = w.remaining_days()

        # Check if an active unread notification already exists for this product
        existing = Notification.query.filter_by(
            user_id=product.user_id,
            notification_type=Config.NOTIF_TYPE_WARRANTY_EXPIRY,
            related_product_id=product.product_id,
            is_read=False
        ).first()

        if not existing:
            notif = Notification(
                user_id=product.user_id,
                notification_type=Config.NOTIF_TYPE_WARRANTY_EXPIRY,
                title=f"Warranty Expiry Alert: {product.product_name}",
                message=(
                    f"Action Required: The warranty for '{product.product_name}' "
                    f"(Model: {product.model_number}, Serial: {product.serial_number}) is nearing expiration. "
                    f"You have {rem_days} day{'s' if rem_days != 1 else ''} remaining before policy expiry "
                    f"on {w.expiry_date.strftime('%Y-%m-%d')}. Submit any outstanding warranty claims or contact support."
                ),
                related_product_id=product.product_id
            )
            db.session.add(notif)
            created_notifications.append(notif)

    if created_notifications:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    return created_notifications


def get_system_anomalies(hours: int = 48) -> list:
    """
    Req 1.6.l: Monitoring & Anomaly Alerts Engine.
    Monitors 7 system security and operational dimensions:
    1. Failed uploads
    2. Repeated login attempts
    3. Duplicate documents
    4. Unusual claim activity
    5. Model failures
    6. Low-confidence predictions
    7. Excessive disagreement between the two models
    """
    from sqlalchemy import func
    from src.models.entities import Claim, ClaimDocument, ModelEvaluation, User

    anomalies = []

    # 1. Failed Uploads
    failed_uploads = AuditLog.query.filter(
        AuditLog.action == "UPLOAD_FAILED"
    ).all()
    if failed_uploads:
        anomalies.append({
            "type": "failed_uploads",
            "title": "Failed Document Uploads",
            "category": "File Ingestion",
            "severity": "Warning",
            "count": len(failed_uploads),
            "description": f"{len(failed_uploads)} failed file upload event(s) logged due to invalid MIME formats or size violations.",
            "recommendation": "Review document upload logs and ensure clients adhere to supported PDF/PNG/JPEG formats."
        })

    # 2. Repeated Login Attempts
    failed_logins = AuditLog.query.filter(
        AuditLog.action == "LOGIN_FAILED"
    ).all()
    login_fails_by_ip = {}
    for fl in failed_logins:
        ip = fl.ip_address or "Unknown"
        login_fails_by_ip[ip] = login_fails_by_ip.get(ip, 0) + 1

    suspicious_ips = [ip for ip, cnt in login_fails_by_ip.items() if cnt >= 3]
    if suspicious_ips or len(failed_logins) >= 3:
        anomalies.append({
            "type": "repeated_logins",
            "title": "Repeated Failed Login Attempts",
            "category": "Authentication Security",
            "severity": "Critical" if suspicious_ips else "Warning",
            "count": len(failed_logins),
            "description": f"{len(failed_logins)} failed login attempt(s) detected across {len(login_fails_by_ip)} IP source(s).",
            "recommendation": "Verify claimant identities and monitor IP sources for potential brute-force activity."
        })

    # 3. Duplicate Documents
    dup_claims = Claim.query.filter(Claim.is_duplicate_flag == True).count()
    dup_hash_counts = db.session.query(
        ClaimDocument.file_hash_sha256, func.count(ClaimDocument.id)
    ).group_by(ClaimDocument.file_hash_sha256).having(func.count(ClaimDocument.id) > 1).all()
    total_dup_docs = sum(cnt for _, cnt in dup_hash_counts) if dup_hash_counts else 0

    if dup_claims > 0 or total_dup_docs > 0:
        anomalies.append({
            "type": "duplicate_documents",
            "title": "Duplicate Document & Claim Inconsistencies",
            "category": "Fraud Prevention",
            "severity": "Warning",
            "count": max(dup_claims, total_dup_docs),
            "description": f"{max(dup_claims, total_dup_docs)} duplicate document occurrences or duplicate claim flags flagged across the fleet.",
            "recommendation": "Investigate flagged dossiers to determine whether invoices or serials were reused."
        })

    # 4. Unusual Claim Activity
    high_amount_claims = sum(1 for c in Claim.query.all() if c.claim_amount >= 2000.0)
    claims_by_user = db.session.query(Claim.user_id, func.count(Claim.id)).group_by(Claim.user_id).having(func.count(Claim.id) >= 3).all()
    burst_filing_users = len(claims_by_user)

    if high_amount_claims > 0 or burst_filing_users > 0:
        anomalies.append({
            "type": "unusual_claim_activity",
            "title": "Unusual Claim Activity",
            "category": "Risk Management",
            "severity": "Warning",
            "count": high_amount_claims + burst_filing_users,
            "description": f"{high_amount_claims} high-value claim(s) (>= $2,000) and {burst_filing_users} user account(s) with high filing volume detected.",
            "recommendation": "Perform senior technician review for high-indemnity warranty replacement requests."
        })

    # 5. Model Failures
    model_failures = AuditLog.query.filter(AuditLog.action == "MODEL_FAILURE").all()
    if model_failures:
        anomalies.append({
            "type": "model_failures",
            "title": "Machine Learning Prediction Faults",
            "category": "AI Health",
            "severity": "Critical",
            "count": len(model_failures),
            "description": f"{len(model_failures)} machine learning pipeline exception(s) logged. Safe fallback heuristics engaged.",
            "recommendation": "Verify Python model and Teachable Machine weights artifacts in model/ directory."
        })

    # 6. Low-Confidence Predictions
    evaluations = ModelEvaluation.query.all()
    low_confs = [
        e for e in evaluations
        if e.model_consistency_status == Config.CONSISTENCY_UNCERTAIN
        or (e.python_conf_valid < Config.MIN_CONFIDENCE_THRESHOLD and e.python_conf_invalid < Config.MIN_CONFIDENCE_THRESHOLD and e.python_conf_manual < Config.MIN_CONFIDENCE_THRESHOLD)
    ]
    if low_confs:
        anomalies.append({
            "type": "low_confidence",
            "title": "Low-Confidence Predictions",
            "category": "Inference Quality",
            "severity": "Warning",
            "count": len(low_confs),
            "description": f"{len(low_confs)} claim prediction(s) executed with confidence scores below the minimum operating threshold ({Config.MIN_CONFIDENCE_THRESHOLD:.2f}).",
            "recommendation": "Review edge cases and gather more representative sample data for model retraining."
        })

    # 7. Excessive Disagreement Between Two Models
    disagreements = [e for e in evaluations if (not e.is_class_match) or e.model_consistency_status == Config.CONSISTENCY_DISAGREEMENT]
    disagreement_rate = (len(disagreements) / len(evaluations) * 100) if evaluations else 0.0
    if len(disagreements) > 0:
        anomalies.append({
            "type": "model_disagreement",
            "title": "Dual-Model Prediction Disagreements",
            "category": "Model Consensus",
            "severity": "Critical" if disagreement_rate > 30.0 else "Warning",
            "count": len(disagreements),
            "description": f"{len(disagreements)} claim(s) resulted in disagreement between Python ML and Teachable Machine ({disagreement_rate:.1f}% divergence rate).",
            "recommendation": "Route diverging claims through senior human adjudication to calibrate consensus thresholds."
        })

    return anomalies


def scan_and_generate_anomaly_alerts() -> list:
    """
    Req 1.6.l: Scans for all 7 active anomaly dimensions and dispatches notifications to system administrators.
    """
    from src.models.entities import User
    anomalies = get_system_anomalies()
    admin_users = User.query.filter_by(role=Config.ROLE_ADMIN).all()
    if not admin_users or not anomalies:
        return []

    created = []
    for admin in admin_users:
        for anom in anomalies:
            existing = Notification.query.filter_by(
                user_id=admin.id,
                notification_type=Config.NOTIF_TYPE_ANOMALY_ALERT,
                title=f"System Anomaly: {anom['title']}",
                is_read=False
            ).first()

            if not existing:
                notif = Notification(
                    user_id=admin.id,
                    notification_type=Config.NOTIF_TYPE_ANOMALY_ALERT,
                    title=f"System Anomaly: {anom['title']}",
                    message=f"[{anom['severity']}] {anom['description']} Action: {anom['recommendation']}"
                )
                db.session.add(notif)
                created.append(notif)

    if created:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    return created

