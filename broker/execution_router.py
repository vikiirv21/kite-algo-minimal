"""
Execution router:

- For PAPER mode: sends orders to PaperBroker.
- For LIVE mode: sends orders to Kite client.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.modes import TradingMode
from .kite_client import KiteClient
from .paper_broker import PaperBroker


@dataclass
class ExecutionRouter:
    mode: TradingMode
    paper_broker: Optional[PaperBroker] = None
    kite_client: Optional[KiteClient] = None

    def __post_init__(self) -> None:
        if self.mode in (TradingMode.PAPER, TradingMode.REPLAY):
            if self.paper_broker is None:
                self.paper_broker = PaperBroker()
        else:
            if self.kite_client is None:
                self.kite_client = KiteClient()

    def place_order(self, symbol: str, side: str, quantity: int, price: float):
        if self.mode in (TradingMode.PAPER, TradingMode.REPLAY):
            assert self.paper_broker is not None
            return self.paper_broker.place_order(symbol, side, quantity, price)
        else:
            # LIVE mode: call Kite API (market order for now)
            assert self.kite_client is not None
            kite = self.kite_client.api
            order_id = kite.place_order(
                variety=kite.VARIETY_REGULAR,
                exchange=kite.EXCHANGE_NFO,
                tradingsymbol=symbol,
                transaction_type=kite.TRANSACTION_TYPE_BUY if side.upper() == "BUY" else kite.TRANSACTION_TYPE_SELL,
                quantity=quantity,
                product=kite.PRODUCT_MIS,
                order_type=kite.ORDER_TYPE_MARKET,
            )
            return order_id
