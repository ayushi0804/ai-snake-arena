"""Legacy-compatible highscore.txt handling (same single-integer file the original game used)."""
from __future__ import annotations
import os
import tempfile


class HighScoreFile:
    def __init__(self, path):
        self.path = str(path)

    def read(self) -> int:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                v = int(f.read().strip())
            return v if 0 <= v <= 1_000_000 else 0
        except (OSError, ValueError):
            return 0

    def write(self, value: int) -> None:
        d = os.path.dirname(os.path.abspath(self.path))
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".hs_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(str(int(value)))
            os.replace(tmp, self.path)       # atomic: never leaves a half-written file
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def update_if_higher(self, score: int) -> bool:
        if score > self.read():
            self.write(score)
            return True
        return False
