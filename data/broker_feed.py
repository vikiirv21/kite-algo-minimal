import logging
from kiteconnect import KiteConnect, exceptions as kite_exceptions
from core.kite_http import kite_request

log = logging.getLogger(__name__)

class BrokerFeed:
    def __init__(self, kite: KiteConnect):
        self._kite = kite
        self._warned_token = False

    def get_ltp(self, symbol: str, exchange: str = "NSE") -> float | None:
        key = f"{exchange}:{symbol}"
        try:
            data = kite_request(self._kite.ltp, key)
            return float(data[key]["last_price"])
        except kite_exceptions.TokenException as exc:
            if not self._warned_token:
                log.error("Kite token invalid while fetching LTP (%s): %s", key, exc)
                self._warned_token = True
            return None
        except Exception as exc:
            log.warning("Error fetching LTP for %s: %r", key, exc)
            return None