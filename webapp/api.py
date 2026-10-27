"""Versioned REST API: /api/v1. Responses: {"ok": true, "data": ...} | {"ok": false, "error": {...}}."""
from __future__ import annotations
import csv
import io
import sqlite3
import time
from flask import Blueprint, current_app, jsonify, request, Response
from storage import services as svc
from snake_core.benchmark import run_pathfinding, run_survival
from snake_core.engine import DIFFICULTIES

bp = Blueprint("api", __name__, url_prefix="/api/v1")
VERSION = "1.0.0"


def db():
    return current_app.extensions["arena_db"]


def ok(data=None, status=200):
    return jsonify({"ok": True, "data": data}), status


def fail(code, message, status, details=None):
    body = {"ok": False, "error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return jsonify(body), status


def guest_id():
    gid = request.headers.get("X-Guest-Id")
    if not gid and request.is_json:
        body = request.get_json(silent=True)
        gid = body.get("guest_id") if isinstance(body, dict) else None
    return gid


def need_guest():
    gid = guest_id()
    if not gid or not svc.GUEST_RE.match(gid):
        return None, fail("guest_required", "A valid X-Guest-Id header (8-64 chars A-Z a-z 0-9 _ -) is required", 400)
    return gid, None


def json_body():
    if not request.is_json:
        return None
    return request.get_json(silent=True)


@bp.errorhandler(svc.ValidationError)
def _validation(e):
    return fail("validation_error", "Request failed validation", 422, e.errors)


@bp.errorhandler(sqlite3.Error)
def _dberr(e):
    current_app.logger.exception("database error")
    return fail("database_error", "A database error occurred", 500)


@bp.route("/health")
def health():
    with db().read() as c:
        c.execute("SELECT 1").fetchone()
    return ok({"status": "ok", "version": VERSION, "time": time.time(),
               "legacy_migration": current_app.config.get("LEGACY_MIGRATION", {}).get("status")})


@bp.route("/matches", methods=["POST"])
def submit_match():
    gid, err = need_guest()
    if err: return err
    body = json_body()
    if body is None:
        return fail("invalid_json", "Content-Type application/json with a JSON object body is required", 400)
    row, created = svc.save_match(db(), gid, body, source="web", display_name=body.get("player_name"))
    return ok({"match": row, "created": created, "verification": "client_reported"}, 201 if created else 200)


@bp.route("/matches")
def history():
    gid, err = need_guest()
    if err: return err
    try:
        limit, offset = int(request.args.get("limit", 20)), int(request.args.get("offset", 0))
    except ValueError:
        return fail("bad_request", "limit/offset must be integers", 400)
    return ok(svc.match_history(db(), gid, limit, offset))


@bp.route("/players/me/stats")
def stats():
    gid, err = need_guest()
    if err: return err
    return ok(svc.player_stats(db(), gid))


@bp.route("/leaderboard")
def leaderboard():
    diff, mode = request.args.get("difficulty"), request.args.get("mode")
    if diff and diff not in DIFFICULTIES: return fail("bad_request", "unknown difficulty", 400)
    if mode and mode not in svc.MODES: return fail("bad_request", "unknown mode", 400)
    try:
        limit = int(request.args.get("limit", 10))
    except ValueError:
        return fail("bad_request", "limit must be an integer", 400)
    return ok({"entries": svc.leaderboard(db(), diff, mode, limit),
               "note": "Scores are client-reported; none are server-verified."})


@bp.route("/metrics/algorithms")
def algo_metrics():
    return ok(svc.algorithm_metrics(db()))


@bp.route("/settings", methods=["GET", "PUT"])
def settings():
    gid, err = need_guest()
    if err: return err
    if request.method == "GET":
        return ok(svc.get_settings(db(), gid))
    body = json_body()
    if body is None:
        return fail("invalid_json", "JSON object body required", 400)
    return ok(svc.put_settings(db(), gid, body))


def _num(body, key, default, lo, hi, kind=int):
    v = body.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
        raise svc.ValidationError({key: f"number {lo}..{hi} required"})
    return kind(v)


@bp.route("/benchmarks/run", methods=["POST"])
def run_benchmark():
    body = json_body() or {}
    if not isinstance(body, dict):
        return fail("invalid_json", "JSON object body required", 400)
    kind = body.get("kind", "pathfinding")
    if kind not in ("pathfinding", "survival"):
        raise svc.ValidationError({"kind": "pathfinding | survival"})
    seed = _num(body, "seed", 1, 0, 2**31 - 1)
    if kind == "pathfinding":
        w, h = _num(body, "board_w", 25, 5, 40), _num(body, "board_h", 12, 5, 40)
        n = _num(body, "scenarios", 100, 1, 500)
        slen = _num(body, "snake_len", 8, 1, max(1, w * h // 3))
        frac = _num(body, "obstacle_fraction", 0.05, 0, 0.2, float)
        rows = run_pathfinding(seed, w, h, n, slen, frac, bool(body.get("wrap", False)))
    else:
        w, h = _num(body, "board_w", 12, 5, 20), _num(body, "board_h", 8, 5, 20)
        games, steps = _num(body, "games", 5, 1, 20), _num(body, "max_steps", 600, 50, 2000)
        diff = body.get("difficulty", "normal")
        if diff not in DIFFICULTIES:
            raise svc.ValidationError({"difficulty": "unknown difficulty"})
        if games * steps * 5 > 30000:
            raise svc.ValidationError({"games": "games x max_steps too large for a synchronous request (<= 6000)"})
        rows = run_survival(seed, w, h, games, diff, steps)
    ids = svc.save_benchmark_rows(db(), rows)
    for r, i in zip(rows, ids):
        r["id"] = i
    return ok({"kind": kind, "results": rows}, 201)


@bp.route("/benchmarks")
def benchmarks():
    return ok(svc.list_benchmarks(db(), int(request.args.get("limit", 100)) if request.args.get("limit", "100").isdigit() else 100))


def _safe_cell(v):
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@") and not _is_number(s) else s


def _is_number(s):
    try:
        float(s); return True
    except ValueError:
        return False


@bp.route("/benchmarks/export.csv")
def export_csv():
    rows = svc.list_benchmarks(db(), 500)
    cols = ["id", "created_at", "kind", "algorithm", "seed", "board_w", "board_h", "wrap", "scenarios",
            "success_rate", "safe_rate", "avg_time_ms", "avg_nodes", "avg_path_len", "avg_score",
            "avg_steps", "completion_rate", "provenance", "details"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:
        w.writerow([_safe_cell(r.get(c)) for c in cols])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=ai-snake-arena-benchmarks.csv"})
