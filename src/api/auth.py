"""Sign-in, registration, profile (SRS i, ii)."""
from __future__ import annotations

import re

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from config.config import Config
from database.db import db
from src.app_security import limiter
from src.models.entities import AuditLog, Claim, Notification, Product, User
from src.security import rbac
from src.security.guards import (invalidate_sessions, login_user, registration_role, require,
                                 safe_next)
from src.rules.validator import email_problem, person_name_problem, phone_problem
from src.services.audit import audit
from src.services.demo_bench import card_reading

auth_bp = Blueprint("auth", __name__)
HOME = {Config.ROLE_ADMIN: "admin.dashboard", Config.ROLE_REVIEWER: "reviewer.queue",
        Config.ROLE_STAFF: "claims.dashboard", Config.ROLE_CUSTOMER: "claims.dashboard"}


def password_problem(password: str, confirm: str | None = None) -> str | None:
    if len(password) < 10:
        return "Use at least 10 characters for your password."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Your password needs at least one letter and one number."
    if confirm is not None and password != confirm:
        return "The two passwords don't match."
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10/minute;60/hour", methods=["POST"])
def login():
    if g.get("user"):
        return redirect(url_for("auth.home"))
    email = request.form.get("email", "").strip().lower()
    retry_in = 0
    if request.method == "POST":
        if (problem := email_problem(email)):
            flash(problem, "danger")
            return _login_page(email, retry_in, 400)
        user = User.query.filter_by(email=email).first()
        was_locked = bool(user and user.is_locked)
        ok, message = login_user(user, request.form.get("password", ""))
        if ok:
            audit("LOGIN_SUCCESS", "User", user.user_id, user=user)
            db.session.commit()
            flash(f"Welcome back, {user.first_name}.", "success")
            return redirect(safe_next(request.args.get("next"), url_for("auth.home")))
        now_locked = bool(user and user.is_locked)
        reason = "locked" if was_locked else ("unknown_email" if user is None else
                                              "disabled" if not user.is_active else "bad_password")
        audit("LOGIN_LOCKED" if now_locked and not was_locked else "LOGIN_FAILED", "User",
              user.user_id if user else None, user=None, email=email, reason=reason)
        db.session.commit()
        if now_locked:                                    # the page shows a countdown instead of a flashed line
            retry_in = user.lock_seconds_left
        else:
            flash(message, "danger")
    return _login_page(email, retry_in, 401 if request.method == "POST" else 200)


def _login_page(email: str, retry_in: int, status: int):
    return render_template("auth/login.html", email=email, card=Config.LOGIN_CARD, retry_in=retry_in,
                           lock=rbac.policy()["login"], reading=card_reading(Config.LOGIN_CARD)), status


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10/hour", methods=["POST"])
def register():
    if g.get("user"):
        return redirect(url_for("auth.home"))
    form = request.form
    if request.method == "POST":
        name = form.get("full_name", "").strip()
        email = form.get("email", "").strip().lower()
        password = form.get("password", "")
        errors = {k: v for k, v in {
            "full_name": person_name_problem(name),
            "email": email_problem(email),
            "password": password_problem(password),
            "confirm_password": None if password == form.get("confirm_password", "") else "The two passwords don't match.",
            "phone": phone_problem(form.get("phone", "")),
        }.items() if v}
        if "email" not in errors and User.query.filter_by(email=email).first():
            errors["email"] = "An account with this email already exists. Sign in instead."
        if errors:
            flash("Some details need attention. Check the highlighted fields.", "warning")
            return render_template("auth/register.html", form=form, errors=errors, card=Config.REGISTER_CARD,
                                   reading=card_reading(Config.REGISTER_CARD)), 400
        user = User(full_name=name, email=email, role=registration_role(form.get("role")),
                    phone_number=form.get("phone", "").strip() or None, address=form.get("address", "").strip() or None)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        audit("ACCOUNT_CREATED", "User", user.user_id, user=user, role=user.role, self_registered=True)
        db.session.commit()
        flash("Your account is ready. Sign in to register your first product.", "success")
        return redirect(url_for("auth.login", email=email))
    return render_template("auth/register.html", form={}, errors={}, card=Config.REGISTER_CARD,
                           reading=card_reading(Config.REGISTER_CARD))


@auth_bp.post("/logout")
def logout():
    if g.get("user"):
        audit("LOGOUT", "User", g.user.user_id)
        db.session.commit()
    csrf_token = session.get("csrf_token")
    session.clear()
    if csrf_token:
        session["csrf_token"] = csrf_token
    flash("You're signed out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.get("/home")
@require()
def home():
    return redirect(url_for(HOME.get(g.user.role, "claims.dashboard")))


@auth_bp.route("/profile", methods=["GET", "POST"])
@require("profile.manage")
def profile():
    user = g.user
    if request.method == "POST":
        action = request.form.get("action")
        if action == "details":
            name = request.form.get("full_name", "").strip()
            phone = request.form.get("phone", "").strip()
            problem = person_name_problem(name) or phone_problem(phone)
            if problem:
                flash(problem, "warning")
            else:
                user.full_name, user.phone_number = name, phone or None
                user.address = request.form.get("address", "").strip() or None
                audit("PROFILE_UPDATED", "User", user.user_id)
                db.session.commit()
                flash("Profile saved.", "success")
        elif action == "password":
            new = request.form.get("new_password", "")
            if not user.check_password(request.form.get("current_password", "")):
                flash("Your current password is not correct.", "danger")
            elif (problem := password_problem(new, request.form.get("confirm_password", ""))):
                flash(problem, "warning")
            elif user.check_password(new):
                flash("Choose a password you haven't used for this account.", "warning")
            else:
                user.set_password(new)
                user.must_change_password = False
                invalidate_sessions(user)                   # sign out every other device
                audit("PASSWORD_CHANGED", "User", user.user_id)
                db.session.commit()
                session["ver"] = user.session_version       # keep this session alive
                flash("Password changed. Other devices were signed out.", "success")
        return redirect(url_for("auth.profile"))
    stats = {"products": Product.query.filter_by(user_id=user.id).count(),
             "claims": Claim.query.filter_by(user_id=user.id).count(),
             "unread": Notification.query.filter_by(user_id=user.id, is_read=False).count()}
    activity = AuditLog.query.filter_by(user_id=user.id).order_by(AuditLog.id.desc()).limit(8).all()
    permissions = sorted(rbac.policy()["roles"].get(user.role, {}).get("permissions", {}).items())
    return render_template("auth/profile.html", user=user, stats=stats, activity=activity, permissions=permissions)
