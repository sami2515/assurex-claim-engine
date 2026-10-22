"""HTTP hardening: secret key, CSRF, rate limiting, cookies and security headers."""
from __future__ import annotations

import gzip
import os
import secrets

from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFError, CSRFProtect

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=["600/hour"])

# All JavaScript, fonts and styles are served from /static. The only inline script is the two-line preloader
# bootstrap in base.html, allowed by a per-request nonce. 'unsafe-inline' for styles covers the CSS custom
# properties that templates set from data (style="--p: .88"); no stylesheet or font comes from a third party.
CSP = ("default-src 'self'; img-src 'self' data: blob:; object-src 'none'; base-uri 'self'; "
       "form-action 'self'; frame-ancestors 'none'; connect-src 'self'; "
       "script-src 'self' 'nonce-{nonce}'; style-src 'self' 'unsafe-inline'; font-src 'self'")


def csp_nonce() -> str:
    """One nonce per request (kept in the WSGI environ, which never outlives the request)."""
    return request.environ.setdefault("assurex.csp_nonce", secrets.token_urlsafe(16))


COMPRESSIBLE = {"text/html", "text/css", "application/javascript", "text/javascript", "application/json",
                "image/svg+xml", "text/plain"}


def _gzip(resp):
    """Compress text responses for browsers that accept gzip (no extra dependency; about 75% smaller pages)."""
    if (resp.mimetype not in COMPRESSIBLE or resp.status_code not in (200, 201) or "Content-Encoding" in resp.headers
            or "gzip" not in request.headers.get("Accept-Encoding", "").lower()):
        return resp
    if resp.direct_passthrough:                                          # static files: read the (small) file once
        resp.direct_passthrough = False
    body = resp.get_data()
    if len(body) < 1024:
        return resp
    resp.set_data(gzip.compress(body, compresslevel=6))
    resp.headers["Content-Encoding"] = "gzip"
    resp.vary.add("Accept-Encoding")
    etag, weak = resp.get_etag()
    if etag and not weak:
        resp.set_etag(etag, weak=True)                                   # the bytes differ from the file's ETag
    return resp


def harden(app) -> None:
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is not set. Run `python database/seed.py` once (it writes a .env with a "
                           "random key) or export SECRET_KEY before starting the app.")
    app.config.setdefault("SESSION_COOKIE_SECURE", os.environ.get("SESSION_COOKIE_SECURE", "0").lower() in ("1", "true"))
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_NAME="assurex_session")
    csrf.init_app(app)
    limiter.init_app(app)
    app.jinja_env.globals["csp_nonce"] = csp_nonce

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        resp.headers.setdefault("Content-Security-Policy", CSP.format(nonce=csp_nonce()))
        if request.is_secure:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if resp.mimetype == "text/html":
            resp.headers["Cache-Control"] = "no-store"
        return _gzip(resp)

    @app.errorhandler(CSRFError)
    def _csrf_error(_e):
        from flask import render_template
        return render_template("components/error.html", code=400, title="This form expired",
                               message="For your security the form could not be accepted. Reload the page and try again."), 400
