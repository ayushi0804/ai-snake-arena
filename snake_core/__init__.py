"""Pure-Python Snake rules + AI. No pygame / Flask imports allowed here."""
from .grid import Grid, DIRS, OPPOSITE
from .engine import GameConfig, GameState, DIFFICULTIES, BOARD_PRESETS
from .ai import choose_move, STRATEGIES
__all__ = ["Grid", "DIRS", "OPPOSITE", "GameConfig", "GameState", "DIFFICULTIES",
           "BOARD_PRESETS", "choose_move", "STRATEGIES"]
