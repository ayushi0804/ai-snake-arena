"""Move selection. Strategies:
  astar | bfs | dijkstra : follow the raw shortest path; only refuse an immediately fatal step.
  adaptive               : path + virtual-snake tail-reachability check, tail-following and
                           max-area recovery. Falls back gracefully; never loops internally.
  hamiltonian            : follow a verified Hamiltonian cycle with safe shortcuts (no obstacles).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from time import perf_counter
from .pathfinding import ALGORITHMS
from .safety import (Situation, planning_blocked, evaluate_moves, simulate_path, tail_reachable)
from .hamilton import get_cycle

STRATEGIES = ("astar", "bfs", "dijkstra", "adaptive", "hamiltonian")


@dataclass
class Decision:
    direction: str | None
    strategy: str
    algorithm: str
    found: bool = False
    path: list = field(default_factory=list)
    explored: int = 0
    path_length: int = 0
    time_ms: float = 0.0
    safe: bool = False
    reason: str = ""
    moves: list = field(default_factory=list)

    def to_dict(self):
        d = self.__dict__.copy()
        d["moves"] = [m.to_dict() for m in self.moves]
        return d


def _best_by_area(legal):
    return max(legal, key=lambda m: (not m.dead_end, m.tail_reachable, m.area))


def choose_move(sit: Situation, strategy: str = "adaptive", base: str = "astar") -> Decision:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}")
    if base not in ALGORITHMS:
        raise ValueError(f"unknown base algorithm {base!r}")
    t0 = perf_counter()
    moves = evaluate_moves(sit)
    legal = [m for m in moves if m.legal]
    algo = base if strategy == "adaptive" else (strategy if strategy in ALGORITHMS else "astar")
    dec = Decision(None, strategy, algo, moves=moves)

    def done(m, reason, safe):
        dec.direction = m.direction if m else None
        dec.reason, dec.safe = reason, safe
        dec.time_ms = (perf_counter() - t0) * 1000.0
        return dec

    if sit.apple is None or not legal:
        return done(None, "no_legal_move" if not legal else "no_target", False)

    reason_prefix = ""
    if strategy == "hamiltonian":
        cyc = None if sit.obstacles else get_cycle(sit.grid.width, sit.grid.height)
        if cyc is not None:
            cycle, idx = cyc
            n, h = len(cycle), idx[sit.snake[0]]
            apple_d = (idx[sit.apple] - h) % n
            tail_d = n if len(sit.snake) == 1 else (idx[sit.snake[-1]] - h) % n
            best, best_d = None, 0
            for m in legal:
                d = (idx[m.cell] - h) % n
                if (d == 1 or (1 < d <= apple_d and d <= tail_d - 1)) and d > best_d:
                    best, best_d = m, d
            if best:
                return done(best, "hamiltonian_cycle", True)
        reason_prefix = "hamiltonian_unavailable;"

    res = ALGORITHMS[algo](sit.grid, sit.snake[0], sit.apple, planning_blocked(sit))
    dec.found, dec.path, dec.explored, dec.path_length = res.found, list(res.path), res.explored, res.length
    by_cell = {m.cell: m for m in legal}

    if strategy in ("astar", "bfs", "dijkstra"):
        if res.found and res.path[0] in by_cell:
            m = by_cell[res.path[0]]
            return done(m, "raw_path", not m.dead_end)
        return done(_best_by_area(legal), "recovery_max_area", False)

    # adaptive (also the fallback when a Hamiltonian cycle is unavailable)
    if res.found and res.path[0] in by_cell:
        final_snake, survived = simulate_path(sit, res.path)
        if survived and tail_reachable(sit.grid, final_snake, sit.obstacles):
            return done(by_cell[res.path[0]], reason_prefix + "safe_path", True)
    tail = sit.snake[-1]
    safe = [m for m in legal if m.tail_reachable and not m.dead_end]
    if safe:
        m = max(safe, key=lambda m: (sit.grid.distance(m.cell, tail), m.area))
        return done(m, reason_prefix + "recovery_follow_tail", True)
    return done(_best_by_area(legal), reason_prefix + "recovery_max_area", False)
