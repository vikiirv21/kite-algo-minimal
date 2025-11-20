# Benchmark Comparison Backend

## Overview

This implementation provides backend support for the dashboard's "Benchmark Comparison" section, allowing tracking and visualization of NIFTY, BANKNIFTY, and FINNIFTY index levels over time.

## Components

### 1. Benchmarks Module (`analytics/benchmarks.py`)

Core module for recording and loading benchmark data.

**Key Functions:**
- `ensure_benchmarks_dir()`: Creates the benchmarks directory if needed
- `append_benchmark_snapshot(ts, nifty, banknifty, finnifty)`: Appends a single snapshot to today's JSONL file
- `load_benchmarks(days=1)`: Loads benchmark data for the last N days (capped at 10)
- `benchmarks_file_for_date(d)`: Returns the path to the JSONL file for a specific date

**Data Format:**
- Files are stored as JSONL (one JSON object per line) in `artifacts/benchmarks/`
- Filename pattern: `benchmarks_YYYY-MM-DD.jsonl`
- Each record contains: `ts` (ISO timestamp), `nifty`, `banknifty`, `finnifty` (prices or null)

### 2. Recorder Script (`scripts/run_benchmark_recorder.py`)

Periodically snapshots index levels during market hours.

**Usage:**
```bash
# Run with default settings (60-second interval)
python -m scripts.run_benchmark_recorder --config configs/dev.yaml

# Run with custom interval
python -m scripts.run_benchmark_recorder --config configs/dev.yaml --interval-seconds 30

# Run with max runtime limit (for testing)
python -m scripts.run_benchmark_recorder --config configs/dev.yaml --interval-seconds 60 --max-runtime-seconds 3600
```

**CLI Arguments:**
- `--config`: Path to config file (default: `configs/dev.yaml`)
- `--interval-seconds`: Seconds between snapshots (default: 60)
- `--max-runtime-seconds`: Maximum runtime in seconds (optional, for safety)
- `--log-level`: Logging level (DEBUG, INFO, WARNING, ERROR)

**Features:**
- Checks market hours from config (`session.market_open_ist`, `session.market_close_ist`)
- Fetches index prices via Kite API
- Defensive error handling (logs warnings but continues on fetch failures)
- Sets individual indices to `null` if fetching fails

### 3. Dashboard API Endpoint (`apps/dashboard.py`)

FastAPI endpoint for retrieving benchmark time-series data.

**Endpoint:**
```
GET /api/benchmarks?days=N
```

**Parameters:**
- `days` (optional, default=1): Number of days to look back (max 10)

**Response Format:**
```json
[
  {
    "ts": "2025-11-20T09:15:30.123456",
    "nifty": 19500.25,
    "banknifty": 45234.8,
    "finnifty": 20456.5
  },
  ...
]
```

**Error Handling:**
- Returns empty array `[]` instead of errors if files are missing
- Logs exceptions without crashing

## Index Symbol Mapping

The recorder uses the following mapping:

| Logical Name | NSE Index Symbol    |
|--------------|---------------------|
| NIFTY        | NIFTY 50            |
| BANKNIFTY    | NIFTY BANK          |
| FINNIFTY     | NIFTY FIN SERVICE   |

## Testing

Run the test suite:
```bash
python tests/test_benchmarks.py
```

Tests cover:
- Directory creation
- Snapshot appending
- Data loading (single/multiple days)
- None value handling
- Empty directory handling
- Days parameter capping

## Manual Testing

1. **Create Sample Data:**
```python
from analytics.benchmarks import append_benchmark_snapshot
from datetime import datetime

append_benchmark_snapshot(datetime.now(), 19500.25, 45234.8, 20456.5)
```

2. **Start Dashboard:**
```bash
uvicorn apps.dashboard:app --reload --port 8765
```

3. **Test API:**
```bash
curl http://127.0.0.1:8765/api/benchmarks?days=1
```

## Notes

- **Paper Mode Only:** Current implementation is designed for PAPER mode but is generic enough for future extension
- **Defensive Design:** Returns empty lists instead of throwing errors when files are missing
- **Data Retention:** Files are kept indefinitely; consider adding a cleanup script for production
- **Authentication:** Recorder requires valid Kite API credentials (set via `.env` or `secrets/kite_secrets.json`)

## Future Enhancements

- Add data retention/cleanup policy
- Support for additional indices
- Aggregation/downsampling for longer time periods
- Caching layer for frequently accessed date ranges
- Live mode support with enhanced monitoring
