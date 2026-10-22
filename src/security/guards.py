"""Flask glue for src/security/rbac.py.

Loopholes in v1 this closes:
  * /register let anyone pick "Administrator"          -> only self_registration roles accepted
  * role read from the cookie session (stale after role change / disable)
                                                       -> user + role reloaded from DB every request,
                                                          session_version invalidates old cookies
  * /documents/<id>/correct-data had no ownership check (IDOR) -> authorize_object()
  * customer-only object checks (`if role == customer and curr_user ...`) -> scope for every role
  * reviewer could decide own claim / any state / override without reason -> SoD + transitions
  * login revealed which emails exist, no lockout, no session rotation -> fixed in login_user()
  * any new route was public unless someone remembered a decorator -> deny-by-default hook
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import abort, current_app, flash, g, redirect, render_template, request, session, url_for
from sqlalchemy import and_, false, or_, select

from src.security import rbac

PUBLIC_ENDPOINTS = {"static", "public.index", "public.blog", "public.health", "public.model_card", "public.test_card", "api.demo_evaluate",
                    "auth.login", "auth.register", "auth.logout",
                    "dev.styleguide"}                     # exists only when DEBUG or ASSUREX_STYLEGUIDE=1
PASSWORD_CHANGE_ALLOWED = {"auth.profile", "auth.logout", "static"}


# ------------------------------------------------------------------ request lifecycle
def init_rbac(app, db, User, AuditLog) -> None:
    app.extensions["rbac"] = {"db": db, "User": User, "AuditLog": AuditLog}

    @app.before_request
    def _load_user_and_enforce_default_deny():
        g.user = None
        uid, ver = session.get("uid"), session.get("ver")
        if uid is not None:
            user = db.session.get(User, uid)
            idle = rbac.policy()["login"]["session_idle_minutes"]
            last = session.get("seen")
            now = datetime.now(timezone.utc).timestamp()
            expired = last is not None and now - last > idle * 60
            if user is None or not user.is_active or user.session_version != ver or expired:
                csrf_token = session.get("csrf_token")
                session.clear()                                  # role changed / disabled / idle
                if csrf_token:
                    session["csrf_token"] = csrf_token
                if expired:
                    flash("You were signed out after a period of inactivity.", "info")
            else:
                g.user = user
                session["seen"] = now
                if user.must_change_password and request.endpoint not in PASSWORD_CHANGE_ALLOWED:
                    flash(rbac.MESSAGES["PASSWORD_CHANGE_REQUIRED"], "info")
                    return redirect(url_for("auth.profile", _anchor="security"))
        endpoint = request.endpoint or ""
        view = app.view_functions.get(endpoint)
        if endpoint in PUBLIC_ENDPOINTS or view is None:
            return None
        if not getattr(view, "_rbac_guarded", False):            # forgot a decorator? fail closed
            current_app.logger.error("Unguarded endpoint blocked: %s", endpoint)
            abort(403)
        return None

    def _can(perm, obj=None, **ctx):
        return bool(rbac.authorize(g.get("user"), perm, obj, **ctx))

    def _role_label(r):
        return rbac.policy()["roles"].get(r, {}).get("label", r or "Visitor")

    # globals (not only context) so macros imported without context can use them too
    app.jinja_env.globals.update(can=_can, role_label=_role_label)

    @app.context_processor
    def _inject():
        return {"current_user": g.get("user")}

    @app.errorhandler(403)
    def _forbidden(_e):
        code = g.get("rbac_code", "NO_PERMISSION")
        message = rbac.MESSAGES.get(code, rbac.MESSAGES["NO_PERMISSION"])
        if request.path.startswith("/api/"):
            from src.api.errors import ErrorCode, fail
            return fail(ErrorCode.NOT_AUTHENTICATED if code == "NOT_AUTHENTICATED" else ErrorCode.NO_PERMISSION, message)
        signed_in = g.get("user") is not None
        return render_template("components/error.html", code=403, reason=code, title="You don't have access to this page",
                               message=message + " This attempt was recorded in the audit trail.",
                               action_url=None if signed_in else url_for("auth.login"),
                               action_label=None if signed_in else "Sign in"), 403


# ------------------------------------------------------------------ decorators
def require(permission: str | None = None):
    """@require("claim.read") on every non-public view. @require() = any signed-in user."""
    def deco(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if g.get("user") is None:
                if request.path.startswith("/api/"):
                    from src.api.errors import ErrorCode, fail
                    return fail(ErrorCode.NOT_AUTHENTICATED)
                flash(rbac.MESSAGES["NOT_AUTHENTICATED"], "warning")
                return redirect(url_for("auth.login", next=request.full_path))
            if permission and not rbac.has_permission(g.user, permission):
                deny("NO_PERMISSION", permission)
            return view(*args, **kwargs)
        wrapper._rbac_guarded = True
        wrapper._rbac_permission = permission
        return wrapper
    return deco


def authorize_object(permission: str, obj, **ctx):
    """Call inside the view after loading the record. 404 when out of scope."""
    decision = rbac.authorize(g.get("user"), permission, obj, **ctx)
    if not decision:
        deny(decision.code, permission, obj, hide=decision.hide)
    return obj


def check(permission: str, obj=None, **ctx) -> rbac.Decision:
    """Non-aborting variant for business-rule checks the view reports itself (flash + redirect)."""
    return rbac.authorize(g.get("user"), permission, obj, **ctx)


def _claim_terms(Claim, user):
    spec = rbac.visible_claims_filter(user)
    if spec.get("all_rows"):
        return None
    terms = []
    for clause in spec["any"]:
        parts = []
        for field, value in clause.items():
            col = getattr(Claim, field)
            parts.append(col.in_(value) if isinstance(value, list) else (col.is_(None) if value is None else col == value))
        terms.append(and_(*parts))
    return or_(*terms) if terms else false()


def scoped_claims(Claim):
    """Use for EVERY claim list/search/export/dashboard query."""
    cond = _claim_terms(Claim, g.user)
    return Claim.query if cond is None else Claim.query.filter(cond)


def scoped_products(Product, Claim):
    """Products the current user may read (same scope semantics as claims)."""
    user = g.user
    scope = rbac.scope_of(user.role, "product.read")
    if scope == "all":
        return Product.query
    if scope == "own":
        return Product.query.filter(Product.user_id == user.id)
    if scope == "service_center":
        sc = user.service_center_id
        return Product.query.filter(Product.service_center_id == sc) if sc is not None else Product.query.filter(false())
    if scope == "assigned_or_queue":
        ids = select(Claim.product_id).where(_claim_terms(Claim, user))
        return Product.query.filter(Product.id.in_(ids))
    return Product.query.filter(false())


def deny(code: str, permission: str, obj=None, hide: bool = False):
    ext = current_app.extensions["rbac"]
    user = g.get("user")
    try:
        ext["db"].session.add(ext["AuditLog"](
            user_id=getattr(user, "id", None), user_role=getattr(user, "role", None),
            action="ACCESS_DENIED", entity_type=type(obj).__name__ if obj is not None else "ENDPOINT",
            entity_id=str(getattr(obj, "claim_id", None) or getattr(obj, "document_id", None)
                          or getattr(obj, "product_id", None) or request.path)[:50],
            ip_address=request.remote_addr,
            details_json=json.dumps({"permission": permission, "code": code, "path": request.path})))
        ext["db"].session.commit()
    except Exception:                                            # auditing must never mask the denial
        ext["db"].session.rollback()
    g.rbac_code = code
    abort(404 if hide else 403)


# ------------------------------------------------------------------ authentication
GENERIC_LOGIN_ERROR = "Email or password is incorrect."
LOCKED_MESSAGE = "Too many attempts. Try again in a few minutes."


def login_user(user, password: str) -> tuple[bool, str]:
    """Constant-message login with lockout and session rotation."""
    cfg = rbac.policy()["login"]
    now = datetime.now(timezone.utc)
    if user is None:
        return False, GENERIC_LOGIN_ERROR                         # no user enumeration
    if user.is_locked:
        return False, LOCKED_MESSAGE
    if not user.check_password(password) or not user.is_active:
        user.failed_logins = (user.failed_logins or 0) + 1
        if user.failed_logins >= cfg["max_failed_attempts"]:
            user.locked_until = now + timedelta(minutes=cfg["lockout_minutes"])
            user.failed_logins = 0
        return False, GENERIC_LOGIN_ERROR
    user.failed_logins, user.locked_until, user.last_login_at = 0, None, now
    csrf_token = session.get("csrf_token")
    session.clear()                                               # rotate: prevents session fixation
    session.permanent = True
    session.update(uid=user.id, ver=user.session_version, seen=now.timestamp())
    if csrf_token:
        session["csrf_token"] = csrf_token
    return True, ""


def safe_next(target: str | None, fallback: str) -> str:
    """Open-redirect guard for ?next=."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return fallback


def registration_role(requested: str | None) -> str:
    """Public sign-up can only create self-registrable roles (customer). Staff, reviewers
    and admins are invited by an administrator from Access control."""
    allowed = rbac.self_registrable_roles()
    return requested if requested in allowed else "customer"


def invalidate_sessions(user) -> None:
    """Call after role change, password change, disable. Kicks every open session of that user."""
    user.session_version = (user.session_version or 0) + 1
