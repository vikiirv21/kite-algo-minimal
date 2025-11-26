# core/kite_env.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone
import io
import os
import tempfile
import logging

from kiteconnect import KiteConnect, exceptions as kite_exceptions

# ---------- Paths ----------
BASE_DIR = Path(__file__).resolve().parents[1]
SECRETS_DIR = BASE_DIR / "secrets"
API_FILE = SECRETS_DIR / "kite.env"
TOK_FILE = SECRETS_DIR / "kite_tokens.env"
CONFIG_HINT = BASE_DIR / "configs" / "dev.yaml"  # just for logging

_log = logging.getLogger(__name__)

# ---------- Utilities ----------
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

def _atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent), encoding=encoding) as tmp:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)

# ---------- Public API (file-only; NO os.environ at runtime) ----------
def read_api_creds() -> Tuple[str, str]:
    cfg = _read_simple_env(API_FILE)
    api_key = cfg.get("KITE_API_KEY")
    api_secret = cfg.get("KITE_API_SECRET")
    if not api_key or not api_secret:
        raise RuntimeError(
            f"Missing KITE_API_KEY/KITE_API_SECRET in {API_FILE}. "
            f"Populate {API_FILE} before running."
        )
    return api_key, api_secret

def read_tokens() -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Returns: (access_token, public_token, login_ts_iso, token_api_key)
    Accepts KITE_LOGIN_TS or legacy KITE_LOGIN_AT for timestamp.
    """
    tok = _read_simple_env(TOK_FILE)
    ts = tok.get("KITE_LOGIN_TS") or tok.get("KITE_LOGIN_AT")
    token_api_key = tok.get("KITE_TOKEN_API_KEY")
    return (
        tok.get("KITE_ACCESS_TOKEN") or None,
        tok.get("KITE_PUBLIC_TOKEN") or None,
        ts or None,
        token_api_key,
    )

def write_token(
    access_token: str,
    public_token: Optional[str] = None,
    login_ts_iso: Optional[str] = None,
    api_key_for_token: Optional[str] = None,
) -> None:
    """
    Write tokens to TOK_FILE (atomic).
    - access_token: required
    - public_token: optional
    - login_ts_iso: optional; default is current UTC ISO
    - api_key_for_token: optional; records which API key minted this token
    """
    if not access_token:
        raise ValueError("access_token is required")

    if not login_ts_iso:
        login_ts_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    buf = io.StringIO()
    buf.write(f"KITE_ACCESS_TOKEN={access_token}\n")
    buf.write(f"KITE_PUBLIC_TOKEN={(public_token or '')}\n")
    buf.write(f"KITE_LOGIN_TS={login_ts_iso}\n")
    if api_key_for_token:
        buf.write(f"KITE_TOKEN_API_KEY={api_key_for_token}\n")
    _atomic_write_text(TOK_FILE, buf.getvalue())

def make_kite_client_from_files(timeout: int = 7) -> KiteConnect:
    api_key, _api_secret = read_api_creds()
    access_token, _public_token, _login_ts, token_api_key = read_tokens()
    if not access_token:
        raise RuntimeError(f"No KITE_ACCESS_TOKEN in {TOK_FILE}. Run your login flow to obtain it.")

    # Fail fast if the token was minted for a different API key
    if token_api_key and token_api_key != api_key:
        raise RuntimeError(
            f"Token belongs to API key {token_api_key}, but current API key is {api_key}. Re-login with the active key."
        )

    kite = KiteConnect(api_key=api_key, timeout=timeout)
    kite.set_access_token(access_token)
    return kite

def describe_creds_for_logs() -> str:
    api_key, _ = read_api_creds()
    access_token, public_token, login_ts, token_api_key = read_tokens()
    return (
        f"Loaded from files: API_KEY={'***' if api_key else 'MISSING'}, "
        f"ACCESS_TOKEN={'set' if access_token else 'MISSING'}, "
        f"PUBLIC_TOKEN={'set' if public_token else 'MISSING'}, "
        f"LOGIN_TS={login_ts or 'NA'}, "
        f"TOKEN_API_KEY={token_api_key or 'NA'}"
    )

# ---------- Compatibility helpers ----------
def load_env_from_files() -> Dict[str, Optional[str]]:
    api_key, api_secret = None, None
    try:
        api_key, api_secret = read_api_creds()
    except Exception:
        api_key, api_secret = None, None

    access_token, public_token, login_ts, _token_key = read_tokens()

    if api_key:
        os.environ.setdefault("KITE_API_KEY", api_key)
    if api_secret:
        os.environ.setdefault("KITE_API_SECRET", api_secret)
    if access_token:
        os.environ.setdefault("KITE_ACCESS_TOKEN", access_token)

    return {
        "api_key": api_key,
        "api_secret": api_secret,
        "access_token": access_token,
        "public_token": public_token,
        "login_ts": login_ts,
    }

# --- Helpers expected by dashboard ---
def read_kite_api_secrets() -> Dict[str, str]:
    api_key, api_secret = read_api_creds()
    return {"KITE_API_KEY": api_key, "KITE_API_SECRET": api_secret}

def read_kite_token() -> Optional[str]:
    access_token, _public, _ts, _token_key = read_tokens()
    return access_token

def make_kite_client_from_env(reload: bool = False, timeout: int = 7) -> KiteConnect:
    return make_kite_client_from_files(timeout=timeout)

def token_is_valid(kite: KiteConnect) -> bool:
    try:
        kite.profile()
        return True
    except kite_exceptions.TokenException:
        return False
    except Exception as exc:
        _log.debug("token_is_valid: non-fatal error: %s", exc)
        return False

def print_loaded_paths(logger: Optional[logging.Logger] = None) -> None:
    lg = logger or _log
    lg.info("BASE_DIR=%s", BASE_DIR)
    lg.info("SECRETS_DIR=%s", SECRETS_DIR)
    lg.info("API_FILE=%s", API_FILE)
    lg.info("TOK_FILE=%s", TOK_FILE)
    if CONFIG_HINT.exists():
        lg.info("CONFIG (hint)=%s", CONFIG_HINT)
    lg.info(describe_creds_for_logs())

def interactive_login_files() -> None:
    raise RuntimeError(
        "Interactive Kite login not available via core.kite_env.interactive_login_files().\n"
        "Please run `python -m scripts.login_kite` or implement the login flow."
    )

def interactive_login() -> None:
    return interactive_login_files()
