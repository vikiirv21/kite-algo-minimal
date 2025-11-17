from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.universe import load_equity_universe
from data.universe.nifty_lists import get_equity_universe_from_indices

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"

# Penny stock threshold (₹)
PENNY_STOCK_THRESHOLD = 20.0
# Minimum lot size for equity
MIN_LOT_SIZE = 1


def filter_low_price_equities(symbols: List[str], min_price: float, kite: Any) -> List[str]:
    """
    Filter out low-priced equities based on current LTP or last close.
    
    Args:
        symbols: List of equity symbols to filter
        min_price: Minimum price threshold
        kite: Kite client for fetching LTP
        
    Returns:
        Filtered list of symbols with price >= min_price
    """
    if not symbols or min_price <= 0:
        return symbols
    
    filtered: List[str] = []
    
    # Batch fetch LTP for all symbols to avoid hammering API
    try:
        # Construct instrument keys for NSE
        instrument_keys = [f"NSE:{symbol}" for symbol in symbols]
        ltp_data = kite.ltp(instrument_keys)
        
        for symbol in symbols:
            key = f"NSE:{symbol}"
            data = ltp_data.get(key, {})
            last_price = data.get("last_price", 0.0)
            
            if last_price >= min_price:
                filtered.append(symbol)
            else:
                logger.debug(
                    "Filtered out %s (price=%.2f < min_price=%.2f)",
                    symbol,
                    last_price,
                    min_price,
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to fetch LTP for price filtering, returning unfiltered list: %s",
            exc,
        )
        return symbols
    
    return filtered


def build_equity_universe(cfg: Dict[str, Any], kite: Any) -> List[str]:
    """
    Build the equity universe based on configuration.
    
    Args:
        cfg: Configuration dictionary
        kite: Kite client for fetching LTP (used for price filtering)
        
    Returns:
        List of equity symbols to trade
    """
    trading = cfg.get("trading", {})
    eu_cfg = trading.get("equity_universe_config") or {}
    mode = (eu_cfg.get("mode") or "all").lower()
    
    if mode == "nifty_lists":
        # Use NIFTY lists mode
        indices = eu_cfg.get("include_indices") or ["NIFTY50"]
        symbols = get_equity_universe_from_indices(indices)
        
        logger.info(
            "Building equity universe from indices=%s, found %d symbols",
            indices,
            len(symbols),
        )
        
        # Apply max_symbols cap
        max_symbols = eu_cfg.get("max_symbols")
        if max_symbols and len(symbols) > int(max_symbols):
            symbols = symbols[: int(max_symbols)]
            logger.info("Applied max_symbols cap, reduced to %d symbols", len(symbols))
        
        # Apply min_price filter
        min_price = eu_cfg.get("min_price")
        if min_price is not None and float(min_price) > 0:
            symbols = filter_low_price_equities(symbols, float(min_price), kite)
            logger.info(
                "Applied min_price filter (%.2f), %d symbols remain",
                float(min_price),
                len(symbols),
            )
        
        return symbols
    
    # Fallback: preserve existing behavior (all F&O / larger universe, etc.)
    # This loads from config/universe_equity.csv
    return load_equity_universe()


@dataclass
class ScannerResult:
    fno: List[str]
    equity: List[str]
    meta: Dict[str, Dict[str, Any]]
    asof: str
    date: str


class MarketScanner:
    """
    Discovers active FnO futures symbols and NSE equity universe, persists the daily universe.
    
    - Scans NFO for index futures (NIFTY, BANKNIFTY)
    - Scans NSE for equity instruments from config/universe_equity.csv
    - Filters out penny stocks (< ₹20)
    - Validates instrument metadata (lot_size, tick_size)
    """

    def __init__(self, kite: Any, config: Any, artifacts_dir: Optional[Path] = None) -> None:
        self.kite = kite
        self.config = config
        self.artifacts_dir = artifacts_dir or ARTIFACTS_DIR
        self.scanner_root = self.artifacts_dir / "scanner"
        self.scanner_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ public
    def scan(self) -> Dict[str, Any]:
        """
        Discover the nearest-month futures for the configured underlyings
        and NSE equity instruments from the enabled universe.
        """
        # Scan FnO futures
        fno_selected, fno_meta = self._scan_fno_futures()
        
        # Scan NSE equities
        equity_selected, equity_meta = self._scan_nse_equities()
        
        # Merge metadata
        meta = {}
        meta.update(fno_meta)
        meta.update(equity_meta)

        payload = {
            "date": date.today().isoformat(),
            "asof": datetime.utcnow().isoformat() + "Z",
            "fno": fno_selected,
            "equity": equity_selected,
            "equity_universe": equity_selected,  # Expose equity universe explicitly
            "meta": meta,
        }
        
        logger.info(
            "MarketScanner: scan complete - %d FnO, %d equity symbols",
            len(fno_selected),
            len(equity_selected),
        )
        
        return payload

    def _scan_fno_futures(self) -> tuple[List[str], Dict[str, Dict[str, Any]]]:
        """Scan NFO for index futures."""
        try:
            instruments = self.kite.instruments("NFO")
        except Exception as exc:  # noqa: BLE001
            logger.error("MarketScanner: unable to fetch NFO instruments from Kite: %s", exc)
            return [], {}

        targets = ("NIFTY", "BANKNIFTY")
        selected: List[str] = []
        meta: Dict[str, Dict[str, Any]] = {}

        for target in targets:
            inst = self._select_nearest_future(instruments, target)
            if not inst:
                logger.warning("MarketScanner: no future found for %s", target)
                continue
            tradingsymbol = str(inst.get("tradingsymbol") or "")
            selected.append(target)
            meta[target] = {
                "tradingsymbol": tradingsymbol,
                "instrument_token": inst.get("instrument_token"),
                "lot_size": inst.get("lot_size"),
                "expiry": self._format_expiry(inst.get("expiry")),
                "tick_size": inst.get("tick_size"),
                "exchange": inst.get("exchange"),
                "segment": inst.get("segment"),
                "name": inst.get("name"),
                "atr": None,
                "last_price": None,
            }

        return selected, meta

    def _scan_nse_equities(self) -> tuple[List[str], Dict[str, Dict[str, Any]]]:
        """
        Scan NSE for equity instruments from the configured universe.
        
        Applies filters:
        - Enabled via build_equity_universe (respects equity_universe_config)
        - Valid instrument metadata
        - Not a penny stock (last_price >= threshold if available)
        """
        # Build equity universe based on configuration
        # This will use NIFTY lists if equity_universe_config.mode == "nifty_lists"
        # Otherwise falls back to load_equity_universe() (config/universe_equity.csv)
        enabled_symbols = build_equity_universe(
            self.config.raw if hasattr(self.config, "raw") else self.config,
            self.kite,
        )
        if not enabled_symbols:
            logger.warning("MarketScanner: no equity symbols enabled in universe")
            return [], {}
        
        logger.info("MarketScanner: scanning %d enabled equity symbols", len(enabled_symbols))
        
        # Fetch NSE instruments
        try:
            instruments = self.kite.instruments("NSE")
        except Exception as exc:  # noqa: BLE001
            logger.error("MarketScanner: unable to fetch NSE instruments from Kite: %s", exc)
            return [], {}

        # Build lookup by tradingsymbol
        nse_instruments_map = {}
        for inst in instruments:
            symbol = inst.get("tradingsymbol")
            if symbol:
                nse_instruments_map[symbol.upper()] = inst

        selected: List[str] = []
        meta: Dict[str, Dict[str, Any]] = {}

        for symbol in enabled_symbols:
            symbol_upper = symbol.upper()
            inst = nse_instruments_map.get(symbol_upper)
            
            if not inst:
                logger.warning("MarketScanner: NSE instrument not found for symbol=%s", symbol)
                continue
            
            # Validate instrument
            if not self._is_valid_equity_instrument(inst, symbol):
                continue
            
            selected.append(symbol)
            meta[symbol] = {
                "tradingsymbol": inst.get("tradingsymbol"),
                "instrument_token": inst.get("instrument_token"),
                "lot_size": inst.get("lot_size") or 1,
                "tick_size": inst.get("tick_size") or 0.05,
                "exchange": inst.get("exchange") or "NSE",
                "segment": inst.get("segment") or "NSE",
                "name": inst.get("name") or symbol,
                "last_price": inst.get("last_price"),
                "atr": None,
            }

        logger.info("MarketScanner: validated %d/%d equity symbols", len(selected), len(enabled_symbols))
        return selected, meta

    def _is_valid_equity_instrument(self, inst: Dict[str, Any], symbol: str) -> bool:
        """
        Validate equity instrument meets criteria:
        - Has valid instrument_token
        - Not a penny stock (if last_price available)
        - Has valid segment
        """
        # Check instrument token
        token = inst.get("instrument_token")
        if not token or token == 0:
            logger.warning("MarketScanner: invalid instrument_token for %s", symbol)
            return False
        
        # Check segment
        segment = inst.get("segment")
        if segment and segment not in ("NSE", "NSE-EQ"):
            logger.debug("MarketScanner: skipping %s - segment=%s", symbol, segment)
            return False
        
        # Penny stock filter (if price is available)
        last_price = inst.get("last_price")
        if last_price is not None:
            try:
                price = float(last_price)
                if price > 0 and price < PENNY_STOCK_THRESHOLD:
                    logger.info(
                        "MarketScanner: filtered penny stock %s (price=%.2f < %.2f)",
                        symbol,
                        price,
                        PENNY_STOCK_THRESHOLD,
                    )
                    return False
            except (TypeError, ValueError):
                pass  # Can't validate price, allow through
        
        return True

    def save(self, data: Dict[str, Any]) -> Optional[Path]:
        today_dir = self.scanner_root / date.today().isoformat()
        today_dir.mkdir(parents=True, exist_ok=True)
        path = today_dir / "universe.json"
        try:
            with path.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, default=str)
            fno_count = len(data.get("fno") or [])
            equity_count = len(data.get("equity") or [])
            logger.info(
                "MarketScanner: saved universe for %s (%d FnO, %d equity symbols) -> %s",
                data.get("date"),
                fno_count,
                equity_count,
                path,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("MarketScanner: failed to save universe %s (%s)", path, exc)
            return None
        return path

    def load_today(self) -> Optional[Dict[str, Any]]:
        path = self.scanner_root / date.today().isoformat() / "universe.json"
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                return None
            fno_count = len(data.get("fno") or [])
            equity_count = len(data.get("equity") or [])
            logger.info(
                "MarketScanner: loaded cached universe for %s (%d FnO, %d equity symbols)",
                data.get("date"),
                fno_count,
                equity_count,
            )
            return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("MarketScanner: failed to load cached universe %s (%s)", path, exc)
            return None

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _format_expiry(raw_expiry: Any) -> Optional[str]:
        if raw_expiry is None:
            return None
        if isinstance(raw_expiry, str):
            return raw_expiry
        if isinstance(raw_expiry, datetime):
            return raw_expiry.date().isoformat()
        if isinstance(raw_expiry, date):
            return raw_expiry.isoformat()
        return None

    def _select_nearest_future(self, instruments: List[Dict[str, Any]], prefix: str) -> Optional[Dict[str, Any]]:
        prefix = prefix.upper()
        best_inst: Optional[Dict[str, Any]] = None
        best_expiry: Optional[datetime] = None
        for inst in instruments:
            tradingsymbol = str(inst.get("tradingsymbol") or "")
            if not tradingsymbol.startswith(prefix):
                continue
            instrument_type = (inst.get("instrument_type") or "").upper()
            if instrument_type != "FUT":
                continue
            expiry_raw = inst.get("expiry")
            try:
                if isinstance(expiry_raw, str):
                    expiry = datetime.strptime(expiry_raw, "%Y-%m-%d")
                elif isinstance(expiry_raw, datetime):
                    expiry = expiry_raw
                elif isinstance(expiry_raw, date):
                    expiry = datetime.combine(expiry_raw, datetime.min.time())
                else:
                    continue
            except Exception:
                continue
            if best_expiry is None or expiry < best_expiry:
                best_expiry = expiry
                best_inst = inst
        return best_inst

    @staticmethod
    def _empty_universe() -> Dict[str, Any]:
        return {
            "date": date.today().isoformat(),
            "asof": datetime.utcnow().isoformat() + "Z",
            "fno": [],
            "equity": [],
            "meta": {},
        }
