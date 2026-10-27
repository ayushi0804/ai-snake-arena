"""Environment-based configuration. A local .env file (see .env.example) is read if present."""
from __future__ import annotations
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path=ROOT / ".env"):
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


def from_env() -> dict:
    load_dotenv()
    env = os.environ
    return {
        "ARENA_ENV": env.get("ARENA_ENV", "development"),
        "ARENA_DB_PATH": env.get("ARENA_DB_PATH", str(ROOT / "data" / "arena.db")),
        "ARENA_LEGACY_HIGHSCORE": env.get("ARENA_LEGACY_HIGHSCORE", str(ROOT / "highscore.txt")),
        "ARENA_CORS_ORIGINS": [o.strip() for o in env.get("ARENA_CORS_ORIGINS", "").split(",") if o.strip()],
        "SECRET_KEY": env.get("ARENA_SECRET_KEY") or secrets.token_hex(32),   # no accounts yet; reserved
        "HOST": env.get("ARENA_HOST", "127.0.0.1"),
        "PORT": int(env.get("ARENA_PORT", "5000")),
        "MAX_CONTENT_LENGTH": 64 * 1024,
    }
