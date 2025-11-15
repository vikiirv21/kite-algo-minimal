# HFT Trading System - Overview

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
*Auto-generated on 2025-11-15T21:49:59.697129+00:00*
