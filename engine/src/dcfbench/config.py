"""Paths and secrets. Secrets come from environment variables or the repo's .env file."""

from __future__ import annotations

import os
import re
from pathlib import Path

REPO_ROOT = Path(os.environ.get("DCFBENCH_ROOT", Path(__file__).resolve().parents[2]))
DATA_DIR = REPO_ROOT / "data"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
UNIVERSE_DIR = DATA_DIR / "universe"
CASES_DIR = DATA_DIR / "cases"

# name -> what it unlocks. Only the U.S. sources are used by this repository.
SECRETS = {
    "SEC_USER_AGENT": "SEC EDGAR (no key, a name and contact email)",
    "FRED_API_KEY": "FRED rates (optional, keyless CSV fallback exists)",
}

_loaded = False


def load_env(path: Path | None = None) -> None:
    """Read KEY=VALUE lines from .env into os.environ. Real environment variables win."""
    global _loaded
    if _loaded and path is None:
        return
    env_path = path or REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            if value and key.strip() not in os.environ:
                os.environ[key.strip()] = value
    _loaded = True


def secret(name: str, required: bool = True) -> str | None:
    load_env()
    value = os.environ.get(name, "").strip()
    if not value:
        if required:
            raise RuntimeError(
                f"{name} is not set. Add it to {REPO_ROOT / '.env'} (see .env.example)."
            )
        return None
    return value


_SECRET_PARAMS = re.compile(r"((?:api_key|crtfc_key|key|token)=)[^&\s]+", re.IGNORECASE)


def redact(text: str) -> str:
    """Remove key values from a URL or message before it is logged or stored."""
    text = _SECRET_PARAMS.sub(r"\1REDACTED", text)
    for name in SECRETS:
        value = os.environ.get(name, "").strip()
        if value and name != "SEC_USER_AGENT" and len(value) >= 6:
            text = text.replace(value, "REDACTED")
    return text
