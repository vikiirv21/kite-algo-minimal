# Backend Telemetry Implementation Summary

## Overview
Implemented backend telemetry for the multi-process engine layout so the dashboard can show per-engine health.

## Implementation Details

### 1. Core Telemetry Module (`core/telemetry.py`)

Created a new telemetry module with:

- **`EngineTelemetry` dataclass**: Structured data for engine health
  - `name`: Engine name (fno, equity, options)
  - `mode`: Trading mode (paper, live)
  - `pid`: Process ID
  - `status`: Engine status (starting, running, stopped, error)
  - `started_at`: Timestamp when engine started
  - `last_heartbeat`: Timestamp of last update
  - `loop_tick`: Current loop iteration count
  - `universe_size`: Number of symbols in trading universe
  - `open_positions`: Number of open positions
  - `last_error`: Error message if status is "error"

- **`EngineTelemetryReporter` class**: Lightweight telemetry writer
  - Writes JSON files to `artifacts/telemetry/{name}_engine.json`
  - `heartbeat()`: Update telemetry with latest health info
  - `mark_stopped()`: Mark engine as stopped on shutdown

### 2. Engine Integration

Integrated telemetry into all three engine entry points:

#### `apps/run_fno_paper.py`
- Initialized telemetry reporter after engine creation
- Wrapped `_loop_once()` to inject heartbeat updates
- Reports: loop_tick, universe_size, open_positions
- Marks as "error" on exception
- Marks as "stopped" on graceful shutdown

#### `apps/run_equity_paper.py`
- Same pattern as FnO engine
- Reports universe size from `_engine.universe`

#### `apps/run_options_paper.py`
- Same pattern as FnO engine
- Reports universe size from `_engine.logical_underlyings`

### 3. Dashboard API Endpoints (`apps/dashboard.py`)

Added two new endpoints:

#### `GET /api/telemetry/engines`
- Aggregates telemetry from all engines
- Returns JSON with structure:
  ```json
  {
    "asof": "2025-11-20T06:27:26.501805",
    "engines": [
      {
        "name": "fno",
        "mode": "paper",
        "pid": 3596,
        "status": "running",
        "started_at": "2025-11-20T06:27:25.096454",
        "last_heartbeat": "2025-11-20T06:27:25.096590",
        "loop_tick": 100,
        "universe_size": 5,
        "open_positions": 2,
        "last_error": null
      },
      // ... more engines
    ]
  }
  ```

#### `GET /api/telemetry/engine_logs`
- Stub endpoint for future log tailing
- Parameters: `engine` (string), `lines` (int)
- Currently returns empty list

### 4. Testing

Created comprehensive test suite in `tests/test_telemetry.py`:

- Test telemetry directory creation
- Test `EngineTelemetry` dataclass
- Test `EngineTelemetryReporter` initialization
- Test heartbeat updates
- Test error status
- Test mark_stopped
- Test partial updates
- Test multiple engines

**All tests pass successfully.**

### 5. Configuration

Updated `.gitignore`:
- Added `artifacts/telemetry/` to exclude generated telemetry files

## Usage

### Starting Engines

Engines automatically create telemetry files when started:

```bash
# Start FnO engine
python -m apps.run_fno_paper --mode paper --config configs/dev.yaml

# Start Equity engine
python -m apps.run_equity_paper --mode paper --config configs/dev.yaml

# Start Options engine
python -m apps.run_options_paper --mode paper --config configs/dev.yaml
```

### Accessing Telemetry

Start dashboard and access endpoint:

```bash
# Start dashboard
uvicorn apps.dashboard:app --reload --port 8765

# Get engine telemetry
curl http://127.0.0.1:8765/api/telemetry/engines
```

## File Changes

### New Files
1. `core/telemetry.py` - Telemetry module (131 lines)
2. `tests/test_telemetry.py` - Test suite (263 lines)

### Modified Files
1. `apps/run_fno_paper.py` - Added telemetry integration
2. `apps/run_equity_paper.py` - Added telemetry integration
3. `apps/run_options_paper.py` - Added telemetry integration
4. `apps/dashboard.py` - Added telemetry API endpoints
5. `.gitignore` - Added telemetry directory

## Security

- ✅ CodeQL security scan passed with 0 vulnerabilities
- ✅ No sensitive data exposed in telemetry
- ✅ File writes are defensive with exception handling
- ✅ No external dependencies introduced

## Design Decisions

1. **File-based telemetry**: Simple, lightweight, no database required
2. **JSON format**: Easy to read, parse, and debug
3. **One file per engine**: Prevents locking issues, easy to aggregate
4. **Minimal engine modifications**: Uses wrapper pattern to avoid invasive changes
5. **Defensive error handling**: Telemetry failures don't crash engines

## Future Enhancements

The stub endpoint `/api/telemetry/engine_logs` can be implemented to:
- Map engine name to log file
- Tail last N lines from log
- Support log streaming
- Filter by severity

## Validation

✅ All unit tests pass
✅ API endpoints tested and working
✅ Manual integration tests successful
✅ No security vulnerabilities
✅ No breaking changes to existing functionality
✅ Minimal code modifications

## Dashboard Integration

Frontend can now:
1. Poll `/api/telemetry/engines` periodically
2. Display engine health cards showing:
   - Engine name and mode
   - Status (running/stopped/error)
   - Loop tick (activity indicator)
   - Universe size
   - Open positions
   - Last heartbeat time
   - Error messages if any
3. Alert on stale heartbeats or error status
