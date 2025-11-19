# Developer Setup & Runbook

## Prerequisites

### System Requirements
- **Python**: 3.10+ (recommended: 3.12)
- **Operating System**: Linux, macOS, or Windows with WSL
- **Memory**: 4GB RAM minimum, 8GB recommended
- **Storage**: 2GB free space for logs and artifacts

### External Dependencies
- **Zerodha Kite Account**: Required for live/paper trading with real data
- **API Keys**: Kite API key and API secret (from Kite Connect portal)

## Initial Setup

### 1. Clone Repository

```bash
git clone https://github.com/vikiirv21/kite-algo-minimal.git
cd kite-algo-minimal
```

### 2. Create Virtual Environment

```bash
# Using venv
python -m venv .venv

# Activate on Linux/macOS
source .venv/bin/activate

# Activate on Windows
.venv\Scripts\activate
```

### 3. Install Dependencies

```bash
# Install from requirements.txt
pip install -r requirements.txt
```

Key dependencies:
- `kiteconnect` - Zerodha Kite API client
- `fastapi` - Web framework for dashboard
- `uvicorn` - ASGI server
- `pandas` - Data manipulation
- `numpy` - Numerical computing
- `pyyaml` - Configuration management
- `python-dotenv` - Environment variable management

### 4. Configure Secrets

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` and add your Kite API credentials:

```env
KITE_API_KEY=your_api_key_here
KITE_API_SECRET=your_api_secret_here
```

Alternatively, create `secrets/kite.json`:

```json
{
  "api_key": "your_api_key",
  "api_secret": "your_api_secret"
}
```

### 5. Create Configuration

Copy the example config:

```bash
cp configs/dev.yaml.example configs/dev.yaml
# OR edit existing configs/dev.yaml
```

Edit `configs/dev.yaml` to customize:

```yaml
trading:
  mode: paper  # Start with paper mode
  paper_capital: 100000
  fno_universe: [NIFTY, BANKNIFTY]

risk:
  risk_per_trade_pct: 0.005
  max_daily_loss: 3000
  max_exposure_pct: 2.0

strategies:
  enabled: true
```

### 6. Initialize Directories

```bash
# Create required directories
mkdir -p artifacts/logs
mkdir -p artifacts/checkpoints
mkdir -p artifacts/market_data
mkdir -p artifacts/analytics
mkdir -p secrets
```

## Authentication

### First-Time Kite Login

```bash
python scripts/login_kite.py
```

This will:
1. Open browser for Kite login
2. Redirect to callback URL with request token
3. Exchange token for access token
4. Store access token in `secrets/`

**Note**: Access tokens expire daily and must be refreshed each trading day.

## Running the System

### Local Development - Paper Mode

#### Option 1: Dashboard + Paper Engine

Terminal 1 - Start Dashboard:
```bash
python scripts/run_dashboard.py
# OR
uvicorn apps.dashboard:app --reload --host 127.0.0.1 --port 8765
```

Terminal 2 - Start Paper Engine:
```bash
python scripts/run_paper_equity.py
# OR for F&O
python scripts/run_paper_fno.py
```

Access dashboard at: `http://127.0.0.1:8765`

#### Option 2: Day Trading Script

```bash
python scripts/run_day.py --login --engines all
```

This orchestrates:
- Kite login (if `--login` flag provided)
- Engine startup
- Trading session
- Graceful shutdown

### Local Development - Live Mode

⚠️ **WARNING**: Live mode places REAL orders with REAL money!

```bash
# Ensure you've logged in today
python scripts/login_kite.py

# Start dashboard (optional but recommended)
python scripts/run_dashboard.py &

# Run live engine (only during market hours!)
# NOT YET IMPLEMENTED - use with caution when available
```

### Backtesting

```bash
python scripts/run_backtest_v3.py
# OR
python scripts/run_backtest.py
```

## Environment Files

### Configuration Locations

The system looks for configuration in this order:
1. `HFT_CONFIG` environment variable path
2. `KITE_DASHBOARD_CONFIG` environment variable path
3. `configs/dev.yaml` (default)

### Secrets Location

Secrets are stored in:
- `secrets/kite.json` - Kite API credentials
- `secrets/access_token.txt` - Daily access token (auto-generated)

⚠️ **Security**: Never commit the `secrets/` directory to version control!

## Operational Runbook

### Daily Startup (Live Trading)

**Pre-Market (before 9:15 AM IST)**

1. **Login to Kite**
   ```bash
   python scripts/login_kite.py
   ```

2. **Verify Configuration**
   ```bash
   cat configs/dev.yaml
   # Ensure mode, universe, and risk parameters are correct
   ```

3. **Start Dashboard**
   ```bash
   python scripts/run_dashboard.py &
   ```

4. **Warm Up Data Cache** (optional)
   ```bash
   python scripts/refresh_market_cache.py
   ```

**Market Hours (9:15 AM - 3:30 PM IST)**

5. **Start Trading Engine**
   ```bash
   python scripts/run_day.py --engines all
   ```

6. **Monitor Dashboard**
   - Open `http://127.0.0.1:8765`
   - Watch positions, P&L, and signals
   - Monitor logs for errors

**Post-Market (after 3:30 PM IST)**

7. **Graceful Shutdown**
   - Engines should auto-stop after market close
   - If not, Ctrl+C to stop
   - Dashboard can continue running for analysis

8. **Analyze Performance**
   ```bash
   python scripts/analyze_performance.py
   python scripts/analyze_paper_results.py
   ```

9. **Review Logs**
   ```bash
   tail -100 artifacts/logs/engine.log
   tail -50 artifacts/logs/trades.log
   ```

10. **Backup State** (optional)
    ```bash
    cp -r artifacts/checkpoints/ backups/$(date +%Y%m%d)/
    ```

### Restart Procedures

#### Restart Dashboard Only
```bash
# Stop (Ctrl+C or kill process)
# Restart
python scripts/run_dashboard.py
```

#### Restart Engine Only
```bash
# Stop (Ctrl+C)
# Restart
python scripts/run_paper_equity.py
```

#### Full System Restart
```bash
# Stop all processes
pkill -f "python scripts/run"
pkill -f "uvicorn apps.dashboard"

# Restart
python scripts/run_dashboard.py &
python scripts/run_paper_equity.py
```

### Emergency Halt

If something goes wrong during live trading:

1. **Via Dashboard**: Click "Emergency Halt" button
2. **Via API**:
   ```bash
   curl -X POST http://127.0.0.1:8765/api/control/halt
   ```
3. **Kill Processes**:
   ```bash
   pkill -f "python scripts/run"
   ```
4. **Manual Kite Portal**: Log in to Kite web and manually close positions if needed

## Logs & Artifacts

### Log Files

Logs are written to `artifacts/logs/`:

```
artifacts/logs/
├── engine.log           # Main engine logs
├── events.jsonl         # Structured event logs (JSON)
├── trades.log          # Trade journal
├── dashboard.log       # Dashboard logs
└── error.log           # Error-specific logs
```

### Viewing Logs

```bash
# Real-time engine logs
tail -f artifacts/logs/engine.log

# Real-time trade logs
tail -f artifacts/logs/trades.log

# Search for errors
grep ERROR artifacts/logs/engine.log

# View structured logs
cat artifacts/logs/events.jsonl | jq '.'
```

### Analytics & Reports

Generated in `artifacts/analytics/`:
- Trade performance reports
- Equity curves
- Strategy-specific metrics
- Backtest results

### State Checkpoints

Stored in `artifacts/checkpoints/`:
- `runtime_state_latest.json` - Latest system state
- `positions_*.json` - Position snapshots
- `orders_*.json` - Order history

## Troubleshooting

### Issue: "Kite login failed"
**Solution**: 
- Check API keys in `.env` or `secrets/kite.json`
- Ensure you have an active Kite account
- Run `python scripts/login_kite.py` again

### Issue: "No module named 'core'"
**Solution**:
- Ensure virtual environment is activated
- Run from project root directory
- Check Python path: `export PYTHONPATH=$(pwd)`

### Issue: "Dashboard not loading"
**Solution**:
- Check if port 8765 is already in use
- Try a different port: `uvicorn apps.dashboard:app --port 8000`
- Check firewall settings

### Issue: "Market data not loading"
**Solution**:
- Verify Kite login/access token
- Check internet connection
- Refresh cache: `python scripts/refresh_market_cache.py`
- Check market hours (9:15 AM - 3:30 PM IST on trading days)

### Issue: "Strategy not generating signals"
**Solution**:
- Verify strategy is enabled in config
- Check logs for errors
- Ensure sufficient market data history
- Verify universe configuration

## Development Tips

### Code Organization
- Keep changes minimal and focused
- Follow existing code patterns
- Add docstrings to new functions
- Update documentation when adding features

### Testing
```bash
# Run specific test
python scripts/test_v3_exec_flow.py

# Demo components
python scripts/demo_scanner.py
python scripts/demo_v3_trader_strategy.py
```

### Configuration Management
- Use `configs/dev.yaml` for development
- Create environment-specific configs (prod.yaml, staging.yaml)
- Never commit secrets

### Performance Tuning
- Monitor CPU and memory usage
- Optimize data caching
- Adjust log levels in production
- Use checkpoints for state recovery

---
*Auto-generated developer documentation*
