"""Hamiltonian cycle for grids with at least one even dimension (verified by is_valid_cycle)."""
from __future__ import annotations
from functools import lru_cache


def _cycle_even_height(w, h):
    cyc = [(0, 0)]
    for y in range(h):
        xs = range(1, w) if y % 2 == 0 else range(w - 1, 0, -1)
        cyc.extend((x, y) for x in xs)
    cyc.extend((0, y) for y in range(h - 1, 0, -1))
    return cyc


def build_cycle(w: int, h: int):
    """Return a list of cells forming a Hamiltonian cycle, or None when none exists
    (both dimensions odd, or a dimension < 2). Plain serpentine rows are NOT a cycle."""
    if w < 2 or h < 2 or (w % 2 == 1 and h % 2 == 1):
        return None
    if h % 2 == 0:
        return _cycle_even_height(w, h)
    return [(y, x) for (x, y) in _cycle_even_height(h, w)]


def is_valid_cycle(cyc, w: int, h: int) -> bool:
    if not cyc or len(cyc) != w * h or len(set(cyc)) != w * h:
        return False
    if any(not (0 <= x < w and 0 <= y < h) for x, y in cyc):
        return False
    return all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(cyc, cyc[1:] + cyc[:1]))


@lru_cache(maxsize=16)
def get_cycle(w: int, h: int):
    cyc = build_cycle(w, h)
    if cyc is None or not is_valid_cycle(cyc, w, h):
        return None
    return cyc, {c: i for i, c in enumerate(cyc)}
