"""
Market Context Layer

Provides broad market awareness for trading strategies through:
1. India VIX regime classification
2. Market breadth metrics (advances/declines, % above EMAs)
3. Symbol relative volume

Design principles:
- Conservative: Only adds filters, never loosens rules
- Configurable: All features can be enabled/disabled
- Robust: Graceful fallback when data unavailable
- Non-breaking: Works alongside existing strategies
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MarketContext:
    """
    Comprehensive market context snapshot.
    
    Provides broad market metrics to inform strategy decisions.
    All fields have safe defaults for graceful degradation.
    """
    # VIX metrics
    vix_value: float = 0.0
    vix_regime: str = "unknown"  # "low", "normal", "high", "panic", "unknown"
    
    # Breadth metrics
    advances: int = 0
    declines: int = 0
    unchanged: int = 0
    pct_above_20ema: float = 0.0  # % of universe above 20 EMA
    pct_above_50ema: float = 0.0  # % of universe above 50 EMA
    
    # Relative volume (per symbol)
    symbol_rvol: Dict[str, float] = field(default_factory=dict)
    
    # Timestamp
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Metadata
    valid: bool = True  # False if context could not be computed
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "vix_value": self.vix_value,
            "vix_regime": self.vix_regime,
            "advances": self.advances,
            "declines": self.declines,
            "unchanged": self.unchanged,
            "pct_above_20ema": self.pct_above_20ema,
            "pct_above_50ema": self.pct_above_50ema,
            "symbol_rvol": self.symbol_rvol,
            "timestamp": self.timestamp.isoformat(),
            "valid": self.valid,
            "errors": self.errors,
        }


@dataclass
class MarketContextConfig:
    """Configuration for MarketContext computation."""
    enabled: bool = False
    
    # VIX configuration
    vix_enabled: bool = True
    vix_symbol: str = "INDIA VIX"
    vix_low_threshold: float = 12.0
    vix_normal_threshold: float = 18.0
    vix_high_threshold: float = 25.0
    vix_panic_threshold: float = 35.0
    
    # Breadth configuration
    breadth_enabled: bool = True
    breadth_universe: str = "NIFTY50"  # Which universe to compute breadth for
    breadth_ema_periods: List[int] = field(default_factory=lambda: [20, 50])
    
    # Relative volume configuration
    rvol_enabled: bool = True
    rvol_lookback_periods: int = 20  # Average volume over N periods
    rvol_min_threshold: float = 0.7  # Minimum RVOL for entries
    
    # Filter configuration
    block_shorts_on_panic: bool = True
    require_stronger_edge_on_weak_breadth: bool = True
    skip_low_rvol: bool = True
    
    @classmethod
    def from_dict(cls, cfg: Optional[Dict[str, Any]]) -> "MarketContextConfig":
        """Create config from dictionary."""
        if not cfg:
            return cls()
        
        # Extract nested configs
        vix_cfg = cfg.get("vix", {})
        breadth_cfg = cfg.get("breadth", {})
        rvol_cfg = cfg.get("relative_volume", {})
        filters_cfg = cfg.get("filters", {})
        
        return cls(
            enabled=cfg.get("enabled", False),
            # VIX
            vix_enabled=vix_cfg.get("enabled", True),
            vix_symbol=vix_cfg.get("symbol", "INDIA VIX"),
            vix_low_threshold=float(vix_cfg.get("low_threshold", 12.0)),
            vix_normal_threshold=float(vix_cfg.get("normal_threshold", 18.0)),
            vix_high_threshold=float(vix_cfg.get("high_threshold", 25.0)),
            vix_panic_threshold=float(vix_cfg.get("panic_threshold", 35.0)),
            # Breadth
            breadth_enabled=breadth_cfg.get("enabled", True),
            breadth_universe=breadth_cfg.get("universe", "NIFTY50"),
            breadth_ema_periods=breadth_cfg.get("ema_periods", [20, 50]),
            # RVOL
            rvol_enabled=rvol_cfg.get("enabled", True),
            rvol_lookback_periods=int(rvol_cfg.get("lookback_periods", 20)),
            rvol_min_threshold=float(rvol_cfg.get("min_rvol", 0.7)),
            # Filters
            block_shorts_on_panic=filters_cfg.get("block_shorts_on_panic", True),
            require_stronger_edge_on_weak_breadth=filters_cfg.get("require_stronger_edge_on_weak_breadth", True),
            skip_low_rvol=filters_cfg.get("skip_low_rvol", True),
        )


class MarketContextBuilder:
    """
    Builder for MarketContext.
    
    Computes market-wide metrics from various data sources.
    """
    
    def __init__(
        self,
        config: MarketContextConfig,
        kite_client: Optional[Any] = None,
        market_data_engine: Optional[Any] = None,
        logger_instance: Optional[logging.Logger] = None,
    ):
        """
        Initialize MarketContextBuilder.
        
        Args:
            config: MarketContextConfig instance
            kite_client: Optional KiteConnect client for VIX data
            market_data_engine: Optional MarketDataEngine for price/volume data
            logger_instance: Optional logger instance
        """
        self.config = config
        self.kite = kite_client
        self.mde = market_data_engine
        self.logger = logger_instance or logger
        
        # Cache for performance
        self._vix_cache: Optional[float] = None
        self._vix_cache_time: Optional[datetime] = None
        self._vix_cache_ttl_seconds = 60  # Cache VIX for 60 seconds
        
        self.logger.info(
            "MarketContextBuilder initialized: enabled=%s, vix=%s, breadth=%s, rvol=%s",
            self.config.enabled,
            self.config.vix_enabled,
            self.config.breadth_enabled,
            self.config.rvol_enabled,
        )
    
    def build(self, symbols: Optional[List[str]] = None) -> MarketContext:
        """
        Build MarketContext snapshot.
        
        Args:
            symbols: Optional list of symbols for RVOL computation
        
        Returns:
            MarketContext with current market metrics
        """
        if not self.config.enabled:
            # Return minimal context when disabled
            return MarketContext(
                valid=False,
                errors=["market_context_disabled"],
            )
        
        context = MarketContext()
        errors = []
        
        # 1. Compute VIX regime
        if self.config.vix_enabled:
            try:
                vix_value, vix_regime = self._compute_vix_regime()
                context.vix_value = vix_value
                context.vix_regime = vix_regime
            except Exception as exc:
                self.logger.warning("Failed to compute VIX regime: %s", exc)
                errors.append(f"vix_error: {exc}")
                context.vix_regime = "unknown"
        
        # 2. Compute market breadth
        if self.config.breadth_enabled:
            try:
                breadth = self._compute_breadth()
                context.advances = breadth["advances"]
                context.declines = breadth["declines"]
                context.unchanged = breadth["unchanged"]
                context.pct_above_20ema = breadth.get("pct_above_20ema", 0.0)
                context.pct_above_50ema = breadth.get("pct_above_50ema", 0.0)
            except Exception as exc:
                self.logger.warning("Failed to compute breadth: %s", exc)
                errors.append(f"breadth_error: {exc}")
        
        # 3. Compute relative volume
        if self.config.rvol_enabled and symbols:
            try:
                rvol_map = self._compute_relative_volume(symbols)
                context.symbol_rvol = rvol_map
            except Exception as exc:
                self.logger.warning("Failed to compute relative volume: %s", exc)
                errors.append(f"rvol_error: {exc}")
        
        context.timestamp = datetime.now(timezone.utc)
        context.errors = errors
        context.valid = len(errors) == 0
        
        if not context.valid:
            self.logger.debug("MarketContext built with errors: %s", errors)
        
        return context
    
    def _compute_vix_regime(self) -> tuple[float, str]:
        """
        Compute India VIX regime.
        
        Returns:
            (vix_value, regime) where regime is "low", "normal", "high", "panic", or "unknown"
        """
        # Check cache first
        now = datetime.now(timezone.utc)
        if self._vix_cache is not None and self._vix_cache_time:
            age = (now - self._vix_cache_time).total_seconds()
            if age < self._vix_cache_ttl_seconds:
                return self._vix_cache, self._classify_vix_regime(self._vix_cache)
        
        # Try to fetch VIX from Kite
        vix_value = self._fetch_india_vix()
        
        if vix_value is None:
            # Fallback: Try to get from market data engine
            if self.mde:
                try:
                    # Try common VIX symbol variations
                    for symbol in ["INDIA VIX", "INDIAVIX", "NSE:INDIA VIX"]:
                        try:
                            quote = self.mde.get_quote(symbol)
                            if quote and "last_price" in quote:
                                vix_value = float(quote["last_price"])
                                break
                        except Exception:
                            continue
                except Exception as exc:
                    self.logger.debug("Could not get VIX from MDE: %s", exc)
        
        if vix_value is None:
            # Final fallback: Use neutral default
            self.logger.warning("Could not fetch India VIX, using neutral regime")
            return 0.0, "unknown"
        
        # Cache the value
        self._vix_cache = vix_value
        self._vix_cache_time = now
        
        regime = self._classify_vix_regime(vix_value)
        return vix_value, regime
    
    def _fetch_india_vix(self) -> Optional[float]:
        """
        Fetch India VIX value from Kite API.
        
        Returns:
            VIX value or None if unavailable
        """
        if not self.kite:
            return None
        
        try:
            # India VIX instrument token (NSE)
            # Note: This may need to be looked up via instruments API
            # For now, try common approaches
            
            # Method 1: Try quote API
            try:
                quotes = self.kite.quote(["NSE:INDIA VIX"])
                if quotes and "NSE:INDIA VIX" in quotes:
                    return float(quotes["NSE:INDIA VIX"]["last_price"])
            except Exception as exc:
                self.logger.debug("VIX quote method 1 failed: %s", exc)
            
            # Method 2: Try alternate symbol
            try:
                quotes = self.kite.quote(["NSE:INDIAVIX"])
                if quotes and "NSE:INDIAVIX" in quotes:
                    return float(quotes["NSE:INDIAVIX"]["last_price"])
            except Exception as exc:
                self.logger.debug("VIX quote method 2 failed: %s", exc)
            
            return None
            
        except Exception as exc:
            self.logger.debug("Failed to fetch India VIX: %s", exc)
            return None
    
    def _classify_vix_regime(self, vix_value: float) -> str:
        """
        Classify VIX regime based on thresholds.
        
        Args:
            vix_value: Current VIX value
        
        Returns:
            Regime classification
        """
        if vix_value <= 0:
            return "unknown"
        elif vix_value < self.config.vix_low_threshold:
            return "low"
        elif vix_value < self.config.vix_normal_threshold:
            return "normal"
        elif vix_value < self.config.vix_high_threshold:
            return "high"
        elif vix_value < self.config.vix_panic_threshold:
            return "very_high"
        else:
            return "panic"
    
    def _compute_breadth(self) -> Dict[str, Any]:
        """
        Compute market breadth metrics.
        
        Returns:
            Dict with advances, declines, unchanged, pct_above_20ema, pct_above_50ema
        """
        if not self.mde:
            # No data source, return zeros
            return {
                "advances": 0,
                "declines": 0,
                "unchanged": 0,
                "pct_above_20ema": 0.0,
                "pct_above_50ema": 0.0,
            }
        
        # Get universe symbols based on config
        universe_symbols = self._get_breadth_universe()
        
        if not universe_symbols:
            self.logger.warning("No symbols in breadth universe: %s", self.config.breadth_universe)
            return {
                "advances": 0,
                "declines": 0,
                "unchanged": 0,
                "pct_above_20ema": 0.0,
                "pct_above_50ema": 0.0,
            }
        
        advances = 0
        declines = 0
        unchanged = 0
        above_20ema = 0
        above_50ema = 0
        valid_count = 0
        
        for symbol in universe_symbols:
            try:
                # Get latest candle and indicators
                candle = self.mde.get_latest_candle(symbol, "5m")
                if not candle:
                    continue
                
                close = candle.get("close", 0.0)
                open_price = candle.get("open", 0.0)
                
                if close <= 0 or open_price <= 0:
                    continue
                
                valid_count += 1
                
                # Advance/Decline logic
                if close > open_price * 1.001:  # Up > 0.1%
                    advances += 1
                elif close < open_price * 0.999:  # Down > 0.1%
                    declines += 1
                else:
                    unchanged += 1
                
                # Check EMAs
                # Get window for EMA computation
                window = self.mde.get_window(symbol, "5m", 60)
                if window and len(window) >= 50:
                    closes = [c["close"] for c in window]
                    
                    # Compute EMAs
                    from core.indicators import ema
                    
                    try:
                        ema20 = ema(closes, 20)
                        if close > ema20:
                            above_20ema += 1
                    except Exception:
                        pass
                    
                    try:
                        ema50 = ema(closes, 50)
                        if close > ema50:
                            above_50ema += 1
                    except Exception:
                        pass
                
            except Exception as exc:
                self.logger.debug("Error processing symbol %s for breadth: %s", symbol, exc)
                continue
        
        # Compute percentages
        if valid_count > 0:
            pct_20 = (above_20ema / valid_count) * 100.0
            pct_50 = (above_50ema / valid_count) * 100.0
        else:
            pct_20 = 0.0
            pct_50 = 0.0
        
        return {
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged,
            "pct_above_20ema": pct_20,
            "pct_above_50ema": pct_50,
        }
    
    def _get_breadth_universe(self) -> List[str]:
        """
        Get list of symbols for breadth computation.
        
        Returns:
            List of symbol strings
        """
        # This would ideally load from a universe config or file
        # For now, return a placeholder list
        
        if self.config.breadth_universe == "NIFTY50":
            # Placeholder: In production, load from config/universe_nifty50.csv
            # or fetch from Kite API indices
            return [
                "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
                "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
                # ... would include all 50 symbols
            ]
        elif self.config.breadth_universe == "NIFTY100":
            # Placeholder
            return []
        else:
            # Try to get from MDE if available
            if self.mde and hasattr(self.mde, "get_universe"):
                try:
                    return self.mde.get_universe()
                except Exception:
                    pass
            return []
    
    def _compute_relative_volume(self, symbols: List[str]) -> Dict[str, float]:
        """
        Compute relative volume for each symbol.
        
        Relative volume = current_volume / avg_volume(N periods)
        
        Args:
            symbols: List of symbols to compute RVOL for
        
        Returns:
            Dict mapping symbol -> RVOL
        """
        if not self.mde:
            return {}
        
        rvol_map = {}
        
        for symbol in symbols:
            try:
                # Get window of candles
                window = self.mde.get_window(symbol, "5m", self.config.rvol_lookback_periods + 1)
                
                if not window or len(window) < 2:
                    continue
                
                # Current volume
                current_volume = window[-1].get("volume", 0.0)
                
                if current_volume <= 0:
                    continue
                
                # Average volume over lookback period (excluding current)
                volumes = [c.get("volume", 0.0) for c in window[:-1]]
                avg_volume = sum(volumes) / len(volumes) if volumes else 1.0
                
                if avg_volume <= 0:
                    avg_volume = 1.0
                
                rvol = current_volume / avg_volume
                rvol_map[symbol] = rvol
                
            except Exception as exc:
                self.logger.debug("Error computing RVOL for %s: %s", symbol, exc)
                continue
        
        return rvol_map
    
    def should_allow_entry(
        self,
        context: MarketContext,
        symbol: str,
        signal: str,
        confidence: float,
    ) -> tuple[bool, str]:
        """
        Check if entry should be allowed based on market context.
        
        Args:
            context: Current MarketContext
            symbol: Trading symbol
            signal: "BUY" or "SELL"
            confidence: Signal confidence (0-1)
        
        Returns:
            (allowed, reason) tuple
        """
        if not self.config.enabled:
            return True, "context_disabled"
        
        # VIX filter: Block shorts on panic
        if self.config.block_shorts_on_panic:
            if signal in ["SELL", "SHORT"] and context.vix_regime in ["panic", "very_high"]:
                return False, f"vix_{context.vix_regime}_no_shorts"
        
        # Breadth filter: Require stronger edge when breadth is weak
        if self.config.require_stronger_edge_on_weak_breadth:
            if signal in ["BUY", "LONG"] and context.pct_above_20ema < 30.0:
                # Market breadth is weak (< 30% above 20 EMA)
                # Require higher confidence
                if confidence < 0.7:
                    return False, "weak_breadth_low_confidence"
        
        # RVOL filter: Skip low relative volume entries
        if self.config.skip_low_rvol:
            rvol = context.symbol_rvol.get(symbol, 1.0)
            if rvol < self.config.rvol_min_threshold:
                return False, f"low_rvol_{rvol:.2f}"
        
        return True, "context_ok"


# Singleton instance for global access
_global_builder: Optional[MarketContextBuilder] = None


def initialize_market_context(
    config: Dict[str, Any],
    kite_client: Optional[Any] = None,
    market_data_engine: Optional[Any] = None,
) -> MarketContextBuilder:
    """
    Initialize global MarketContextBuilder.
    
    Args:
        config: Application config dict
        kite_client: Optional KiteConnect client
        market_data_engine: Optional MarketDataEngine
    
    Returns:
        Initialized MarketContextBuilder
    """
    global _global_builder
    
    mc_config = MarketContextConfig.from_dict(config.get("market_context"))
    _global_builder = MarketContextBuilder(
        config=mc_config,
        kite_client=kite_client,
        market_data_engine=market_data_engine,
    )
    
    return _global_builder


def get_market_context_builder() -> Optional[MarketContextBuilder]:
    """Get the global MarketContextBuilder instance."""
    return _global_builder


def build_market_context(symbols: Optional[List[str]] = None) -> MarketContext:
    """
    Build MarketContext using global builder.
    
    Args:
        symbols: Optional list of symbols for RVOL
    
    Returns:
        MarketContext snapshot
    """
    if _global_builder is None:
        # Return minimal context if not initialized
        return MarketContext(
            valid=False,
            errors=["market_context_not_initialized"],
        )
    
    return _global_builder.build(symbols)
