from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Sequence, Tuple

from broker.kite_client import KiteClient
from core.kite_http import kite_request

logger = logging.getLogger(__name__)


@dataclass
class ATMOptionPair:
    """
    Represents an ATM option pair (CE and PE) for a given underlying.
    
    This dataclass is used by the expiry-aware ATM option strike resolver.
    """
    underlying: str
    expiry: date
    strike: float
    ce_symbol: str
    pe_symbol: str
    
    def to_dict(self) -> Dict[str, any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "underlying": self.underlying,
            "expiry": self.expiry.isoformat() if self.expiry else None,
            "strike": self.strike,
            "ce_symbol": self.ce_symbol,
            "pe_symbol": self.pe_symbol,
        }


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

    def resolve_atm_for_underlying(self, logical: str, spot: Optional[float]) -> Optional[Dict[str, str]]:
        """
        Given an underlying logical name (e.g., NIFTY) and a spot price, return
        ATM CE and ATM PE tradingsymbols on the nearest expiry.

        Returns:
            {"CE": "NIFTY25NOV25000CE", "PE": "NIFTY25NOV25000PE"} or {} if not found.
            Returns None if spot is None (missing LTP data).
        """
        # Handle missing spot price gracefully
        if spot is None:
            logger.error(
                "Cannot resolve ATM for underlying=%s: spot price is None (missing LTP data)",
                logical,
            )
            return None

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
    
    def iter_underlyings(self):
        """
        Iterate over all underlyings and their option contracts.
        
        Yields:
            Tuple of (underlying_name, list_of_contracts)
        """
        return self._by_name.items()
    
    def get_all_tradingsymbols(self) -> List[str]:
        """
        Get all option tradingsymbols in the universe.
        
        Returns:
            List of tradingsymbol strings
        """
        symbols = []
        for contracts in self._by_name.values():
            for contract in contracts:
                ts = contract.get("tradingsymbol")
                if ts:
                    symbols.append(ts)
        return symbols
    
    def resolve_atm_option_pair(
        self,
        underlying: str,
        spot: float,
        dt: Optional[datetime] = None
    ) -> Optional[ATMOptionPair]:
        """
        Resolve ATM option pair using expiry-aware logic.
        
        This method uses the expiry calendar to determine the correct expiry date
        and then finds the ATM CE/PE pair at the nearest strike.
        
        Args:
            underlying: Underlying symbol (NIFTY, BANKNIFTY, FINNIFTY)
            spot: Current spot price of the underlying
            dt: Reference datetime (default: now)
            
        Returns:
            ATMOptionPair if successful, None if unable to resolve
        """
        try:
            # Import here to avoid circular dependencies
            from core.expiry_calendar import get_next_expiry
            
            if dt is None:
                from datetime import datetime
                import pytz
                dt = datetime.now(pytz.timezone("Asia/Kolkata"))
            
            # Get the next expiry using the expiry calendar
            next_expiry = get_next_expiry(underlying, dt)
            
            # Get all contracts for this underlying
            key = underlying.upper()
            contracts = self._by_name.get(key, [])
            if not contracts:
                logger.warning("No option contracts found for underlying=%s", underlying)
                return None
            
            # Filter contracts for the target expiry
            expiry_contracts = [c for c in contracts if c.get("expiry") == next_expiry]
            if not expiry_contracts:
                logger.warning(
                    "No contracts found for underlying=%s on expiry=%s",
                    underlying, next_expiry
                )
                return None
            
            # Calculate ATM strike (round to nearest 50 for indices)
            strike_step = 50.0
            atm_strike = round(spot / strike_step) * strike_step
            
            # Find CE and PE at ATM strike
            ce_symbol = None
            pe_symbol = None
            
            for c in expiry_contracts:
                strike = float(c.get("strike", 0.0))
                if abs(strike - atm_strike) < 0.01:  # Match with small tolerance
                    ts = c.get("tradingsymbol")
                    inst_type = (c.get("instrument_type") or "").upper()
                    
                    if inst_type == "CE" and not ce_symbol:
                        ce_symbol = ts
                    elif inst_type == "PE" and not pe_symbol:
                        pe_symbol = ts
            
            # If exact ATM not found, find nearest strike
            if not ce_symbol or not pe_symbol:
                logger.debug(
                    "Exact ATM strike %.2f not found for %s, finding nearest",
                    atm_strike, underlying
                )
                
                ce_best: Tuple[float, str] | None = None
                pe_best: Tuple[float, str] | None = None
                
                for c in expiry_contracts:
                    strike = float(c.get("strike", 0.0))
                    ts = c.get("tradingsymbol")
                    inst_type = (c.get("instrument_type") or "").upper()
                    
                    if not ts:
                        continue
                    
                    dist = abs(strike - spot)
                    
                    if inst_type == "CE":
                        if ce_best is None or dist < ce_best[0]:
                            ce_best = (dist, ts)
                            atm_strike = strike  # Update to actual strike
                    elif inst_type == "PE":
                        if pe_best is None or dist < pe_best[0]:
                            pe_best = (dist, ts)
                
                if ce_best:
                    ce_symbol = ce_best[1]
                if pe_best:
                    pe_symbol = pe_best[1]
            
            if not ce_symbol or not pe_symbol:
                logger.warning(
                    "Unable to resolve ATM pair for underlying=%s spot=%.2f expiry=%s",
                    underlying, spot, next_expiry
                )
                return None
            
            return ATMOptionPair(
                underlying=underlying,
                expiry=next_expiry,
                strike=atm_strike,
                ce_symbol=ce_symbol,
                pe_symbol=pe_symbol,
            )
            
        except Exception as exc:
            logger.error(
                "Failed to resolve ATM option pair for %s: %s",
                underlying, exc, exc_info=True
            )
            return None
