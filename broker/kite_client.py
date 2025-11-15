import os
from typing import Optional

from dotenv import load_dotenv
from kiteconnect import KiteConnect

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_PATH)


class KiteClient:
    """
    Thin wrapper around KiteConnect.

    In LIVE mode:
    - Requires KITE_API_KEY, KITE_API_SECRET, KITE_ACCESS_TOKEN in .env.
    """

    def __init__(self, access_token: Optional[str] = None) -> None:
        api_key = os.getenv("KITE_API_KEY")
        if not api_key:
            raise RuntimeError("KITE_API_KEY not set in .env")

        self._kite = KiteConnect(api_key=api_key)

        access_token = access_token or os.getenv("KITE_ACCESS_TOKEN")
        if access_token:
            self._kite.set_access_token(access_token)
        else:
            raise RuntimeError("KITE_ACCESS_TOKEN not set. Run scripts.login_kite first.")

    @property
    def api(self) -> KiteConnect:
        return self._kite
