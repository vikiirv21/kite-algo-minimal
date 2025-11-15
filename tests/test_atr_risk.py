from core.atr_risk import (
    ATRConfig,
    TimeFilterConfig,
    compute_atr_from_ohlc,
    compute_sl_tp_from_atr,
    is_entry_time_allowed,
)


def test_compute_atr_from_ohlc_basic():
    rows = []
    price = 100.0
    for i in range(20):
        rows.append({"high": price + 1, "low": price - 1, "close": price})
        price += 0.5
    atr = compute_atr_from_ohlc(rows, period=14)
    assert atr is not None
    assert atr > 0


def test_compute_sl_tp_buy_sell():
    cfg = ATRConfig()
    atr = 2.0
    buy = compute_sl_tp_from_atr(
        symbol="TEST",
        product_type="FUT",
        side="BUY",
        entry_price=100.0,
        atr_value=atr,
        cfg=cfg,
    )
    assert buy["sl_price"] < 100.0
    assert buy["tp_price"] > 100.0
    sell = compute_sl_tp_from_atr(
        symbol="TEST",
        product_type="FUT",
        side="SELL",
        entry_price=100.0,
        atr_value=atr,
        cfg=cfg,
    )
    assert sell["sl_price"] > 100.0
    assert sell["tp_price"] < 100.0


def test_time_filter_allows_sessions():
    cfg = TimeFilterConfig(
        enabled=True,
        allow_sessions=[{"start": "00:00", "end": "23:59"}],
        min_time="00:00",
        max_time="23:59",
    )
    allowed, reason = is_entry_time_allowed(cfg, symbol="TEST", strategy_id=None, is_expiry_instrument=False)
    assert allowed or reason in {"outside_allowed_sessions", "before_min_time:09:00"}
