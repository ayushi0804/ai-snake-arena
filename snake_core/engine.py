"""Game rules, independent of any renderer. Cell coordinates; snake[0] is the head."""
from __future__ import annotations
import random
from collections import deque
from dataclasses import dataclass
from .grid import Grid, OPPOSITE
from .pathfinding import reachable_area
from .safety import Situation

# base/step/max are ticks per second; obst is the fraction of cells that become obstacles.
DIFFICULTIES = {
    "classic": dict(base=8.0, step=0.0, max=8.0, obst=0.0, extras=False),
    "easy":    dict(base=6.0, step=0.10, max=12.0, obst=0.0, extras=True),
    "normal":  dict(base=8.0, step=0.15, max=16.0, obst=0.015, extras=True),
    "hard":    dict(base=10.0, step=0.25, max=20.0, obst=0.03, extras=True),
    "insane":  dict(base=12.0, step=0.30, max=24.0, obst=0.05, extras=True),
}
BOARD_PRESETS = {"small": (16, 10), "classic": (25, 12), "large": (30, 16)}
POINTS = {"normal": 1, "golden": 3}
POWERUPS = ("slow", "double", "shrink")
EFFECT_TICKS = 60
GOLDEN_TTL, POWERUP_TTL = 40, 60


@dataclass
class Item:
    pos: tuple
    kind: str
    ttl: int | None = None


@dataclass
class GameConfig:
    width: int = 25
    height: int = 12
    wrap: bool = False
    difficulty: str = "normal"
    obstacles: bool = True
    powerups: bool = True
    seed: int | None = None
    stall_limit: int | None = None   # end the game if no apple for this many steps (AI runs)

    def validate(self):
        if not (5 <= self.width <= 60 and 5 <= self.height <= 60):
            raise ValueError("board dimensions must be 5..60")
        if self.difficulty not in DIFFICULTIES:
            raise ValueError("unknown difficulty")
        return self


class GameState:
    def __init__(self, config: GameConfig | None = None):
        self.config = (config or GameConfig()).validate()
        c = self.config
        self.rng = random.Random(c.seed)
        self.grid = Grid(c.width, c.height, c.wrap)
        self.diff = DIFFICULTIES[c.difficulty]
        start = (min(2, c.width - 1), min(2, c.height - 1))
        self.snake = deque([start])
        self.direction = "down"
        self._queue = deque()
        self.obstacles = set()
        self._place_obstacles(start)
        self.apple = self.bonus = self.powerup = None
        self.effects = {"double": 0, "slow": 0}
        self.score = self.apples = self.steps = self.since_apple = 0
        self.alive, self.outcome, self.events = True, None, []
        self._spawn_apple()

    # ---------- setup helpers ----------
    def _place_obstacles(self, start):
        if not self.config.obstacles or self.diff["obst"] <= 0:
            return
        g = self.grid
        count = round(g.width * g.height * self.diff["obst"])
        cand = [c for c in g.cells() if g.distance(c, start) > 3]
        self.rng.shuffle(cand)
        for cell in cand:
            if len(self.obstacles) >= count:
                break
            self.obstacles.add(cell)
            if reachable_area(g, start, self.obstacles) != g.width * g.height - len(self.obstacles):
                self.obstacles.discard(cell)    # never split the board

    def free_cells(self):
        used = set(self.snake) | self.obstacles
        used.update(i.pos for i in (self.apple, self.bonus, self.powerup) if i)
        return [c for c in self.grid.cells() if c not in used]

    def _spawn_apple(self) -> bool:
        free = self.free_cells()
        if not free:
            self.apple = None
            return False
        self.apple = Item(self.rng.choice(free), "normal")
        return True

    def _spawn_item(self, kind, ttl):
        free = self.free_cells()
        return Item(self.rng.choice(free), kind, ttl) if free else None

    # ---------- input ----------
    def set_direction(self, d: str) -> bool:
        """Queue a turn. Rejects reversals and repeats relative to the last queued direction."""
        if d not in OPPOSITE or len(self._queue) >= 2:
            return False
        last = self._queue[-1] if self._queue else self.direction
        if d == last or (d == OPPOSITE[last] and len(self.snake) > 1):
            return False   # a 1-segment snake has no neck, so reversing it is safe
        self._queue.append(d)
        return True

    # ---------- simulation ----------
    @property
    def speed(self) -> float:
        d = self.diff
        s = min(d["max"], d["base"] + d["step"] * self.apples)
        return s * (0.6 if self.effects["slow"] > 0 else 1.0)

    @property
    def tick_interval(self) -> float:
        return 1.0 / self.speed

    @property
    def multiplier(self) -> int:
        return 2 if self.effects["double"] > 0 else 1

    def situation(self) -> Situation:
        return Situation(self.grid, tuple(self.snake), frozenset(self.obstacles),
                         self.apple.pos if self.apple else None,
                         frozenset([self.bonus.pos]) if self.bonus else frozenset())

    def _die(self, why):
        self.alive, self.outcome = False, why
        self.events.append("died")
        return self.events

    def step(self):
        self.events = []
        if not self.alive:
            return self.events
        if self._queue:
            self.direction = self._queue.popleft()
        self.steps += 1
        self.since_apple += 1
        target = self.grid.step(self.snake[0], self.direction)
        if target is None:
            return self._die("wall")
        if target in self.obstacles:
            return self._die("obstacle")
        eats_apple = self.apple is not None and target == self.apple.pos
        eats_bonus = self.bonus is not None and target == self.bonus.pos
        grows = eats_apple or eats_bonus
        occupied = list(self.snake) if grows else list(self.snake)[:-1]   # tail moves away
        if target in occupied:
            return self._die("self")
        self.snake.appendleft(target)
        if not grows:
            self.snake.pop()
        if eats_apple:
            self._gain(POINTS["normal"])
            self.since_apple = 0
            self.events.append("apple")
            if not self._spawn_apple():
                self.alive, self.outcome = False, "won"
                self.events.append("won")
                return self.events
        elif eats_bonus:
            self._gain(POINTS["golden"])
            self.bonus = None
            self.events.append("bonus")
        elif self.powerup is not None and target == self.powerup.pos:
            self._apply_powerup(self.powerup.kind)
            self.powerup = None
            self.events.append("powerup")
        self._tick_timers()
        self._maybe_spawn_extras()
        lim = self.config.stall_limit
        if lim and self.since_apple > lim:
            self.alive, self.outcome = False, "stalled"
            self.events.append("died")
        return self.events

    def _gain(self, pts):
        self.score += pts * self.multiplier
        self.apples += 1

    def _apply_powerup(self, kind):
        if kind == "shrink":
            for _ in range(min(3, len(self.snake) - 1)):
                self.snake.pop()
        else:
            self.effects[kind] = EFFECT_TICKS

    def _tick_timers(self):
        for k in self.effects:
            if self.effects[k] > 0:
                self.effects[k] -= 1
        for name in ("bonus", "powerup"):
            item = getattr(self, name)
            if item is not None and item.ttl is not None:
                item.ttl -= 1
                if item.ttl <= 0:
                    setattr(self, name, None)

    def _maybe_spawn_extras(self):
        if not (self.diff["extras"] and self.config.powerups):
            return
        if self.bonus is None and self.rng.random() < 0.02:
            self.bonus = self._spawn_item("golden", GOLDEN_TTL)
        if self.powerup is None and self.rng.random() < 0.012:
            self.powerup = self._spawn_item(self.rng.choice(POWERUPS), POWERUP_TTL)

    def summary(self) -> dict:
        return dict(score=self.score, apples=self.apples, steps=self.steps,
                    length=len(self.snake), outcome=self.outcome or "running")
