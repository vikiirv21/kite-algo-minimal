import logging
from kiteconnect import KiteConnect, exceptions as kite_exceptions
from core.kite_http import kite_request

log = logging.getLogger(__name__)


class BrokerAuthError(Exception):
    """Raised when broker authentication fails (invalid API key or access token)."""
    pass


class BrokerFeed:
    def __init__(self, kite: KiteConnect):
        self._kite = kite
        self._warned_token = False
        # Track symbols we've already warned about to avoid log spam
        self._warned_missing_symbols = set()
        # Count consecutive auth errors to detect persistent auth failures
        self._consecutive_auth_errors = 0
        self._max_auth_errors_before_raise = 3

    def get_ltp(self, symbol: str, exchange: str = "NSE") -> float | None:
        """
        Fetch last traded price for a symbol.
        
        Returns:
            float | None: The last traded price, or None if unavailable.
                         Strategies must handle None as "no trade / hold".
        
        Raises:
            BrokerAuthError: If broker authentication consistently fails
                            (after multiple consecutive failures).
        
        Note:
            If a symbol is missing in the LTP map, logs a warning once per symbol
            and returns None instead of raising KeyError.
        """
        key = f"{exchange}:{symbol}"
        try:
            data = kite_request(self._kite.ltp, key)
            # Reset auth error count on success
            self._consecutive_auth_errors = 0
            return float(data[key]["last_price"])
        except KeyError:
            # Symbol not found in LTP response - log once per symbol
            if key not in self._warned_missing_symbols:
                log.warning("Symbol %s not found in LTP data (will not warn again)", key)
                self._warned_missing_symbols.add(key)
            return None
        except kite_exceptions.TokenException as exc:
            self._consecutive_auth_errors += 1
            error_msg = str(exc)
            is_auth_error = (
                "Incorrect `api_key` or `access_token`" in error_msg
                or "Invalid `api_key`" in error_msg
            )
            
            if not self._warned_token:
                log.error("Kite token invalid while fetching LTP (%s): %s", key, exc)
                self._warned_token = True
            
            # Raise BrokerAuthError after multiple consecutive auth errors
            if is_auth_error and self._consecutive_auth_errors >= self._max_auth_errors_before_raise:
                raise BrokerAuthError(
                    f"Broker authentication failed: {exc}. "
                    "Please re-login via scripts.run_day --login"
                ) from exc
            
            return None
        except Exception as exc:
            log.warning("Error fetching LTP for %s: %r", key, exc)
            return None