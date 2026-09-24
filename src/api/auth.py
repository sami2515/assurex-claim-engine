import json
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
        if user and user.check_password(password) and (user.is_active is not False):
            if not user.is_active:
                user.is_active = True
                db.session.commit()

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
            fail_reason = "User not found" if not user else ("Invalid password" if not user.check_password(password) else "Account disabled")
            # Req l: Monitor repeated login attempts via AuditLog
            audit_fail = AuditLog(
                user_id=user.id if user else None,
                user_role=user.role if user else None,
                action="LOGIN_FAILED",
                entity_type="USER",
                entity_id=user.user_id if user else email,
                ip_address=request.remote_addr,
                details_json=json.dumps({"attempted_email": email, "reason": fail_reason})
            )
            db.session.add(audit_fail)
            db.session.commit()

            if not user:
                flash(f"Account with email '{email}' does not exist. Please register first or use a demo account.", "danger")
            elif not user.check_password(password):
                flash("Invalid password entered. Please check your credentials.", "danger")
            else:
                flash("Account is disabled. Please contact the administrator.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """
    Req 1.6.i: User Registration and Authentication.
    Supports registration for Customers, Service-Center Staff, Claim Reviewers, and Administrators.
    Maintains a unique User ID and enforces role-based access.
    """
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        confirm_password = request.form.get("confirm_password", "")
        role_input = request.form.get("role", "").strip().lower()
        role_map = {
            "customer": Config.ROLE_CUSTOMER,
            "staff": Config.ROLE_STAFF,
            "service_center_staff": Config.ROLE_STAFF,
            "reviewer": Config.ROLE_REVIEWER,
            "claim_reviewer": Config.ROLE_REVIEWER,
            "admin": Config.ROLE_ADMIN,
            "administrator": Config.ROLE_ADMIN
        }
        role = role_map.get(role_input, Config.ROLE_CUSTOMER)

        if not email or not password or not full_name:
            flash("Name, email, and password are required fields.", "warning")
            return render_template("auth/register.html")

        if confirm_password and password != confirm_password:
            flash("Passwords do not match. Please re-enter.", "warning")
            return render_template("auth/register.html")

        if User.query.filter_by(email=email).first():
            flash("An account with this email address already exists.", "warning")
            return render_template("auth/register.html")

        user = User(
            email=email,
            full_name=full_name,
            role=role,
            phone_number=phone,
            address=address
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        audit = AuditLog(
            user_id=user.id,
            user_role=user.role,
            action="ACCOUNT_CREATION",
            entity_type="USER",
            entity_id=user.user_id,
            ip_address=request.remote_addr,
            details_json=json.dumps({"role": user.role, "email": user.email})
        )
        db.session.add(audit)
        db.session.commit()

        role_display = {
            Config.ROLE_CUSTOMER: "Customer",
            Config.ROLE_STAFF: "Service Staff",
            Config.ROLE_REVIEWER: "Claim Reviewer",
            Config.ROLE_ADMIN: "Administrator"
        }.get(role, role)

        flash(f"Account created successfully as {role_display}! You may now sign in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """
    Req 1.6.ii: User Profile Management.
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
        return redirect(url_for("claims.customer_dashboard"))
    else:
        return redirect(url_for("claims.customer_dashboard"))
