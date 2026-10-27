import json, os, pathlib, sqlite3, tempfile, unittest
from storage.db import Database
from storage.legacy import migrate_legacy_highscore
from storage.highscore import HighScoreFile
from storage.desktop import DesktopRecorder
from storage import services as svc
from webapp import create_app
from snake_core import GameState, GameConfig, choose_move

ROOT = pathlib.Path(__file__).resolve().parent.parent
G1, G2, G3 = "guest-aaaaaaaa", "guest-bbbbbbbb", "guest-cccccccc"


def payload(**kw):
    p = dict(mode="manual", difficulty="normal", board_w=25, board_h=12, wrap=False, obstacles=False, score=5,
             apples_collected=5, steps=60, duration_ms=9000, outcome="wall")
    p.update(kw)
    return p


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dbpath = os.path.join(self.tmp.name, "t.db")
        self.hs = os.path.join(self.tmp.name, "highscore.txt")
        self.app = create_app({"ARENA_DB_PATH": self.dbpath, "ARENA_LEGACY_HIGHSCORE": self.hs, "TESTING": True,
                               "ARENA_CORS_ORIGINS": ["http://allowed.example"]})
        self.c = self.app.test_client()
        self.db = self.app.extensions["arena_db"]

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, body, guest=G1, path="/api/v1/matches"):
        return self.c.post(path, json=body, headers={"X-Guest-Id": guest} if guest else {})

    def status(self, url):
        r = self.c.get(url)
        code = r.status_code
        r.close()
        return code

    def get(self, path, guest=G1):
        return self.c.get(path, headers={"X-Guest-Id": guest} if guest else {})


class DatabaseTests(Base):
    def test_migrations_idempotent_and_versioned(self):
        d = Database(os.path.join(self.tmp.name, "fresh.db"))
        self.assertEqual(d.init(), [1])
        self.assertEqual(d.init(), [])
        with d.read() as c:
            self.assertEqual([r[0] for r in c.execute("SELECT version FROM schema_migrations")], [1])
            names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"players", "matches", "benchmark_runs", "settings", "meta"} <= names)

    def test_transaction_rolls_back_on_error(self):
        with self.assertRaises(RuntimeError):
            with self.db.transaction() as c:
                svc.get_or_create_player(c, G1)
                raise RuntimeError("boom")
        with self.db.read() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM players").fetchone()[0], 0)

    def test_sql_injection_is_inert(self):
        evil = "x'); DROP TABLE matches;--"
        with self.assertRaises(svc.ValidationError):
            with self.db.transaction() as c:
                svc.get_or_create_player(c, evil)
        r = self.post(payload(), guest=G1, path="/api/v1/matches")
        self.assertEqual(r.status_code, 201)
        r = self.c.put("/api/v1/settings", json={"name": "Robert'); DROP TABLE players;--"[:20]}, headers={"X-Guest-Id": G1})
        self.assertEqual(r.status_code, 200)
        with self.db.read() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM matches").fetchone()[0], 1)


class LegacyTests(Base):
    def test_migrates_once_preserves_file(self):
        pathlib.Path(self.hs).write_text("43")
        self.assertEqual(migrate_legacy_highscore(self.db, self.hs), {"status": "migrated", "score": 43})
        self.assertEqual(migrate_legacy_highscore(self.db, self.hs)["status"], "already_migrated")
        self.assertEqual(pathlib.Path(self.hs).read_text(), "43")
        lb = self.get("/api/v1/leaderboard").get_json()["data"]["entries"]
        self.assertEqual([(e["score"], e["trust"]) for e in lb], [(43, "legacy_import")])

    def test_invalid_and_missing(self):
        self.assertEqual(migrate_legacy_highscore(self.db, self.hs)["status"], "missing")
        for bad in ("abc", "-5", "99999999999", ""):
            pathlib.Path(self.hs).write_text(bad)
            self.assertEqual(migrate_legacy_highscore(self.db, self.hs)["status"], "invalid", bad)
        with self.db.read() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM matches").fetchone()[0], 0)

    def test_the_users_real_highscore_file_imports(self):
        d = Database(os.path.join(self.tmp.name, "real.db")); d.init()
        r = migrate_legacy_highscore(d, str(ROOT / "highscore.txt"))
        self.assertEqual(r["status"], "migrated")
        self.assertEqual(r["score"], int((ROOT / "highscore.txt").read_text()))

    def test_highscore_file_roundtrip_and_atomicity(self):
        h = HighScoreFile(self.hs)
        self.assertEqual(h.read(), 0)
        self.assertTrue(h.update_if_higher(7)); self.assertFalse(h.update_if_higher(3))
        self.assertEqual(h.read(), 7)
        pathlib.Path(self.hs).write_text("garbage"); self.assertEqual(h.read(), 0)
        self.assertEqual([p for p in os.listdir(self.tmp.name) if p.startswith(".hs_")], [])

    def test_desktop_recorder_persists_and_survives_restart(self):
        pathlib.Path(self.hs).write_text("12")
        rec = DesktopRecorder(self.dbpath, self.hs, self.tmp.name)
        self.assertTrue(rec.ok and rec.record(payload(score=9, apples_collected=9, steps=100, duration_ms=15000)))
        rec2 = DesktopRecorder(self.dbpath, self.hs, self.tmp.name)
        self.assertEqual(rec2.guest_id, rec.guest_id)
        with self.db.read() as c:
            rows = c.execute("SELECT source, trust, score FROM matches ORDER BY id").fetchall()
        self.assertEqual([tuple(r) for r in rows], [("legacy", "legacy_import", 12), ("desktop", "local_desktop", 9)])


class ApiTests(Base):
    def test_health_and_headers(self):
        r = self.c.get("/api/v1/health")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])

    def test_submit_validation_and_codes(self):
        self.assertEqual(self.post(payload()).status_code, 201)
        self.assertEqual(self.post(payload(), guest=None).status_code, 400)
        self.assertEqual(self.post(payload(), guest="bad id!").status_code, 400)
        self.assertEqual(self.c.post("/api/v1/matches", data="nope", headers={"X-Guest-Id": G1}).status_code, 400)
        for bad in (dict(outcome="cheated"), dict(mode="god"), dict(difficulty="x"), dict(score=-1), dict(score=1000, apples_collected=5),
                    dict(apples_collected=99), dict(duration_ms=10), dict(board_w=500), dict(score="9"), dict(mode="ai", algorithm="magic")):
            r = self.post(payload(**bad))
            self.assertEqual(r.status_code, 422, bad)
            self.assertFalse(r.get_json()["ok"])
            self.assertIn("details", r.get_json()["error"])
        self.assertEqual(self.get("/api/v1/nope").status_code, 404)
        self.assertEqual(self.get("/api/v1/nope").get_json()["error"]["code"], "not_found")
        self.assertEqual(self.c.delete("/api/v1/matches").status_code, 405)

    def test_idempotent_submission_and_trust_label(self):
        p = payload(client_match_id="match-0001-abcd")
        a, b = self.post(p), self.post(p)
        self.assertEqual((a.status_code, b.status_code), (201, 200))
        self.assertEqual(a.get_json()["data"]["verification"], "client_reported")
        self.assertEqual(self.get("/api/v1/matches").get_json()["data"]["total"], 1)

    def test_errors_do_not_leak_internals(self):
        import webapp.api as api
        orig = svc.player_stats
        svc.player_stats = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret /etc/path detail"))
        try:
            self.app.config["PROPAGATE_EXCEPTIONS"] = False
            self.app.testing = False
            r = self.get("/api/v1/players/me/stats")
        finally:
            svc.player_stats = orig
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("secret", r.get_data(as_text=True))

    def test_leaderboard_ordering_filters_best_per_player(self):
        self.post(payload(score=10, apples_collected=10, steps=100, duration_ms=20000), G1)
        self.post(payload(score=30, apples_collected=30, steps=300, duration_ms=60000), G1)
        self.post(payload(score=20, apples_collected=20, steps=200, duration_ms=40000), G2)
        self.post(payload(score=20, apples_collected=20, steps=200, duration_ms=40000, difficulty="hard"), G3)
        self.post(payload(score=99, apples_collected=99, steps=500, duration_ms=100000, mode="ai", algorithm="adaptive", difficulty="hard"), G3)
        e = self.get("/api/v1/leaderboard").get_json()["data"]["entries"]
        self.assertEqual([(x["rank"], x["score"]) for x in e], [(1, 99), (2, 30), (3, 20)])
        e = self.get("/api/v1/leaderboard?difficulty=hard&mode=manual").get_json()["data"]["entries"]
        self.assertEqual([x["score"] for x in e], [20])
        self.assertEqual(self.get("/api/v1/leaderboard?difficulty=zzz").status_code, 400)
        # ties: earlier submission wins
        self.post(payload(score=20, apples_collected=20, steps=200, duration_ms=40000), "guest-dddddddd")
        e = self.get("/api/v1/leaderboard?difficulty=normal").get_json()["data"]["entries"]
        self.assertEqual([x["score"] for x in e], [30, 20, 20])

    def test_stats_empty_then_real(self):
        self.assertEqual(self.get("/api/v1/players/me/stats").get_json()["data"]["total_matches"], 0)
        self.post(payload(score=4, apples_collected=4, steps=50, duration_ms=8000, outcome="self"))
        self.post(payload(score=8, apples_collected=8, steps=90, duration_ms=12000, outcome="won", difficulty="hard"))
        d = self.get("/api/v1/players/me/stats").get_json()["data"]
        self.assertEqual((d["total_matches"], d["best_score"], d["average_score"], d["apples_collected"], d["total_play_time_ms"]), (2, 8, 6.0, 12, 20000))
        self.assertEqual(d["difficulty_distribution"], {"normal": 1, "hard": 1})
        self.assertEqual(d["boards_completed"], 1)
        self.assertEqual([p["score"] for p in d["score_progression"]], [4, 8])
        self.assertEqual(self.get("/api/v1/players/me/stats", G2).get_json()["data"]["total_matches"], 0)

    def test_algorithm_metrics_weighted_and_none_when_undefined(self):
        ai = lambda dec, t, n, l, pf: payload(mode="ai", algorithm="astar", steps=100, duration_ms=20000,
                                              ai_metrics=dict(decisions=dec, total_time_ms=t, total_nodes=n, total_path_len=l, paths_found=pf))
        self.post(ai(10, 5.0, 100, 50, 10)); self.post(ai(30, 15.0, 600, 90, 20))
        self.post(payload(mode="ai", algorithm="hamiltonian", steps=50, duration_ms=9000))
        m = {x["algorithm"]: x for x in self.get("/api/v1/metrics/algorithms").get_json()["data"]["played_matches"]}
        self.assertAlmostEqual(m["astar"]["avg_decision_ms"], 0.5)
        self.assertAlmostEqual(m["astar"]["avg_nodes_explored"], 17.5)
        self.assertAlmostEqual(m["astar"]["path_success_rate"], 0.75)
        self.assertAlmostEqual(m["astar"]["avg_path_length"], 140 / 30, places=1)
        self.assertIsNone(m["hamiltonian"]["avg_decision_ms"])
        self.assertEqual(self.post(ai(10, 5.0, 100, 50, 11)).status_code, 422)

    def test_settings_roundtrip_and_validation(self):
        self.assertEqual(self.get("/api/v1/settings").get_json()["data"], {})
        r = self.c.put("/api/v1/settings", json={"difficulty": "hard", "volume": 0.3, "wrap": True}, headers={"X-Guest-Id": G1})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.get("/api/v1/settings").get_json()["data"]["difficulty"], "hard")
        for bad in ({"difficulty": "x"}, {"volume": 5}, {"hack": 1}, {"wrap": "yes"}):
            self.assertEqual(self.c.put("/api/v1/settings", json=bad, headers={"X-Guest-Id": G1}).status_code, 422)

    def test_cors_only_for_configured_origins(self):
        ok = self.c.get("/api/v1/health", headers={"Origin": "http://allowed.example"})
        no = self.c.get("/api/v1/health", headers={"Origin": "http://evil.example"})
        self.assertEqual(ok.headers.get("Access-Control-Allow-Origin"), "http://allowed.example")
        self.assertNotIn("Access-Control-Allow-Origin", no.headers)

    def test_benchmarks_reproducible_exportable_and_validated(self):
        body = {"kind": "pathfinding", "seed": 5, "scenarios": 20, "board_w": 15, "board_h": 10, "snake_len": 6}
        a = self.c.post("/api/v1/benchmarks/run", json=body).get_json()["data"]["results"]
        b = self.c.post("/api/v1/benchmarks/run", json=body).get_json()["data"]["results"]
        key = lambda rs: [(r["algorithm"], r["success_rate"], r["safe_rate"], r["avg_nodes"], r["avg_path_len"]) for r in rs]
        self.assertEqual(key(a), key(b))
        by = {r["algorithm"]: r for r in a}
        self.assertEqual(by["bfs"]["avg_path_len"], by["astar"]["avg_path_len"])
        self.assertLessEqual(by["astar"]["avg_nodes"], by["dijkstra"]["avg_nodes"])
        self.assertEqual(len(self.get("/api/v1/benchmarks").get_json()["data"]), 6)
        csv_text = self.c.get("/api/v1/benchmarks/export.csv")
        self.assertEqual(csv_text.mimetype, "text/csv")
        self.assertEqual(len(csv_text.get_data(as_text=True).strip().splitlines()), 7)
        self.assertIn("server python engine", csv_text.get_data(as_text=True))
        for bad in ({"scenarios": 10**6}, {"board_w": 2}, {"kind": "x"}, {"seed": -1}):
            self.assertEqual(self.c.post("/api/v1/benchmarks/run", json=bad).status_code, 422, bad)
        s = self.c.post("/api/v1/benchmarks/run", json={"kind": "survival", "seed": 2, "games": 2, "max_steps": 150}).get_json()["data"]["results"]
        self.assertEqual({r["algorithm"] for r in s}, {"astar", "bfs", "dijkstra", "adaptive", "hamiltonian"})
        self.assertEqual(self.c.post("/api/v1/benchmarks/run", json={"kind": "survival", "games": 20, "max_steps": 2000}).status_code, 422)


class IntegrationTests(Base):
    def test_play_full_game_save_and_see_in_dashboard(self):
        s = GameState(GameConfig(width=12, height=8, difficulty="normal", seed=11, stall_limit=300))
        metrics = dict(decisions=0, total_time_ms=0.0, total_nodes=0, total_path_len=0, paths_found=0)
        while s.alive and s.steps < 400:
            d = choose_move(s.situation(), "adaptive")
            metrics["decisions"] += 1; metrics["total_time_ms"] += d.time_ms; metrics["total_nodes"] += d.explored
            if d.found: metrics["paths_found"] += 1; metrics["total_path_len"] += d.path_length
            if d.direction: s.set_direction(d.direction)
            s.step()
        self.assertGreater(s.score, 0)
        body = payload(mode="ai", algorithm="adaptive", board_w=12, board_h=8, score=s.score, apples_collected=s.apples, steps=s.steps,
                       duration_ms=int(s.steps * 125), outcome=s.outcome or "stalled", ai_metrics=metrics)
        r = self.post(body)
        self.assertEqual(r.status_code, 201, r.get_json())
        dash = self.get("/api/v1/players/me/stats").get_json()["data"]
        self.assertEqual((dash["total_matches"], dash["best_score"]), (1, s.score))
        self.assertEqual(self.get("/api/v1/leaderboard").get_json()["data"]["entries"][0]["score"], s.score)
        self.assertEqual(self.get("/api/v1/matches").get_json()["data"]["items"][0]["algorithm"], "adaptive")
        self.assertEqual(self.get("/dashboard").status_code, 200)

    def test_all_pages_render_with_nav_and_no_user_data(self):
        for p in ("/", "/play", "/dashboard", "/leaderboard", "/history", "/benchmark", "/settings", "/offline"):
            r = self.c.get(p)
            self.assertEqual(r.status_code, 200, p)
            t = r.get_data(as_text=True)
            self.assertIn('rel="manifest"', t); self.assertIn("viewport-fit=cover", t)


class PwaTests(Base):
    def test_manifest_icons_and_service_worker(self):
        m = self.c.get("/manifest.webmanifest")
        self.assertEqual(m.mimetype, "application/manifest+json")
        man = m.get_json()
        for k in ("name", "short_name", "start_url", "display", "icons", "theme_color", "background_color"):
            self.assertIn(k, man)
        self.assertEqual(man["display"], "standalone")
        sizes = {i["sizes"] for i in man["icons"]}
        self.assertTrue({"192x192", "512x512"} <= sizes)
        for i in man["icons"]:
            self.assertEqual(self.status(i["src"]), 200, i["src"])
        sw = self.c.get("/sw.js")
        self.assertEqual(sw.status_code, 200)
        self.assertEqual(sw.headers["Cache-Control"], "no-cache")
        text = sw.get_data(as_text=True)
        self.assertNotIn("__VERSION__", text); self.assertNotIn("__PAGES__", text); self.assertNotIn("__ASSETS__", text)
        import re
        pages = json.loads(re.search(r"const PAGES = (\[.*?\]);", text).group(1))
        assets = json.loads(re.search(r"const ASSETS = (\[.*?\]);", text).group(1))
        self.assertIn("/play", pages); self.assertIn("/offline", pages)
        for need in ("/static/js/engine.js", "/static/js/ai.js", "/static/js/game.js", "/static/css/app.css", "/static/icons/icon-192.png"):
            self.assertIn(need, assets)
        for url in pages + assets + ["/manifest.webmanifest"]:        # addAll() fails if any precache URL 404s
            self.assertEqual(self.status(url), 200, url)
        self.assertNotIn("/api/", "".join(pages + assets))

    def test_cache_version_changes_when_assets_change(self):
        from webapp import static_version
        v1 = static_version()
        extra = pathlib.Path(__file__).resolve().parent.parent / "webapp" / "static" / "css" / "_probe.css"
        try:
            extra.write_text("/*x*/")
            self.assertNotEqual(v1, static_version())
        finally:
            extra.unlink()
        self.assertEqual(v1, static_version())


if __name__ == "__main__":
    unittest.main()
