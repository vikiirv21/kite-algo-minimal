"""Shared KiteTicker factory using secrets from secrets/*.env."""

from __future__ import annotations

import logging
from kiteconnect import KiteTicker

from core.kite_secrets import get_kite_credentials

logger = logging.getLogger(__name__)


def make_kite_ticker() -> KiteTicker:
    creds = get_kite_credentials()
    api_key = creds.get("api_key")
    access_token = creds.get("access_token")

    if not api_key or not access_token:
        raise RuntimeError("KiteTicker: api_key or access_token missing from secrets.")

    logger.info(
        "KiteTicker: creating ticker with api_key=%s***, access_token=%s***",
        (api_key or "")[:4],
        (access_token or "")[:4],
    )

    return KiteTicker(api_key, access_token)
