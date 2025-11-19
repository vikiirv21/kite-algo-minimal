#!/usr/bin/env python3
"""
Auto-generate curated documentation for the HFT trading system.

This script scans the repository structure and generates markdown documentation
in the docs/ folder based on current code and structure.

Usage:
    python tools/docs/generate_docs.py
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any


def find_repo_root(start_path: Path) -> Path:
    """Find repository root by looking for .git folder."""
    current = start_path.resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    # Fallback to script location's grandparent
    return start_path.resolve().parents[2]


def scan_directory_tree(root: Path, max_depth: int = 3) -> str:
    """Generate a text tree representation of directory structure."""
    lines = []
    
    def walk_dir(path: Path, prefix: str = "", depth: int = 0):
        if depth > max_depth:
            return
        
        try:
            items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
            # Filter out common non-essential directories
            items = [
                i for i in items 
                if not i.name.startswith('.') 
                and i.name not in ['__pycache__', 'node_modules', '.pytest_cache']
            ]
            
            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                connector = "└── " if is_last else "├── "
                lines.append(f"{prefix}{connector}{item.name}{'/' if item.is_dir() else ''}")
                
                if item.is_dir() and depth < max_depth:
                    extension = "    " if is_last else "│   "
                    walk_dir(item, prefix + extension, depth + 1)
        except PermissionError:
            pass
    
    walk_dir(root)
    return "\n".join(lines)


def extract_fastapi_endpoints(file_path: Path) -> list[dict[str, Any]]:
    """Extract FastAPI endpoints from a Python file using AST."""
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return []
    
    endpoints = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                # Handle @app.get(), @router.post(), etc.
                if isinstance(decorator, ast.Call):
                    if isinstance(decorator.func, ast.Attribute):
                        method = decorator.func.attr
                        if method in ['get', 'post', 'put', 'delete', 'patch']:
                            # Extract path from first argument
                            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                                path = decorator.args[0].value
                                docstring = ast.get_docstring(node) or ""
                                endpoints.append({
                                    'method': method.upper(),
                                    'path': path,
                                    'handler': node.name,
                                    'module': file_path.relative_to(file_path.parents[2]).as_posix(),
                                    'docstring': docstring.split('\n')[0] if docstring else ""
                                })
    
    return endpoints


def scan_python_files_for_endpoints(root: Path, directories: list[str]) -> list[dict[str, Any]]:
    """Scan specified directories for FastAPI endpoints."""
    all_endpoints = []
    
    for dir_name in directories:
        dir_path = root / dir_name
        if not dir_path.exists():
            continue
        
        for py_file in dir_path.rglob("*.py"):
            if py_file.name.startswith('_') and py_file.name != '__init__.py':
                continue
            endpoints = extract_fastapi_endpoints(py_file)
            all_endpoints.extend(endpoints)
    
    return all_endpoints


def extract_class_info(file_path: Path) -> list[dict[str, Any]]:
    """Extract class information from a Python file."""
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return []
    
    classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            docstring = ast.get_docstring(node) or ""
            classes.append({
                'name': node.name,
                'docstring': docstring.split('\n')[0] if docstring else ""
            })
    
    return classes


def get_file_docstring(file_path: Path) -> str:
    """Get the module-level docstring from a Python file."""
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source)
        return ast.get_docstring(tree) or ""
    except (SyntaxError, UnicodeDecodeError):
        return ""


def build_architecture_doc(repo_root: Path) -> str:
    """Generate ARCHITECTURE.md with high-level system overview."""
    
    # Scan key directories
    key_dirs = ['apps', 'core', 'engine', 'analytics', 'strategies', 'broker', 'scripts', 'ui']
    tree_parts = []
    
    for dir_name in key_dirs:
        dir_path = repo_root / dir_name
        if dir_path.exists():
            tree_parts.append(f"\n{dir_name}/\n{scan_directory_tree(dir_path, max_depth=1)}")
    
    content = f"""# System Architecture

## Overview

This is a high-frequency trading (HFT) system built for the Indian stock market via Zerodha Kite API.

### Project Description

- **Real-time Trading**: Supports paper, live, and backtest modes with real-time tick processing
- **Multi-Strategy Framework**: Pluggable strategy architecture with risk management and portfolio tracking
- **Web Dashboard**: FastAPI-based dashboard for monitoring and control

## High-Level Structure

```
{"".join(tree_parts)}
```

## Major Subsystems

### Dashboard / UI
- **Location**: `apps/dashboard.py`, `ui/` folder
- **Purpose**: Web-based monitoring and control interface
- **Technology**: FastAPI, Jinja2 templates, Server-Sent Events (SSE)
- **Features**: Real-time position tracking, P&L monitoring, strategy control

### Trading Engines
- **Paper Engine** (`engine/paper_engine.py`): Simulated trading with virtual capital
- **Live Engine** (`engine/live_engine.py`): Real order placement via Kite API
- **Execution Bridge** (`engine/execution_bridge.py`): Mode-aware order routing

### Scanner & Signal Generation
- **Scanner** (`core/scanner.py`): Technical pattern detection and signal generation
- **Indicators** (`core/indicators.py`): Technical indicator library (EMA, RSI, MACD, etc.)
- **Signal Filters** (`core/signal_filters.py`, `core/pattern_filters.py`): Multi-stage signal validation

### Strategy Layer
- **Strategy Engine v3** (`core/strategy_engine_v3.py`): Modern strategy execution framework
- **Strategy Registry** (`core/strategy_registry.py`): Strategy catalog and metadata
- **Strategies** (`strategies/`): Individual strategy implementations
  - EMA crossover strategies
  - Mean reversion strategies
  - Trend following strategies

### Risk & Portfolio Management
- **Risk Engine v2** (`core/risk_engine_v2.py`): Position sizing, loss limits, exposure management
- **Portfolio Engine** (`core/portfolio_engine.py`): Portfolio-level P&L and position tracking
- **Trade Guardian** (`core/trade_guardian.py`): Pre-trade validation and safety checks
- **Adaptive Risk Manager** (`risk/adaptive_risk_manager.py`): Dynamic risk adjustment

### Market Data & Execution
- **Market Data Engine v2** (`core/market_data_engine_v2.py`): Candle fetching and caching
- **Execution Engine v3** (`core/execution_engine_v3.py`): Order management and execution
- **Broker Integration** (`broker/`): Kite API integration, auth, and order routing

### Analytics & Monitoring
- **Telemetry** (`analytics/telemetry.py`): System-wide metrics collection
- **Trade Recorder** (`analytics/trade_recorder.py`): Trade journaling and performance tracking
- **Strategy Performance** (`analytics/strategy_performance.py`): Strategy-level metrics

### Utilities / Tools
- **Scripts** (`scripts/`): CLI tools for running engines, analysis, and management
- **Tools** (`tools/`): Development and documentation tools
- **Config Management** (`core/config.py`): YAML-based configuration

## Key Entrypoints

### Main Runners
- `scripts/run_day.py` - Main day trading orchestrator
- `scripts/run_session.py` - Session-based trading runner
- `scripts/run_paper_equity.py` - Paper trading for equities
- `scripts/run_paper_fno.py` - Paper trading for F&O

### Dashboard
- `scripts/run_dashboard.py` - Start the web dashboard
- `apps/dashboard.py` - Dashboard application

### Analysis
- `scripts/analyze_performance.py` - Performance analysis
- `scripts/analyze_paper_results.py` - Paper trading results analysis

## Configuration

- **Main Config**: `configs/dev.yaml` (and other environment configs)
- **Secrets**: `secrets/` (API keys, tokens - gitignored)
- **Artifacts**: `artifacts/` (logs, checkpoints, market data cache)

## Data Flow

```
Kite WebSocket Ticks
        ↓
Market Data Engine
        ↓
Scanner / Strategy Engine
        ↓
Signal Generation
        ↓
Risk Validation (Trade Guardian)
        ↓
Execution Engine
        ↓
Broker (Paper / Live)
        ↓
Portfolio Engine (P&L tracking)
        ↓
Analytics & Telemetry
```

---
*Auto-generated from repository structure*
"""
    
    return content


def build_frontend_doc(repo_root: Path) -> str:
    """Generate FRONTEND_DASHBOARD.md documenting the dashboard UI."""
    
    dashboard_file = repo_root / "apps" / "dashboard.py"
    endpoints = []
    if dashboard_file.exists():
        endpoints = extract_fastapi_endpoints(dashboard_file)
    
    # Check for templates and static directories
    templates_dir = repo_root / "templates"
    static_dir = repo_root / "static"
    ui_dir = repo_root / "ui"
    
    templates_exist = templates_dir.exists() and list(templates_dir.glob("*.html"))
    static_exist = static_dir.exists() and list(static_dir.rglob("*"))
    ui_exist = ui_dir.exists()
    
    content = f"""# Frontend Dashboard

## Overview

The dashboard provides a web-based interface for monitoring and controlling the trading system in real-time.

## Dashboard Location

- **Main App**: `apps/dashboard.py`
- **Dashboard Logs**: `apps/dashboard_logs.py`
- **API Routes**: `apps/api_strategies.py`
- **Templates**: `{"templates/" if templates_exist else "ui/templates/ (if present)"}` 
- **Static Assets**: `{"static/" if static_exist else "ui/static/ (if present)"}`
- **UI Module**: `{"ui/" if ui_exist else "(may vary)"}`

## Architecture

The dashboard is built with:
- **Backend**: FastAPI (Python)
- **Frontend**: HTML templates (Jinja2) + JavaScript
- **Real-time Updates**: Server-Sent Events (SSE) for live data streaming
- **API**: RESTful endpoints for data and control

## Main Screens/Sections

### 1. Overview / Home
- System status and health
- Market hours indicator
- Active engines and their status
- Current P&L snapshot
- Recent alerts/notifications

### 2. Engines / Status
- Engine state (running, stopped, error)
- Active strategies
- Position counts
- Resource utilization

### 3. Signals
- Recent signals generated
- Signal quality metrics
- Strategy-specific signals
- Historical signal performance

### 4. Positions & Portfolio
- Current open positions
- Unrealized P&L
- Position sizing
- Entry prices and current prices

### 5. Logs
- Real-time log streaming
- Log filtering and search
- Error tracking
- System events

### 6. Risk
- Risk metrics and limits
- Exposure levels
- Loss tracking
- Circuit breaker status

### 7. Strategy Lab
- Strategy configuration
- Parameter tuning
- Backtest results
- Performance comparison

### 8. Analytics
- Equity curve
- Trade history
- Performance metrics (Sharpe, win rate, etc.)
- Drawdown analysis

## API Endpoints

The dashboard exposes the following HTTP endpoints:

| Method | Path | Handler | Purpose |
|--------|------|---------|---------|
"""
    
    # Add extracted endpoints
    for ep in endpoints:
        desc = ep['docstring'][:50] + "..." if len(ep['docstring']) > 50 else ep['docstring']
        content += f"| {ep['method']} | `{ep['path']}` | `{ep['handler']}` | {desc} |\n"
    
    if not endpoints:
        content += "| GET | `/` | `dashboard_page` | Main dashboard UI |\n"
        content += "| GET | `/api/state` | `get_state` | System state |\n"
        content += "| GET | `/api/positions` | `get_positions` | Current positions |\n"
        content += "| *More endpoints detected via scanning* |\n"
    
    content += """
## Backend Integration

The dashboard connects to backend services through:

### State Management APIs
- `/api/state` - Overall system state
- `/api/config` - Configuration data
- `/api/health` - Health check endpoint

### Position & Portfolio APIs
- `/api/positions` - Current positions
- `/api/portfolio` - Portfolio summary
- `/api/pnl` - P&L data

### Strategy & Signal APIs
- `/api/strategies` - Strategy list and status
- `/api/signals` - Recent signals
- `/api/strategy/{id}` - Individual strategy details

### Analytics APIs
- `/api/analytics/trades` - Trade history
- `/api/analytics/performance` - Performance metrics
- `/api/analytics/equity-curve` - Equity curve data

### Control APIs
- `/api/control/start` - Start trading
- `/api/control/stop` - Stop trading
- `/api/control/halt` - Emergency halt

### Log APIs
- `/api/logs` - Log entries
- `/api/logs/stream` - SSE log streaming

## Running the Dashboard

```bash
# Using the script
python scripts/run_dashboard.py

# Using uvicorn directly
uvicorn apps.dashboard:app --reload --host 127.0.0.1 --port 8765
```

Access at: `http://127.0.0.1:8765`

## Technology Stack

- **FastAPI**: High-performance async web framework
- **Jinja2**: Template engine for HTML rendering
- **JavaScript**: Client-side interactivity
- **Server-Sent Events**: Real-time data push from server to client
- **Chart.js / Plotly**: Data visualization (if present)

## Security Notes

⚠️ **Important**: 
- Dashboard should only be accessible on localhost in production
- No authentication is enabled by default
- Use reverse proxy with auth for remote access
- Secure API keys in `secrets/` directory

---
*Auto-generated from apps/dashboard.py analysis*
"""
    
    return content


def build_backend_services_doc(repo_root: Path) -> str:
    """Generate BACKEND_SERVICES.md documenting backend services and engines."""
    
    # Scan for FastAPI apps
    endpoints = scan_python_files_for_endpoints(repo_root, ['apps', 'core', 'engine', 'ui'])
    
    # Scan strategies
    strategies_dir = repo_root / "strategies"
    strategies = []
    if strategies_dir.exists():
        for py_file in strategies_dir.glob("*.py"):
            if py_file.name in ['__init__.py', 'base.py']:
                continue
            classes = extract_class_info(py_file)
            for cls in classes:
                if 'Strategy' in cls['name']:
                    strategies.append({
                        'file': py_file.name,
                        'class': cls['name'],
                        'description': cls['docstring'] or "Strategy implementation"
                    })
    
    content = f"""# Backend Services

## Overview

The backend consists of trading engines, services, strategies, and supporting infrastructure.

## Main Backend Apps

### Apps Directory (`apps/`)
- `dashboard.py` - Web dashboard FastAPI application
- `dashboard_logs.py` - Log streaming and management
- `api_strategies.py` - Strategy-related API endpoints
- `server.py` - Main server orchestrator (if present)
- `run_service.py` - Service runner
- `run_equity_paper.py`, `run_fno_paper.py`, `run_options_paper.py` - Mode-specific runners

### Engine Directory (`engine/`)
- `paper_engine.py` - Paper trading engine with simulated fills
- `live_engine.py` - Live trading engine with real order placement
- `equity_paper_engine.py` - Equity-specific paper engine
- `options_paper_engine.py` - Options-specific paper engine
- `execution_bridge.py` - Unified execution interface
- `execution_engine.py` - Order execution logic
- `meta_strategy_engine.py` - Meta-strategy coordinator
- `bootstrap.py` - Engine initialization

### Core Directory (`core/`)
- `strategy_engine_v3.py` - Strategy execution framework v3
- `market_data_engine_v2.py` - Market data management v2
- `risk_engine_v2.py` - Risk validation and management v2
- `portfolio_engine.py` - Portfolio tracking and P&L
- `execution_engine_v3.py` - Execution engine v3
- `trade_guardian.py` - Pre-trade validation
- `scanner.py` - Technical pattern scanner
- `orchestrator.py` - System orchestration (if present)

### Analytics Directory (`analytics/`)
- `telemetry.py` - System metrics collection
- `trade_recorder.py` - Trade journaling
- `strategy_performance.py` - Strategy analytics

## Entry Points

### Main Day Trading
```bash
python scripts/run_day.py --login --engines all
```
Orchestrates the full trading day with login, engine startup, and shutdown.

### Paper Trading
```bash
# Equity paper trading
python scripts/run_paper_equity.py

# F&O paper trading
python scripts/run_paper_fno.py

# Options paper trading
python scripts/run_paper_options.py
```

### Session-Based Trading
```bash
python scripts/run_session.py
```
Runs a trading session with configurable parameters.

## FastAPI Services

### Detected Endpoints

| Method | Path | Handler | Module |
|--------|------|---------|--------|
"""
    
    # Add endpoints
    for ep in sorted(endpoints, key=lambda x: x['path']):
        content += f"| {ep['method']} | `{ep['path']}` | `{ep['handler']}` | {ep['module']} |\n"
    
    content += f"""

## Trading Engines

### Paper Engine
**File**: `engine/paper_engine.py`

Simulates trading with virtual capital:
- Instant fills at requested prices
- No slippage (unless configured)
- Position tracking in memory
- P&L calculation
- Risk-free strategy testing

### Live Engine
**File**: `engine/live_engine.py`

Places real orders via Kite API:
- WebSocket tick processing
- Real order placement and tracking
- Fill confirmations via API
- Safety guardrails and validation
- Market hours enforcement

### Execution Bridge
**File**: `engine/execution_bridge.py`

Mode-aware routing:
- Routes orders to appropriate broker (paper/live)
- Unified interface for all modes
- Order lifecycle management

## Strategies

### Available Strategies

| File | Class | Description |
|------|-------|-------------|
"""
    
    for strat in strategies:
        content += f"| `{strat['file']}` | `{strat['class']}` | {strat['description'][:60]}{'...' if len(strat['description']) > 60 else ''} |\n"
    
    content += """

### Strategy Framework

All strategies inherit from `BaseStrategy` and implement:
- `generate_signal()` - Core signal generation logic
- Configuration via YAML
- State management
- Risk integration

## Configuration

Backend services are configured via YAML files in `configs/`:

```yaml
trading:
  mode: paper  # or live
  paper_capital: 500000
  fno_universe: [NIFTY, BANKNIFTY]

risk:
  risk_per_trade_pct: 0.005
  max_daily_loss: 3000
  max_exposure_pct: 2.0

strategies:
  enabled: true
  # Strategy-specific config
```

## Broker Integration

### Kite Client (`broker/`)
- `kite_client.py` - Kite API wrapper
- `auth.py` - Authentication handling
- `live_broker.py` - Live broker implementation
- `execution_router.py` - Order routing logic

### Authentication Flow
1. Login via `scripts/login_kite.py`
2. Store access token in `secrets/`
3. Engines load token on startup
4. Token validation before each session

## Service Architecture

```
FastAPI App (Dashboard)
        ↓
   Engine Layer (Paper/Live)
        ↓
   Strategy Engine v3
        ↓
   Market Data Engine v2
        ↓
   Risk Engine v2
        ↓
   Execution Engine v3
        ↓
   Broker Layer (Kite)
```

## Monitoring & Health

Services expose health endpoints:
- `/health` - Basic health check
- `/api/state` - Detailed system state
- `/api/metrics` - Performance metrics

Logs are written to `artifacts/logs/`:
- `engine.log` - Engine events
- `events.jsonl` - Structured JSON logs
- `trades.log` - Trade journal

---
*Auto-generated from repository analysis*
"""
    
    return content


def build_utilities_doc(repo_root: Path) -> str:
    """Generate UTILITIES.md documenting tools and scripts."""
    
    scripts_dir = repo_root / "scripts"
    tools_dir = repo_root / "tools"
    
    # Collect scripts with docstrings
    scripts = []
    if scripts_dir.exists():
        for py_file in sorted(scripts_dir.glob("*.py")):
            if py_file.name == '__init__.py':
                continue
            docstring = get_file_docstring(py_file)
            first_line = docstring.split('\n')[0] if docstring else f"Script: {py_file.name}"
            scripts.append({
                'name': py_file.name,
                'path': f"scripts/{py_file.name}",
                'description': first_line[:80]
            })
    
    # Collect tools
    tools = []
    if tools_dir.exists():
        for py_file in tools_dir.rglob("*.py"):
            if py_file.name == '__init__.py' or '__pycache__' in str(py_file):
                continue
            docstring = get_file_docstring(py_file)
            first_line = docstring.split('\n')[0] if docstring else f"Tool: {py_file.name}"
            tools.append({
                'name': py_file.name,
                'path': str(py_file.relative_to(repo_root)),
                'description': first_line[:80]
            })
    
    content = f"""# Utilities & Tools

## Overview

This document describes helper scripts and tools for managing the trading system.

## Scripts (`scripts/`)

### Trading & Execution

| Script | Description |
|--------|-------------|
"""
    
    # Add trading-related scripts
    trading_scripts = [s for s in scripts if any(x in s['name'] for x in ['run_', 'paper', 'live', 'session'])]
    for script in trading_scripts:
        content += f"| `{script['name']}` | {script['description']} |\n"
    
    content += """
### Analysis & Reporting

| Script | Description |
|--------|-------------|
"""
    
    # Add analysis scripts
    analysis_scripts = [s for s in scripts if any(x in s['name'] for x in ['analyze', 'show', 'replay'])]
    for script in analysis_scripts:
        content += f"| `{script['name']}` | {script['description']} |\n"
    
    content += """
### Development & Utilities

| Script | Description |
|--------|-------------|
"""
    
    # Add other scripts
    other_scripts = [s for s in scripts if s not in trading_scripts and s not in analysis_scripts]
    for script in other_scripts:
        content += f"| `{script['name']}` | {script['description']} |\n"
    
    content += f"""

## Tools (`tools/`)

| Tool | Description |
|------|-------------|
"""
    
    for tool in tools:
        content += f"| `{tool['path']}` | {tool['description']} |\n"
    
    content += """

## Common Usage Examples

### Running Engines

```bash
# Paper trading (equity)
python scripts/run_paper_equity.py

# Paper trading (F&O)
python scripts/run_paper_fno.py

# Full day trading with login
python scripts/run_day.py --login --engines all
```

### Analysis & Monitoring

```bash
# Analyze paper trading results
python scripts/analyze_paper_results.py

# Show current paper state
python scripts/show_paper_state.py

# Analyze overall performance
python scripts/analyze_performance.py
```

### Development

```bash
# Generate documentation
python scripts/generate_docs.py

# Run tests
python scripts/test_v3_exec_flow.py
python scripts/test_v3_strategy_flow.py

# Demo/testing
python scripts/demo_scanner.py
python scripts/demo_v3_trader_strategy.py
```

### Authentication

```bash
# Login to Kite (interactive browser login)
python scripts/login_kite.py

# Test WebSocket connection
python scripts/diag_kite_ws.py
```

### Data Management

```bash
# Refresh market data cache
python scripts/refresh_market_cache.py

# Backfill historical data
python scripts/backfill_history.py

# Replay from historical data
python scripts/replay_from_historical.py
```

### Backtesting

```bash
# Run backtest v1
python scripts/run_backtest_v1.py

# Run backtest v3
python scripts/run_backtest_v3.py

# Run strategy-specific backtest
python scripts/run_backtest.py
```

## Helper Modules

### Risk Management
- `risk/adaptive_risk_manager.py` - Dynamic risk adjustment
- `risk/position_sizer.py` - Position sizing algorithms
- `risk/cost_model.py` - Trading cost models

### Data Management
- `data/broker_feed.py` - Broker data integration
- `data/instruments.py` - Instrument management
- `data/backtest_data.py` - Historical data for backtesting

### Configuration
- `config/` - Environment-specific configurations
- `configs/` - YAML configuration files

## Artifacts Directory

Runtime artifacts are stored in `artifacts/`:

```
artifacts/
├── checkpoints/     # State checkpoints
├── logs/            # System and trade logs
├── market_data/     # Cached market data
├── analytics/       # Performance reports
└── backtests/       # Backtest results
```

## Environment Variables

Key environment variables:
- `HFT_CONFIG` - Path to configuration file
- `KITE_DASHBOARD_CONFIG` - Dashboard-specific config
- Additional variables in `.env` file

## Development Tools

### Linting & Formatting
```bash
# (If configured in the project)
# ruff check .
# black .
```

### Testing
```bash
# Run tests (if pytest is configured)
python -m pytest tests/
```

---
*Auto-generated from repository structure*
"""
    
    return content


def build_api_endpoints_doc(repo_root: Path) -> str:
    """Generate API_ENDPOINTS.md with all HTTP endpoints."""
    
    # Scan for all FastAPI endpoints
    endpoints = scan_python_files_for_endpoints(
        repo_root, 
        ['apps', 'core', 'engine', 'ui', 'analytics', 'services']
    )
    
    content = """# API Endpoints

## Overview

This document lists all HTTP API endpoints exposed by the trading system's backend services.

## Endpoint Summary

"""
    
    # Group endpoints by prefix
    by_prefix = {}
    for ep in endpoints:
        path = ep['path']
        prefix = path.split('/')[1] if len(path.split('/')) > 1 else 'root'
        if prefix not in by_prefix:
            by_prefix[prefix] = []
        by_prefix[prefix].append(ep)
    
    # Add grouped endpoints
    for prefix in sorted(by_prefix.keys()):
        prefix_display = f"/{prefix}" if prefix != 'root' else "Root"
        content += f"\n### {prefix_display}\n\n"
        content += "| Method | Path | Handler | Module | Description |\n"
        content += "|--------|------|---------|--------|-------------|\n"
        
        for ep in sorted(by_prefix[prefix], key=lambda x: x['path']):
            desc = ep.get('docstring', '')[:50]
            if len(ep.get('docstring', '')) > 50:
                desc += "..."
            content += f"| {ep['method']} | `{ep['path']}` | `{ep['handler']}` | `{ep['module']}` | {desc} |\n"
    
    content += """

## API Categories

### Dashboard & UI Endpoints
Routes serving the web dashboard interface and frontend assets.
- Typically found in `apps/dashboard.py`
- Includes HTML pages, static files, and UI-related APIs

### State & System Endpoints
System state, health checks, and configuration.
- `/api/state` - Overall system state
- `/api/health` - Health check
- `/api/config` - Configuration data

### Position & Portfolio Endpoints
Current positions, P&L, and portfolio data.
- `/api/positions` - Current positions
- `/api/portfolio` - Portfolio summary
- `/api/pnl` - P&L data

### Strategy & Signal Endpoints
Strategy management and signal monitoring.
- `/api/strategies` - Strategy list
- `/api/signals` - Recent signals
- `/api/strategy/{id}` - Strategy details

### Analytics Endpoints
Performance metrics, trade history, and analytics.
- `/api/analytics/trades` - Trade history
- `/api/analytics/performance` - Performance metrics
- `/api/analytics/equity-curve` - Equity curve

### Control Endpoints
Trading control and management.
- `/api/control/start` - Start trading
- `/api/control/stop` - Stop trading
- `/api/control/halt` - Emergency halt

### Log Endpoints
Log streaming and management.
- `/api/logs` - Log entries
- `/api/logs/stream` - SSE log stream

## Authentication

⚠️ **Note**: Most endpoints currently do not require authentication. This is suitable for local-only deployments but should be secured for remote access.

## CORS Configuration

CORS is typically configured to allow:
- `localhost` origins during development
- Specific domains in production

## Rate Limiting

Consider implementing rate limiting for:
- Analytics endpoints (high data volume)
- Control endpoints (security)
- Log streaming (resource intensive)

## Example Usage

### Get System State
```bash
curl http://localhost:8765/api/state
```

### Get Current Positions
```bash
curl http://localhost:8765/api/positions
```

### Stream Logs (SSE)
```bash
curl -N http://localhost:8765/api/logs/stream
```

### Control Trading
```bash
# Start trading
curl -X POST http://localhost:8765/api/control/start

# Emergency halt
curl -X POST http://localhost:8765/api/control/halt
```

## Response Formats

All API responses are typically JSON:

```json
{
  "status": "success",
  "data": { ... },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

Error responses:

```json
{
  "status": "error",
  "message": "Error description",
  "code": "ERROR_CODE"
}
```

## WebSocket Endpoints

Some endpoints may support WebSocket connections for real-time updates:
- Log streaming
- Position updates
- Signal notifications

---
*Auto-generated via AST scanning of FastAPI routes*
"""
    
    return content


def build_dev_setup_doc(repo_root: Path) -> str:
    """Generate DEV_SETUP_AND_RUNBOOK.md."""
    
    # Check for requirements file
    req_file = repo_root / "requirements.txt"
    has_req = req_file.exists()
    
    # Check for pyproject.toml
    pyproject = repo_root / "pyproject.toml"
    has_pyproject = pyproject.exists()
    
    content = f"""# Developer Setup & Runbook

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
.venv\\Scripts\\activate
```

### 3. Install Dependencies

```bash
{"# Install from requirements.txt" if has_req else "# Install from pyproject.toml (or requirements if present)"}
{"pip install -r requirements.txt" if has_req else "pip install -e ."}
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
{{
  "api_key": "your_api_key",
  "api_secret": "your_api_secret"
}}
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
"""
    
    return content


def main():
    """Main documentation generation function."""
    # Find repository root
    script_path = Path(__file__).resolve()
    repo_root = find_repo_root(script_path)
    
    print(f"Repository root: {repo_root}")
    
    # Ensure docs directory exists
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(exist_ok=True)
    
    print(f"Docs directory: {docs_dir}")
    
    # Delete all existing .md files in docs/ ONLY
    print("\nCleaning old documentation...")
    deleted_count = 0
    for md_file in docs_dir.glob("*.md"):
        print(f"  Deleting: {md_file.name}")
        md_file.unlink()
        deleted_count += 1
    
    print(f"Deleted {deleted_count} old documentation files.")
    
    # Generate new documentation
    print("\nGenerating documentation...")
    
    docs_to_generate = [
        ("ARCHITECTURE.md", build_architecture_doc),
        ("FRONTEND_DASHBOARD.md", build_frontend_doc),
        ("BACKEND_SERVICES.md", build_backend_services_doc),
        ("UTILITIES.md", build_utilities_doc),
        ("API_ENDPOINTS.md", build_api_endpoints_doc),
        ("DEV_SETUP_AND_RUNBOOK.md", build_dev_setup_doc),
    ]
    
    for filename, builder_func in docs_to_generate:
        print(f"  Generating {filename}...")
        try:
            content = builder_func(repo_root)
            file_path = docs_dir / filename
            file_path.write_text(content, encoding="utf-8")
            print(f"    ✓ {filename} ({len(content):,} chars)")
        except Exception as e:
            print(f"    ✗ Error generating {filename}: {e}")
    
    print("\n" + "="*60)
    print("DOCUMENTATION GENERATION COMPLETE")
    print("="*60)
    print(f"Location: {docs_dir}")
    print(f"Files generated: {len(docs_to_generate)}")
    print("\nGenerated files:")
    for filename, _ in docs_to_generate:
        file_path = docs_dir / filename
        if file_path.exists():
            size = file_path.stat().st_size
            print(f"  ✓ {filename:<35} ({size:,} bytes)")
    print("="*60)


if __name__ == "__main__":
    main()
