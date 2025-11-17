import logging
from kiteconnect import KiteConnect, exceptions as kite_exceptions
from core.kite_http import kite_request

log = logging.getLogger(__name__)

class BrokerFeed:
    def __init__(self, kite: KiteConnect):
        self._kite = kite
        self._warned_token = False
        # Track symbols we've already warned about to avoid log spam
        self._warned_missing_symbols = set()

    def get_ltp(self, symbol: str, exchange: str = "NSE") -> float | None:
        """
        Fetch last traded price for a symbol.
        
        Returns:
            float | None: The last traded price, or None if unavailable.
                         Strategies must handle None as "no trade / hold".
        
        Note:
            If a symbol is missing in the LTP map, logs a warning once per symbol
            and returns None instead of raising KeyError.
        """
        key = f"{exchange}:{symbol}"
        try:
            data = kite_request(self._kite.ltp, key)
            return float(data[key]["last_price"])
        except KeyError:
            # Symbol not found in LTP response - log once per symbol
            if key not in self._warned_missing_symbols:
                log.warning("Symbol %s not found in LTP data (will not warn again)", key)
                self._warned_missing_symbols.add(key)
            return None
        except kite_exceptions.TokenException as exc:
            if not self._warned_token:
                log.error("Kite token invalid while fetching LTP (%s): %s", key, exc)
                self._warned_token = True
            return None
        except Exception as exc:
            log.warning("Error fetching LTP for %s: %r", key, exc)
            return None