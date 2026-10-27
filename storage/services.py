"""Business logic over the database: players, matches, stats, leaderboard, settings, benchmarks."""
from __future__ import annotations
import json
import re
import sqlite3
from snake_core.engine import DIFFICULTIES
from snake_core.ai import STRATEGIES

GUEST_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MATCH_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
OUTCOMES = ("wall", "self", "obstacle", "won", "stalled", "quit")
MODES = ("manual", "ai")
MAX_SCORE = 100_000


class ValidationError(Exception):
    def __init__(self, errors: dict):
        super().__init__("validation failed")
        self.errors = errors


def clean_name(name) -> str:
    if not isinstance(name, str):
        return "Guest"
    name = re.sub(r"[\x00-\x1f\x7f<>]", "", name).strip()[:20]
    return name or "Guest"


def get_or_create_player(conn, guest_id: str, display_name=None) -> int:
    if not isinstance(guest_id, str) or not GUEST_RE.match(guest_id):
        raise ValidationError({"guest_id": "must be 8-64 chars of A-Z a-z 0-9 _ -"})
    row = conn.execute("SELECT id, display_name FROM players WHERE guest_id = ?", (guest_id,)).fetchone()
    if row:
        if display_name is not None and clean_name(display_name) != row["display_name"]:
            conn.execute("UPDATE players SET display_name = ? WHERE id = ?", (clean_name(display_name), row["id"]))
        return row["id"]
    cur = conn.execute("INSERT INTO players(guest_id, display_name) VALUES (?, ?)",
                       (guest_id, clean_name(display_name)))
    return cur.lastrowid


def _int(p, key, lo, hi, errors, default=None):
    v = p.get(key, default)
    if isinstance(v, bool) or not isinstance(v, int) or not (lo <= v <= hi):
        errors[key] = f"integer {lo}..{hi} required"
        return None
    return v


def validate_match(p) -> dict:
    """Validate and plausibility-check a client-reported match. Never marks it server-verified."""
    if not isinstance(p, dict):
        raise ValidationError({"body": "JSON object required"})
    e = {}
    mode = p.get("mode")
    if mode not in MODES:
        e["mode"] = f"one of {MODES}"
    algo = p.get("algorithm")
    if mode == "ai" and algo not in STRATEGIES:
        e["algorithm"] = f"one of {STRATEGIES}"
    if mode == "manual":
        algo = None
    diff = p.get("difficulty")
    if diff not in DIFFICULTIES:
        e["difficulty"] = f"one of {tuple(DIFFICULTIES)}"
    outcome = p.get("outcome")
    if outcome not in OUTCOMES:
        e["outcome"] = f"one of {OUTCOMES}"
    cmid = p.get("client_match_id")
    if cmid is not None and (not isinstance(cmid, str) or not MATCH_ID_RE.match(cmid)):
        e["client_match_id"] = "8-64 chars of A-Z a-z 0-9 _ -"
    w, h = _int(p, "board_w", 5, 60, e), _int(p, "board_h", 5, 60, e)
    score = _int(p, "score", 0, MAX_SCORE, e)
    apples = _int(p, "apples_collected", 0, 3600, e)
    steps = _int(p, "steps", 0, 1_000_000, e)
    dur = _int(p, "duration_ms", 0, 10**9, e)
    for k in ("wrap", "obstacles"):
        if not isinstance(p.get(k, False), bool):
            e[k] = "boolean required"
    ai = p.get("ai_metrics") or {}
    ai_vals = dict(ai_decisions=0, ai_total_time_ms=0.0, ai_total_nodes=0, ai_total_path_len=0, ai_paths_found=0)
    if mode == "ai":
        if not isinstance(ai, dict):
            e["ai_metrics"] = "object required"
        else:
            try:
                dec = int(ai.get("decisions", 0)); pf = int(ai.get("paths_found", 0))
                tt = float(ai.get("total_time_ms", 0)); tn = int(ai.get("total_nodes", 0))
                tl = int(ai.get("total_path_len", 0))
                if min(dec, pf, tt, tn, tl) < 0 or pf > dec or dec > (steps or 0) + 1 or tt > 3.6e6:
                    raise ValueError
                ai_vals = dict(ai_decisions=dec, ai_total_time_ms=tt, ai_total_nodes=tn,
                               ai_total_path_len=tl, ai_paths_found=pf)
            except (TypeError, ValueError):
                e["ai_metrics"] = "inconsistent or invalid AI metrics"
    if not e:  # plausibility: reject impossible combinations (not a proof of honesty)
        if apples > steps:
            e["apples_collected"] = "cannot exceed steps"
        if apples > w * h:
            e["apples_collected"] = "cannot exceed board cells"
        if score > apples * 6:
            e["score"] = "exceeds the maximum reachable for the apples collected"
        if dur < steps * 15:
            e["duration_ms"] = "too short for the number of steps"
    if e:
        raise ValidationError(e)
    return dict(client_match_id=cmid, mode=mode, algorithm=algo, difficulty=diff, board_w=w, board_h=h,
                wrap=int(p.get("wrap", False)), obstacles=int(p.get("obstacles", False)), score=score,
                apples_collected=apples, steps=steps, duration_ms=dur, outcome=outcome, **ai_vals)


def save_match(db, guest_id, payload, source="web", trust="client_reported", display_name=None):
    """Validate + persist in one transaction. Idempotent on client_match_id. Returns (row, created)."""
    m = validate_match(payload)
    with db.transaction() as conn:
        if m["client_match_id"]:
            dup = conn.execute("SELECT * FROM matches WHERE client_match_id = ?", (m["client_match_id"],)).fetchone()
            if dup:
                return dict(dup), False
        pid = get_or_create_player(conn, guest_id, display_name)
        cols = list(m) + ["player_id", "source", "trust"]
        vals = list(m.values()) + [pid, source, trust]
        cur = conn.execute(f"INSERT INTO matches({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
        row = conn.execute("SELECT * FROM matches WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row), True


def match_history(db, guest_id, limit=20, offset=0):
    limit, offset = max(1, min(int(limit), 100)), max(0, int(offset))
    with db.read() as c:
        p = c.execute("SELECT id FROM players WHERE guest_id = ?", (guest_id,)).fetchone()
        if not p:
            return {"total": 0, "items": []}
        total = c.execute("SELECT COUNT(*) FROM matches WHERE player_id = ?", (p["id"],)).fetchone()[0]
        rows = c.execute("SELECT * FROM matches WHERE player_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                         (p["id"], limit, offset)).fetchall()
    return {"total": total, "items": [dict(r) for r in rows]}


def player_stats(db, guest_id):
    with db.read() as c:
        p = c.execute("SELECT id, display_name FROM players WHERE guest_id = ?", (guest_id,)).fetchone()
        empty = {"total_matches": 0, "player": None}
        if not p:
            return empty
        pid = p["id"]
        t = c.execute("""SELECT COUNT(*) n, MAX(score) best, AVG(score) avg, SUM(apples_collected) apples,
                         SUM(duration_ms) dur, AVG(duration_ms) avgdur, SUM(outcome='won') wins
                         FROM matches WHERE player_id = ?""", (pid,)).fetchone()
        if not t["n"]:
            return empty
        recent = [dict(r) for r in c.execute("SELECT * FROM matches WHERE player_id = ? ORDER BY id DESC LIMIT 10", (pid,))]
        prog = [dict(r) for r in c.execute("""SELECT id, score, duration_ms, created_at, mode FROM
                 (SELECT * FROM matches WHERE player_id = ? ORDER BY id DESC LIMIT 30) ORDER BY id ASC""", (pid,))]
        diff = {r["difficulty"]: r["n"] for r in c.execute(
            "SELECT difficulty, COUNT(*) n FROM matches WHERE player_id = ? GROUP BY difficulty", (pid,))}
        modes = {r["mode"]: r["n"] for r in c.execute(
            "SELECT mode, COUNT(*) n FROM matches WHERE player_id = ? GROUP BY mode", (pid,))}
        outcomes = {r["outcome"]: r["n"] for r in c.execute(
            "SELECT outcome, COUNT(*) n FROM matches WHERE player_id = ? GROUP BY outcome", (pid,))}
    return {"player": p["display_name"], "total_matches": t["n"], "best_score": t["best"],
            "average_score": round(t["avg"], 2), "apples_collected": t["apples"],
            "total_play_time_ms": t["dur"], "average_duration_ms": round(t["avgdur"], 1),
            "boards_completed": t["wins"], "completion_rate": round(t["wins"] / t["n"], 4),
            "score_progression": prog, "difficulty_distribution": diff, "mode_distribution": modes,
            "outcome_distribution": outcomes, "recent_matches": recent,
            "note": "All figures are client-reported and not server-verified."}


def leaderboard(db, difficulty=None, mode=None, limit=10):
    limit = max(1, min(int(limit), 50))
    flt, args = "", []
    if difficulty:
        flt += " AND {a}.difficulty = ?"; args.append(difficulty)
    if mode:
        flt += " AND {a}.mode = ?"; args.append(mode)
    sql = f"""SELECT p.display_name, m.score, m.mode, m.algorithm, m.difficulty, m.source, m.trust, m.created_at
      FROM matches m JOIN players p ON p.id = m.player_id
      WHERE m.id = (SELECT m2.id FROM matches m2 WHERE m2.player_id = m.player_id {flt.format(a='m2')}
                    ORDER BY m2.score DESC, m2.id ASC LIMIT 1) {flt.format(a='m')}
      ORDER BY m.score DESC, m.id ASC LIMIT ?"""
    with db.read() as c:
        rows = c.execute(sql, args + args + [limit]).fetchall()
    return [dict(r, rank=i + 1) for i, r in enumerate(rows)]


def algorithm_metrics(db):
    with db.read() as c:
        rows = c.execute("""SELECT algorithm, COUNT(*) matches, AVG(score) avg_score, AVG(duration_ms) avg_duration_ms,
            SUM(ai_decisions) d, SUM(ai_total_time_ms) t, SUM(ai_total_nodes) n, SUM(ai_total_path_len) l,
            SUM(ai_paths_found) pf FROM matches WHERE mode = 'ai' AND algorithm IS NOT NULL
            GROUP BY algorithm ORDER BY algorithm""").fetchall()
        bench = c.execute("""SELECT * FROM benchmark_runs WHERE id IN
            (SELECT MAX(id) FROM benchmark_runs GROUP BY kind, algorithm) ORDER BY kind, algorithm""").fetchall()
    played = [dict(algorithm=r["algorithm"], matches=r["matches"], avg_score=round(r["avg_score"], 2),
                   avg_duration_ms=round(r["avg_duration_ms"]),
                   decisions=r["d"],
                   avg_decision_ms=round(r["t"] / r["d"], 4) if r["d"] else None,
                   avg_nodes_explored=round(r["n"] / r["d"], 2) if r["d"] else None,
                   path_success_rate=round(r["pf"] / r["d"], 4) if r["d"] else None,
                   avg_path_length=round(r["l"] / r["pf"], 2) if r["pf"] else None) for r in rows]
    return {"played_matches": played, "benchmarks": [dict(b) for b in bench],
            "provenance": {"played_matches": "client-reported by browser/desktop games",
                           "benchmarks": "measured by the server's Python engine; see benchmark rows"}}


SETTING_RULES = {
    "difficulty": lambda v: v in DIFFICULTIES, "board": lambda v: v in ("small", "classic", "large"),
    "mode": lambda v: v in MODES, "strategy": lambda v: v in STRATEGIES,
    "base": lambda v: v in ("astar", "bfs", "dijkstra"),
    "wrap": lambda v: isinstance(v, bool), "obstacles": lambda v: isinstance(v, bool),
    "powerups": lambda v: isinstance(v, bool), "sound": lambda v: isinstance(v, bool),
    "showPath": lambda v: isinstance(v, bool), "theme": lambda v: v in ("dark", "light"),
    "volume": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1,
    "speed": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and 0.5 <= v <= 2,
    "name": lambda v: isinstance(v, str) and len(v) <= 20,
}


def validate_settings(data) -> dict:
    if not isinstance(data, dict):
        raise ValidationError({"body": "JSON object required"})
    bad = {k: "invalid value" if k in SETTING_RULES else "unknown setting"
           for k, v in data.items() if k not in SETTING_RULES or not SETTING_RULES[k](v)}
    if bad:
        raise ValidationError(bad)
    return dict(data)


def get_settings(db, guest_id) -> dict:
    with db.read() as c:
        r = c.execute("SELECT s.data FROM settings s JOIN players p ON p.id = s.player_id WHERE p.guest_id = ?",
                      (guest_id,)).fetchone()
    return json.loads(r["data"]) if r else {}


def put_settings(db, guest_id, data) -> dict:
    clean = validate_settings(data)
    with db.transaction() as c:
        pid = get_or_create_player(c, guest_id, clean.get("name"))
        c.execute("""INSERT INTO settings(player_id, data) VALUES (?, ?)
                     ON CONFLICT(player_id) DO UPDATE SET data = excluded.data,
                     updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')""", (pid, json.dumps(clean)))
    return clean


def save_benchmark_rows(db, rows: list) -> list:
    cols = ["kind", "algorithm", "seed", "board_w", "board_h", "wrap", "scenarios", "success_rate", "safe_rate",
            "avg_time_ms", "avg_nodes", "avg_path_len", "avg_score", "avg_steps", "completion_rate",
            "details", "provenance"]
    ids = []
    with db.transaction() as c:
        for r in rows:
            r = dict(r, details=json.dumps(r.get("details") or {}))
            cur = c.execute(f"INSERT INTO benchmark_runs({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                            [r.get(k) for k in cols])
            ids.append(cur.lastrowid)
    return ids


def list_benchmarks(db, limit=100):
    with db.read() as c:
        rows = c.execute("SELECT * FROM benchmark_runs ORDER BY id DESC LIMIT ?", (max(1, min(int(limit), 500)),)).fetchall()
    return [dict(r) for r in rows]
