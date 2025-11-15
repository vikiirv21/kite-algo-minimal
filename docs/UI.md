# Dashboard UI Documentation

## Overview

The Arthayukti HFT Dashboard is a modern, real-time trading dashboard built with FastAPI (backend) and vanilla JavaScript (frontend). It provides comprehensive monitoring of trading engines, positions, orders, signals, and backtests.

## Architecture

### Frontend Stack
- **HTML**: Single-page app with tab-based navigation
- **CSS**: Custom dark theme with HFT aesthetic
- **JavaScript**: Vanilla JS with fetch API for data updates
- **No frameworks**: Lightweight, fast, minimal dependencies

### Backend Stack
- **FastAPI**: RESTful API endpoints
- **Python 3.10+**: Backend logic
- **File-based state**: JSON checkpoints for persistence

## Dashboard Structure

### Main Tabs

1. **Overview** - Real-time trading status and performance
2. **Signals & Strategies** - Signal generation and strategy analytics
3. **Orders & Positions** - Trade execution and position tracking
4. **Backtests** - Historical strategy performance analysis
5. **Logs** - Filtered engine logs (Engine/Trades/Signals/System)
6. **Config & Safety** - Configuration viewer

### Overview Tab Components

#### Top Bar
- **Brand**: Arthayukti logo and name
- **Market Status**: Real-time market open/closed indicator with IST clock
- **Engine Pills**: Paper/Live/Scanner status indicators

#### Main Grid (3 columns)

**Column 1: Engines**
- Shows F&O Paper Engine status
- Last checkpoint timestamp and age
- Market status indicator

**Column 2: Portfolio & P&L**
- Equity (total capital value)
- Realized P&L
- Unrealized P&L
- Daily P&L
- Exposure percentage
- Free notional capital
- Position count

**Column 3: Run Config & Risk**
- Active configuration file
- FnO universe
- Paper capital
- Risk per trade percentage
- Max daily loss limit
- Max exposure multiplier
- Risk profile (Conservative/Default/Aggressive)
- Meta-engine status

**Column 1 (Row 2): Equity Curve**
- Today's equity progression chart
- Shows: Equity, Capital, Realized P&L lines
- Real-time updates

**Column 2 (Row 2): Recent Signals**
- Latest 50 signals
- Time, Symbol, Timeframe, Signal type, Price, Strategy
- Color-coded signal badges (BUY=green, SELL=red, HOLD=gray)

**Column 3 (Row 2): Today at a Glance**
- Realized P&L (large display)
- Number of trades
- Win rate percentage
- Win/Loss counts
- Largest win/loss
- Average R-multiple

#### Positions & Orders (Full width)
Split panel showing:
- **Left**: Open positions with unrealized P&L
- **Right**: Recent orders with status

#### System Health (Full width)
- Market status pill
- Last log timestamp
- Last error timestamp
- Error/Warning counts
- Recent logs preview

#### Strategy Snapshot (Full width)
Table showing all active strategies:
- Logical name, Symbol, Timeframe
- Last signal type
- Last price
- Buy/Sell/Exit/Hold counts

## API Endpoints Reference

### Core Dashboard APIs

#### `/api/meta`
**Purpose**: Market clock and status  
**Returns**:
```json
{
  "now_ist": "2025-11-15T20:10:09.617+05:30",
  "market_open": true,
  "market_status": "OPEN",
  "status_payload": {...}
}
```
**Refresh Rate**: 5 seconds

#### `/api/engines/status`
**Purpose**: Engine health check  
**Returns**:
```json
{
  "engines": [{
    "engine": "fno_paper",
    "running": true,
    "last_checkpoint_ts": "2025-11-15T19:45:00+05:30",
    "checkpoint_age_seconds": 120.5,
    "market_open": true,
    "mode": "paper"
  }]
}
```
**Refresh Rate**: 5 seconds

#### `/api/portfolio/summary`
**Purpose**: Portfolio P&L and metrics  
**Returns**:
```json
{
  "paper_capital": 500000.0,
  "total_realized_pnl": 1250.50,
  "total_unrealized_pnl": -320.25,
  "equity": 500930.25,
  "total_notional": 125000.0,
  "free_notional": 375930.25,
  "exposure_pct": 0.25,
  "daily_pnl": 930.25,
  "has_positions": true,
  "position_count": 3
}
```
**Refresh Rate**: 7 seconds

#### `/api/summary/today`
**Purpose**: Today's trading performance  
**Returns**:
```json
{
  "date": "2025-11-15",
  "realized_pnl": 1250.50,
  "num_trades": 12,
  "win_trades": 8,
  "loss_trades": 4,
  "win_rate": 66.7,
  "largest_win": 450.0,
  "largest_loss": -280.0,
  "avg_r": 1.25
}
```
**Refresh Rate**: 30 seconds

#### `/api/signals/recent?limit=50`
**Purpose**: Recent trading signals  
**Returns**: Array of signal objects
```json
[{
  "ts": "2025-11-15T14:30:00+05:30",
  "symbol": "NIFTY24DECFUT",
  "logical": "NIFTY_EMA_5m",
  "signal": "BUY",
  "tf": "5m",
  "price": 19500.50,
  "profile": "momentum",
  "strategy": "ema_crossover"
}]
```
**Refresh Rate**: 8 seconds

#### `/api/orders/recent?limit=50`
**Purpose**: Recent order activity  
**Returns**:
```json
{
  "orders": [{
    "ts": "2025-11-15T14:30:05+05:30",
    "symbol": "NIFTY24DECFUT",
    "side": "BUY",
    "quantity": 50,
    "price": 19500.75,
    "status": "FILLED"
  }]
}
```
**Refresh Rate**: 9 seconds

#### `/api/positions/open`
**Purpose**: Current open positions  
**Returns**: Array of position objects
```json
[{
  "symbol": "NIFTY24DECFUT",
  "side": "LONG",
  "quantity": 50,
  "avg_price": 19500.50,
  "last_price": 19520.25,
  "unrealized_pnl": 987.50
}]
```
**Refresh Rate**: 9 seconds

#### `/api/stats/equity?days=1`
**Purpose**: Equity curve data points  
**Returns**: Array of snapshots
```json
[{
  "ts": "2025-11-15T09:15:00+05:30",
  "equity": 500000.0,
  "paper_capital": 500000.0,
  "realized": 0.0,
  "unrealized": 0.0
}]
```
**Refresh Rate**: 20 seconds

#### `/api/stats/strategies?days=1`
**Purpose**: Strategy performance aggregates  
**Returns**: Array of strategy stats
```json
[{
  "key": "NIFTY_EMA_5m",
  "logical": "NIFTY_EMA_5m",
  "symbol": "NIFTY",
  "strategy": "ema_crossover",
  "last_ts": "2025-11-15T14:30:00+05:30",
  "last_signal": "BUY",
  "last_price": 19500.50,
  "timeframe": "5m",
  "buy_count": 5,
  "sell_count": 4,
  "exit_count": 8,
  "hold_count": 120
}]
```
**Refresh Rate**: 15 seconds

#### `/api/logs/recent?limit=120&kind=engine`
**Purpose**: Filtered log stream  
**Query Params**:
- `limit`: Number of entries (default: 150)
- `level`: Filter by log level (INFO/WARN/ERROR)
- `contains`: Substring filter
- `kind`: Log category (engine/trades/signals/system)

**Returns**:
```json
{
  "logs": [{
    "ts": "2025-11-15T14:30:00+05:30",
    "level": "INFO",
    "logger": "engine.fno_paper",
    "message": "Signal processed: BUY NIFTY"
  }],
  "entries": [...]
}
```
**Refresh Rate**: 15 seconds

#### `/api/health`
**Purpose**: Aggregate system health  
**Returns**:
```json
{
  "engine_status": {...},
  "log_health": {
    "last_log_ts": "...",
    "last_error_ts": "...",
    "error_count_recent": 0,
    "warning_count_recent": 2
  },
  "market_status": {...}
}
```
**Refresh Rate**: 15 seconds

#### `/api/config/summary`
**Purpose**: Active configuration summary  
**Returns**:
```json
{
  "config_path": "configs/dev.yaml",
  "mode": "paper",
  "fno_universe": ["NIFTY", "BANKNIFTY"],
  "paper_capital": 500000.0,
  "risk_per_trade_pct": 0.005,
  "max_daily_loss": 3000.0,
  "max_exposure_pct": 2.0,
  "risk_profile": "Default",
  "meta_enabled": true
}
```
**Refresh Rate**: 30 seconds

### Backtest APIs

#### `/api/backtests`
**Purpose**: List all backtest runs  
**Returns**:
```json
{
  "runs": [{
    "run_id": "2025-11-14_1545",
    "strategy": "ema_crossover",
    "symbol": "NIFTY",
    "timeframe": "5m",
    "date_from": "2025-11-01",
    "date_to": "2025-11-14",
    "net_pnl": 12500.50,
    "win_rate": 65.5,
    "total_trades": 42
  }]
}
```

#### `/api/backtests/{run_id}/summary`
**Purpose**: Detailed backtest results  
**Returns**: Complete backtest summary with config and metrics

#### `/api/backtests/{run_id}/equity_curve`
**Purpose**: Equity curve for specific run  
**Returns**:
```json
{
  "run_id": "strategy/2025-11-14_1545",
  "equity_curve": [{
    "ts": "2025-11-14T10:30:00",
    "equity": 500050.0,
    "pnl": 50.0
  }]
}
```

## Error Handling

### Retry Logic
All API calls use `fetchWithRetry()` with:
- 3 retry attempts
- Exponential backoff (1s, 2s, 4s)
- Graceful degradation on failure

### Empty States
Every UI component shows helpful messages when:
- No data available yet
- API call fails
- Network is unavailable

### Console Logging
- Warnings logged for HTTP errors (non-2xx)
- Errors logged for network failures
- Success/failure status visible in browser console

## Adding New UI Sections

### Step 1: Add HTML
Add new card to appropriate tab in `ui/templates/dashboard.html`:
```html
<section class="card">
  <div class="card-header">
    <h2>My New Panel</h2>
    <span class="badge badge-muted" id="my-count">0</span>
  </div>
  <div class="card-body">
    <div id="my-content">Loading...</div>
  </div>
</section>
```

### Step 2: Add API Endpoint
Add route in `ui/dashboard.py`:
```python
@router.get("/api/my_data")
async def api_my_data() -> JSONResponse:
    try:
        data = load_my_data()
        return JSONResponse(data)
    except Exception as exc:
        logger.exception("Failed to load my data: %s", exc)
        return JSONResponse({"items": [], "error": str(exc)})
```

### Step 3: Add JavaScript
Add fetch function in `ui/static/dashboard.js`:
```javascript
async function fetchMyData() {
  try {
    const res = await fetchWithRetry("/api/my_data");
    if (!res.ok) {
      console.warn(`Failed to fetch my data: HTTP ${res.status}`);
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    renderMyData(data);
  } catch (err) {
    console.error("Failed to fetch my data:", err);
    const el = document.getElementById("my-content");
    if (el) el.textContent = "Error loading data";
  }
}

function renderMyData(data) {
  const el = document.getElementById("my-content");
  if (!el) return;
  
  if (!data.items || data.items.length === 0) {
    el.textContent = "No data available";
    return;
  }
  
  // Render your data
  el.innerHTML = data.items.map(item => `
    <div>${item.name}: ${item.value}</div>
  `).join('');
}
```

### Step 4: Add Refresh Call
In `DOMContentLoaded` listener:
```javascript
fetchMyData();
setInterval(fetchMyData, 10000); // Refresh every 10s
```

### Step 5: Add CSS (if needed)
Add styles in `ui/static/dashboard.css`:
```css
#my-content {
  font-size: 0.9rem;
  line-height: 1.6;
}
```

## Known Limitations

1. **Logs Auto-scroll**: May conflict with manual scrolling. Use logs tab for full control.

2. **Refresh Rates**: Fixed intervals, not adaptive. Heavy polling with many tabs open.

3. **No WebSocket**: Uses HTTP polling. More efficient to use WebSocket for real-time updates.

4. **Browser Support**: Designed for modern browsers (Chrome, Firefox, Safari, Edge). IE not supported.

5. **Mobile Support**: Basic responsive design, but optimized for desktop use (1280px+).

6. **Timezone**: All times shown in IST. No timezone selection.

7. **Historical Data**: Overview shows "today" only. Use backtests for historical analysis.

## Troubleshooting

### Dashboard shows "Error loading data"
- Check if backend is running: `python -m ui.dashboard`
- Check browser console for API errors
- Verify network connectivity
- Check if paper engine checkpoint exists

### Market status not updating
- Verify system clock is correct
- Check `/api/meta` endpoint manually
- Clear browser cache and reload

### Signals/Orders not appearing
- Verify paper engine is running
- Check if `artifacts/signals.csv` exists
- Check if `artifacts/orders.csv` exists
- Verify file permissions

### Equity curve not rendering
- Check if `artifacts/snapshots.csv` exists
- Verify data format in snapshots
- Check browser console for SVG errors

### Backtests tab empty
- Verify `artifacts/backtests/` directory exists
- Check if any backtest runs completed
- Verify JSON result files are valid

### High CPU usage
- Reduce refresh intervals in dashboard.js
- Close unused tabs
- Check for console errors causing retry loops

## Performance Tips

1. **Reduce Refresh Rates**: Edit interval timers in dashboard.js
2. **Limit Data Points**: Use `limit` query param on APIs
3. **Filter Logs**: Use `kind` param to reduce log volume
4. **Close Unused Tabs**: Each tab polls independently
5. **Use Modern Browser**: Latest Chrome/Firefox for best performance

## Security Considerations

1. **No Authentication**: Dashboard has no auth. Use firewall/VPN for production.
2. **CORS Enabled**: Allow all origins. Restrict in production.
3. **Sensitive Data**: Config may contain sensitive settings. Don't expose publicly.
4. **API Keys**: Never log or display full API keys in UI.

## Future Enhancements

1. **WebSocket**: Replace polling with WebSocket for efficiency
2. **Authentication**: Add login system
3. **Themes**: Light/dark theme toggle
4. **Timezone Support**: User-selectable timezone
5. **Mobile App**: Native mobile experience
6. **Alerts**: Browser notifications for important events
7. **Export**: Download data as CSV/JSON
8. **Comparison**: Compare multiple backtest runs side-by-side
