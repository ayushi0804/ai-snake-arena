from __future__ import annotations

DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}


class Grid:
    """Cell-coordinate board (x, y). Optional toroidal wrap-around."""
    __slots__ = ("width", "height", "wrap")

    def __init__(self, width: int, height: int, wrap: bool = False):
        if not isinstance(width, int) or not isinstance(height, int) or width < 2 or height < 2:
            raise ValueError("grid dimensions must be integers >= 2")
        self.width, self.height, self.wrap = width, height, bool(wrap)

    def in_bounds(self, c) -> bool:
        return (isinstance(c, tuple) and len(c) == 2 and isinstance(c[0], int)
                and isinstance(c[1], int) and 0 <= c[0] < self.width and 0 <= c[1] < self.height)

    def step(self, c, direction):
        dx, dy = DIRS[direction]
        x, y = c[0] + dx, c[1] + dy
        if self.wrap:
            return (x % self.width, y % self.height)
        return (x, y) if 0 <= x < self.width and 0 <= y < self.height else None

    def neighbors(self, c):
        out = []
        for d in DIRS:
            n = self.step(c, d)
            if n is not None and n != c and n not in out:
                out.append(n)
        return out

    def distance(self, a, b) -> int:
        dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
        if self.wrap:
            dx, dy = min(dx, self.width - dx), min(dy, self.height - dy)
        return dx + dy

    def direction_between(self, a, b):
        for d in DIRS:
            if self.step(a, d) == b:
                return d
        return None

    def cells(self):
        return [(x, y) for y in range(self.height) for x in range(self.width)]
