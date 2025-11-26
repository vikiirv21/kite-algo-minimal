"""
Technical Analysis (TA) Patterns & Utilities Module

Library-style, pure pandas-based utilities for:
- Candlestick pattern detection (hammer, inverted hammer, pinbar, engulfing)
- Volume spike detection
- ATR-based volatility mode classification (expanding, normal, compressing)

All functions accept OHLCV DataFrames (with columns: open, high, low, close, volume)
and return pandas Series aligned with the input index.

Usage Guidelines:
-----------------
Timeframes: Designed for intraday use (1m, 5m, 15m) on Indian indices.
Typical parameters for NIFTY/BANKNIFTY/FINNIFTY:
  - 1m: body_ratio_threshold=0.25, wick_ratio_threshold=2.0
  - 5m: body_ratio_threshold=0.30, wick_ratio_threshold=2.5
  - 15m: body_ratio_threshold=0.35, wick_ratio_threshold=3.0

Note: These are library utilities with no hard coupling to any specific engine.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd


# =============================================================================
# CANDLESTICK PATTERN DETECTION
# =============================================================================


def detect_hammer(
    df: pd.DataFrame,
    body_ratio_threshold: float = 0.30,
    wick_ratio_threshold: float = 2.0,
) -> pd.Series:
    """
    Detect hammer candlestick pattern.

    A hammer has a small body near the top of the candle's range with a long
    lower wick (shadow) at least `wick_ratio_threshold` times the body size.

    Characteristics:
    - Small real body (open-close range) relative to total candle range
    - Long lower shadow (wick)
    - Little or no upper shadow
    - Typically appears after a downtrend (bullish reversal signal)

    Args:
        df: DataFrame with at least columns ["open", "high", "low", "close"].
        body_ratio_threshold: Maximum ratio of body to total range for
            a valid hammer. Lower values require smaller bodies. Typical
            values: 0.25-0.35 for intraday (1m-15m).
        wick_ratio_threshold: Minimum ratio of lower wick to body size.
            Higher values require longer wicks. Typical values: 2.0-3.0.

    Returns:
        pd.Series[bool]: True where hammer pattern is detected, aligned
        with df.index.

    Example (1m NIFTY):
        >>> hammers = detect_hammer(df, body_ratio_threshold=0.25, wick_ratio_threshold=2.0)

    Example (15m BANKNIFTY):
        >>> hammers = detect_hammer(df, body_ratio_threshold=0.35, wick_ratio_threshold=3.0)
    """
    open_price = df["open"]
    high = df["high"]
    low = df["low"]
    close = df["close"]

    # Calculate body size and candle range
    body = (close - open_price).abs()
    candle_range = high - low

    # Lower shadow: distance from body bottom to low
    body_bottom = np.minimum(open_price, close)
    lower_shadow = body_bottom - low

    # Upper shadow: distance from body top to high
    body_top = np.maximum(open_price, close)
    upper_shadow = high - body_top

    # Avoid division by zero
    candle_range_safe = candle_range.replace(0, np.nan)
    body_safe = body.replace(0, np.nan)

    # Conditions for hammer pattern:
    # 1. Small body relative to candle range
    body_ratio = body / candle_range_safe
    small_body = body_ratio <= body_ratio_threshold

    # 2. Long lower shadow (at least wick_ratio_threshold * body)
    long_lower_shadow = lower_shadow >= (wick_ratio_threshold * body)

    # 3. Upper shadow should be minimal (less than body)
    minimal_upper_shadow = upper_shadow <= body

    # Combine conditions
    is_hammer = small_body & long_lower_shadow & minimal_upper_shadow

    # Fill NaN with False
    return is_hammer.fillna(False).astype(bool)


def detect_inverted_hammer(
    df: pd.DataFrame,
    body_ratio_threshold: float = 0.30,
    wick_ratio_threshold: float = 2.0,
) -> pd.Series:
    """
    Detect inverted hammer candlestick pattern.

    An inverted hammer has a small body near the bottom with a long upper
    wick (shadow) at least `wick_ratio_threshold` times the body size.

    Characteristics:
    - Small real body near the low of the candle
    - Long upper shadow (wick)
    - Little or no lower shadow
    - Typically appears after a downtrend (potential bullish reversal)

    Args:
        df: DataFrame with at least columns ["open", "high", "low", "close"].
        body_ratio_threshold: Maximum ratio of body to total range.
            Typical values: 0.25-0.35 for intraday (1m-15m).
        wick_ratio_threshold: Minimum ratio of upper wick to body size.
            Typical values: 2.0-3.0.

    Returns:
        pd.Series[bool]: True where inverted hammer pattern is detected,
        aligned with df.index.

    Example (5m FINNIFTY):
        >>> inv_hammers = detect_inverted_hammer(df, body_ratio_threshold=0.30, wick_ratio_threshold=2.5)
    """
    open_price = df["open"]
    high = df["high"]
    low = df["low"]
    close = df["close"]

    body = (close - open_price).abs()
    candle_range = high - low

    # Upper shadow: distance from body top to high
    body_top = np.maximum(open_price, close)
    upper_shadow = high - body_top

    # Lower shadow: distance from body bottom to low
    body_bottom = np.minimum(open_price, close)
    lower_shadow = body_bottom - low

    candle_range_safe = candle_range.replace(0, np.nan)

    # Conditions for inverted hammer:
    # 1. Small body relative to candle range
    body_ratio = body / candle_range_safe
    small_body = body_ratio <= body_ratio_threshold

    # 2. Long upper shadow (at least wick_ratio_threshold * body)
    long_upper_shadow = upper_shadow >= (wick_ratio_threshold * body)

    # 3. Lower shadow should be minimal (less than body)
    minimal_lower_shadow = lower_shadow <= body

    is_inverted_hammer = small_body & long_upper_shadow & minimal_lower_shadow

    return is_inverted_hammer.fillna(False).astype(bool)


def detect_pinbar(
    df: pd.DataFrame,
    body_ratio_threshold: float = 0.30,
    wick_ratio_threshold: float = 2.5,
) -> pd.Series:
    """
    Detect pinbar (pin bar) candlestick pattern.

    A pinbar is characterized by a small body with a long "nose" (wick)
    extending in one direction. This function detects both bullish pinbars
    (long lower wick) and bearish pinbars (long upper wick).

    A pinbar is essentially a hammer OR an inverted hammer pattern,
    indicating potential reversal points.

    Args:
        df: DataFrame with at least columns ["open", "high", "low", "close"].
        body_ratio_threshold: Maximum ratio of body to total range.
            Typical values: 0.25-0.35 for intraday.
        wick_ratio_threshold: Minimum ratio of dominant wick to body size.
            Pinbars typically have longer wicks than standard hammers.
            Typical values: 2.5-3.5.

    Returns:
        pd.Series[bool]: True where pinbar pattern is detected (either
        bullish or bearish), aligned with df.index.

    Example (5m NIFTY):
        >>> pinbars = detect_pinbar(df, body_ratio_threshold=0.30, wick_ratio_threshold=2.5)
    """
    # Pinbar = hammer OR inverted hammer with same thresholds
    bullish_pin = detect_hammer(df, body_ratio_threshold, wick_ratio_threshold)
    bearish_pin = detect_inverted_hammer(df, body_ratio_threshold, wick_ratio_threshold)

    return bullish_pin | bearish_pin


def detect_engulfing(
    df: pd.DataFrame,
    direction: Literal["bullish", "bearish"] = "bullish",
) -> pd.Series:
    """
    Detect engulfing candlestick pattern.

    Bullish engulfing: Current green candle completely engulfs previous red candle.
    Bearish engulfing: Current red candle completely engulfs previous green candle.

    Engulfing patterns are strong reversal signals when they appear after
    a sustained trend.

    Args:
        df: DataFrame with at least columns ["open", "high", "low", "close"].
        direction: Either "bullish" or "bearish".
            - "bullish": Detects bullish engulfing (reversal from downtrend)
            - "bearish": Detects bearish engulfing (reversal from uptrend)

    Returns:
        pd.Series[bool]: True where engulfing pattern is detected, aligned
        with df.index. First row is always False (needs previous candle).

    Example (15m BANKNIFTY bullish engulfing):
        >>> bull_engulf = detect_engulfing(df, direction="bullish")

    Example (1m NIFTY bearish engulfing):
        >>> bear_engulf = detect_engulfing(df, direction="bearish")
    """
    open_price = df["open"]
    close = df["close"]

    # Current candle properties
    curr_open = open_price
    curr_close = close
    curr_body_top = np.maximum(curr_open, curr_close)
    curr_body_bottom = np.minimum(curr_open, curr_close)

    # Previous candle properties (shifted by 1)
    prev_open = open_price.shift(1)
    prev_close = close.shift(1)
    prev_body_top = np.maximum(prev_open, prev_close)
    prev_body_bottom = np.minimum(prev_open, prev_close)

    # Determine candle colors
    curr_is_green = curr_close > curr_open
    curr_is_red = curr_close < curr_open
    prev_is_green = prev_close > prev_open
    prev_is_red = prev_close < prev_open

    if direction == "bullish":
        # Bullish engulfing: current green candle engulfs previous red candle
        # Conditions:
        # 1. Current candle is green (close > open)
        # 2. Previous candle is red (close < open)
        # 3. Current body completely engulfs previous body
        engulfs_body = (curr_body_top >= prev_body_top) & (curr_body_bottom <= prev_body_bottom)
        is_engulfing = curr_is_green & prev_is_red & engulfs_body
    else:  # bearish
        # Bearish engulfing: current red candle engulfs previous green candle
        # Conditions:
        # 1. Current candle is red (close < open)
        # 2. Previous candle is green (close > open)
        # 3. Current body completely engulfs previous body
        engulfs_body = (curr_body_top >= prev_body_top) & (curr_body_bottom <= prev_body_bottom)
        is_engulfing = curr_is_red & prev_is_green & engulfs_body

    return is_engulfing.fillna(False).astype(bool)


# =============================================================================
# VOLUME ANALYSIS
# =============================================================================


def volume_spike(
    df: pd.DataFrame,
    window: int = 20,
    factor: float = 1.5,
) -> pd.Series:
    """
    Detect volume spikes above rolling average.

    A volume spike indicates unusual trading activity, often preceding
    significant price moves. Useful for confirming breakouts or reversals.

    Args:
        df: DataFrame with at least column ["volume"].
        window: Rolling window period for average volume calculation.
            Typical values:
            - 1m timeframe: 20-30 (20-30 minutes of data)
            - 5m timeframe: 20 (100 minutes / ~1.5 hours)
            - 15m timeframe: 14-20 (3.5-5 hours)
        factor: Multiplier above rolling average to qualify as spike.
            Typical values:
            - Conservative: 1.5x (more signals)
            - Moderate: 2.0x (balanced)
            - Aggressive: 2.5x (fewer, stronger signals)

    Returns:
        pd.Series[bool]: True where volume spike is detected, aligned
        with df.index.

    Example (5m NIFTY, moderate spike detection):
        >>> spikes = volume_spike(df, window=20, factor=2.0)

    Example (1m BANKNIFTY, conservative detection for scalping):
        >>> spikes = volume_spike(df, window=30, factor=1.5)
    """
    volume = df["volume"]

    # Calculate rolling average volume
    avg_volume = volume.rolling(window=window, min_periods=1).mean()

    # Detect spikes where current volume exceeds threshold
    is_spike = volume > (avg_volume * factor)

    return is_spike.fillna(False).astype(bool)


# =============================================================================
# VOLATILITY ANALYSIS (ATR-BASED)
# =============================================================================


def atr(
    df: pd.DataFrame,
    period: int = 14,
) -> pd.Series:
    """
    Calculate Average True Range (ATR) - pandas-based implementation.

    ATR measures market volatility by decomposing the entire range of
    an asset price for that period.

    True Range is the greatest of:
    - Current High - Current Low
    - |Current High - Previous Close|
    - |Current Low - Previous Close|

    Args:
        df: DataFrame with at least columns ["high", "low", "close"].
        period: ATR smoothing period. Typical values:
            - Short-term (scalping): 7-10
            - Standard: 14
            - Long-term: 20-21

    Returns:
        pd.Series[float]: ATR values aligned with df.index.
        First (period-1) values use available data (progressive smoothing).

    Example (14-period ATR for NIFTY):
        >>> atr_values = atr(df, period=14)

    Note:
        This is a pandas-based implementation complementing the list-based
        version in core/indicators.py. Use this when working with DataFrames.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    # Calculate True Range components
    hl = high - low  # High - Low
    hc = (high - close.shift(1)).abs()  # |High - Prev Close|
    lc = (low - close.shift(1)).abs()  # |Low - Prev Close|

    # True Range = max of the three components
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)

    # ATR = Exponential Moving Average of True Range (Wilder's smoothing)
    # Wilder's smoothing: alpha = 1/period
    atr_values = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    return atr_values


def atr_volatility_mode(
    df: pd.DataFrame,
    period: int = 14,
    expand_factor: float = 1.2,
    compress_factor: float = 0.8,
) -> pd.Series:
    """
    Classify volatility mode based on ATR relative to its rolling average.

    Modes:
    - "expanding": ATR > expand_factor * ATR_avg (volatility increasing)
    - "compressing": ATR < compress_factor * ATR_avg (volatility decreasing)
    - "normal": ATR within normal range

    This helps identify regime changes useful for position sizing and
    strategy selection.

    Args:
        df: DataFrame with at least columns ["high", "low", "close"].
        period: ATR calculation period. Default 14.
        expand_factor: Threshold multiplier for "expanding" mode.
            When ATR > expand_factor * rolling_ATR_avg, volatility is expanding.
            Typical values: 1.2-1.5 (20-50% above average).
        compress_factor: Threshold multiplier for "compressing" mode.
            When ATR < compress_factor * rolling_ATR_avg, volatility is compressing.
            Typical values: 0.7-0.8 (20-30% below average).

    Returns:
        pd.Series[str]: Labels "expanding", "normal", or "compressing"
        aligned with df.index.

    Example (standard parameters for NIFTY/BANKNIFTY):
        >>> vol_mode = atr_volatility_mode(df, period=14, expand_factor=1.2, compress_factor=0.8)

    Example (more sensitive detection for scalping):
        >>> vol_mode = atr_volatility_mode(df, period=10, expand_factor=1.15, compress_factor=0.85)

    Strategy guidance:
    - "expanding": Widen stop-losses, reduce position size, expect larger moves
    - "compressing": Tighten stop-losses, potential breakout setup brewing
    - "normal": Standard risk parameters
    """
    # Calculate ATR
    atr_values = atr(df, period=period)

    # Rolling average of ATR (same period for consistency)
    atr_avg = atr_values.rolling(window=period, min_periods=1).mean()

    # Classify volatility mode
    # Calculate ratio (avoid division by zero)
    atr_avg_safe = atr_avg.replace(0, np.nan)
    ratio = atr_values / atr_avg_safe

    # Vectorized classification using numpy.select
    conditions = [
        ratio >= expand_factor,
        ratio <= compress_factor,
    ]
    choices = ["expanding", "compressing"]

    # Default to "normal" for ratios in between or NaN values
    mode = pd.Series(
        np.select(conditions, choices, default="normal"),
        index=df.index,
    )

    return mode


# =============================================================================
# SELF-TEST / USAGE EXAMPLE
# =============================================================================


def _create_dummy_ohlcv(n_bars: int = 100, base_price: float = 22000.0) -> pd.DataFrame:
    """Create dummy OHLCV data for testing (simulates NIFTY-like price action)."""
    np.random.seed(42)

    # Generate random walk for close prices
    returns = np.random.normal(0, 0.002, n_bars)  # 0.2% std dev
    close = base_price * np.cumprod(1 + returns)

    # Generate open, high, low based on close
    open_prices = close * (1 + np.random.uniform(-0.001, 0.001, n_bars))
    high = np.maximum(close, open_prices) * (1 + np.abs(np.random.normal(0, 0.001, n_bars)))
    low = np.minimum(close, open_prices) * (1 - np.abs(np.random.normal(0, 0.001, n_bars)))

    # Generate volume with some spikes
    base_volume = 100000
    volume = np.random.poisson(base_volume, n_bars).astype(float)
    # Add some volume spikes
    spike_indices = np.random.choice(n_bars, size=10, replace=False)
    volume[spike_indices] *= np.random.uniform(2, 4, 10)

    # Inject some hammer patterns (small body, long lower wick)
    hammer_indices = [20, 45, 70]
    for idx in hammer_indices:
        if idx < n_bars:
            # Create hammer: close near high, open slightly below, low much lower
            close[idx] = high[idx] * 0.998
            open_prices[idx] = close[idx] * 0.998
            low[idx] = close[idx] * 0.985  # Long lower wick

    # Inject some engulfing patterns
    if n_bars > 55:
        # Bullish engulfing at index 50
        # Previous candle: red (close < open)
        open_prices[49] = close[49] * 1.002
        # Current candle: green and engulfs
        open_prices[50] = close[49] * 0.998
        close[50] = open_prices[49] * 1.003
        high[50] = close[50] * 1.001
        low[50] = open_prices[50] * 0.999

    df = pd.DataFrame(
        {
            "open": open_prices,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )

    return df


def _run_self_test() -> bool:
    """Run self-test demonstrating all TA pattern functions."""
    print("=" * 60)
    print("TA Patterns Module - Self Test")
    print("=" * 60)

    # Create dummy data
    df = _create_dummy_ohlcv(n_bars=100)
    print(f"\nCreated dummy OHLCV data: {len(df)} bars")
    print(f"Price range: {df['close'].min():.2f} - {df['close'].max():.2f}")
    print(f"Volume range: {df['volume'].min():.0f} - {df['volume'].max():.0f}")

    all_passed = True

    # Test 1: Hammer detection
    print("\n--- Test 1: Hammer Detection ---")
    hammers = detect_hammer(df, body_ratio_threshold=0.30, wick_ratio_threshold=2.0)
    n_hammers = hammers.sum()
    print(f"Hammers detected: {n_hammers}")
    print(f"  Result type: {type(hammers).__name__}")
    print(f"  Result dtype: {hammers.dtype}")
    assert isinstance(hammers, pd.Series), "Should return pd.Series"
    assert hammers.dtype == bool, "Should return bool Series"
    assert len(hammers) == len(df), "Should match input length"
    print("  ✓ Hammer detection passed")

    # Test 2: Inverted Hammer detection
    print("\n--- Test 2: Inverted Hammer Detection ---")
    inv_hammers = detect_inverted_hammer(df, body_ratio_threshold=0.30, wick_ratio_threshold=2.0)
    n_inv_hammers = inv_hammers.sum()
    print(f"Inverted hammers detected: {n_inv_hammers}")
    assert isinstance(inv_hammers, pd.Series), "Should return pd.Series"
    assert inv_hammers.dtype == bool, "Should return bool Series"
    print("  ✓ Inverted hammer detection passed")

    # Test 3: Pinbar detection (combines hammer + inverted hammer)
    print("\n--- Test 3: Pinbar Detection ---")
    pinbars = detect_pinbar(df, body_ratio_threshold=0.30, wick_ratio_threshold=2.5)
    n_pinbars = pinbars.sum()
    print(f"Pinbars detected: {n_pinbars}")
    assert isinstance(pinbars, pd.Series), "Should return pd.Series"
    print("  ✓ Pinbar detection passed")

    # Test 4: Engulfing detection
    print("\n--- Test 4: Engulfing Detection ---")
    bull_engulf = detect_engulfing(df, direction="bullish")
    bear_engulf = detect_engulfing(df, direction="bearish")
    print(f"Bullish engulfing detected: {bull_engulf.sum()}")
    print(f"Bearish engulfing detected: {bear_engulf.sum()}")
    assert isinstance(bull_engulf, pd.Series), "Should return pd.Series"
    assert isinstance(bear_engulf, pd.Series), "Should return pd.Series"
    assert not bull_engulf.iloc[0], "First bar should be False (needs previous)"
    print("  ✓ Engulfing detection passed")

    # Test 5: Volume spike detection
    print("\n--- Test 5: Volume Spike Detection ---")
    spikes = volume_spike(df, window=20, factor=1.5)
    n_spikes = spikes.sum()
    print(f"Volume spikes detected: {n_spikes}")
    assert isinstance(spikes, pd.Series), "Should return pd.Series"
    assert spikes.dtype == bool, "Should return bool Series"
    print("  ✓ Volume spike detection passed")

    # Test 6: ATR calculation
    print("\n--- Test 6: ATR Calculation ---")
    atr_values = atr(df, period=14)
    print(f"ATR (latest): {atr_values.iloc[-1]:.4f}")
    print(f"ATR range: {atr_values.min():.4f} - {atr_values.max():.4f}")
    assert isinstance(atr_values, pd.Series), "Should return pd.Series"
    assert len(atr_values) == len(df), "Should match input length"
    assert atr_values.iloc[-1] > 0, "ATR should be positive"
    print("  ✓ ATR calculation passed")

    # Test 7: ATR Volatility Mode
    print("\n--- Test 7: ATR Volatility Mode ---")
    vol_mode = atr_volatility_mode(df, period=14, expand_factor=1.2, compress_factor=0.8)
    mode_counts = vol_mode.value_counts()
    print(f"Volatility mode distribution:")
    for mode_name, count in mode_counts.items():
        print(f"  {mode_name}: {count}")
    assert isinstance(vol_mode, pd.Series), "Should return pd.Series"
    assert set(vol_mode.unique()).issubset({"expanding", "normal", "compressing"}), "Invalid modes"
    print("  ✓ ATR volatility mode passed")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total patterns on {len(df)} bars:")
    print(f"  - Hammers: {n_hammers}")
    print(f"  - Inverted Hammers: {n_inv_hammers}")
    print(f"  - Pinbars: {n_pinbars}")
    print(f"  - Bullish Engulfing: {bull_engulf.sum()}")
    print(f"  - Bearish Engulfing: {bear_engulf.sum()}")
    print(f"  - Volume Spikes: {n_spikes}")
    print(f"  - Latest ATR: {atr_values.iloc[-1]:.4f}")
    print(f"  - Current Vol Mode: {vol_mode.iloc[-1]}")

    if all_passed:
        print("\n✓ All tests passed!")
    else:
        print("\n✗ Some tests failed!")

    return all_passed


if __name__ == "__main__":
    import sys

    success = _run_self_test()
    sys.exit(0 if success else 1)
