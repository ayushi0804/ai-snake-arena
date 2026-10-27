from __future__ import annotations
import hashlib
import logging
from pathlib import Path
from flask import Flask, jsonify, request
from storage.db import Database
from storage.legacy import migrate_legacy_highscore
from . import config as cfg

log = logging.getLogger("arena")
STATIC = Path(__file__).parent / "static"


def static_version() -> str:
    """Hash of all static files + templates: changes whenever the app shell changes, which
    rotates the service-worker cache so clients never keep stale assets."""
    h = hashlib.sha1()
    for base in (STATIC, Path(__file__).parent / "templates"):
        for p in sorted(base.rglob("*")):
            if p.is_file():
                h.update(p.name.encode()); h.update(p.read_bytes())
    return h.hexdigest()[:12]


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(cfg.from_env())
    app.config.update(overrides or {})
    db = Database(app.config["ARENA_DB_PATH"])
    db.init()
    app.extensions["arena_db"] = db
    app.config["LEGACY_MIGRATION"] = migrate_legacy_highscore(db, app.config["ARENA_LEGACY_HIGHSCORE"])

    from .api import bp as api_bp
    from .views import bp as views_bp
    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)

    @app.after_request
    def headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; "
                                                   "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
                                                   "manifest-src 'self'; worker-src 'self'; frame-ancestors 'none'")
        origin = request.headers.get("Origin")
        if request.path.startswith("/api/") and origin and origin in app.config["ARENA_CORS_ORIGINS"]:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Guest-Id"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, OPTIONS"
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    def err(code, msg, status):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": {"code": code, "message": msg}}), status
        return msg, status

    @app.errorhandler(404)
    def _404(e): return err("not_found", "Resource not found", 404)

    @app.errorhandler(405)
    def _405(e): return err("method_not_allowed", "Method not allowed", 405)

    @app.errorhandler(413)
    def _413(e): return err("payload_too_large", "Request body too large", 413)

    @app.errorhandler(Exception)
    def _500(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return err(e.name.lower().replace(" ", "_"), e.description, e.code)
        log.exception("unhandled error")           # details stay in the server log only
        return err("internal_error", "Internal server error", 500)

    return app
