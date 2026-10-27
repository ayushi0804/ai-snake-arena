"""Reproducible benchmarks. Pathfinding benchmarks compare algorithms on IDENTICAL generated states;
survival benchmarks play whole games and are reported separately (a shortest path says nothing
about surviving afterwards)."""
from __future__ import annotations
import random
from .grid import Grid, DIRS
from .pathfinding import ALGORITHMS, bfs
from .safety import Situation, planning_blocked, simulate_path, tail_reachable
from .engine import GameState, GameConfig
from .ai import choose_move

VERSION = "1"


def make_scenario(seed: int, index: int, w: int, h: int, snake_len: int, obstacle_frac: float, wrap=False):
    rng = random.Random(seed * 100003 + index)
    grid = Grid(w, h, wrap)
    for _ in range(100):
        cur = (rng.randrange(w), rng.randrange(h))
        body = [cur]
        while len(body) < snake_len:
            opts = [n for n in grid.neighbors(body[-1]) if n not in body]
            if not opts:
                break
            body.append(rng.choice(opts))
        if len(body) == snake_len:
            break
    body.reverse()     # head = last cell of the walk
    taken = set(body)
    free = [c for c in grid.cells() if c not in taken]
    obs = set(rng.sample(free, min(len(free) - 2, round(w * h * obstacle_frac))))
    free = [c for c in free if c not in obs]
    return Situation(grid, tuple(body[::-1][::-1]), frozenset(obs), rng.choice(free))


def run_pathfinding(seed=1, w=25, h=12, scenarios=100, snake_len=8, obstacle_frac=0.05, wrap=False, repeats=3):
    scs = [make_scenario(seed, i, w, h, snake_len, obstacle_frac, wrap) for i in range(scenarios)]
    out = []
    for name, fn in ALGORITHMS.items():
        found = safe = shortest = 0
        t = nodes = plen = 0.0
        for s in scs:
            blocked = planning_blocked(s)
            best = min((fn(s.grid, s.snake[0], s.apple, blocked) for _ in range(repeats)), key=lambda r: r.time_ms)
            t += best.time_ms
            nodes += best.explored
            if best.found:
                found += 1
                plen += best.length
                snake, ok = simulate_path(s, best.path)
                safe += bool(ok and tail_reachable(s.grid, snake, s.obstacles))
                shortest += best.length == bfs(s.grid, s.snake[0], s.apple, blocked).length
        n = len(scs)
        out.append(dict(kind="pathfinding", algorithm=name, seed=seed, board_w=w, board_h=h, wrap=int(wrap),
                        scenarios=n, success_rate=found / n, safe_rate=safe / n, avg_time_ms=t / n,
                        avg_nodes=nodes / n, avg_path_len=(plen / found) if found else None,
                        avg_score=None, avg_steps=None, completion_rate=None,
                        details={"snake_len": snake_len, "obstacle_fraction": obstacle_frac, "repeats": repeats,
                                 "shortest_path_rate_vs_bfs": (shortest / found) if found else None,
                                 "safe_rate_definition": "path found AND virtual snake survives AND can reach its tail after eating",
                                 "time_definition": "min of repeats, algorithm call only"},
                        provenance=f"server python engine v{VERSION}; seeded scenarios; unweighted grid"))
    return out


def run_survival(seed=1, w=12, h=8, games=5, difficulty="normal", max_steps=600, strategies=None):
    out = []
    for strat in strategies or ("astar", "bfs", "dijkstra", "adaptive", "hamiltonian"):
        scores, steps, wins, deaths, stalls, capped = [], [], 0, 0, 0, 0
        for g in range(games):
            st = GameState(GameConfig(width=w, height=h, difficulty=difficulty, seed=seed * 1009 + g,
                                      stall_limit=w * h * 4))
            while st.alive and st.steps < max_steps:
                d = choose_move(st.situation(), strat)
                if d.direction:
                    st.set_direction(d.direction)
                st.step()
            scores.append(st.score); steps.append(st.steps)
            if st.outcome == "won": wins += 1
            elif st.outcome == "stalled": stalls += 1
            elif st.alive: capped += 1
            else: deaths += 1
        out.append(dict(kind="survival", algorithm=strat, seed=seed, board_w=w, board_h=h, wrap=0, scenarios=games,
                        success_rate=None, safe_rate=1 - deaths / games, avg_time_ms=None, avg_nodes=None,
                        avg_path_len=None, avg_score=sum(scores) / games, avg_steps=sum(steps) / games,
                        completion_rate=wins / games,
                        details={"games": games, "wins": wins, "collision_deaths": deaths, "stalled": stalls,
                                 "reached_step_cap": capped, "max_steps": max_steps, "difficulty": difficulty,
                                 "safe_rate_definition": "games NOT ended by a collision (survived, stalled or capped)",
                                 "completion_rate_definition": "wins / games (board filled)"},
                        provenance=f"server python engine v{VERSION}; seeded games"))
    return out
