"""Lets the Pygame game record finished matches in the same database (best effort, never fatal)."""
from __future__ import annotations
import os
import uuid
from pathlib import Path
from .db import Database
from .services import save_match
from .legacy import migrate_legacy_highscore


class DesktopRecorder:
    def __init__(self, db_path, highscore_path, data_dir):
        self.db = Database(str(db_path))
        self.guest_file = Path(data_dir) / "desktop_guest_id.txt"
        self.ok = False
        try:
            self.db.init()
            migrate_legacy_highscore(self.db, str(highscore_path))
            self.guest_id = self._guest_id()
            self.ok = True
        except Exception:   # the game must stay playable without a database
            self.ok = False

    def _guest_id(self):
        try:
            gid = self.guest_file.read_text().strip()
            if len(gid) >= 8:
                return gid
        except OSError:
            pass
        gid = "desktop-" + uuid.uuid4().hex[:16]
        self.guest_file.parent.mkdir(parents=True, exist_ok=True)
        self.guest_file.write_text(gid)
        return gid

    def record(self, payload: dict) -> bool:
        if not self.ok:
            return False
        try:
            save_match(self.db, self.guest_id, payload, source="desktop", trust="local_desktop",
                       display_name="Desktop Player")
            return True
        except Exception:
            return False
