from functools import wraps
from flask import Blueprint, request, session, redirect, url_for, flash, jsonify, render_template, g
from config.config import Config
from database.db import db
from src.models.entities import User, AuditLog

auth_bp = Blueprint("auth", __name__)


def get_current_user():
    """Retrieves currently authenticated User object from session."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


def login_required(f):
    """Guard ensuring an authenticated session exists."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in to access this portal.", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*allowed_roles):
    """Guard enforcing specific role permissions."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("user_id"):
                flash("Please sign in to continue.", "warning")
                return redirect(url_for("auth.login"))
            user_role = session.get("role")
            if user_role not in allowed_roles:
                flash("Unauthorized access: You do not possess the required privileges.", "danger")
                return redirect(url_for("auth.portal_redirect"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """User authentication endpoint supporting form submission and JSON API."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password) and user.is_active:
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
                ip_address=request.remote_addr
            )
            db.session.add(audit)
            db.session.commit()

            flash(f"Welcome back, {user.full_name}!", "success")
            return redirect(url_for("auth.portal_redirect"))
        else:
            flash("Invalid email or password. Please verify credentials.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Customer account self-registration endpoint."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()

        if not email or not password or not full_name:
            flash("Name, email, and password are required fields.", "warning")
            return render_template("auth/register.html")

        if User.query.filter_by(email=email).first():
            flash("An account with this email address already exists.", "warning")
            return render_template("auth/register.html")

        user = User(
            email=email,
            full_name=full_name,
            role=Config.ROLE_CUSTOMER,
            phone_number=phone,
            address=address
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("Account created successfully! You may now sign in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@auth_bp.route("/logout")
def logout():
    """Terminates session and records audit event."""
    user_id = session.get("user_id")
    if user_id:
        audit = AuditLog(
            user_id=user_id,
            user_role=session.get("role"),
            action="USER_LOGOUT",
            entity_type="USER",
            entity_id=session.get("user_code", ""),
            ip_address=request.remote_addr
        )
        db.session.add(audit)
        db.session.commit()

    session.clear()
    flash("You have been signed out safely.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/portal")
@login_required
def portal_redirect():
    """Smart router directing users to their role-specific dashboard."""
    role = session.get("role")
    if role == Config.ROLE_ADMIN:
        return redirect(url_for("admin.dashboard"))
    elif role == Config.ROLE_REVIEWER:
        return redirect(url_for("reviewer.queue"))
    elif role == Config.ROLE_STAFF:
        return redirect(url_for("claims.claims_list"))
    else:
        return redirect(url_for("claims.customer_dashboard"))
