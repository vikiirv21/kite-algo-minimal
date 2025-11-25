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
        kite: KiteConnect,
        fallback_capital: float = 0.0,
        cache_ttl_seconds: float = 30.0,
    ) -> None:
        """
        Initialize with Kite client.

        Args:
            kite: Authenticated KiteConnect instance
            fallback_capital: Capital to use if API call fails
            cache_ttl_seconds: How long to cache capital before auto-refresh
        """
        self._kite = kite
        self._fallback_capital = float(fallback_capital)
        self._cache_ttl = cache_ttl_seconds
        self._cached_capital: Optional[float] = None
        self._last_fetch_time: float = 0.0
        logger.info(
            "LiveCapitalProvider initialized (fallback=%.2f, cache_ttl=%.1fs)",
            self._fallback_capital,
            self._cache_ttl,
        )

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
                logger.debug("LiveCapitalProvider: fetched capital=%.2f", available)
                return available

            # Fallback: compute from available.cash if net is zero
            available_dict = snapshot.get("available") or {}
            if isinstance(available_dict, dict):
                cash = self._safe_float(available_dict.get("cash"))
                if cash > 0:
                    self._cached_capital = cash
                    self._last_fetch_time = time.time()
                    logger.debug("LiveCapitalProvider: fallback to cash=%.2f", cash)
                    return cash

            logger.warning(
                "LiveCapitalProvider: Could not extract capital from margins response, using fallback=%.2f",
                self._fallback_capital,
            )
            return self._fallback_capital

        except Exception as exc:
            logger.error(
                "LiveCapitalProvider: Failed to fetch margins: %s, using fallback=%.2f",
                exc,
                self._fallback_capital,
            )
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
        kite: KiteConnect instance (required for LIVE mode)
        config_capital: Fallback/default capital from config
        cache_ttl_seconds: Cache TTL for live capital provider

    Returns:
        CapitalProvider instance
    """
    mode_upper = mode.upper()

    if mode_upper == "LIVE":
        if kite is None:
            logger.warning(
                "LIVE mode requested but no Kite client provided, falling back to config capital"
            )
            return ConfigCapitalProvider(config_capital)

        return LiveCapitalProvider(
            kite=kite,
            fallback_capital=config_capital,
            cache_ttl_seconds=cache_ttl_seconds,
        )

    # PAPER mode or unknown - use config capital
    return ConfigCapitalProvider(config_capital)
