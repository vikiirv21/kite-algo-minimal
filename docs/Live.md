# Live Trading Mode

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

## Running Live Mode

### Prerequisites

1. **Kite Login**: Ensure you have a valid Kite session
   ```bash
   python -m scripts.login_kite
   ```

2. **Config**: Set mode to "live" in your config file or use CLI flag

### Start Live Engine

```bash
# Via config file
python -m scripts.run_day --engines fno

# Via CLI override
python -m scripts.run_day --mode live --engines fno
```

### With Login

```bash
python -m scripts.run_day --login --mode live --engines fno
```

## Configuration

Required config fields for Live mode:

```yaml
trading:
  mode: "live"
  logical_universe:
    - "NIFTY"
    - "BANKNIFTY"
  
broker:
  # Optional broker-specific settings
  # Credentials come from environment/secrets files
  
risk:
  max_daily_loss_pct: 0.02
  per_trade_risk_pct: 0.0025
  max_daily_trades: 40
```

## Artifacts & State

### Checkpoint Paths

- **Live**: `artifacts/checkpoints/live_state_latest.json`
- **Paper**: `artifacts/checkpoints/paper_state_latest.json`

### Journal Paths

- **Live**: `artifacts/live/<YYYY-MM-DD>/`
  - `orders.csv`
  - `fills.csv`
  - `trades.csv`

- **Paper**: `artifacts/journal/<YYYY-MM-DD>/`
  - `orders.csv`
  - `fills.csv`
  - `trades.csv`

## Safety Features

### Pre-Order Checks

1. **Login Validation**: Every order verifies active Kite session
2. **Market Hours**: Orders rejected if market is closed
3. **Risk Engine**: Evaluates every order intent
   - BLOCK: Order completely rejected
   - REDUCE: Order quantity reduced
   - HALT_SESSION: Engine stops completely

### Error Handling

- All broker API calls wrapped in try-except
- Exceptions logged but don't crash engine
- Failed orders journaled with error status

### Logging

- Clear visual indicators: 🔴 for live orders
- Warnings when live mode starts
- Order details logged before placement
- Status updates for fills/rejections

## Monitoring

### Live State

Check current state via checkpoint:
```bash
cat artifacts/checkpoints/live_state_latest.json
```

### Logs

View structured logs:
```bash
tail -f artifacts/logs/events.jsonl
```

### Positions

Fetch from Kite:
```python
from broker.kite_bridge import KiteBroker
broker = KiteBroker({})
broker.ensure_logged_in()
positions = broker.fetch_positions()
```

## Stopping Live Engine

- **Graceful**: Press Ctrl+C
- **Emergency**: Kill process (orders remain active with broker)

The engine saves a final checkpoint on shutdown.

## Risk Management

Live mode enforces all configured risk limits:

- Max daily loss
- Per-symbol loss limits  
- Max concurrent positions
- Trade throttling
- Time-based entry filters
- Consecutive loss limits

See `core/risk_engine.py` for full risk logic.

## Differences from Paper Mode

| Aspect | Paper | Live |
|--------|-------|------|
| Order Execution | Instant simulation | Real Kite API |
| Fill Handling | Immediate | WebSocket updates |
| Slippage | None | Real market conditions |
| Latency | Zero | Network + broker latency |
| Order Tracking | In-memory | Kite order ID tracking |
| Cost | Free | Real brokerage fees |

## Troubleshooting

### "Not logged in" error
- Run `python -m scripts.login_kite` to refresh token
- Check `secrets/kite_tokens.env` exists

### "Cannot subscribe to ticks"
- Verify instrument tokens are valid
- Check WebSocket connectivity
- Ensure API key/token are correct

### Orders not being placed
- Check risk engine logs for BLOCK decisions
- Verify market hours
- Check position limits

### Lost connection
- WebSocket auto-reconnects
- Check logs for reconnection attempts
- Restart engine if needed

## Best Practices

1. **Test in Paper First**: Always test strategies in paper mode
2. **Small Position Sizes**: Start with minimal quantities
3. **Monitor Closely**: Watch logs and positions actively
4. **Risk Limits**: Set conservative risk limits initially
5. **Market Hours**: Trade during liquid hours (avoid first/last 15min)
6. **Review Orders**: Check pending orders regularly
7. **Stop Losses**: Always use stop losses
8. **Daily Reset**: Restart engine fresh each trading day

## Emergency Procedures

### Stop All Trading

1. Stop the engine: Ctrl+C or kill process
2. Cancel pending orders via broker interface
3. Close positions manually if needed

### Max Loss Reached

Engine automatically stops when:
- Daily loss limit reached
- Per-symbol loss limit reached
- Risk engine triggers HALT_SESSION

## Support

For issues or questions:
- Check logs in `artifacts/logs/`
- Review error events in `artifacts/logs/events.jsonl`
- Verify config settings
- Ensure Kite session is valid
