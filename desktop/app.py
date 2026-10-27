"""Pygame front end. Rules/AI come from snake_core; persistence from storage. This file only wires
input -> simulation -> rendering, with a fixed-timestep simulation decoupled from the 60 fps render loop."""
from __future__ import annotations
import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame                                     # noqa: E402
from snake_core import GameConfig, GameState, choose_move, DIFFICULTIES, BOARD_PRESETS, STRATEGIES   # noqa: E402
from storage.highscore import HighScoreFile       # noqa: E402
from storage.desktop import DesktopRecorder       # noqa: E402
from .audio import Audio                          # noqa: E402
from .render import Renderer                      # noqa: E402

PANEL_H = 84
OUTCOMES = {"wall": "Hit the wall", "self": "Ran into itself", "obstacle": "Hit an obstacle",
            "won": "Board completed!", "stalled": "AI stalled"}


@dataclass
class Settings:
    # defaults reproduce the original game: AI on, A*, constant 8 ticks/s, 25x12, no extras
    mode: str = "ai"
    strategy: str = "astar"
    base: str = "astar"
    difficulty: str = "classic"
    board: str = "classic"
    wrap: bool = False
    obstacles: bool = True
    powerups: bool = True
    speed: float = 1.0
    show_path: bool = True
    muted: bool = False


MENU = [("Mode", "mode", ["ai", "manual"]), ("Strategy", "strategy", list(STRATEGIES)),
        ("Adaptive base search", "base", ["astar", "bfs", "dijkstra"]), ("Difficulty", "difficulty", list(DIFFICULTIES)),
        ("Board", "board", list(BOARD_PRESETS)), ("Wrap-around walls", "wrap", [False, True]),
        ("Obstacles", "obstacles", [True, False]), ("Bonus apples / power-ups", "powerups", [True, False]),
        ("Speed x", "speed", [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]), ("Show AI path", "show_path", [True, False]),
        ("Sound muted", "muted", [False, True])]


class App:
    def __init__(self, skip_menu=False):
        pygame.mixer.pre_init(22050, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("Crawling Cobras - AI Snake Arena")
        self.s = Settings()
        self.hs = HighScoreFile(ROOT / "highscore.txt")
        self.high = self.hs.read()
        self.recorder = DesktopRecorder(os.environ.get("ARENA_DB_PATH", ROOT / "data" / "arena.db"),
                                        ROOT / "highscore.txt", ROOT / "data")
        self.audio = Audio(pygame, ROOT / "game_over.mp3")
        self.skip_menu = skip_menu
        self.clock = pygame.time.Clock()
        self.screen = None

    # ---------- setup ----------
    def open_window(self):
        w, h = BOARD_PRESETS[self.s.board]
        cell = max(16, min(40, 1100 // w, 620 // h))
        self.screen = pygame.display.set_mode((w * cell, h * cell + PANEL_H))
        self.r = Renderer(pygame, self.screen, cell, w, h, PANEL_H)

    def new_state(self):
        w, h = BOARD_PRESETS[self.s.board]
        return GameState(GameConfig(width=w, height=h, wrap=self.s.wrap, difficulty=self.s.difficulty,
                                    obstacles=self.s.obstacles, powerups=self.s.powerups))

    # ---------- menu ----------
    def menu(self) -> bool:
        w, h = 900, 560
        self.screen = pygame.display.set_mode((w, h))
        self.r = Renderer(pygame, self.screen, 40, w // 40, (h - PANEL_H) // 40, PANEL_H)
        self.r.width = w
        idx = 0
        while True:
            self.clock.tick(30)
            for e in pygame.event.get():
                if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                    return False
                if e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_UP:
                        idx = (idx - 1) % len(MENU)
                    elif e.key == pygame.K_DOWN:
                        idx = (idx + 1) % len(MENU)
                    elif e.key in (pygame.K_LEFT, pygame.K_RIGHT):
                        _, key, opts = MENU[idx]
                        cur = opts.index(getattr(self.s, key)) if getattr(self.s, key) in opts else 0
                        setattr(self.s, key, opts[(cur + (1 if e.key == pygame.K_RIGHT else -1)) % len(opts)])
                    elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        return True
            self.r.menu([(label, getattr(self.s, key)) for label, key, _ in MENU], idx)
            pygame.display.flip()

    # ---------- one game session ----------
    def play(self) -> str:
        """Returns 'menu', 'quit'."""
        self.open_window()
        self.audio.muted = self.s.muted
        st, phase, acc, sim_ms = self.new_state(), "running", 0.0, 0.0
        dec = None
        stats = dict(decisions=0, total_time_ms=0.0, total_nodes=0, total_path_len=0, paths_found=0)
        saved_msg = ""

        def restart():
            nonlocal st, phase, acc, sim_ms, dec, stats, saved_msg
            st, phase, acc, sim_ms, dec, saved_msg = self.new_state(), "running", 0.0, 0.0, None, ""
            stats = dict(decisions=0, total_time_ms=0.0, total_nodes=0, total_path_len=0, paths_found=0)

        while True:
            dt = self.clock.tick(60) / 1000.0
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    return "quit"
                if e.type != pygame.KEYDOWN:
                    continue
                k = e.key
                if k == pygame.K_ESCAPE:
                    return "quit"                                 # original behaviour
                if k == pygame.K_BACKSPACE:
                    return "menu"
                if k == pygame.K_m:
                    self.s.mode = "manual" if self.s.mode == "ai" else "ai"
                elif k in (pygame.K_a, pygame.K_b, pygame.K_d, pygame.K_s, pygame.K_h):
                    self.s.strategy = {pygame.K_a: "astar", pygame.K_b: "bfs", pygame.K_d: "dijkstra",
                                       pygame.K_s: "adaptive", pygame.K_h: "hamiltonian"}[k]
                elif k in (pygame.K_p, pygame.K_SPACE):
                    if phase in ("running", "paused"):
                        phase = "paused" if phase == "running" else "running"
                elif k == pygame.K_r:
                    restart()
                elif k in (pygame.K_RETURN, pygame.K_KP_ENTER) and phase == "over":
                    restart()                                       # original behaviour
                elif k == pygame.K_v:
                    self.s.show_path = not self.s.show_path
                elif k == pygame.K_n:
                    self.s.muted = self.audio.muted = not self.s.muted
                elif k in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    self.s.speed = min(2.0, round(self.s.speed + 0.25, 2))
                elif k in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    self.s.speed = max(0.5, round(self.s.speed - 0.25, 2))
                elif phase == "running" and self.s.mode == "manual":
                    d = {pygame.K_UP: "up", pygame.K_DOWN: "down", pygame.K_LEFT: "left", pygame.K_RIGHT: "right"}.get(k)
                    if d:
                        st.set_direction(d)

            if phase == "running":
                acc += dt
                interval = st.tick_interval / self.s.speed
                steps_this_frame = 0
                while acc >= interval and phase == "running" and steps_this_frame < 5:
                    acc -= interval
                    steps_this_frame += 1
                    if self.s.mode == "ai":
                        st.config.stall_limit = st.grid.width * st.grid.height * 4
                        dec = choose_move(st.situation(), self.s.strategy, self.s.base)
                        if dec.reason != "hamiltonian_cycle":
                            stats["decisions"] += 1
                            stats["total_time_ms"] += dec.time_ms
                            stats["total_nodes"] += dec.explored
                            if dec.found:
                                stats["paths_found"] += 1
                                stats["total_path_len"] += dec.path_length
                        if dec.direction:
                            st.set_direction(dec.direction)
                    else:
                        st.config.stall_limit = None
                    events = st.step()
                    sim_ms += interval * 1000
                    for ev in events:
                        self.audio.play("die" if ev == "died" else ev)
                    if st.score > self.high:
                        self.high = st.score
                        try:
                            self.hs.write(self.high)               # same file/format as the original game
                        except OSError:
                            pass
                    interval = st.tick_interval / self.s.speed
                    if not st.alive:
                        phase = "over"
                        saved_msg = self.record(st, sim_ms, stats)

            # ---------- render ----------
            self.r.board(st, dec.path if (dec and self.s.mode == "ai") else [], self.s.show_path and self.s.mode == "ai")
            row1 = [("Score", st.score), ("High Score", self.high), ("Mode", "AI" if self.s.mode == "ai" else "Manual"),
                    ("Strategy", self.s.strategy.upper()), ("Level", self.s.difficulty), ("Speed", f"{st.speed * self.s.speed:.1f}/s")]
            if dec and self.s.mode == "ai":
                ai = (f"{dec.strategy}: {'path ' + str(dec.path_length) if dec.found else 'no path'} | explored {dec.explored} | "
                      f"{dec.time_ms:.2f} ms | {'safe' if dec.safe else 'RISKY'} | {dec.reason.replace('_', ' ')}")
            else:
                ai = "AI idle" if self.s.mode == "ai" else "Manual: arrows to steer"
            fx = ("  [x2]" if st.effects["double"] > 0 else "") + ("  [slow]" if st.effects["slow"] > 0 else "")
            self.r.panel(row1, ai + fx, "A* B BFS D Dijkstra S Adaptive H Hamilton | M mode | P pause | V path | N mute | +/- speed | Backspace menu | Esc quit")
            if phase == "paused":
                self.r.overlay("PAUSED", ["Press P or Space to resume"], (255, 255, 255))
            elif phase == "over":
                title = "YOU WIN!" if st.outcome == "won" else "GAME OVER!"
                self.r.overlay(title, [OUTCOMES.get(st.outcome, ""), f"Your Score: {st.score}  High Score: {self.high}",
                                       "Press Enter to Restart or ESC to Quit", saved_msg])
            pygame.display.flip()

    def record(self, st, sim_ms, stats) -> str:
        total = stats["decisions"]
        ai_mode = self.s.mode == "ai" and total * 2 >= st.steps
        p = dict(mode="ai" if ai_mode else "manual", difficulty=self.s.difficulty, board_w=st.grid.width, board_h=st.grid.height,
                 wrap=st.grid.wrap, obstacles=bool(st.obstacles), score=st.score, apples_collected=st.apples, steps=st.steps,
                 duration_ms=int(sim_ms), outcome=st.outcome or "quit")
        if ai_mode:
            p["algorithm"] = self.s.strategy
            p["ai_metrics"] = {**stats, "total_time_ms": round(stats["total_time_ms"], 3)}
        elif self.s.mode == "ai":
            p["mode"] = "manual"
        ok = self.recorder.record(p)
        return "Match saved to local database" if ok else "(match not saved: database unavailable)"


def main(argv=None):
    ap = argparse.ArgumentParser(description="AI Snake Arena - desktop game")
    ap.add_argument("--no-menu", action="store_true", help="skip the start menu (original game defaults)")
    args = ap.parse_args(argv)
    app = App(args.no_menu)
    try:
        go = True if args.no_menu else app.menu()
        while go:
            result = app.play()
            if result == "quit":
                break
            go = app.menu()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
