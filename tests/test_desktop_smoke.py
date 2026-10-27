"""Smoke test of desktop/app.py wiring using a stub pygame (real pygame is not required for this test).
It proves the state machine, AI loop, persistence and recording run without errors; it does NOT validate
real pygame rendering."""
import os, sys, tempfile, types, unittest
from unittest import mock


def make_stub():
    pg = mock.MagicMock(name="pygame")
    keys = ["QUIT", "KEYDOWN", "K_ESCAPE", "K_BACKSPACE", "K_m", "K_a", "K_b", "K_d", "K_s", "K_h", "K_p", "K_SPACE", "K_r", "K_RETURN",
            "K_KP_ENTER", "K_v", "K_n", "K_PLUS", "K_EQUALS", "K_KP_PLUS", "K_MINUS", "K_KP_MINUS", "K_UP", "K_DOWN", "K_LEFT", "K_RIGHT"]
    for i, k in enumerate(keys):
        setattr(pg, k, 1000 + i)
    pg.SRCALPHA = 65536
    return pg


class DesktopSmoke(unittest.TestCase):
    def test_loop_plays_records_and_quits(self):
        pg = make_stub()
        tmp = tempfile.mkdtemp()
        os.environ["ARENA_DB_PATH"] = os.path.join(tmp, "d.db")
        sys.modules["pygame"] = pg
        for m in [k for k in sys.modules if k.startswith("desktop")]:
            del sys.modules[m]
        import desktop.app as app
        ev = lambda k: types.SimpleNamespace(type=pg.KEYDOWN, key=k)
        frames = {"n": 0}

        def get_events():
            frames["n"] += 1
            if frames["n"] == 3: return [ev(pg.K_s)]                  # switch to adaptive
            if frames["n"] == 5: return [ev(pg.K_p)]                  # pause
            if frames["n"] == 6: return [ev(pg.K_p)]                  # resume
            if frames["n"] == 8: return [ev(pg.K_m), ev(pg.K_UP)]     # to manual and steer
            if frames["n"] == 10: return [ev(pg.K_m)]                 # back to AI
            if frames["n"] == 400: return [ev(pg.K_ESCAPE)]
            return []
        pg.event.get.side_effect = get_events
        pg.time.Clock.return_value.tick.return_value = 200            # 200 ms per frame -> fast simulated time
        a = app.App(skip_menu=True)
        a.hs.path = os.path.join(tmp, "highscore.txt")
        a.s.difficulty = "normal"
        self.assertEqual(a.play(), "quit")
        self.assertGreater(a.high, 0)
        self.assertTrue(a.recorder.ok)
        with open(a.hs.path) as f:
            self.assertEqual(f.read(), str(a.high))
        # exercise the game-over -> database path directly
        st = a.new_state()
        st.score, st.apples, st.steps, st.outcome = 7, 7, 80, "wall"
        a.s.mode = "manual"
        msg = a.record(st, 12000, dict(decisions=0, total_time_ms=0.0, total_nodes=0, total_path_len=0, paths_found=0))
        self.assertIn("saved", msg)
        with a.recorder.db.read() as c:
            row = c.execute("SELECT source, trust, score FROM matches WHERE score = 7").fetchone()
        self.assertEqual(tuple(row), ("desktop", "local_desktop", 7))


if __name__ == "__main__":
    unittest.main()
