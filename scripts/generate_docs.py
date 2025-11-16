#!/usr/bin/env python3
"""
Auto-generate comprehensive documentation for the HFT trading system.

This script scans the repository structure and generates markdown documentation
covering all engines, strategies, indicators, and system components.
"""

from __future__ import annotations

import ast
import inspect
import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Repository root
REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"

# Key directories to scan
ENGINE_DIR = REPO_ROOT / "engine"
CORE_DIR = REPO_ROOT / "core"
STRATEGIES_DIR = REPO_ROOT / "strategies"
BROKER_DIR = REPO_ROOT / "broker"
UI_DIR = REPO_ROOT / "ui"
SCRIPTS_DIR = REPO_ROOT / "scripts"
ANALYTICS_DIR = REPO_ROOT / "analytics"
RISK_DIR = REPO_ROOT / "risk"


class CodeAnalyzer:
    """Analyzes Python code files to extract structure and documentation."""
    
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.source = file_path.read_text(encoding="utf-8", errors="ignore")
        try:
            self.tree = ast.parse(self.source)
        except SyntaxError:
            logger.warning(f"Failed to parse {file_path}")
            self.tree = None
    
    def extract_classes(self) -> List[Dict[str, Any]]:
        """Extract class names and their methods."""
        if not self.tree:
            return []
        
        classes = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                methods = []
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        if not item.name.startswith('_') or item.name in ['__init__']:
                            methods.append(item.name)
                
                docstring = ast.get_docstring(node)
                classes.append({
                    "name": node.name,
                    "methods": methods,
                    "docstring": docstring or ""
                })
        
        return classes
    
    def extract_functions(self) -> List[Dict[str, Any]]:
        """Extract top-level functions."""
        if not self.tree:
            return []
        
        functions = []
        for node in self.tree.body:
            if isinstance(node, ast.FunctionDef):
                if not node.name.startswith('_'):
                    docstring = ast.get_docstring(node)
                    functions.append({
                        "name": node.name,
                        "docstring": docstring or ""
                    })
        
        return functions
    
    def extract_imports(self) -> List[str]:
        """Extract import statements to understand dependencies."""
        if not self.tree:
            return []
        
        imports = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        
        return imports


def generate_overview() -> str:
    """Generate Overview.md with big picture architecture."""
    content = """# HFT Trading System - Overview

## System Architecture

This is a high-frequency trading (HFT) system built for the Indian stock market via Zerodha Kite API.

### Core Philosophy

- **Separation of Concerns**: Clear boundaries between paper/live/backtest modes
- **Event-Driven**: WebSocket-based real-time tick processing
- **Risk-First**: Multiple layers of risk validation before execution
- **State Management**: Persistent checkpoints and journaling
- **Self-Documenting**: Auto-generated documentation from code

## System Components

### Trading Modes

1. **Paper Mode** (`engine/paper_engine.py`)
   - Simulated trading with virtual capital
   - Instant fills at requested prices
   - Risk-free strategy testing

2. **Live Mode** (`engine/live_engine.py`)
   - Real order placement via Kite API
   - WebSocket tick processing
   - Full safety guardrails

3. **Backtest Mode** (`broker/backtest_broker.py`)
   - Historical data replay
   - Performance metrics
   - Strategy optimization

### Core Engines

- **Strategy Engine v2** (`core/strategy_engine_v2.py`): Modern strategy framework
- **Market Data Engine** (`core/market_data_engine.py`): Candle management and caching
- **Risk Engine** (`core/risk_engine.py`): Position sizing and risk checks
- **Execution Router** (`broker/execution_router.py`): Mode-aware order routing

### Data Flow

```
WebSocket Ticks → Market Data Engine → Strategy Engine → Risk Engine → Execution Router
                                                                              ↓
                                                              Paper Broker / Live Broker
```

### State Management

- **StateStore** (`core/state_store.py`): Runtime state checkpointing
- **JournalStore**: Order and fill history
- **TradeRecorder** (`analytics/trade_recorder.py`): Performance tracking

## Key Features

- Multi-timeframe strategy support
- Dynamic position sizing
- Adaptive risk management
- Real-time performance monitoring
- Web-based dashboard
- Comprehensive logging and analytics

## Technology Stack

- **Language**: Python 3.12+
- **Broker API**: Zerodha KiteConnect
- **Web Framework**: FastAPI
- **Data**: Pandas, NumPy
- **Market Hours**: IST 9:15 AM - 3:30 PM

## Getting Started

See `Commands.md` for running the system in different modes.

---
*Auto-generated on {timestamp}*
"""
    timestamp = datetime.now(timezone.utc).isoformat()
    return content.replace("{timestamp}", timestamp)


def generate_repo_map() -> str:
    """Generate RepoMap.md with file/folder tree."""
    content = """# Repository Map

## Directory Structure

```
kite-algo-minimal/
│
├── engine/              # Trading engines
│   ├── paper_engine.py      # Paper trading orchestrator
│   ├── live_engine.py       # Live trading orchestrator  
│   ├── equity_paper_engine.py
│   ├── options_paper_engine.py
│   ├── meta_strategy_engine.py
│   └── bootstrap.py         # Engine initialization
│
├── core/                # Core system components
│   ├── strategy_engine_v2.py    # Modern strategy framework
│   ├── market_data_engine.py    # Market data management
│   ├── risk_engine.py           # Risk validation
│   ├── risk_engine_v2.py        # Enhanced risk engine
│   ├── indicators.py            # Technical indicators
│   ├── state_store.py           # State management
│   ├── strategy_registry.py    # Strategy catalog
│   ├── config.py                # Configuration management
│   └── ...
│
├── strategies/          # Trading strategies
│   ├── base.py                  # Base strategy class
│   ├── ema20_50_intraday_v2.py  # EMA crossover strategy
│   ├── fno_intraday_trend.py    # F&O trend following
│   ├── mean_reversion_intraday.py
│   └── equity_intraday_simple.py
│
├── broker/              # Broker integrations
│   ├── execution_router.py      # Mode-aware routing
│   ├── paper_broker.py          # Paper trading broker
│   ├── live_broker.py           # Live trading broker
│   ├── backtest_broker.py       # Backtest broker
│   ├── kite_bridge.py           # Kite API wrapper
│   └── auth.py                  # Authentication
│
├── ui/                  # Web dashboard
│   ├── dashboard.py             # FastAPI dashboard
│   ├── services.py              # Dashboard services
│   ├── static/                  # Static assets
│   └── templates/               # HTML templates
│
├── scripts/             # Utility scripts
│   ├── generate_docs.py         # Documentation generator
│   ├── run_paper_equity.py      # Run paper equity mode
│   ├── run_backtest.py          # Run backtests
│   ├── login_kite.py            # Kite authentication
│   └── ...
│
├── analytics/           # Performance analytics
│   ├── trade_recorder.py        # Trade journaling
│   ├── strategy_performance.py  # Strategy metrics
│   └── ...
│
├── risk/                # Risk management
│   ├── adaptive_risk_manager.py
│   ├── position_sizer.py
│   └── cost_model.py
│
├── data/                # Data management
│   ├── broker_feed.py
│   ├── instruments.py
│   └── backtest_data.py
│
├── docs/                # Documentation (auto-generated)
│   └── *.md
│
├── artifacts/           # Runtime artifacts
│   ├── checkpoints/
│   ├── logs/
│   └── market_data/
│
├── configs/             # Configuration files
├── secrets/             # API credentials (gitignored)
└── tests/               # Test suite

```

## Key Files

### Engine Layer
- `engine/paper_engine.py`: Main paper trading orchestrator with simulated fills
- `engine/live_engine.py`: Live trading with real Kite orders

### Core Layer
- `core/strategy_engine_v2.py`: Strategy execution framework
- `core/market_data_engine.py`: Candle fetching and caching
- `core/risk_engine.py`: Risk checks and position sizing
- `core/indicators.py`: Technical indicator library
- `core/state_store.py`: State persistence

### Strategy Layer
- `strategies/base.py`: Base strategy interface
- `strategies/*.py`: Individual strategy implementations

### Broker Layer
- `broker/execution_router.py`: Routes orders based on mode
- `broker/paper_broker.py`: In-memory position tracking
- `broker/kite_bridge.py`: Kite API integration

### UI Layer
- `ui/dashboard.py`: FastAPI web dashboard
- `ui/templates/`: Dashboard HTML templates

---
*Auto-generated on {timestamp}*
"""
    timestamp = datetime.now(timezone.utc).isoformat()
    return content.replace("{timestamp}", timestamp)


def analyze_engine_file(file_path: Path) -> Dict[str, Any]:
    """Analyze an engine file and extract key information."""
    analyzer = CodeAnalyzer(file_path)
    classes = analyzer.extract_classes()
    functions = analyzer.extract_functions()
    
    return {
        "file": file_path.name,
        "classes": classes,
        "functions": functions
    }


def generate_paper_docs() -> str:
    """Generate Paper.md documenting paper trading engine."""
    paper_file = ENGINE_DIR / "paper_engine.py"
    info = analyze_engine_file(paper_file) if paper_file.exists() else {}
    
    content = """# Paper Trading Mode

## Overview

The **Paper Trading Engine** simulates trading without placing real orders. It provides a risk-free environment to test strategies and track hypothetical performance.

## Architecture

### Core Components

- **PaperEngine** (`engine/paper_engine.py`): Main paper trading orchestrator
- **PaperBroker** (`broker/paper_broker.py`): In-memory position tracking
- **StrategyEngine v2**: Strategy logic and signal generation
- **RiskEngine**: Risk checks and position sizing
- **MarketDataEngine**: Market data fetching and caching

### Execution Router

The `ExecutionRouter` in paper mode routes all orders to `PaperBroker`:
- Orders filled instantly at requested price
- No slippage simulation (optional enhancement)
- No brokerage costs (unless using CostModel)

## How It Works

1. **Initialization**
   - Loads config and paper capital amount
   - Initializes in-memory broker with zero positions
   - Sets up strategy and risk engines
   - Configures universe of symbols to trade

2. **Main Loop**
   - Fetches LTP (Last Traded Price) for each symbol
   - Runs strategy engine to generate signals
   - Validates signals through risk engine
   - Places simulated orders via PaperBroker
   - Updates positions and P&L

3. **Position Tracking**
   - Entry price averaging for multiple entries
   - Realized P&L on exits
   - Unrealized P&L on open positions
   - Position-level stop loss tracking

4. **State Management**
   - Periodic checkpoints to disk
   - Order and fill journaling
   - Equity curve snapshots
   - Trade performance metrics

## Key Classes

"""
    
    # Add class information
    if info.get("classes"):
        for cls in info["classes"]:
            content += f"### {cls['name']}\n\n"
            if cls.get("docstring"):
                content += f"{cls['docstring']}\n\n"
            if cls.get("methods"):
                content += "**Methods:**\n"
                for method in cls["methods"][:10]:  # Limit to first 10
                    content += f"- `{method}()`\n"
                content += "\n"
    
    content += """
## Running Paper Mode

```bash
# Run paper trading for equities
python scripts/run_paper_equity.py

# Run paper trading for F&O
python scripts/run_paper_fno.py
```

## Configuration

Paper mode configuration in `configs/config.yaml`:

```yaml
trading:
  mode: PAPER
  paper_capital: 100000
  
risk:
  max_positions_total: 5
  per_trade_risk_pct: 2.0
```

## Benefits

- **Risk-Free Testing**: No real capital at risk
- **Fast Iteration**: Quick strategy validation
- **Full Logging**: Complete audit trail
- **Realistic Simulation**: Same code path as live

## Limitations

- **Instant Fills**: No slippage or partial fills
- **No Market Impact**: Assumes infinite liquidity
- **Perfect Execution**: No rejected orders

---
*Auto-generated on {timestamp}*
"""
    timestamp = datetime.now(timezone.utc).isoformat()
    return content.replace("{timestamp}", timestamp)


def generate_live_docs() -> str:
    """Generate Live.md documenting live trading engine."""
    live_file = ENGINE_DIR / "live_engine.py"
    info = analyze_engine_file(live_file) if live_file.exists() else {}
    
    content = """# Live Trading Mode

## Overview

The **Live Trading Engine** places **REAL orders** via the Kite broker API. It runs in parallel with the Paper engine but diverges at the execution layer.

## Architecture

### Shared Components

Live mode shares the following components with Paper mode:

- **StrategyEngine v2**: Strategy logic and signal generation
- **RiskEngine**: Risk checks, position sizing, and safety guardrails
- **MarketDataEngine**: Market data fetching and candle management
- **StateStore**: Checkpoint and state management

### Live-Specific Components

- **LiveEngine** (`engine/live_engine.py`): Main live trading orchestrator
- **KiteBroker** (`broker/kite_bridge.py`): Kite API adapter for orders and ticks
- **WebSocket Ticker**: Real-time price updates via Kite WebSocket

## How It Works

1. **Initialization**
   - Validates Kite session (requires valid access token)
   - Subscribes to WebSocket ticks for configured symbols
   - Loads risk settings and universe from config

2. **Tick Processing**
   - Receives ticks via WebSocket
   - Updates market data engine
   - Runs strategy engine for each symbol
   - Generates signals (BUY, SELL, EXIT, HOLD)

3. **Order Placement**
   - Signal → Order Intent
   - Intent → RiskEngine validation
   - If approved → Place REAL order via KiteBroker
   - Track pending orders and handle updates

4. **Safety Guardrails**
   - Login validation before every order
   - Market hours check (IST 9:15 AM - 3:30 PM)
   - RiskEngine blocks (BLOCK, REDUCE, HALT_SESSION)
   - Robust exception handling
   - Clear log warnings

## Key Classes

"""
    
    if info.get("classes"):
        for cls in info["classes"]:
            content += f"### {cls['name']}\n\n"
            if cls.get("docstring"):
                content += f"{cls['docstring']}\n\n"
            if cls.get("methods"):
                content += "**Methods:**\n"
                for method in cls["methods"][:10]:
                    content += f"- `{method}()`\n"
                content += "\n"
    
    content += """
## Running Live Mode

**⚠️ WARNING: Live mode places REAL orders with REAL money!**

```bash
# First, authenticate with Kite
python scripts/login_kite.py

# Then run live engine
python scripts/run_live.py
```

## Configuration

Live mode configuration in `configs/config.yaml`:

```yaml
trading:
  mode: LIVE
  capital: 100000
  
risk:
  mode: live
  max_daily_loss_pct: 5.0
  max_positions_total: 3
  per_trade_risk_pct: 1.0
```

## Safety Features

- **Pre-Order Validation**: Login check before every order
- **Market Hours**: Only trades during market hours
- **Risk Limits**: Hard caps on position size and daily loss
- **Emergency Halt**: Can halt all trading instantly
- **Order Tracking**: Full order lifecycle monitoring

## Live vs Paper Differences

| Feature | Paper | Live |
|---------|-------|------|
| Order Placement | Simulated | Real Kite API |
| Fill Timing | Instant | Async via WebSocket |
| Slippage | None | Real market slippage |
| Costs | Optional | Real brokerage fees |
| Risk | Zero | Real capital |

## Monitoring

- Check dashboard at `http://localhost:8000`
- Monitor logs in `artifacts/logs/`
- Track positions in real-time
- View P&L and performance metrics

---
*Auto-generated on {timestamp}*
"""
    timestamp = datetime.now(timezone.utc).isoformat()
    return content.replace("{timestamp}", timestamp)


def generate_execution_engine_docs() -> str:
    """Generate ExecutionEngine.md."""
    content = """# Execution Engine

## Overview

The **Execution Router** provides mode-aware order routing, directing orders to the appropriate broker based on the trading mode.

## Architecture

### ExecutionRouter

Located in `broker/execution_router.py`, the router determines where orders go:

- **PAPER/REPLAY**: Routes to `PaperBroker`
- **LIVE**: Routes to `KiteClient` (real orders)

### Components

1. **ExecutionRouter** (`broker/execution_router.py`)
   - Mode detection
   - Order routing logic
   - Broker initialization

2. **PaperBroker** (`broker/paper_broker.py`)
   - In-memory position tracking
   - Instant fill simulation
   - P&L calculation

3. **LiveBroker/KiteBroker** (`broker/kite_bridge.py`)
   - Real Kite API integration
   - Order placement and tracking
   - WebSocket order updates

4. **BacktestBroker** (`broker/backtest_broker.py`)
   - Historical data replay
   - Slippage simulation
   - Commission modeling

## Order Flow

```
Strategy Signal
      ↓
Risk Validation
      ↓
Order Intent
      ↓
ExecutionRouter
      ↓
   [Mode Check]
      ↓
Paper → PaperBroker.place_order()
Live  → KiteBroker.place_order()
```

## Broker Interfaces

### PaperBroker

```python
def place_order(symbol, side, quantity, price):
    # Instant fill at requested price
    # Update internal positions
    # Return order_id
```

### KiteBroker

```python
def place_order(symbol, side, quantity, price):
    # Call Kite API
    # Track pending order
    # Wait for WebSocket confirmation
    # Return order_id
```

## Key Features

- **Unified Interface**: Same API regardless of mode
- **Mode Isolation**: Clear separation between paper/live
- **Safety**: Validation at router level
- **Flexibility**: Easy to add new brokers

## Configuration

```yaml
trading:
  mode: PAPER  # or LIVE, REPLAY, BACKTEST
```

---
*Auto-generated on {timestamp}*
"""
    timestamp = datetime.now(timezone.utc).isoformat()
    return content.replace("{timestamp}", timestamp)


def generate_strategy_engine_docs() -> str:
    """Generate StrategyEngine.md."""
    strategy_file = CORE_DIR / "strategy_engine_v2.py"
    info = analyze_engine_file(strategy_file) if strategy_file.exists() else {}
    
    content = """# Strategy Engine v2

## Overview

The **Strategy Engine v2** is a modern strategy execution framework with unified indicator calculations and clean separation between strategy logic, market data, and execution.

## Architecture

### Core Components

1. **StrategyEngineV2** (`core/strategy_engine_v2.py`)
   - Strategy lifecycle management
   - Signal generation coordination
   - State tracking

2. **BaseStrategy** - Abstract base class for all strategies
   - Signal generation interface
   - State management
   - Configuration handling

3. **StrategyState** - Per-strategy state tracking
   - Position tracking
   - Signal history
   - Metadata storage

4. **OrderIntent** - Pre-execution order representation
   - Symbol, action, quantity
   - Reason and confidence
   - Metadata

## Key Classes

"""
    
    if info.get("classes"):
        for cls in info["classes"]:
            content += f"### {cls['name']}\n\n"
            if cls.get("docstring"):
                content += f"{cls['docstring']}\n\n"
            if cls.get("methods"):
                content += "**Methods:**\n"
                for method in cls["methods"][:10]:
                    content += f"- `{method}()`\n"
                content += "\n"
    
    content += """
## Signal Flow

```
Market Data
     ↓
Strategy.generate_signal()
     ↓
OrderIntent
     ↓
Risk Validation
     ↓
Execution
```

## Strategy Implementation

### Example Strategy Structure

```python
class MyStrategy(BaseStrategy):
    def __init__(self, config, strategy_state):
        super().__init__(config, strategy_state)
        self.name = "MyStrategy"
        self.timeframe = "5m"
    
    def generate_signal(self, symbol, candles, ltp, metadata):
        # Calculate indicators
        # Generate trading signal
        # Return OrderIntent or None
        pass
```

## Strategy Registry

Strategies are registered in `core/strategy_registry.py`:

```python
STRATEGY_REGISTRY = {{
    "EMA_20_50": StrategyInfo(
        code="EMA_20_50",
        name="EMA 20/50 Crossover",
        enabled=True,
        ...
    )
}}
```

## Features

- **Indicator Integration**: Direct access to `core.indicators`
- **State Management**: Per-strategy position and signal tracking
- **Configuration**: YAML-based strategy parameters
- **Extensibility**: Easy to add new strategies
- **Testing**: Clean interfaces for unit testing

## Benefits Over v1

- **Cleaner API**: No direct market data fetching in strategies
- **Better Testing**: Strategies receive all data as parameters
- **Unified Indicators**: Single source of truth for calculations
- **State Isolation**: Each strategy has independent state

---
*Auto-generated on {timestamp}*
"""
    timestamp = datetime.now(timezone.utc).isoformat()
    return content.replace("{timestamp}", timestamp)


def analyze_indicators() -> List[str]:
    """Extract list of indicators from indicators.py."""
    indicators_file = CORE_DIR / "indicators.py"
    if not indicators_file.exists():
        return []
    
    analyzer = CodeAnalyzer(indicators_file)
    functions = analyzer.extract_functions()
    return [f["name"] for f in functions]


def generate_indicators_docs() -> str:
    """Generate Indicators.md."""
    indicators = analyze_indicators()
    
    content = """# Technical Indicators

## Overview

The `core/indicators.py` module provides a unified indicator library with vectorized, efficient calculations for technical analysis.

## Features

- **Vectorized**: Efficient numpy-based calculations
- **Flexible**: Returns single values or full series
- **Dependency-Light**: No pandas required
- **Well-Tested**: Comprehensive test coverage

## Available Indicators

"""
    
    if indicators:
        for indicator in indicators:
            content += f"### `{indicator}()`\n\n"
            content += f"Calculates {indicator.upper()} indicator.\n\n"
    
    content += """
## Usage Examples

### EMA (Exponential Moving Average)

```python
from core import indicators

# Get latest EMA value
ema_20 = indicators.ema(close_prices, period=20)

# Get full EMA series
ema_series = indicators.ema(close_prices, period=20, return_series=True)
```

### RSI (Relative Strength Index)

```python
# Get current RSI
rsi_14 = indicators.rsi(close_prices, period=14)

# Overbought/oversold check
if rsi_14 > 70:
    # Overbought
elif rsi_14 < 30:
    # Oversold
```

### SMA (Simple Moving Average)

```python
sma_50 = indicators.sma(close_prices, period=50)
sma_200 = indicators.sma(close_prices, period=200)

# Golden cross
if sma_50 > sma_200:
    # Bullish
```

### MACD (Moving Average Convergence Divergence)

```python
macd, signal, histogram = indicators.macd(close_prices)

if macd > signal:
    # Bullish crossover
```

### Bollinger Bands

```python
upper, middle, lower = indicators.bollinger_bands(close_prices, period=20, std_dev=2)

# Price breakout
if price > upper:
    # Upper band breakout
```

### ATR (Average True Range)

```python
atr_14 = indicators.atr(high_prices, low_prices, close_prices, period=14)

# Position sizing based on volatility
position_size = capital * risk_pct / atr_14
```

## Implementation Details

- **Input Validation**: Checks for sufficient data points
- **Type Flexibility**: Accepts lists or numpy arrays
- **NaN Handling**: Graceful handling of missing data
- **Performance**: Optimized for real-time tick processing

## Adding New Indicators

To add a new indicator:

1. Add function to `core/indicators.py`
2. Follow naming convention (lowercase, descriptive)
3. Include docstring with parameters and returns
4. Add unit tests in `tests/test_indicators.py`
5. Update this documentation (auto-generated)

---
*Auto-generated on {timestamp}*
"""
    timestamp = datetime.now(timezone.utc).isoformat()
    return content.replace("{timestamp}", timestamp)


def analyze_strategies() -> List[Dict[str, Any]]:
    """Extract strategy information."""
    strategies = []
    
    if not STRATEGIES_DIR.exists():
        return strategies
    
    for file_path in STRATEGIES_DIR.glob("*.py"):
        if file_path.name.startswith("_") or file_path.name == "base.py":
            continue
        
        analyzer = CodeAnalyzer(file_path)
        classes = analyzer.extract_classes()
        
        for cls in classes:
            if "Strategy" in cls["name"]:
                strategies.append({
                    "name": cls["name"],
                    "file": file_path.name,
                    "docstring": cls.get("docstring", "")
                })
    
    return strategies


def generate_strategies_docs() -> str:
    """Generate Strategies.md."""
    strategies = analyze_strategies()
    
    content = """# Trading Strategies

## Overview

This document lists all implemented trading strategies in the system.

## Strategy List

"""
    
    for strategy in strategies:
        content += f"### {strategy['name']}\n\n"
        content += f"**File**: `strategies/{strategy['file']}`\n\n"
        if strategy.get("docstring"):
            content += f"{strategy['docstring']}\n\n"
        content += "---\n\n"
    
    content += """
## Strategy Structure

All strategies inherit from `BaseStrategy` and implement:

```python
class MyStrategy(BaseStrategy):
    def generate_signal(self, symbol, candles, ltp, metadata):
        # Strategy logic here
        return OrderIntent(...) or None
```

## Strategy Types

### Trend Following
- EMA crossover strategies
- Momentum-based entries
- Trend confirmation filters

### Mean Reversion
- Bollinger Band reversions
- RSI oversold/overbought
- Support/resistance bounces

### Breakout
- Range breakouts
- Volume-confirmed breakouts
- Volatility-based entries

## Strategy Configuration

Strategies are configured in `configs/config.yaml`:

```yaml
strategies:
  EMA_20_50:
    enabled: true
    timeframe: "5m"
    symbols: ["NIFTY", "BANKNIFTY"]
    params:
      fast_period: 20
      slow_period: 50
```

## Adding New Strategies

1. Create new file in `strategies/` directory
2. Inherit from `BaseStrategy`
3. Implement `generate_signal()` method
4. Register in `core/strategy_registry.py`
5. Add configuration in `configs/config.yaml`
6. Test in paper mode first

---
*Auto-generated on {timestamp}*
"""
    timestamp = datetime.now(timezone.utc).isoformat()
    return content.replace("{timestamp}", timestamp)


def generate_market_data_engine_docs() -> str:
    """Generate MarketDataEngine.md."""
    content = """# Market Data Engine

## Overview

The **Market Data Engine** manages candle data fetching, caching, and real-time updates via the Kite API.

## Architecture

### Components

1. **MarketDataEngine** (`core/market_data_engine.py`)
   - Historical candle fetching
   - Local cache management
   - LTP (Last Traded Price) retrieval
   - Multi-timeframe support

2. **Cache System**
   - JSON-based candle storage
   - Incremental updates
   - Timeframe-specific caching

3. **Kite Integration**
   - Historical data API calls
   - WebSocket tick processing
   - Instrument token resolution

## Features

### Candle Management

```python
# Fetch historical candles
candles = mde.fetch_historical("NIFTY", "5m", count=200)

# Load from cache
candles = mde.load_cache("NIFTY", "5m")

# Save to cache
mde.save_cache("NIFTY", "5m", candles)
```

### LTP Retrieval

```python
# Get last traded price
ltp = mde.get_ltp("NIFTY")

# Batch LTP for multiple symbols
ltps = mde.get_ltp_batch(["NIFTY", "BANKNIFTY", "FINNIFTY"])
```

### Multi-Timeframe

```python
# Configure multiple timeframes per symbol
config = {{
    "NIFTY": ["1m", "5m", "15m"],
    "BANKNIFTY": ["1m", "5m"]
}}

# Engine handles all timeframes automatically
```

## Cache Structure

```
artifacts/market_data/
├── NIFTY_1m.json
├── NIFTY_5m.json
├── BANKNIFTY_1m.json
└── ...
```

## Candle Format

```python
{{
    "ts": "2024-01-15T09:15:00+00:00",
    "open": 21500.0,
    "high": 21520.0,
    "low": 21495.0,
    "close": 21510.0,
    "volume": 1250000
}}
```

## Performance

- **Cache-First**: Reduces API calls
- **Incremental Updates**: Only fetches new candles
- **Async-Ready**: Supports concurrent requests
- **Rate Limiting**: Respects Kite API limits

## Timeframe Support

| Timeframe | Interval | Use Case |
|-----------|----------|----------|
| 1m | minute | Scalping |
| 3m | 3minute | Quick trades |
| 5m | 5minute | Intraday |
| 15m | 15minute | Swing |
| 60m | 60minute | Hourly |
| day | day | Daily |

---
*Auto-generated on {timestamp}*
"""
    timestamp = datetime.now(timezone.utc).isoformat()
    return content.replace("{timestamp}", timestamp)


def generate_risk_engine_docs() -> str:
    """Generate RiskEngine.md."""
    content = """# Risk Engine

## Overview

The **Risk Engine** validates all trading decisions before execution, enforcing position limits, loss limits, and other safety guardrails.

## Architecture

### Components

1. **RiskEngine** (`core/risk_engine.py`)
   - Entry validation
   - Exit validation
   - Position sizing
   - Loss tracking

2. **RiskConfig** - Configuration dataclass
   - Capital limits
   - Position limits
   - Loss limits
   - Trade frequency limits

3. **RiskDecision** - Risk check result
   - ALLOW: Trade approved
   - BLOCK: Trade rejected
   - REDUCE: Trade approved with reduced size
   - HALT_SESSION: Stop all trading

## Risk Checks

### Entry Checks

```python
ctx = TradeContext(
    symbol="NIFTY",
    action="BUY",
    qty=75,
    capital=100000,
    ...
)

decision = risk_engine.check_entry(ctx)

if decision.action == RiskAction.ALLOW:
    # Place order
elif decision.action == RiskAction.REDUCE:
    # Place order with reduced qty
    adjusted_qty = decision.adjusted_qty
else:
    # Block trade
```

### Exit Checks

```python
ctx = TradeContext(
    symbol="NIFTY",
    action="EXIT",
    position_qty=75,
    ...
)

decision = risk_engine.check_exit(ctx)
# Exits are usually always allowed
```

## Risk Rules

### Position Limits

- **Max Positions Total**: Hard cap on concurrent positions
- **Max Positions Per Symbol**: Limit on same symbol
- **Position Sizing**: Based on capital and risk percentage

### Loss Limits

- **Max Daily Loss (Absolute)**: Hard rupee amount
- **Max Daily Loss (Percentage)**: Percentage of capital
- **Max Per-Trade Loss**: Stop loss per position

### Frequency Limits

- **Max Trades Per Symbol Per Day**: Prevent overtrading
- **Min Seconds Between Entries**: Cool-down period
- **Trade Throttling**: Rate limiting

## Configuration

```yaml
risk:
  mode: live
  capital: 100000
  per_trade_risk_pct: 2.0
  
  max_daily_loss_abs: 5000
  max_daily_loss_pct: 5.0
  
  max_positions_total: 5
  max_positions_per_symbol: 2
  max_trades_per_symbol_per_day: 3
  min_seconds_between_entries: 300
```

## Risk Actions

| Action | Meaning | Behavior |
|--------|---------|----------|
| ALLOW | Trade approved | Execute as requested |
| BLOCK | Trade rejected | Do not execute |
| REDUCE | Size reduced | Execute with smaller qty |
| HALT_SESSION | Emergency stop | Stop all trading immediately |

## State Tracking

The risk engine tracks:
- Open positions
- Daily P&L
- Trade counts per symbol
- Last trade timestamps
- Capital utilization

## Safety Features

- **Pre-Trade Validation**: All signals validated before execution
- **Dynamic Position Sizing**: Based on ATR or volatility
- **Circuit Breakers**: Auto-halt on loss limits
- **Override Capability**: Manual halt/resume

## Integration

```python
# Initialize
risk_engine = RiskEngine(config, state, logger)

# Check entry
decision = risk_engine.check_entry(trade_context)

# Update state after fill
risk_engine.update_state(fill_info)
```

---
*Auto-generated on {timestamp}*
"""
    timestamp = datetime.now(timezone.utc).isoformat()
    return content.replace("{timestamp}", timestamp)


def generate_signals_docs() -> str:
    """Generate Signals.md."""
    content = """# Trading Signals

## Overview

Signals are the output of strategy evaluation, indicating desired trading actions.

## Signal Types

### BUY
- Enter a new long position
- Add to existing long position
- Generated when bullish conditions met

### SELL
- Enter a new short position
- Add to existing short position
- Generated when bearish conditions met

### EXIT
- Close existing position
- Can be profit target or stop loss
- Generated when exit conditions met

### HOLD
- No action required
- Default when no setup present
- Maintains current position state

## Signal Structure

### OrderIntent

```python
class OrderIntent:
    symbol: str          # Trading symbol
    action: str          # "BUY", "SELL", "EXIT"
    qty: int            # Order quantity
    reason: str         # Human-readable reason
    strategy_code: str  # Strategy identifier
    confidence: float   # Signal confidence (0-1)
    metadata: dict      # Additional data
```

### Example Signal

```python
signal = OrderIntent(
    symbol="NIFTY",
    action="BUY",
    qty=75,
    reason="EMA 20 crossed above EMA 50",
    strategy_code="EMA_20_50",
    confidence=0.85,
    metadata={{
        "ema_20": 21500.0,
        "ema_50": 21480.0,
        "rsi": 62.5
    }}
)
```

## Signal Generation

### Strategy-Based

```python
def generate_signal(self, symbol, candles, ltp, metadata):
    # Calculate indicators
    ema_20 = indicators.ema(closes, 20)
    ema_50 = indicators.ema(closes, 50)
    
    # Generate signal
    if ema_20 > ema_50 and not self.state.is_position_open(symbol):
        return OrderIntent(
            symbol=symbol,
            action="BUY",
            qty=self.calculate_qty(),
            reason="Bullish EMA crossover",
            strategy_code=self.name,
            confidence=0.8
        )
    
    return None  # HOLD
```

## Signal Quality

Signals are scored on:
- **Confidence**: Strategy's conviction (0-1)
- **Timing**: How fresh the setup is
- **Context**: Market regime alignment
- **Risk/Reward**: Expected profit vs risk

## Signal Filters

### Pattern Filters
- Trend alignment
- Volume confirmation
- Volatility requirements

### Risk Filters
- Position limits
- Capital constraints
- Correlation limits

### Time Filters
- Market hours
- High-volatility periods
- News events

## Signal Flow

```
Strategy.generate_signal()
        ↓
   OrderIntent
        ↓
Signal Quality Check
        ↓
  Risk Validation
        ↓
   Execution
```

## Signal Metadata

Metadata can include:
- Indicator values at signal time
- Support/resistance levels
- Volatility metrics
- Volume profile
- Market regime

## Best Practices

1. **Clear Reasons**: Always provide human-readable reason
2. **Confidence Scoring**: Rate signal quality
3. **Metadata**: Include all relevant context
4. **Validation**: Check data quality before signaling
5. **Filtering**: Apply multiple confirmation layers

---
*Auto-generated on {timestamp}*
"""
    timestamp = datetime.now(timezone.utc).isoformat()
    return content.replace("{timestamp}", timestamp)


def generate_backtesting_docs() -> str:
    """Generate Backtesting.md."""
    content = """# Backtesting Engine

## Overview

The backtesting engine allows historical testing of strategies using past market data.

## Architecture

### Components

1. **BacktestBroker** (`broker/backtest_broker.py`)
   - Historical fill simulation
   - Slippage modeling
   - Commission tracking

2. **BacktestRunner** (`scripts/run_backtest.py`)
   - Data replay orchestration
   - Performance calculation
   - Report generation

3. **BacktestData** (`data/backtest_data.py`)
   - Historical data loading
   - Candle reconstruction
   - Tick simulation

## Running Backtests

### Basic Backtest

```bash
python scripts/run_backtest.py \\
  --strategy EMA_20_50 \\
  --symbol NIFTY \\
  --start 2024-01-01 \\
  --end 2024-03-31 \\
  --capital 100000
```

### Multi-Strategy Backtest

```bash
python scripts/run_backtest.py \\
  --strategies EMA_20_50,MEAN_REV \\
  --symbols NIFTY,BANKNIFTY \\
  --start 2024-01-01 \\
  --end 2024-12-31
```

## Performance Metrics

### Return Metrics
- **Total Return**: Absolute profit/loss
- **Return %**: Percentage return on capital
- **CAGR**: Annualized return
- **Sharpe Ratio**: Risk-adjusted return

### Risk Metrics
- **Max Drawdown**: Largest peak-to-trough decline
- **Win Rate**: Percentage of winning trades
- **Avg Win/Loss**: Average profit vs loss
- **Profit Factor**: Gross profit / gross loss

### Trade Metrics
- **Total Trades**: Number of round trips
- **Win Trades**: Number of profitable trades
- **Loss Trades**: Number of losing trades
- **Avg Trade Duration**: Average holding period

## Backtest Reports

### Console Output

```
=== Backtest Results ===
Strategy: EMA_20_50
Period: 2024-01-01 to 2024-03-31
Initial Capital: ₹100,000

Total Return: ₹12,500 (12.5%)
Max Drawdown: ₹3,200 (3.2%)
Sharpe Ratio: 1.85
Win Rate: 62.5%

Total Trades: 48
Winning: 30
Losing: 18
Avg Win: ₹850
Avg Loss: ₹420
```

### CSV Report

Detailed trade-by-trade report saved to `artifacts/backtests/`.

### Equity Curve

Visual representation of capital over time.

## Configuration

```yaml
backtest:
  slippage_pct: 0.05
  commission_per_trade: 20
  start_date: "2024-01-01"
  end_date: "2024-03-31"
  capital: 100000
```

## Data Requirements

- Historical OHLCV candles
- Sufficient lookback period for indicators
- Clean, validated data (no gaps)

## Limitations

- **Look-Ahead Bias**: Ensure no future data leakage
- **Overfitting**: Beware of curve-fitting parameters
- **Market Impact**: Assumes no slippage beyond model
- **Regime Changes**: Past ≠ future performance

## Best Practices

1. **Walk-Forward Testing**: Rolling window validation
2. **Out-of-Sample**: Test on unseen data
3. **Multiple Periods**: Test across market regimes
4. **Realistic Costs**: Include slippage and commissions
5. **Robustness**: Test parameter sensitivity

---
*Auto-generated on {timestamp}*
"""
    timestamp = datetime.now(timezone.utc).isoformat()
    return content.replace("{timestamp}", timestamp)


def extract_dashboard_endpoints() -> List[Dict[str, str]]:
    """Extract API endpoints from dashboard.py."""
    dashboard_file = UI_DIR / "dashboard.py"
    if not dashboard_file.exists():
        return []
    
    endpoints = []
    content = dashboard_file.read_text(encoding="utf-8", errors="ignore")
    
    # Find FastAPI route decorators
    route_pattern = r'@(?:app|router)\.(?:get|post|put|delete)\(["\']([^"\']+)["\']\)'
    matches = re.findall(route_pattern, content)
    
    for match in matches:
        endpoints.append({"path": match})
    
    return endpoints


def generate_dashboard_docs() -> str:
    """Generate Dashboard.md."""
    endpoints = extract_dashboard_endpoints()
    
    content = """# Web Dashboard

## Overview

The web dashboard provides real-time monitoring and control of the trading system via a FastAPI-based web interface.

## Architecture

### Components

1. **Dashboard API** (`ui/dashboard.py`)
   - FastAPI application
   - RESTful API endpoints
   - WebSocket support (future)

2. **Dashboard Services** (`ui/services.py`)
   - Business logic layer
   - State aggregation
   - Data formatting

3. **Frontend** (`ui/templates/` and `ui/static/`)
   - HTML templates (Jinja2)
   - JavaScript for interactivity
   - CSS styling

## API Endpoints

"""
    
    if endpoints:
        for endpoint in endpoints:
            content += f"### `{endpoint['path']}`\n\n"
            content += "Description: [Auto-extracted endpoint]\n\n"
    else:
        content += "*(Endpoints will be documented once extracted)*\n\n"
    
    content += """
## Key Features

### Real-Time Monitoring
- Live positions and P&L
- Recent trades
- Order status
- Strategy performance

### Control Panel
- Start/stop trading
- Emergency halt
- Strategy enable/disable
- Risk parameter adjustment

### Analytics
- Equity curve
- Trade history
- Performance metrics
- Win/loss analysis

### System Status
- Market hours
- Kite connection status
- Engine health
- Last heartbeat

## Running the Dashboard

```bash
# Start dashboard server
python scripts/run_dashboard.py

# Or use uvicorn directly
uvicorn ui.dashboard:app --reload --port 8000
```

## Accessing the Dashboard

```
http://localhost:8000
```

## API Usage

### Get Current State

```bash
curl http://localhost:8000/api/state
```

### Get Positions

```bash
curl http://localhost:8000/api/positions
```

### Get Trade History

```bash
curl http://localhost:8000/api/trades
```

## Configuration

```yaml
dashboard:
  host: "0.0.0.0"
  port: 8000
  reload: false
  log_level: "info"
```

## Security

⚠️ **Important**: The dashboard should not be exposed to the public internet without:
- Authentication
- HTTPS/TLS
- API rate limiting
- CORS configuration

## Development

### Local Development

```bash
# Run with auto-reload
uvicorn ui.dashboard:app --reload --port 8000
```

### Adding New Endpoints

1. Define route in `ui/dashboard.py`
2. Implement logic in `ui/services.py`
3. Update frontend templates
4. Test endpoint

---
*Auto-generated on {timestamp}*
"""
    timestamp = datetime.now(timezone.utc).isoformat()
    return content.replace("{timestamp}", timestamp)


def generate_commands_docs() -> str:
    """Generate Commands.md."""
    content = """# Common Commands

## Overview

This document lists common CLI commands for running and managing the trading system.

## Authentication

### Login to Kite

```bash
# Interactive login (opens browser)
python scripts/login_kite.py
```

## Trading Modes

### Paper Trading

```bash
# Run paper trading for equities
python scripts/run_paper_equity.py

# Run paper trading for F&O
python scripts/run_paper_fno.py

# Run paper trading for options
python scripts/run_paper_options.py
```

### Live Trading

⚠️ **WARNING: Real money at risk!**

```bash
# Run live trading
python scripts/run_live.py

# Or use specific engine
python -m engine.live_engine
```

### Backtesting

```bash
# Run backtest
python scripts/run_backtest.py --strategy EMA_20_50 --symbol NIFTY

# Run backtest v1
python scripts/run_backtest_v1.py
```

## Analysis & Reporting

### Performance Analysis

```bash
# Analyze paper trading results
python scripts/analyze_paper_results.py

# Analyze overall performance
python scripts/analyze_performance.py

# Show paper state
python scripts/show_paper_state.py
```

### Strategy Analysis

```bash
# Run indicator scanner
python scripts/run_indicator_scanner.py

# Analyze and learn
python scripts/analyze_and_learn.py
```

## Dashboard

### Start Dashboard

```bash
# Run dashboard
python scripts/run_dashboard.py

# Or use uvicorn directly
uvicorn ui.dashboard:app --host 0.0.0.0 --port 8000
```

## Data Management

### Refresh Market Cache

```bash
# Refresh cached market data
python scripts/refresh_market_cache.py
```

### Historical Replay

```bash
# Replay from historical data
python scripts/replay_from_historical.py
```

## Diagnostics

### WebSocket Diagnostics

```bash
# Test Kite WebSocket connection
python scripts/diag_kite_ws.py
```

### State Inspection

```bash
# Show current state
python scripts/show_paper_state.py
```

## Development

### Run Tests

```bash
# Run all tests
python -m pytest tests/

# Run specific test
python -m pytest tests/test_strategy_engine_v2.py

# Run with coverage
python -m pytest --cov=. tests/
```

### Generate Documentation

```bash
# Regenerate all documentation
python scripts/generate_docs.py
```

## Configuration

### Edit Configuration

```bash
# Edit main config
nano configs/config.yaml

# Edit environment variables
nano .env
```

### View Configuration

```bash
# View current config
cat configs/config.yaml
```

## Logs

### View Logs

```bash
# View engine logs
tail -f artifacts/logs/engine.log

# View JSON logs
tail -f artifacts/logs/events.jsonl

# View all logs
tail -f artifacts/logs/*.log
```

### Clear Logs

```bash
# Clear old logs (careful!)
rm artifacts/logs/*.log
```

## Artifacts

### View Artifacts

```bash
# List checkpoints
ls -lah artifacts/checkpoints/

# List market data cache
ls -lah artifacts/market_data/

# List backtest results
ls -lah artifacts/backtests/
```

## Common Workflows

### Morning Routine (Live Trading)

```bash
# 1. Login to Kite
python scripts/login_kite.py

# 2. Refresh market cache
python scripts/refresh_market_cache.py

# 3. Start dashboard
python scripts/run_dashboard.py &

# 4. Start live engine (after market open)
python scripts/run_live.py
```

### Evening Routine

```bash
# 1. Analyze day's performance
python scripts/analyze_performance.py

# 2. Review logs
tail -100 artifacts/logs/engine.log

# 3. Backup state
cp artifacts/checkpoints/runtime_state_latest.json backups/
```

### Strategy Development

```bash
# 1. Test in paper mode
python scripts/run_paper_equity.py

# 2. Analyze results
python scripts/analyze_paper_results.py

# 3. Backtest on historical data
python scripts/run_backtest.py --strategy NEW_STRATEGY

# 4. Review metrics
# 5. Refine and repeat
```

---
*Auto-generated on {timestamp}*
"""
    timestamp = datetime.now(timezone.utc).isoformat()
    return content.replace("{timestamp}", timestamp)


def generate_changelog() -> str:
    """Generate Changelog.md."""
    content = """# Architecture Changelog

## Overview

This document tracks significant architectural changes to the trading system.

## Format

```
YYYY-MM-DD - Component - Change Description
```

---

## {{date}} - Initial Documentation

- Created comprehensive documentation system
- Implemented `scripts/generate_docs.py`
- Added GitHub Actions workflow for auto-updates
- Documented all major system components

---

## Future Changes

Architectural changes will be automatically detected and logged here by the documentation system.

### Detection Rules

- Engine file modifications
- Strategy additions/removals
- Indicator changes
- API endpoint updates
- Configuration schema changes

---
*Auto-generated on {timestamp}*
"""
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    timestamp = datetime.now(timezone.utc).isoformat()
    return content.replace("{date}", date).replace("{timestamp}", timestamp)


def main():
    """Main documentation generation function."""
    logger.info("Starting documentation generation...")
    
    # Ensure docs directory exists
    DOCS_DIR.mkdir(exist_ok=True)
    
    # Generate all documentation files
    docs = {
        "Overview.md": generate_overview(),
        "RepoMap.md": generate_repo_map(),
        "Paper.md": generate_paper_docs(),
        "Live.md": generate_live_docs(),
        "ExecutionEngine.md": generate_execution_engine_docs(),
        "StrategyEngine.md": generate_strategy_engine_docs(),
        "MarketDataEngine.md": generate_market_data_engine_docs(),
        "RiskEngine.md": generate_risk_engine_docs(),
        "Indicators.md": generate_indicators_docs(),
        "Strategies.md": generate_strategies_docs(),
        "Signals.md": generate_signals_docs(),
        "Backtesting.md": generate_backtesting_docs(),
        "Dashboard.md": generate_dashboard_docs(),
        "Commands.md": generate_commands_docs(),
        "Changelog.md": generate_changelog(),
    }
    
    # Write all documentation files
    for filename, content in docs.items():
        file_path = DOCS_DIR / filename
        file_path.write_text(content, encoding="utf-8")
        logger.info(f"Generated {filename}")
    
    logger.info(f"Documentation generation complete! {len(docs)} files created in {DOCS_DIR}")
    
    # Print summary
    print("\n" + "="*60)
    print("DOCUMENTATION GENERATION SUMMARY")
    print("="*60)
    for filename in sorted(docs.keys()):
        file_path = DOCS_DIR / filename
        size = file_path.stat().st_size
        print(f"  ✓ {filename:<30} ({size:,} bytes)")
    print("="*60)
    print(f"\nTotal: {len(docs)} files generated")
    print(f"Location: {DOCS_DIR}")
    print("\n")


if __name__ == "__main__":
    main()
