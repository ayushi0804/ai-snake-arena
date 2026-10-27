"""Create/upgrade the database and import the legacy highscore.txt (safe to run repeatedly)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from webapp import config
from storage.db import Database
from storage.legacy import migrate_legacy_highscore

cfg = config.from_env()
db = Database(cfg["ARENA_DB_PATH"])
print("database:", cfg["ARENA_DB_PATH"])
print("migrations applied now:", db.init() or "none (already up to date)")
print("legacy highscore:", migrate_legacy_highscore(db, cfg["ARENA_LEGACY_HIGHSCORE"]))
