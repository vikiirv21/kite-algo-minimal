# Multi-Process Architecture (v3 Phase 1) - Usage Guide

## Overview

Architecture v3 Phase 1 introduces a multi-process layout where each engine (FnO, Equity, Options) can run as its own Python process, while keeping the existing single-process, multi-threaded behavior intact as the default.

## Key Features

- **Backward Compatible**: Default behavior unchanged
- **Two Layouts**:
  - `single` (default): All engines in one process (existing behavior)
  - `multi`: Each engine in its own process (new architecture)
- **Shared Configuration**: Both layouts use the same config file
- **Shared Artifacts**: All engines write to the same artifacts/ directory

## Usage

### Single-Process Mode (Default)

This is the existing behavior - all engines run in one process:

```bash
# Runs all engines in one process (default)
python -m scripts.run_session --mode paper --config configs/dev.yaml

# Explicitly specify single-process layout
python -m scripts.run_session --mode paper --config configs/dev.yaml --layout single
```

### Multi-Process Mode (New)

Each engine runs in its own process:

```bash
# Run all engines in separate processes
python -m scripts.run_session --mode paper --config configs/dev.yaml --layout multi
```

This will start three separate processes:
- FnO Paper Engine (apps.run_fno_paper)
- Equity Paper Engine (apps.run_equity_paper)
- Options Paper Engine (apps.run_options_paper)

### Running Individual Engines

You can also run individual engines directly:

```bash
# Run FnO paper engine only
python -m apps.run_fno_paper --config configs/dev.yaml --mode paper

# Run equity paper engine only
python -m apps.run_equity_paper --config configs/dev.yaml --mode paper

# Run options paper engine only
python -m apps.run_options_paper --config configs/dev.yaml --mode paper
```

## Process Management

### Multi-Process Monitoring

When using `--layout multi`, the session orchestrator:

1. Starts each engine as a separate subprocess
2. Monitors all processes continuously
3. If any engine fails unexpectedly:
   - Logs an ERROR
   - Stops all other engines
   - Exits with error code 1

### Graceful Shutdown

On Ctrl+C or SIGTERM:

1. Session orchestrator sends SIGTERM to all engine processes
2. Waits up to 10 seconds for graceful shutdown
3. Force kills (SIGKILL) any remaining processes
4. Runs end-of-day analytics and report generation

## Artifacts and State

All engines (regardless of layout) share:

- **artifacts/orders.csv** - Order log (append mode)
- **artifacts/signals.csv** - Signal log (append mode)
- **artifacts/checkpoints/** - State checkpoints
- **artifacts/journal/** - Trading journal

The multi-process architecture uses simple file appends with minimal write contention risk.

## Pre-Market Checks

The session orchestrator runs the same pre-market checks for both layouts:

- Time sanity check
- Filesystem setup
- Secrets validation
- Config validation
- Token authentication (optional, skipped on network issues)

## End-of-Day Pipeline

Both layouts run the same end-of-day pipeline:

- Analytics generation
- Daily backtests (optional)
- Report generation (JSON + Markdown)

## Configuration

The multi-process layout uses the same config file (`configs/dev.yaml`) with no changes required:

```yaml
trading:
  mode: "paper"
  fno_universe:
    - "NIFTY"
    - "BANKNIFTY"
    - "FINNIFTY"
  options_underlyings:
    - "NIFTY"
    - "BANKNIFTY"
    - "FINNIFTY"
  equity_universe: []  # Managed via config/universe_equity.csv
```

## Logging

Each engine process logs with its own context:

- **Single-process**: All logs interleaved in one stream
- **Multi-process**: Each engine has independent stdout/stderr

The session orchestrator logs:
- Engine start commands and PIDs
- Process monitoring events
- Non-zero exit codes

Example multi-process log output:
```
Starting multi-process engines
Starting fno engine: python -m apps.run_fno_paper --mode paper --config configs/dev.yaml
  fno engine started with PID=12345
Starting equity engine: python -m apps.run_equity_paper --mode paper --config configs/dev.yaml
  equity engine started with PID=12346
Starting options engine: python -m apps.run_options_paper --mode paper --config configs/dev.yaml
  options engine started with PID=12347
Started 3 engines: fno (PID=12345), equity (PID=12346), options (PID=12347)
```

## Testing

### Dry Run

Test pre-market checks without starting engines:

```bash
# Single-process (default)
python -m scripts.run_session --mode paper --config configs/dev.yaml --dry-run

# Multi-process
python -m scripts.run_session --mode paper --config configs/dev.yaml --layout multi --dry-run
```

### Validation Suite

Run the validation test suite:

```bash
python tests/test_multiprocess_architecture.py
```

Tests verify:
- All imports work
- Bootstrap functions are callable
- run_session supports --layout flag

## Troubleshooting

### Engine Process Dies Unexpectedly

If an engine process exits with a non-zero code:
1. Check the engine's log output
2. Verify Kite token is valid
3. Ensure config file is correct
4. Check network connectivity

### Process Not Stopping Gracefully

If processes don't stop within 10 seconds:
- They will be force killed (SIGKILL)
- Check for hanging threads or blocking I/O
- Review engine shutdown logic

### Artifacts Collision

If multiple processes write to the same files:
- CSV files use append mode (low contention)
- Checkpoints are per-engine (paper_state_latest.json, etc.)
- Consider running engines sequentially if issues arise

## Migration Path

To migrate from single-process to multi-process:

1. **Phase 1** (Current): Both modes available, single is default
2. **Phase 2** (Future): Test multi-process extensively
3. **Phase 3** (Future): Make multi-process the default
4. **Phase 4** (Future): Deprecate single-process mode

## Architecture Details

### Module Structure

```
core/
  engine_bootstrap.py      # Shared bootstrap utilities

apps/
  run_fno_paper.py         # FnO engine entrypoint
  run_equity_paper.py      # Equity engine entrypoint
  run_options_paper.py     # Options engine entrypoint

scripts/
  run_session.py           # Session orchestrator (updated with --layout)
  run_day.py               # Existing single-process runner (unchanged)
```

### Bootstrap Utilities

`core/engine_bootstrap.py` provides:
- `setup_engine_logging()` - Initialize logging
- `build_kite_client()` - Create Kite client from stored tokens
- `resolve_fno_universe()` - Resolve FnO symbols
- `resolve_equity_universe()` - Resolve equity symbols
- `resolve_options_universe()` - Resolve options underlyings
- `load_scanner_universe()` - Load scanner snapshot

These utilities avoid code duplication between the three engine entrypoints.

## Security

✓ CodeQL scan: No security issues found
✓ All tokens loaded from secrets/ directory
✓ No credentials in code or logs
✓ Subprocess spawning validated

## Future Enhancements

Possible improvements for Phase 2+:

- Per-engine log files
- Process health monitoring with metrics
- Automatic restart on failure (optional)
- Inter-process communication (IPC)
- Distributed mode across multiple machines
- Load balancing and resource limits
