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
