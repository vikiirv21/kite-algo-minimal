"""Kite auth helper utilities.

Provides helpers to read API key/secret and access token from environment
or fallback files. Also helpers to create a KiteConnect instance and
verify tokens.

Priorities:
- Environment variables: KITE_API_KEY, KITE_API_SECRET, KITE_ACCESS_TOKEN
- secrets/kite_secrets.json (for API key/secret)
- artifacts/kite_access_token.txt (for token)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Optional

from kiteconnect import KiteConnect


BASE_DIR = Path(__file__).resolve().parents[1]
SECRETS_DIR = BASE_DIR / "secrets"
SECRETS_PATH = SECRETS_DIR / "kite_secrets.json"
SECRETS_ENV_PATH = SECRETS_DIR / "kite.env"
TOK_FILE = SECRETS_DIR / "kite_tokens.env"
ARTIFACTS_PATH = BASE_DIR / "artifacts"
TOKEN_FILE = ARTIFACTS_PATH / "kite_access_token.txt"


def _read_json_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {k.lower(): v for k, v in data.items() if isinstance(v, str)}
    except Exception:
        pass
    return {}


def _read_simple_env(path: Path) -> Dict[str, str]:
    """Read simple KEY=VALUE file (no export)."""
    data: Dict[str, str] = {}
    if not path.exists():
        return data
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()
    except Exception:
        return {}
    return data


def read_kite_api_secrets() -> Dict[str, str]:
    """Return a dict with api_key and api_secret.

    Prefer environment variables KITE_API_KEY and KITE_API_SECRET.
    Fall back to secrets/kite.env or secrets/kite_secrets.json. Raises RuntimeError if not found.
    """
    api_key = os.environ.get("KITE_API_KEY")
    api_secret = os.environ.get("KITE_API_SECRET")
    if api_key and api_secret:
        return {"api_key": api_key, "api_secret": api_secret}

    # try simple env file (kite.env)
    env_file = _read_simple_env(SECRETS_ENV_PATH)
    if env_file:
        api_key = api_key or env_file.get("KITE_API_KEY")
        api_secret = api_secret or env_file.get("KITE_API_SECRET")
        if api_key and api_secret:
            return {"api_key": api_key, "api_secret": api_secret}

    # try secrets file
    cfg = _read_json_file(SECRETS_PATH)
    if cfg:
        api_key = api_key or cfg.get("api_key") or cfg.get("kite_api_key")
        api_secret = api_secret or cfg.get("api_secret") or cfg.get("kite_api_secret")
        if api_key and api_secret:
            return {"api_key": api_key, "api_secret": api_secret}

    raise RuntimeError(
        "Kite API key/secret not found. Set KITE_API_KEY/KITE_API_SECRET or create secrets/kite_secrets.json"
    )


def read_kite_token() -> Optional[str]:
    """Return access token string if present from env or token files; otherwise None."""
    token = os.environ.get("KITE_ACCESS_TOKEN")
    if token:
        return token.strip()

    # secrets/kite_tokens.env
    tok_env = _read_simple_env(TOK_FILE)
    if tok_env.get("KITE_ACCESS_TOKEN"):
        return tok_env["KITE_ACCESS_TOKEN"].strip()

    # fallback token file
    try:
        if TOKEN_FILE.exists():
            with TOKEN_FILE.open("r", encoding="utf-8") as f:
                content = f.read().strip()
            return content or None
    except Exception:
        pass
    return None


def make_kite_client_from_env(reload: bool = False) -> KiteConnect:
    """Create KiteConnect client from env/secrets and set access token when present.

    If API key/secret missing raises RuntimeError. Access token is optional.
    """
    creds = read_kite_api_secrets()
    api_key = creds.get("api_key")
    kite = KiteConnect(api_key=api_key)

    token = read_kite_token()
    if token:
        try:
            kite.set_access_token(token)
        except Exception:
            # Don't raise here – token may be invalid; leave it to token_is_valid
            pass
    return kite


def token_is_valid(kite: KiteConnect) -> bool:
    """Return True if kite.profile() succeeds, False otherwise (no exceptions)."""
    if kite is None:
        return False
    try:
        kite.profile()
        return True
    except Exception:
        return False


def print_loaded_paths(logger) -> None:
    """Log which secrets/token paths are being used (existence only)."""
    logger.info("Kite auth paths: env(KITE_API_KEY)=%s, env(KITE_ACCESS_TOKEN)=%s", bool(os.environ.get("KITE_API_KEY")), bool(os.environ.get("KITE_ACCESS_TOKEN")))
    logger.info("secrets file: %s (exists=%s)", SECRETS_PATH, SECRETS_PATH.exists())
    logger.info("token file: %s (exists=%s)", TOKEN_FILE, TOKEN_FILE.exists())

