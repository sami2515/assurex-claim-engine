import hmac
import json
import secrets
from functools import wraps
from flask import Blueprint, request, session, redirect, url_for, flash, jsonify, render_template, g
from config.config import Config
from database.db import db
from src.models.entities import User, AuditLog

auth_bp = Blueprint("auth", __name__)


def generate_csrf_token():
    """Generates and stores a cryptographically secure CSRF token in session."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def validate_csrf_token(token: str) -> bool:
    """Validates submitted CSRF token against session."""
    session_token = session.get("csrf_token")
    if not session_token or not token:
        return False
    return hmac.compare_digest(str(session_token), str(token))


def csrf_protect(f):
    """Decorator enforcing CSRF token validation on state-changing requests."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            from flask import current_app
            # Allow testing bypass only when explicitly configured
            if current_app.config.get("TESTING") and not current_app.config.get("WTF_CSRF_ENABLED", False):
                return f(*args, **kwargs)
            
            token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
            if not validate_csrf_token(token):
                flash("Security validation failed (Invalid or missing CSRF token). Please try again.", "danger")
                return redirect(request.referrer or url_for("auth.login")), 403
        return f(*args, **kwargs)
    return decorated_function


def get_current_user():
    """
    Retrieves currently authenticated User object from database using session identity.
    Returns fresh DB instance or None if not found/invalid.
    """
    user_id = session.get("user_id")
    if not user_id:
        return None
    try:
        if isinstance(user_id, str) and not user_id.isdigit():
            return User.query.filter_by(user_id=user_id).first()
        return db.session.get(User, int(user_id))
    except Exception:
        return None


def login_required(f):
    """Guard ensuring an active, authenticated user identity exists in database."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in to access this portal.", "warning")
            return redirect(url_for("auth.login"))
        
        user = get_current_user()
        if not user:
            session.clear()
            flash("Session expired. Please sign in again.", "warning")
            return redirect(url_for("auth.login"))
        
        if user.is_active is False:
            session.clear()
            flash("Your account has been deactivated. Please contact the administrator.", "danger")
            return redirect(url_for("auth.login"))
        
        # Ensure session role is synchronized with database single source of truth
        session["role"] = user.role
        return f(*args, **kwargs)
    return decorated_function


def role_required(*allowed_roles):
    """
    Guard enforcing DB-backed role permissions as the single source of truth.
    Does NOT rely on stale session cookies; verifies directly against database record.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("user_id"):
                flash("Please sign in to continue.", "warning")
                return redirect(url_for("auth.login"))
            
            user = get_current_user()
            if not user:
                session.clear()
                flash("Session expired. Please sign in again.", "warning")
                return redirect(url_for("auth.login"))
            
            if user.is_active is False:
                session.clear()
                flash("Your account has been deactivated. Please contact the administrator.", "danger")
                return redirect(url_for("auth.login"))
            
            # Authoritative check from database record directly
            if user.role not in allowed_roles:
                flash("Unauthorized access: You don't have the required permissions.", "danger")
                return redirect(url_for("auth.portal_redirect"))
            
            # Synchronize session state with DB
            session["role"] = user.role
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@auth_bp.route("/login", methods=["GET", "POST"])
@csrf_protect
def login():
    """
    User authentication endpoint.
    Verifies credentials, enforces active account status, applies CSRF protection,
    and records audit trail events for login successes and failures.
    Deactivated accounts cannot log in under any circumstances.
    """
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required fields.", "warning")
            return render_template("auth/login.html")

        user = User.query.filter_by(email=email).first()

        if not user:
            # Login failed - non-existent user
            audit_fail = AuditLog(
                user_id=None,
                user_role=None,
                action="LOGIN_FAILED",
                entity_type="USER",
                entity_id=email,
                ip_address=request.remote_addr,
                details_json=json.dumps({"attempted_email": email, "reason": "User not found"})
            )
            db.session.add(audit_fail)
            db.session.commit()
            flash(f"Account with email '{email}' does not exist. Please register first or use a demo account.", "danger")
            return render_template("auth/login.html")

        if not user.check_password(password):
            # Login failed - bad password
            audit_fail = AuditLog(
                user_id=user.id,
                user_role=user.role,
                action="LOGIN_FAILED",
                entity_type="USER",
                entity_id=user.user_id,
                ip_address=request.remote_addr,
                details_json=json.dumps({"attempted_email": email, "reason": "Invalid password"})
            )
            db.session.add(audit_fail)
            db.session.commit()
            flash("Invalid password entered. Please check your credentials.", "danger")
            return render_template("auth/login.html")

        if not user.is_active:
            # Login blocked - inactive/deactivated account (NO AUTO-REACTIVATION)
            audit_fail = AuditLog(
                user_id=user.id,
                user_role=user.role,
                action="LOGIN_FAILED",
                entity_type="USER",
                entity_id=user.user_id,
                ip_address=request.remote_addr,
                details_json=json.dumps({"attempted_email": email, "reason": "Account disabled"})
            )
            db.session.add(audit_fail)
            db.session.commit()
            flash("Account is disabled. Please contact the administrator.", "danger")
            return render_template("auth/login.html")

        # Session establishment for verified active user
        session["user_id"] = user.id
        session["user_code"] = user.user_id
        session["role"] = user.role
        session["user_name"] = user.full_name
        session["email"] = user.email

        # Record login audit log
        audit = AuditLog(
            user_id=user.id,
            user_role=user.role,
            action="USER_LOGIN_SUCCESS",
            entity_type="USER",
            entity_id=user.user_id,
            ip_address=request.remote_addr,
            details_json=json.dumps({"role": user.role, "email": user.email})
        )
        db.session.add(audit)
        db.session.commit()

        flash(f"Welcome back, {user.full_name}!", "success")
        return redirect(url_for("auth.portal_redirect"))

    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
@csrf_protect
def register():
    """
    User Registration and Authentication (Customer Self-Registration).
    Public registration deterministically creates Customer accounts only.
    Client-submitted role values are ignored to prevent privilege escalation.
    """
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        confirm_password = request.form.get("confirm_password", "")
        # Public self-registration ALWAYS creates CUSTOMER accounts only.
        # Any client-supplied role parameter is strictly ignored.
        role = Config.ROLE_CUSTOMER

        if not email or not password or not full_name:
            flash("Name, email, and password are required fields.", "warning")
            return render_template("auth/register.html")

        if "@" not in email or "." not in email.split("@")[-1]:
            flash("Please enter a valid email address.", "warning")
            return render_template("auth/register.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "warning")
            return render_template("auth/register.html")

        if confirm_password and password != confirm_password:
            flash("Passwords do not match. Please re-enter.", "warning")
            return render_template("auth/register.html")

        if User.query.filter_by(email=email).first():
            flash("An account with this email address already exists.", "warning")
            return render_template("auth/register.html")

        # Phone number format validation
        if phone:
            digits_only = ''.join(c for c in phone if c.isdigit())
            if len(digits_only) < 7 or len(digits_only) > 15:
                flash("Phone number must contain between 7 and 15 digits.", "warning")
                return render_template("auth/register.html")

        # Address length validation
        if address and len(address) < 5:
            flash("Please enter a complete address (at least 5 characters).", "warning")
            return render_template("auth/register.html")

        user = User(
            email=email,
            full_name=full_name,
            role=role,
            phone_number=phone,
            address=address
        )
        user.set_password(password)
        try:
            db.session.add(user)
            db.session.flush()

            audit = AuditLog(
                user_id=user.id,
                user_role=user.role,
                action="ACCOUNT_CREATED",
                entity_type="USER",
                entity_id=user.user_id,
                ip_address=request.remote_addr,
                details_json=json.dumps({"role": user.role, "email": user.email, "self_registered": True, "ip": request.remote_addr})
            )
            db.session.add(audit)
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("An error occurred during registration. Please try again.", "danger")
            return render_template("auth/register.html")

        flash("Account created successfully as Customer! You may now sign in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """
    User Profile Management.
    Enables viewing unique User ID, role credentials, account details, and updating contact info & security credentials.
    """
    user = get_current_user()
    if not user:
        flash("User session not found.", "warning")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        action = request.form.get("action", "update_info")
        if action == "update_info":
            full_name = request.form.get("full_name", "").strip()
            phone = request.form.get("phone", "").strip()
            address = request.form.get("address", "").strip()

            if not full_name:
                flash("Full name cannot be blank.", "warning")
                return redirect(url_for("auth.profile"))

            user.full_name = full_name
            user.phone_number = phone
            user.address = address
            session["user_name"] = full_name

            audit = AuditLog(
                user_id=user.id,
                user_role=user.role,
                action="USER_PROFILE_UPDATED",
                entity_type="USER",
                entity_id=user.user_id,
                ip_address=request.remote_addr
            )
            db.session.add(audit)
            db.session.commit()
            flash("Your profile details have been updated successfully.", "success")
            return redirect(url_for("auth.profile"))

        elif action == "change_password":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_new_password = request.form.get("confirm_new_password", "")

            if not user.check_password(current_password):
                flash("Current password is incorrect.", "danger")
                return redirect(url_for("auth.profile"))

            if len(new_password) < 8:
                flash("New password must be at least 8 characters long.", "warning")
                return redirect(url_for("auth.profile"))

            if new_password != confirm_new_password:
                flash("New passwords do not match.", "warning")
                return redirect(url_for("auth.profile"))

            user.set_password(new_password)
            audit = AuditLog(
                user_id=user.id,
                user_role=user.role,
                action="USER_PASSWORD_CHANGED",
                entity_type="USER",
                entity_id=user.user_id,
                ip_address=request.remote_addr
            )
            db.session.add(audit)
            db.session.commit()
            flash("Your password has been changed successfully.", "success")
            return redirect(url_for("auth.profile"))

    # Compute contextual stats for profile summary widgets
    stats = {
        "products_count": len(user.products) if hasattr(user, "products") else 0,
        "claims_count": len(user.claims) if hasattr(user, "claims") else 0,
        "audit_logs_count": AuditLog.query.filter_by(user_id=user.id).count()
    }

    return render_template("auth/profile.html", user=user, stats=stats)


@auth_bp.route("/logout")
def logout():
    """Terminates session and records audit event."""
    user = get_current_user()
    if user:
        audit = AuditLog(
            user_id=user.id,
            user_role=user.role,
            action="USER_LOGOUT",
            entity_type="USER",
            entity_id=user.user_id,
            ip_address=request.remote_addr,
            details_json=json.dumps({"email": user.email, "role": user.role})
        )
        db.session.add(audit)
        db.session.commit()

    session.clear()
    flash("Signed out successfully.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/portal")
@login_required
def portal_redirect():
    """Smart router directing users to their role-specific dashboard based on DB role."""
    user = get_current_user()
    role = user.role if user else session.get("role")
    if role == Config.ROLE_ADMIN:
        return redirect(url_for("admin.dashboard"))
    elif role == Config.ROLE_REVIEWER:
        return redirect(url_for("reviewer.queue"))
    elif role == Config.ROLE_STAFF:
        return redirect(url_for("claims.customer_dashboard"))
    else:
        return redirect(url_for("claims.customer_dashboard"))
