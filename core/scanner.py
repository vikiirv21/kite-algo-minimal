from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"


@dataclass
class ScannerResult:
    fno: List[str]
    meta: Dict[str, Dict[str, Any]]
    asof: str
    date: str


class MarketScanner:
    """
    Discovers active FnO futures symbols and persists the daily universe.
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
        Discover the nearest-month futures for the configured underlyings.
        """
        try:
            instruments = self.kite.instruments("NFO")
        except Exception as exc:  # noqa: BLE001
            logger.error("MarketScanner: unable to fetch instruments from Kite: %s", exc)
            return self._empty_universe()

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
            }

        payload = {
            "date": date.today().isoformat(),
            "asof": datetime.utcnow().isoformat() + "Z",
            "fno": selected,
            "meta": meta,
        }
        return payload

    def save(self, data: Dict[str, Any]) -> Optional[Path]:
        today_dir = self.scanner_root / date.today().isoformat()
        today_dir.mkdir(parents=True, exist_ok=True)
        path = today_dir / "universe.json"
        try:
            with path.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, default=str)
            logger.info(
                "MarketScanner: saved universe for %s (%d symbols) -> %s",
                data.get("date"),
                len(data.get("fno") or []),
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
            logger.info(
                "MarketScanner: loaded cached universe for %s (%d symbols)",
                data.get("date"),
                len(data.get("fno") or []),
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
            "meta": {},
        }
