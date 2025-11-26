"""
Shared Kite client factory using secrets/kite.env and secrets/kite_tokens.env.
"""

from __future__ import annotations

from typing import Optional

from kiteconnect import KiteConnect

from core.kite_secrets import get_kite_credentials


def make_kite_client(
    api_key: Optional[str] = None,
    access_token: Optional[str] = None,
) -> KiteConnect:
    """
    Create a KiteConnect client using secrets by default.

    Args:
        api_key: Optional override for API key
        access_token: Optional override for access token

    Returns:
        Authenticated KiteConnect instance (access token set)
    """
    creds = get_kite_credentials()
    api_key = api_key or creds.get("api_key")
    access_token = access_token or creds.get("access_token")

    if not api_key:
        raise RuntimeError("Kite API key not found. Populate secrets/kite.env (KITE_API_KEY).")
    if not access_token:
        raise RuntimeError("Kite access token not found. Run `python -m scripts.run_day --login --engines none`.")

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite
