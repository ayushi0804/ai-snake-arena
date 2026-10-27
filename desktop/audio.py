"""Synthesised sound effects (no asset files needed). Silent if no audio device is available."""
from __future__ import annotations
import math
from array import array
from pathlib import Path

TONES = {"apple": [(660, .07), (880, .08)], "bonus": [(880, .06), (1175, .06), (1568, .1)],
         "powerup": [(520, .06), (780, .06), (1040, .1)], "die": [(330, .15), (220, .15), (147, .3)],
         "won": [(523, .1), (659, .1), (784, .1), (1047, .3)]}


class Audio:
    def __init__(self, pygame, custom_game_over: Path | None = None):
        self.pg, self.muted, self.sounds, self.ok = pygame, False, {}, False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(22050, -16, 1, 512)
            freq, _fmt, channels = pygame.mixer.get_init()
            for name, notes in TONES.items():
                samples = array("h")
                for f, d in notes:
                    n = int(freq * d)
                    for i in range(n):
                        env = 1.0 - i / n
                        v = int(9000 * env * (1 if math.sin(2 * math.pi * f * i / freq) >= 0 else -1))
                        samples.extend([v] * channels)
                self.sounds[name] = pygame.mixer.Sound(buffer=samples.tobytes())
            if custom_game_over and custom_game_over.exists():     # keep the original optional game_over.mp3
                try:
                    self.sounds["die"] = pygame.mixer.Sound(str(custom_game_over))
                except Exception:
                    pass
            self.ok = True
        except Exception:
            self.ok = False

    def play(self, name):
        if self.ok and not self.muted and name in self.sounds:
            try:
                self.sounds[name].play()
            except Exception:
                pass
