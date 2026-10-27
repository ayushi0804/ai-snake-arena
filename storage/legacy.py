"""One-time, idempotent import of the original highscore.txt. The file is never modified or deleted."""
from __future__ import annotations
import os
from .services import get_or_create_player, MAX_SCORE

META_KEY = "legacy_highscore_migrated"


def migrate_legacy_highscore(db, path) -> dict:
    if not path or not os.path.isfile(path):
        return {"status": "missing"}
    try:
        with open(path, "r", encoding="utf-8") as f:
            score = int(f.read().strip())
        if not 0 <= score <= MAX_SCORE:
            raise ValueError
    except (OSError, ValueError):
        return {"status": "invalid"}
    with db.transaction() as c:
        if c.execute("SELECT 1 FROM meta WHERE key = ?", (META_KEY,)).fetchone():
            return {"status": "already_migrated"}
        if score > 0:
            pid = get_or_create_player(c, "legacy-desktop-player", "Desktop (legacy)")
            c.execute("""INSERT INTO matches(client_match_id, player_id, source, trust, mode, algorithm, difficulty,
                         board_w, board_h, score, outcome) VALUES ('legacy-highscore-import', ?, 'legacy',
                         'legacy_import', 'unknown', NULL, 'classic', 25, 12, ?, 'quit')""", (pid, score))
        c.execute("INSERT INTO meta(key, value) VALUES (?, ?)", (META_KEY, str(score)))
    return {"status": "migrated", "score": score}
