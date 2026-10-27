"""A*, BFS and Dijkstra on a Grid. All return SearchResult; none raise on unreachable goals.

`blocked` is a set of impassable cells. `costs` maps cell -> cost of ENTERING it (default 1.0,
must be > 0). BFS ignores costs (it is only optimal on unweighted graphs). A* uses
Manhattan distance scaled by the minimum step cost, so it stays admissible.
"""
from __future__ import annotations
import heapq
import itertools
from collections import deque
from dataclasses import dataclass, field, asdict
from time import perf_counter


@dataclass
class SearchResult:
    algorithm: str
    found: bool
    path: list = field(default_factory=list)   # cells after start, ending at goal
    explored: int = 0                          # nodes expanded
    cost: float = 0.0
    time_ms: float = 0.0
    reason: str = "ok"

    @property
    def length(self) -> int:
        return len(self.path)

    def to_dict(self):
        d = asdict(self)
        d["length"] = self.length
        return d


def _precheck(grid, start, goal, blocked):
    if not grid.in_bounds(start):
        return "invalid_start"
    if not grid.in_bounds(goal):
        return "invalid_goal"
    if goal in blocked:
        return "goal_blocked"
    return None


def _result(name, t0, found, came, start, goal, explored, cost=None, reason=None):
    path = []
    if found:
        cur = goal
        while cur != start:
            path.append(cur)
            cur = came[cur]
        path.reverse()
    return SearchResult(name, found, path, explored, float(len(path) if cost is None else cost),
                        (perf_counter() - t0) * 1000.0, reason or ("ok" if found else "unreachable"))


def bfs(grid, start, goal, blocked=frozenset(), costs=None) -> SearchResult:
    t0 = perf_counter()
    err = _precheck(grid, start, goal, blocked)
    if err:
        return _result("bfs", t0, False, {}, start, goal, 0, 0.0, err)
    came, seen, queue, explored = {}, {start}, deque([start]), 0
    while queue:
        cur = queue.popleft()
        explored += 1
        if cur == goal:
            return _result("bfs", t0, True, came, start, goal, explored)
        for n in grid.neighbors(cur):
            if n not in seen and n not in blocked:
                seen.add(n)
                came[n] = cur
                queue.append(n)
    return _result("bfs", t0, False, came, start, goal, explored)


def _weighted(name, grid, start, goal, blocked, costs, use_heuristic) -> SearchResult:
    t0 = perf_counter()
    err = _precheck(grid, start, goal, blocked)
    if err:
        return _result(name, t0, False, {}, start, goal, 0, 0.0, err)
    costs = costs or {}
    if any(c <= 0 for c in costs.values()):
        raise ValueError("movement costs must be > 0")
    min_cost = min([1.0] + list(costs.values()))
    h = (lambda c: grid.distance(c, goal) * min_cost) if use_heuristic else (lambda c: 0.0)
    g, came, closed, explored = {start: 0.0}, {}, set(), 0
    tie = itertools.count()
    heap = [(h(start), next(tie), start)]
    while heap:
        _, _, cur = heapq.heappop(heap)
        if cur in closed:
            continue
        closed.add(cur)
        explored += 1
        if cur == goal:
            return _result(name, t0, True, came, start, goal, explored, g[cur])
        for n in grid.neighbors(cur):
            if n in blocked or n in closed:
                continue
            ng = g[cur] + costs.get(n, 1.0)
            if ng < g.get(n, float("inf")):
                g[n] = ng
                came[n] = cur
                heapq.heappush(heap, (ng + h(n), next(tie), n))
    return _result(name, t0, False, came, start, goal, explored)


def astar(grid, start, goal, blocked=frozenset(), costs=None) -> SearchResult:
    return _weighted("astar", grid, start, goal, blocked, costs, True)


def dijkstra(grid, start, goal, blocked=frozenset(), costs=None) -> SearchResult:
    return _weighted("dijkstra", grid, start, goal, blocked, costs, False)


ALGORITHMS = {"astar": astar, "bfs": bfs, "dijkstra": dijkstra}


def distances_from(grid, start, blocked=frozenset()) -> dict:
    """BFS distance map over free cells (start is always included)."""
    dist, queue = {start: 0}, deque([start])
    while queue:
        cur = queue.popleft()
        for n in grid.neighbors(cur):
            if n not in dist and n not in blocked:
                dist[n] = dist[cur] + 1
                queue.append(n)
    return dist


def reachable_area(grid, start, blocked=frozenset()) -> int:
    return len(distances_from(grid, start, blocked))
