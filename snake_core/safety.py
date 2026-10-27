"""Safety validation: predicted collisions, moving tail, growth, dead ends, tail reachability."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from .grid import DIRS
from .pathfinding import distances_from


@dataclass(frozen=True)
class Situation:
    """Everything the AI is allowed to know. snake[0] is the head."""
    grid: object
    snake: tuple
    obstacles: frozenset
    apple: tuple | None
    extra_growth: frozenset = frozenset()   # other cells that also grow the snake (bonus apple)


@dataclass
class MoveInfo:
    direction: str
    cell: tuple | None
    legal: bool
    grows: bool = False
    area: int = 0
    tail_reachable: bool = False
    dead_end: bool = False

    def to_dict(self):
        return asdict(self)


def planning_blocked(sit: Situation) -> set:
    """Cells a path may not use. The tail is excluded: it vacates on the first step.
    Slightly conservative (other segments also vacate later) but never yields an illegal path."""
    return set(sit.snake[:-1]) | set(sit.obstacles)


def tail_reachable(grid, snake, obstacles) -> bool:
    if len(snake) <= 1:
        return True
    blocked = set(snake[1:]) | set(obstacles)
    dist = distances_from(grid, snake[0], blocked)
    return any(n in dist for n in grid.neighbors(snake[-1]))


def evaluate_move(sit: Situation, direction: str) -> MoveInfo:
    grid, snake = sit.grid, sit.snake
    cell = grid.step(snake[0], direction)
    if cell is None or cell in sit.obstacles:
        return MoveInfo(direction, cell, False)
    grows = cell == sit.apple or cell in sit.extra_growth
    if len(snake) > 1 and cell == snake[1]:
        return MoveInfo(direction, cell, False, grows)   # 180-degree reversal is never allowed
    body_after = list(snake) if grows else list(snake[:-1])   # moving tail handling
    if cell in body_after:
        return MoveInfo(direction, cell, False, grows)
    new_snake = [cell] + body_after
    blocked = set(new_snake[1:]) | set(sit.obstacles)
    dist = distances_from(grid, cell, blocked)
    area = len(dist)
    tr = len(new_snake) <= 1 or any(n in dist for n in grid.neighbors(new_snake[-1]))
    return MoveInfo(direction, cell, True, grows, area, tr, (not tr) and area < len(new_snake))


def evaluate_moves(sit: Situation) -> list:
    return [evaluate_move(sit, d) for d in DIRS]


def simulate_path(sit: Situation, path) -> tuple:
    """Follow `path` with a virtual snake (growing when it reaches the apple).
    Returns (final_snake, survived)."""
    snake = list(sit.snake)
    for cell in path:
        grows = cell == sit.apple or cell in sit.extra_growth
        occupied = snake if grows else snake[:-1]
        if cell in sit.obstacles or cell in occupied:
            return snake, False
        snake = [cell] + (snake if grows else snake[:-1])
    return snake, True
