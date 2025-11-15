from __future__ import annotations

import logging
import time
from typing import Any, Callable, Iterable, Optional, TypeVar

from kiteconnect import exceptions as kite_exceptions
from requests import exceptions as requests_exceptions

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_DELAYS = (1, 2, 3, 5, 8)


def _extract_status_code(exc: Exception) -> Optional[int]:
    for attr in ("code", "status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return status
    return None


def _should_retry(exc: Exception) -> bool:
    if isinstance(exc, kite_exceptions.TokenException):
        return False

    if isinstance(
        exc,
        (
            kite_exceptions.NetworkException,
            requests_exceptions.Timeout,
            requests_exceptions.ConnectionError,
            requests_exceptions.HTTPError,
        ),
    ):
        return True

    status = _extract_status_code(exc)
    if status is None:
        return False
    if status == 429:
        return True
    if 500 <= status < 600:
        return True
    return False


def kite_request(
    fn: Callable[..., T],
    *args: Any,
    delays: Iterable[int] = DEFAULT_DELAYS,
    **kwargs: Any,
) -> T:
    """
    Execute a Kite REST call with retry/backoff semantics.
    """
    delays_list = list(delays)
    attempt = 0
    while True:
        attempt += 1
        try:
            return fn(*args, **kwargs)
        except kite_exceptions.TokenException:
            raise
        except Exception as exc:  # noqa: BLE001
            retry_index = attempt - 1
            should_retry = retry_index < len(delays_list) and _should_retry(exc)
            if not should_retry:
                logger.error("Kite request failed (attempt=%s): %s", attempt, exc, exc_info=True)
                raise
            delay = delays_list[retry_index]
            logger.warning(
                "Kite request failed (attempt=%s/%s): %s. Retrying in %ss.",
                attempt,
                len(delays_list) + 1,
                exc,
                delay,
            )
            time.sleep(delay)
