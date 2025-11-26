"""
Unified loader for Kite credentials from secrets/*.env.

Prefers dotenv parsing if python-dotenv is installed, otherwise falls back to
manual key=value parsing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

try:
    from dotenv import dotenv_values  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    dotenv_values = None

ROOT = Path(__file__).resolve().parents[1]
SECRETS_DIR = ROOT / "secrets"
API_FILE = SECRETS_DIR / "kite.env"
TOK_FILE = SECRETS_DIR / "kite_tokens.env"


def _read_simple_env(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip()
    return data


def _load_env_file(path: Path) -> Dict[str, str]:
    """
    Load key=value pairs from the given file.
    Returns {} if file missing or dotenv not installed.
    """
    if not path.exists():
        return {}
    if dotenv_values is None:
        return _read_simple_env(path)
    return {k: v for k, v in dotenv_values(path).items() if v is not None}


def get_kite_credentials() -> Dict[str, Optional[str]]:
    """
    Unified place to read all Kite credentials from:
      - secrets/kite.env
      - secrets/kite_tokens.env

    Returns keys:
      api_key, api_secret, access_token, public_token, login_ts
    """
    api_env = _load_env_file(API_FILE)
    token_env = _load_env_file(TOK_FILE)

    return {
        "api_key": api_env.get("KITE_API_KEY"),
        "api_secret": api_env.get("KITE_API_SECRET"),
        "access_token": token_env.get("KITE_ACCESS_TOKEN"),
        "public_token": token_env.get("KITE_PUBLIC_TOKEN"),
        "login_ts": token_env.get("KITE_LOGIN_TS"),
    }
