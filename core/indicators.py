"""
Unified Indicator Library for Strategy Engine v2

Provides vectorized, efficient indicator calculations for technical analysis.
Accepts lists or numpy arrays, returns both latest values and full series.
Dependency-light implementation (no pandas required for core calculations).
"""

from __future__ import annotations
from typing import List, Dict, Any, Union, Tuple, Optional
import math

# Type aliases for clarity
NumericSeries = Union[List[float], List[int]]
NumericValue = Union[float, int]


def _ensure_list(series: Any) -> List[float]:
    """Convert input to list of floats."""
    if hasattr(series, 'tolist'):  # numpy array
        return [float(x) for x in series.tolist()]
    return [float(x) for x in series]


def _validate_series(series: NumericSeries, min_length: int = 1) -> None:
    """Validate that series has sufficient data."""
    if not series or len(series) < min_length:
        raise ValueError(f"Series must have at least {min_length} values, got {len(series) if series else 0}")


def ema(series: NumericSeries, period: int, return_series: bool = False) -> Union[float, List[float]]:
    """
    Exponential Moving Average
    
    Args:
        series: Price series (list or array)
        period: EMA period
        return_series: If True, return full EMA series; if False, return only latest value
    
    Returns:
        Latest EMA value (float) or full EMA series (list)
    """
    _validate_series(series, period)
    data = _ensure_list(series)
    
    if period <= 1:
        return data if return_series else data[-1]
    
    alpha = 2.0 / (period + 1.0)
    ema_values = []
    
    # Initialize with first value
    ema_val = data[0]
    ema_values.append(ema_val)
    
    # Calculate EMA for rest of series
    for price in data[1:]:
        ema_val = alpha * price + (1.0 - alpha) * ema_val
        ema_values.append(ema_val)
    
    return ema_values if return_series else ema_values[-1]


def sma(series: NumericSeries, period: int, return_series: bool = False) -> Union[float, List[float]]:
    """
    Simple Moving Average
    
    Args:
        series: Price series (list or array)
        period: SMA period
        return_series: If True, return full SMA series; if False, return only latest value
    
    Returns:
        Latest SMA value (float) or full SMA series (list)
    """
    _validate_series(series, period)
    data = _ensure_list(series)
    
    if period <= 1:
        return data if return_series else data[-1]
    
    sma_values = []
    
    for i in range(len(data)):
        if i < period - 1:
            # Not enough data yet, use average of what we have
            sma_values.append(sum(data[:i+1]) / (i + 1))
        else:
            # Full period window
            window = data[i - period + 1:i + 1]
            sma_values.append(sum(window) / period)
    
    return sma_values if return_series else sma_values[-1]


def rsi(series: NumericSeries, period: int = 14, return_series: bool = False) -> Union[float, List[float]]:
    """
    Relative Strength Index
    
    Args:
        series: Price series (list or array)
        period: RSI period (default 14)
        return_series: If True, return full RSI series; if False, return only latest value
    
    Returns:
        Latest RSI value (float) or full RSI series (list)
    """
    _validate_series(series, period + 1)
    data = _ensure_list(series)
    
    rsi_values = []
    gains = []
    losses = []
    
    # Calculate price changes
    for i in range(1, len(data)):
        change = data[i] - data[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    
    # Calculate RSI for each point
    for i in range(len(gains)):
        if i < period - 1:
            # Not enough data yet
            rsi_values.append(50.0)
        else:
            # Calculate average gain and loss
            if i == period - 1:
                # First RSI: simple average
                avg_gain = sum(gains[0:period]) / period
                avg_loss = sum(losses[0:period]) / period
            else:
                # Subsequent RSI: smoothed average (Wilder's smoothing)
                avg_gain = (avg_gain * (period - 1) + gains[i]) / period
                avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            
            if avg_loss == 0:
                rsi_values.append(100.0)
            else:
                rs = avg_gain / avg_loss
                rsi_val = 100.0 - (100.0 / (1.0 + rs))
                rsi_values.append(rsi_val)
    
    return rsi_values if return_series else rsi_values[-1]


def atr(high: NumericSeries, low: NumericSeries, close: NumericSeries, 
        period: int = 14, return_series: bool = False) -> Union[float, List[float]]:
    """
    Average True Range
    
    Args:
        high: High price series
        low: Low price series
        close: Close price series
        period: ATR period (default 14)
        return_series: If True, return full ATR series; if False, return only latest value
    
    Returns:
        Latest ATR value (float) or full ATR series (list)
    """
    _validate_series(high, period)
    _validate_series(low, period)
    _validate_series(close, period)
    
    high_data = _ensure_list(high)
    low_data = _ensure_list(low)
    close_data = _ensure_list(close)
    
    if not (len(high_data) == len(low_data) == len(close_data)):
        raise ValueError("high, low, and close series must have same length")
    
    # Calculate True Range
    tr_values = []
    for i in range(len(close_data)):
        h = high_data[i]
        l = low_data[i]
        
        if i == 0:
            # First bar: TR is simply high - low
            tr = h - l
        else:
            c_prev = close_data[i - 1]
            tr1 = h - l
            tr2 = abs(h - c_prev)
            tr3 = abs(l - c_prev)
            tr = max(tr1, tr2, tr3)
        
        tr_values.append(tr)
    
    # Calculate ATR as EMA of TR
    atr_values = []
    atr_val = sum(tr_values[:period]) / period  # First ATR is simple average
    atr_values.extend([atr_val] * period)
    
    # Wilder's smoothing for subsequent values
    for i in range(period, len(tr_values)):
        atr_val = (atr_val * (period - 1) + tr_values[i]) / period
        atr_values.append(atr_val)
    
    return atr_values if return_series else atr_values[-1]


def supertrend(high: NumericSeries, low: NumericSeries, close: NumericSeries,
               period: int = 10, multiplier: float = 3.0,
               return_series: bool = False) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    SuperTrend Indicator
    
    Args:
        high: High price series
        low: Low price series
        close: Close price series
        period: ATR period (default 10)
        multiplier: ATR multiplier (default 3.0)
        return_series: If True, return full series; if False, return only latest value
    
    Returns:
        Dict with 'supertrend', 'direction' (+1 for uptrend, -1 for downtrend), 'upper_band', 'lower_band'
        or list of such dicts if return_series=True
    """
    _validate_series(high, period)
    _validate_series(low, period)
    _validate_series(close, period)
    
    high_data = _ensure_list(high)
    low_data = _ensure_list(low)
    close_data = _ensure_list(close)
    
    # Calculate ATR
    atr_series = atr(high, low, close, period, return_series=True)
    
    # Calculate HL2 (middle price)
    hl2_series = [(high_data[i] + low_data[i]) / 2.0 for i in range(len(close_data))]
    
    supertrend_values = []
    direction = 1  # Start with uptrend
    
    for i in range(len(close_data)):
        basic_upper = hl2_series[i] + multiplier * atr_series[i]
        basic_lower = hl2_series[i] - multiplier * atr_series[i]
        
        # Initialize on first bar
        if i == 0:
            final_upper = basic_upper
            final_lower = basic_lower
            st_value = final_lower
            direction = 1
        else:
            # Calculate final bands
            prev_close = close_data[i - 1]
            
            # Upper band
            if basic_upper < supertrend_values[i - 1]['final_upper'] or prev_close > supertrend_values[i - 1]['final_upper']:
                final_upper = basic_upper
            else:
                final_upper = supertrend_values[i - 1]['final_upper']
            
            # Lower band
            if basic_lower > supertrend_values[i - 1]['final_lower'] or prev_close < supertrend_values[i - 1]['final_lower']:
                final_lower = basic_lower
            else:
                final_lower = supertrend_values[i - 1]['final_lower']
            
            # Determine direction and SuperTrend value
            if close_data[i] <= final_upper:
                st_value = final_upper
                direction = -1  # Downtrend
            else:
                st_value = final_lower
                direction = 1  # Uptrend
        
        supertrend_values.append({
            'supertrend': st_value,
            'direction': direction,
            'upper_band': final_upper,
            'lower_band': final_lower,
            'final_upper': final_upper,
            'final_lower': final_lower
        })
    
    if return_series:
        return supertrend_values
    else:
        return {
            'supertrend': supertrend_values[-1]['supertrend'],
            'direction': supertrend_values[-1]['direction'],
            'upper_band': supertrend_values[-1]['upper_band'],
            'lower_band': supertrend_values[-1]['lower_band']
        }


def bollinger(close: NumericSeries, period: int = 20, stddev: float = 2.0,
              return_series: bool = False) -> Union[Dict[str, float], List[Dict[str, float]]]:
    """
    Bollinger Bands
    
    Args:
        close: Close price series
        period: Moving average period (default 20)
        stddev: Number of standard deviations (default 2.0)
        return_series: If True, return full series; if False, return only latest value
    
    Returns:
        Dict with 'middle', 'upper', 'lower' or list of such dicts if return_series=True
    """
    _validate_series(close, period)
    data = _ensure_list(close)
    
    # Calculate SMA (middle band)
    sma_series = sma(data, period, return_series=True)
    
    bollinger_values = []
    
    for i in range(len(data)):
        if i < period - 1:
            # Not enough data yet
            middle = sma_series[i]
            bollinger_values.append({
                'middle': middle,
                'upper': middle,
                'lower': middle
            })
        else:
            # Calculate standard deviation for window
            window = data[i - period + 1:i + 1]
            middle = sma_series[i]
            
            # Standard deviation
            variance = sum((x - middle) ** 2 for x in window) / period
            std = math.sqrt(variance)
            
            bollinger_values.append({
                'middle': middle,
                'upper': middle + stddev * std,
                'lower': middle - stddev * std
            })
    
    return bollinger_values if return_series else bollinger_values[-1]


def vwap(close: NumericSeries, volume: NumericSeries, 
         return_series: bool = False) -> Union[float, List[float]]:
    """
    Volume Weighted Average Price
    
    Args:
        close: Close price series
        volume: Volume series
        return_series: If True, return full VWAP series; if False, return only latest value
    
    Returns:
        Latest VWAP value (float) or full VWAP series (list)
    """
    _validate_series(close, 1)
    _validate_series(volume, 1)
    
    close_data = _ensure_list(close)
    volume_data = _ensure_list(volume)
    
    if len(close_data) != len(volume_data):
        raise ValueError("close and volume series must have same length")
    
    vwap_values = []
    cumulative_pv = 0.0
    cumulative_vol = 0.0
    
    for i in range(len(close_data)):
        pv = close_data[i] * volume_data[i]
        cumulative_pv += pv
        cumulative_vol += volume_data[i]
        
        if cumulative_vol > 0:
            vwap_values.append(cumulative_pv / cumulative_vol)
        else:
            vwap_values.append(close_data[i])
    
    return vwap_values if return_series else vwap_values[-1]


def slope(series: NumericSeries, period: int, 
          return_series: bool = False) -> Union[float, List[float]]:
    """
    Linear regression slope over a period
    
    Args:
        series: Price series
        period: Period for slope calculation
        return_series: If True, return full slope series; if False, return only latest value
    
    Returns:
        Latest slope value (float) or full slope series (list)
    """
    _validate_series(series, period)
    data = _ensure_list(series)
    
    slope_values = []
    
    for i in range(len(data)):
        if i < period - 1:
            # Not enough data yet
            slope_values.append(0.0)
        else:
            # Calculate slope using linear regression
            window = data[i - period + 1:i + 1]
            n = len(window)
            
            # x values: 0, 1, 2, ..., n-1
            sum_x = n * (n - 1) / 2
            sum_y = sum(window)
            sum_xy = sum(j * window[j] for j in range(n))
            sum_x2 = n * (n - 1) * (2 * n - 1) / 6
            
            # Slope = (n*sum_xy - sum_x*sum_y) / (n*sum_x2 - sum_x^2)
            denominator = n * sum_x2 - sum_x * sum_x
            if denominator != 0:
                slope_val = (n * sum_xy - sum_x * sum_y) / denominator
            else:
                slope_val = 0.0
            
            slope_values.append(slope_val)
    
    return slope_values if return_series else slope_values[-1]


def hl2(high: NumericSeries, low: NumericSeries, 
        return_series: bool = False) -> Union[float, List[float]]:
    """
    HL2: Average of High and Low (typical price without close)
    
    Args:
        high: High price series
        low: Low price series
        return_series: If True, return full series; if False, return only latest value
    
    Returns:
        Latest HL2 value (float) or full HL2 series (list)
    """
    _validate_series(high, 1)
    _validate_series(low, 1)
    
    high_data = _ensure_list(high)
    low_data = _ensure_list(low)
    
    if len(high_data) != len(low_data):
        raise ValueError("high and low series must have same length")
    
    hl2_values = [(high_data[i] + low_data[i]) / 2.0 for i in range(len(high_data))]
    
    return hl2_values if return_series else hl2_values[-1]


def hl3(high: NumericSeries, low: NumericSeries, close: NumericSeries,
        return_series: bool = False) -> Union[float, List[float]]:
    """
    HL3: Average of High, Low, and Close (typical price)
    
    Args:
        high: High price series
        low: Low price series
        close: Close price series
        return_series: If True, return full series; if False, return only latest value
    
    Returns:
        Latest HL3 value (float) or full HL3 series (list)
    """
    _validate_series(high, 1)
    _validate_series(low, 1)
    _validate_series(close, 1)
    
    high_data = _ensure_list(high)
    low_data = _ensure_list(low)
    close_data = _ensure_list(close)
    
    if not (len(high_data) == len(low_data) == len(close_data)):
        raise ValueError("high, low, and close series must have same length")
    
    hl3_values = [(high_data[i] + low_data[i] + close_data[i]) / 3.0 
                  for i in range(len(high_data))]
    
    return hl3_values if return_series else hl3_values[-1]


def compute_bundle(
    series: Dict[str, List[float]],
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Compute a unified bundle of indicators for Strategy Engine v3.
    
    This is the primary indicator computation function for v3 strategies.
    It computes all standard indicators and returns them in a dictionary.
    
    Args:
        series: Dict with keys: open, high, low, close, volume (lists)
        config: Optional configuration for indicator parameters
    
    Returns:
        Dictionary of computed indicators with keys like:
        - ema9, ema20, ema50, ema100, ema200
        - sma20, sma50
        - rsi14
        - atr14
        - bb_upper, bb_middle, bb_lower
        - vwap
        - slope10
        - trend (derived from EMAs)
    """
    config = config or {}
    close = series.get("close", [])
    high = series.get("high", [])
    low = series.get("low", [])
    volume = series.get("volume", [])
    
    if not close or len(close) < 20:
        return {}
    
    bundle = {}
    
    try:
        # EMAs
        if len(close) >= 9:
            bundle["ema9"] = ema(close, 9)
        if len(close) >= 20:
            bundle["ema20"] = ema(close, 20)
        if len(close) >= 50:
            bundle["ema50"] = ema(close, 50)
        if len(close) >= 100:
            bundle["ema100"] = ema(close, 100)
        if len(close) >= 200:
            bundle["ema200"] = ema(close, 200)
        
        # SMAs
        if len(close) >= 20:
            bundle["sma20"] = sma(close, 20)
        if len(close) >= 50:
            bundle["sma50"] = sma(close, 50)
        
        # RSI
        if len(close) >= 15:
            bundle["rsi14"] = rsi(close, 14)
        
        # ATR
        if len(high) >= 14 and len(low) >= 14:
            bundle["atr14"] = atr(high, low, close, 14)
        
        # Bollinger Bands
        if len(close) >= 20:
            bb = bollinger(close, 20, 2.0)
            bundle["bb_upper"] = bb["upper"]
            bundle["bb_middle"] = bb["middle"]
            bundle["bb_lower"] = bb["lower"]
        
        # VWAP
        if volume and len(volume) == len(close):
            bundle["vwap"] = vwap(close, volume)
        
        # Slope
        if len(close) >= 10:
            bundle["slope10"] = slope(close, 10)
        
        # HL2/HL3
        if high and low:
            bundle["hl2"] = hl2(high, low)
            bundle["hl3"] = hl3(high, low, close)
        
        # Trend determination
        if "ema20" in bundle and "ema50" in bundle:
            bundle["trend"] = "up" if bundle["ema20"] > bundle["ema50"] else "down"
        
    except Exception as e:
        # Log error but don't crash - return partial bundle
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("Error computing indicator bundle: %s", e)
    
    return bundle
