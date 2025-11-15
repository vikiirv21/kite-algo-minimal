# core/kite_auth.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass

from kiteconnect import KiteConnect, exceptions as kite_exceptions

# Optional back-compat loaders
try:
    from core.kite_env import load_env_from_files  # type: ignore
except Exception:
    load_env_from_files = None  # type: ignore[misc]

# Fallback to file-based tokens if env missing
try:
    from core.kite_env import read_tokens as _file_read_tokens, read_api_creds as _file_read_api  # type: ignore
except Exception:
    _file_read_tokens = None
    _file_read_api = None

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_ROOT = Path(os.environ.get("KITE_ALGO_ARTIFACTS", BASE_DIR / "artifacts")).expanduser()
TOKEN_FILE_DEFAULT = ARTIFACTS_ROOT / "kite_access_token.txt"

@dataclass
class KiteSecrets:
    api_key: Optional[str]
    api_secret: Optional[str]

def read_kite_api_secrets() -> Dict[str, Optional[str]]:
    """
    Returns {"KITE_API_KEY": ..., "KITE_API_SECRET": ...}
    Prefers env; falls back to file-based creds if available.
    """
    api_key = os.environ.get("KITE_API_KEY")
    api_secret = os.environ.get("KITE_API_SECRET")
    if not api_key and _file_read_api:
        try:
            ak, sk = _file_read_api()
            api_key = api_key or ak
            api_secret = api_secret or sk
        except Exception:
            pass
    if not api_key:
        raise RuntimeError(
            "read_kite_api_secrets: Missing KITE_API_KEY. Ensure env is set or secrets files exist."
        )
    return {"KITE_API_KEY": api_key, "KITE_API_SECRET": api_secret}

def _token_file_path() -> Path:
    p = os.environ.get("KITE_ACCESS_TOKEN_FILE")
    if p:
        return Path(p).expanduser().resolve()
    return TOKEN_FILE_DEFAULT

def read_kite_token() -> Optional[str]:
    """
    Read access token from env → file-based secrets → legacy artifacts token file.
    """
    tok = os.environ.get("KITE_ACCESS_TOKEN")
    if tok:
        return tok.strip()

    if _file_read_tokens:
        try:
            access, _public, _ts, _key = _file_read_tokens()
            if access:
                return access
        except Exception:
            pass

    path = _token_file_path()
    if path.exists():
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            return None
    return None

def make_kite_client_from_env(*, reload: bool = False) -> KiteConnect:
    if reload and load_env_from_files:
        try:
            load_env_from_files()  # set env via setdefault
        except Exception:
            pass

    secrets = read_kite_api_secrets()
    api_key = secrets["KITE_API_KEY"]
    if not api_key:
        raise RuntimeError("KITE_API_KEY is required.")

    kite = KiteConnect(api_key=api_key)
    token = read_kite_token()
    if token:
        try:
            kite.set_access_token(token)
        except Exception:
            pass
    return kite

def token_is_valid(kite: KiteConnect) -> bool:
    try:
        _ = kite.profile()
        return True
    except kite_exceptions.TokenException:
        return False
    except Exception:
        return False

def print_loaded_paths(logger) -> None:
    try:
        token_path = _token_file_path()
        logger.info("Artifacts root: %s", str(ARTIFACTS_ROOT))
        logger.info("Access token file: %s (exists=%s)", str(token_path), token_path.exists())
    except Exception:
        pass

__all__ = [
    "read_kite_api_secrets",
    "read_kite_token",
    "make_kite_client_from_env",
    "token_is_valid",
    "print_loaded_paths",
]
