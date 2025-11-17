# Arthayukti Dashboard - User Guide

## Overview

The **Arthayukti Dashboard** is a modern, dark-themed web interface for monitoring and controlling your HFT (High-Frequency Trading) system. It provides real-time visibility into engines, portfolio, signals, logs, and system health.

## Quick Start

### Running the Dashboard

```bash
# Navigate to project root
cd /path/to/kite-algo-minimal

# Start the dashboard server
uvicorn ui.dashboard:app --reload --port 8765

# Open in browser
# http://localhost:8765
```

### What You'll See

The dashboard automatically loads and displays:
- **Top Bar**: App branding, mode indicator, market status, and server time
- **Mode & Engines**: Current trading mode and engine status
- **Portfolio**: Real-time P&L, equity, positions
- **Logs**: Streaming engine logs with filtering
- **Signals**: Recent trading signals and active strategies
- **System Health**: Configuration and health metrics

## Dashboard Panels

### 1. Mode & Engines Panel

**What it shows:**
- Current trading mode (PAPER / LIVE / IDLE)
- Engine status (Running / Stopped)
- Last checkpoint timestamp
- Time since last update

**Mode Detection:**
The mode is automatically determined from engine status:
- **LIVE**: One or more live engines are running
- **PAPER**: Only paper engines are running  
- **IDLE**: No engines are running

**Live Mode Warning:**
When in LIVE mode, a red warning banner appears to remind you that real orders may be sent to the broker.

### 2. Portfolio & Positions Panel

**Metrics displayed:**
- **Equity**: Total account value
- **Realized P&L**: Closed position profits/losses
- **Unrealized P&L**: Open position profits/losses
- **Daily P&L**: Total P&L for today
- **Total Notional**: Sum of position values
- **Exposure**: Percentage of capital deployed

**Positions Table:**
- Symbol, Side (LONG/SHORT), Quantity
- Average price, Last traded price
- Unrealized P&L (color-coded)

### 3. Logs / Events Panel

**Features:**
- Real-time log streaming
- Filter by category: All / Engine / Trades / Signals / System
- Color-coded log levels (INFO=blue, WARN=orange, ERROR=red)
- Monospace font for readability
- Auto-scrolls to latest entries
- Manual refresh button

**Log Categories:**
- **Engine**: Core engine operations and heartbeats
- **Trades**: Order placement, fills, executions
- **Signals**: Strategy signals and indicators
- **System**: Everything else

### 4. Signals & Strategies Panel

**Top Section - Active Strategies:**
Shows currently active strategies with:
- Strategy name / logical ID
- Symbol being traded
- Last signal (BUY/SELL/EXIT/HOLD)
- Timeframe
- Signal counts (Buy/Sell/Exit/Hold)

**Bottom Section - Recent Signals:**
Recent signals with:
- Timestamp
- Symbol
- Signal direction (color-coded badge)
- Timeframe
- Price at signal
- Strategy name

### 5. System Health & Meta Panel

**Configuration Section:**
- Trading mode
- Universe (NIFTY, BANKNIFTY, etc.)
- Paper capital
- Risk profile

**Today's Summary:**
- Realized P&L
- Number of trades
- Win rate percentage
- Average R-multiple

**Health Metrics:**
- Market status
- Recent errors count
- Recent warnings count
- Last log timestamp

## Top Bar Elements

### Server Time
- Updates every second
- Shows IST (Indian Standard Time)
- Formatted as HH:MM:SS

### Mode Badge
- **PAPER** (Blue): Paper trading mode
- **LIVE** (Green): Live trading mode
- **IDLE** (Gray): No engines running

### Market Status Pill
- **MARKET OPEN** (Green): Trading session active
- **MARKET CLOSED** (Gray): Outside trading hours

## Data Refresh Rates

Different data updates at different intervals:

| Data Type | Refresh Interval |
|-----------|------------------|
| Server Time | 1 second |
| Market Status | 5 seconds |
| Logs | 5 seconds |
| Engines Status | 10 seconds |
| Portfolio | 10 seconds |
| Signals | 10 seconds |
| Health & Config | 30 seconds |

## API Endpoints Used

The dashboard connects to these backend APIs:

- `/api/system/time` - Server timestamp
- `/api/meta` - Market status and regime
- `/api/engines/status` - Engine health
- `/api/portfolio/summary` - Portfolio metrics
- `/api/positions/open` - Open positions
- `/api/logs` - Engine logs (with optional filters)
- `/api/signals/recent` - Recent signals
- `/api/stats/strategies` - Strategy statistics
- `/api/health` - System health check
- `/api/config/summary` - Configuration summary
- `/api/summary/today` - Today's trade summary

## Responsive Design

The dashboard is responsive and works on various screen sizes:

- **Desktop (1400px+)**: 3-column grid layout
- **Tablet (768px-1399px)**: 2-column layout
- **Mobile (<768px)**: Single column stack

## Dark Theme

The dashboard uses a carefully crafted dark color palette:

**Background Colors:**
- Primary: `#0a0e1a` (Very dark blue-gray)
- Secondary: `#111827` (Dark gray)
- Tertiary: `#1f2937` (Lighter gray)

**Text Colors:**
- Primary: `#f3f4f6` (Light gray)
- Secondary: `#9ca3af` (Medium gray)
- Muted: `#6b7280` (Dark gray)

**Accent Colors:**
- Primary: `#3b82f6` (Blue)
- Success: `#10b981` (Green)
- Warning: `#f59e0b` (Orange)
- Danger: `#ef4444` (Red)

## Browser Compatibility

**Supported Browsers:**
- Chrome 90+
- Edge 90+
- Firefox 88+
- Safari 14+

**Requirements:**
- JavaScript enabled
- Modern browser with ES6 support
- Cookies enabled (for any future features)

## Troubleshooting

### Dashboard Not Loading

1. Check server is running:
   ```bash
   ps aux | grep uvicorn
   ```

2. Check port is not in use:
   ```bash
   lsof -i :8765
   ```

3. Check for errors:
   ```bash
   tail -f artifacts/logs/app.log
   ```

### APIs Not Responding

1. Test individual endpoints:
   ```bash
   curl http://localhost:8765/api/meta
   ```

2. Check backend logs for errors

3. Verify config file is loaded correctly

### Data Not Updating

1. Check browser console for errors (F12)
2. Verify network tab shows successful API calls
3. Check polling is active (should see requests every few seconds)

## Security Considerations

**What the Dashboard Does:**
- ✅ Reads data from backend APIs
- ✅ Displays real-time information
- ✅ Shows current mode and status

**What the Dashboard Does NOT Do:**
- ❌ Place orders
- ❌ Modify positions
- ❌ Change configuration
- ❌ Start/stop engines

**Live Mode Warning:**
When live engines are detected, a prominent warning banner is displayed to remind users that real trading is active.

## Extending the Dashboard

### Adding a New Panel

1. **Update HTML** (`ui/templates/index.html`):
   ```html
   <section class="panel panel-custom">
       <div class="panel-header">
           <h2>My Custom Panel</h2>
       </div>
       <div class="panel-body" id="custom-panel-body">
           <div class="loading">Loading...</div>
       </div>
   </section>
   ```

2. **Add Styles** (`ui/static/css/arthayukti.css`):
   ```css
   .panel-custom {
       grid-column: span 1;
   }
   ```

3. **Add Update Function** (`ui/static/js/arthayukti.js`):
   ```javascript
   async function updateCustomPanel() {
       const data = await apiGet('/api/my-endpoint');
       const panelBody = document.getElementById('custom-panel-body');
       if (!data || !panelBody) return;
       
       // Render your data
       panelBody.innerHTML = `<div>${data.value}</div>`;
   }
   ```

4. **Add to Polling** (`ui/static/js/arthayukti.js`):
   ```javascript
   function startPolling() {
       // ... existing code ...
       intervals.custom = setInterval(updateCustomPanel, 15000);
   }
   ```

## Performance Tips

**For Large Log Files:**
- Use log filtering to reduce data
- Adjust `LOG_LIMIT` in JavaScript config
- Consider log rotation on backend

**For Many Positions:**
- Positions table shows top 10 by default
- Consider pagination for large portfolios

**For Slow Networks:**
- Increase polling intervals in JavaScript config
- Use browser dev tools to monitor network usage

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review backend logs in `artifacts/logs/`
3. Check browser console for JavaScript errors
4. Verify all API endpoints are responding

## Version History

**v1.0 (Current)**
- Initial release
- Dark theme implementation
- All core panels functional
- Automatic mode detection
- Real-time data polling
- Responsive design

---

**Happy Trading! 📈**
