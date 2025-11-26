"""
Capital Provider - Abstracts capital retrieval for LIVE and PAPER modes.

In LIVE mode, fetches real-time capital from Kite API via margins("equity").
In PAPER mode, uses config-based paper_capital.

This ensures position sizing uses accurate capital at trade time.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from kiteconnect import KiteConnect
from broker.auth import make_kite_client_from_env, token_is_valid

logger = logging.getLogger(__name__)


class CapitalProvider(ABC):
    """Abstract base class for capital providers."""

    @abstractmethod
    def get_available_capital(self) -> float:
        """
        Get the current available capital for trading.

        Returns:
            Available capital in rupees
        """
        pass

    @abstractmethod
    def refresh(self) -> float:
        """
        Force refresh capital from source and return updated value.

        Returns:
            Refreshed available capital in rupees
        """
        pass


class ConfigCapitalProvider(CapitalProvider):
    """
    Capital provider for PAPER mode.

    Uses static capital from config (paper_capital or live_capital).
    """

    def __init__(self, capital: float) -> None:
        """
        Initialize with static capital value.

        Args:
            capital: Capital value from config
        """
        self._capital = float(capital)
        logger.info("ConfigCapitalProvider initialized with capital=%.2f", self._capital)

    def get_available_capital(self) -> float:
        """Return configured capital."""
        return self._capital

    def refresh(self) -> float:
        """No-op for config-based capital. Returns current value."""
        return self._capital

    def set_capital(self, capital: float) -> None:
        """
        Update capital (e.g., after PnL calculations).

        Args:
            capital: New capital value
        """
        self._capital = float(capital)


class LiveCapitalProvider(CapitalProvider):
    """
    Capital provider for LIVE mode.

    Fetches real-time available capital from Kite API via margins("equity").
    Caches the value and allows forced refresh.
    """

    def __init__(
        self,
        fallback_capital: float = 0.0,
        cache_ttl_seconds: float = 30.0,
    ) -> None:
        """
        Initialize LiveCapitalProvider using the shared auth helper.

        Args:
            fallback_capital: Capital to use if API call fails
            cache_ttl_seconds: How long to cache capital before auto-refresh
        """
        self._fallback_capital = float(fallback_capital)
        self._cache_ttl = cache_ttl_seconds
        self._cached_capital: Optional[float] = None
        self._last_fetch_time: float = 0.0
        self._using_fallback: bool = False
        self._last_error: Optional[str] = None
        self._kite: Optional[KiteConnect] = None

        # Build client using shared auth helper
        try:
            self._kite = make_kite_client_from_env()
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "LiveCapitalProvider: failed to build Kite client: %s. "
                "Falling back to config capital.",
                exc,
            )
            self._kite = None
            return

        if self._kite is None:
            logger.warning(
                "LiveCapitalProvider: no Kite client available from make_kite_client_from_env; "
                "falling back to config capital"
            )
            return

        # Optionally do a lightweight margins() call here, but do not crash if it fails
        try:
            margins = self._kite.margins("equity")
            # If this succeeds, we can mark that broker-based capital works
            self._using_fallback = False
            logger.debug("LiveCapitalProvider: margins() sanity check passed")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "LiveCapitalProvider: margins() sanity check failed in constructor: %s. "
                "Will try again lazily; starting with fallback capital.",
                exc,
            )
            self._using_fallback = True
            self._last_error = str(exc)

        logger.info(
            "LiveCapitalProvider initialized (fallback=%.2f, cache_ttl=%.1fs, kite=%s)",
            self._fallback_capital,
            self._cache_ttl,
            "OK" if self._kite else "None",
        )

    @classmethod
    def from_shared_auth(
        cls,
        *,
        fallback_capital: float,
        cache_ttl_seconds: float = 30.0,
    ) -> "LiveCapitalProvider":
        """Factory that reuses shared auth helper (now same as default constructor)."""
        return cls(
            fallback_capital=fallback_capital,
            cache_ttl_seconds=cache_ttl_seconds,
        )

    def get_client(self) -> Optional[KiteConnect]:
        """Return the Kite client (or None if not available)."""
        return self._kite

    def get_available_capital(self) -> float:
        """
        Get available capital, using cache if fresh.

        Returns:
            Available capital from Kite API or fallback
        """
        now = time.time()
        if (
            self._cached_capital is not None
            and (now - self._last_fetch_time) < self._cache_ttl
        ):
            return self._cached_capital

        return self.refresh()

    def refresh(self) -> float:
        """
        Force fetch fresh capital from Kite API.

        Returns:
            Available capital from Kite margins("equity") API
        """
        if self._kite is None:
            logger.error(
                "LiveCapitalProvider: no Kite client available. "
                "Run `python -m scripts.run_day --login --engines none` and retry. Using fallback=%.2f",
                self._fallback_capital,
            )
            self._using_fallback = True
            self._last_error = "no_kite_client"
            return self._fallback_capital

        try:
            from core.kite_http import kite_request

            funds = kite_request(self._kite.margins, "equity")

            # Extract available capital from response
            # Response structure: {"equity": {"net": <float>, "available": {...}, "utilised": {...}}}
            # or direct: {"net": <float>, ...}
            snapshot = funds.get("equity") if isinstance(funds, dict) and "equity" in funds else funds
            if not isinstance(snapshot, dict):
                snapshot = {}

            # "net" is the total available margin after all utilizations
            available = self._safe_float(snapshot.get("net"))

            if available > 0:
                self._cached_capital = available
                self._last_fetch_time = time.time()
                self._using_fallback = False
                self._last_error = None
                logger.debug("LiveCapitalProvider: fetched capital=%.2f", available)
                return available

            # Fallback: compute from available.cash if net is zero
            available_dict = snapshot.get("available") or {}
            if isinstance(available_dict, dict):
                cash = self._safe_float(available_dict.get("cash"))
                if cash > 0:
                    self._cached_capital = cash
                    self._last_fetch_time = time.time()
                    self._using_fallback = False
                    self._last_error = None
                    logger.debug("LiveCapitalProvider: fallback to cash=%.2f", cash)
                    return cash

            logger.warning(
                "LiveCapitalProvider: Could not extract capital from margins response, using fallback=%.2f",
                self._fallback_capital,
            )
            self._using_fallback = True
            self._last_error = "could_not_extract_margins"
            return self._fallback_capital

        except Exception as exc:
            logger.error(
                "LiveCapitalProvider: margins() failed (%s). This usually means the access token is invalid or expired. "
                "Run `python -m scripts.run_day --login --engines none` and retry. Using fallback=%.2f",
                exc,
                self._fallback_capital,
            )
            self._using_fallback = True
            self._last_error = str(exc)
            return self._fallback_capital

    def invalidate_cache(self) -> None:
        """Invalidate cached capital, forcing next get to refresh."""
        self._cached_capital = None
        self._last_fetch_time = 0.0

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        """Safely convert value to float."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @property
    def capital_source(self) -> str:
        return "fallback" if self._using_fallback else "broker"

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error


def create_capital_provider(
    mode: str,
    kite: Optional[KiteConnect] = None,
    config_capital: float = 500000.0,
    cache_ttl_seconds: float = 30.0,
) -> CapitalProvider:
    """
    Factory function to create the appropriate capital provider.

    Args:
        mode: Trading mode - "LIVE" or "PAPER"
        kite: KiteConnect instance (deprecated, ignored; provider builds its own)
        config_capital: Fallback/default capital from config
        cache_ttl_seconds: Cache TTL for live capital provider

    Returns:
        CapitalProvider instance
    """
    mode_upper = mode.upper()

    if mode_upper == "LIVE":
        # Build LiveCapitalProvider using shared auth helper
        provider = LiveCapitalProvider(
            fallback_capital=config_capital,
            cache_ttl_seconds=cache_ttl_seconds,
        )
        if provider._kite is None:
            logger.warning(
                "LIVE mode requested but no valid Kite client available; falling back to config capital"
            )
            return ConfigCapitalProvider(config_capital)
        return provider

    # PAPER mode or unknown - use config capital
    return ConfigCapitalProvider(config_capital)
