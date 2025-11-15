from __future__ import annotations

import logging
from datetime import date
from typing import Dict, List, Sequence, Tuple

from broker.kite_client import KiteClient
from core.kite_http import kite_request

logger = logging.getLogger(__name__)


class OptionUniverse:
    """
    Helper to work with index options instruments from NFO.

    - Loads instruments("NFO") once.
    - Groups options by underlying name (e.g., NIFTY, BANKNIFTY).
    - For each underlying + spot, can resolve ATM CE and ATM PE on nearest expiry.
    """

    def __init__(self, kite_client: KiteClient | None = None) -> None:
        self._kite_client = kite_client or KiteClient()
        kite = self._kite_client.api

        logger.info("Loading NFO option instruments for OptionUniverse...")
        instruments = kite_request(kite.instruments, "NFO")

        self._by_name: Dict[str, List[dict]] = {}
        for inst in instruments:
            # We only care about index options
            if inst.get("segment") != "NFO-OPT":
                continue
            name = inst.get("name")
            if not name:
                continue
            self._by_name.setdefault(name.upper(), []).append(inst)

    @staticmethod
    def _pick_nearest_expiry(contracts: Sequence[dict]) -> List[dict]:
        """
        Given a list of option contracts for an underlying, pick all contracts
        that share the nearest expiry >= today. If none are >= today, use the
        earliest expiry available.

        This naturally prefers weekly expiry first, then monthly, as long as
        weekly is the nearer date.
        """
        if not contracts:
            return []

        today = date.today()
        dated = [c for c in contracts if isinstance(c.get("expiry"), date)]
        if not dated:
            return list(contracts)

        future = [c for c in dated if c["expiry"] >= today]
        if future:
            target_expiry = sorted(future, key=lambda c: c["expiry"])[0]["expiry"]
        else:
            target_expiry = sorted(dated, key=lambda c: c["expiry"])[0]["expiry"]

        return [c for c in dated if c["expiry"] == target_expiry]

    def resolve_atm_for_underlying(self, logical: str, spot: float) -> Dict[str, str]:
        """
        Given an underlying logical name (e.g., NIFTY) and a spot price, return
        ATM CE and ATM PE tradingsymbols on the nearest expiry.

        Returns:
            {"CE": "NIFTY25NOV25000CE", "PE": "NIFTY25NOV25000PE"} or {} if not found.
        """
        key = logical.upper()
        contracts = self._by_name.get(key, [])
        if not contracts:
            logger.warning("No option contracts found in NFO for logical=%s", logical)
            return {}

        same_expiry = self._pick_nearest_expiry(contracts)
        if not same_expiry:
            logger.warning("No contracts with valid expiry for logical=%s", logical)
            return {}

        ce_best: Tuple[float, str] | None = None
        pe_best: Tuple[float, str] | None = None

        for c in same_expiry:
            strike = float(c.get("strike", 0.0))
            ts = c.get("tradingsymbol")
            inst_type = c.get("instrument_type")
            if not ts or not inst_type:
                continue

            dist = abs(strike - spot)
            if inst_type.upper() == "CE":
                if ce_best is None or dist < ce_best[0]:
                    ce_best = (dist, ts)
            elif inst_type.upper() == "PE":
                if pe_best is None or dist < pe_best[0]:
                    pe_best = (dist, ts)

        result: Dict[str, str] = {}
        if ce_best:
            result["CE"] = ce_best[1]
        if pe_best:
            result["PE"] = pe_best[1]

        if not result:
            logger.warning("Could not resolve ATM CE/PE for logical=%s spot=%.2f", logical, spot)

        return result

    def resolve_atm_for_many(self, spots: Dict[str, float]) -> Dict[str, Dict[str, str]]:
        """
        Resolve ATM CE/PE for multiple logical underlyings.

        Args:
            spots: mapping logical_name -> spot_price

        Returns:
            mapping logical_name -> {"CE": ts_ce, "PE": ts_pe}
        """
        out: Dict[str, Dict[str, str]] = {}
        for logical, spot in spots.items():
            res = self.resolve_atm_for_underlying(logical, spot)
            if res:
                out[logical] = res
        return out
