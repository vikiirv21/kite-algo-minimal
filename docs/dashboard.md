# Dashboard -- Architecture & Endpoints

## Summary

The dashboard entry point lives at `ui\dashboard.py` and is mounted via FastAPI.
Dashboard code does not embed a ticker; `/api/quotes` is expected to read `artifacts/live_quotes.json`.
Detected 29 `/api/*` routes inside the dashboard module.

## Dashboard Router

| Method | Path | Source |
| ------ | ---- | ------ |
| `GET` | `/` | `ui\dashboard.py` |
| `GET` | `/api/auth/status` | `ui\dashboard.py` |
| `GET` | `/api/config/summary` | `ui\dashboard.py` |
| `GET` | `/api/debug/auth` | `ui\dashboard.py` |
| `GET` | `/api/engines/status` | `ui\dashboard.py` |
| `GET` | `/api/health` | `ui\dashboard.py` |
| `GET` | `/api/logs` | `ui\dashboard.py` |
| `GET` | `/api/logs/recent` | `ui\dashboard.py` |
| `GET` | `/api/margins` | `ui\dashboard.py` |
| `GET` | `/api/meta` | `ui\dashboard.py` |
| `GET` | `/api/monitor/trade_flow` | `ui\dashboard.py` |
| `GET` | `/api/orders` | `ui\dashboard.py` |
| `GET` | `/api/orders/recent` | `ui\dashboard.py` |
| `GET` | `/api/pm/log` | `ui\dashboard.py` |
| `GET` | `/api/portfolio/summary` | `ui\dashboard.py` |
| `GET` | `/api/positions/open` | `ui\dashboard.py` |
| `GET` | `/api/positions_normalized` | `ui\dashboard.py` |
| `GET` | `/api/quality/summary` | `ui\dashboard.py` |
| `GET` | `/api/quotes` | `ui\dashboard.py` |
| `POST` | `/api/resync` | `ui\dashboard.py` |
| `GET` | `/api/signals` | `ui\dashboard.py` |
| `GET` | `/api/signals/recent` | `ui\dashboard.py` |
| `GET` | `/api/state` | `ui\dashboard.py` |
| `GET` | `/api/stats/equity` | `ui\dashboard.py` |
| `GET` | `/api/stats/strategies` | `ui\dashboard.py` |
| `GET` | `/api/strategy_performance` | `ui\dashboard.py` |
| `GET` | `/api/summary/today` | `ui\dashboard.py` |
| `GET` | `/api/system/time` | `ui\dashboard.py` |
| `GET` | `/api/trade_flow` | `ui\dashboard.py` |

## FastAPI Endpoints (repo-wide)

| Method | Path | File |
| ------ | ---- | ---- |
| `GET` | `/` | `apps\dashboard.py` |
| `GET` | `/` | `ui\dashboard.py` |
| `GET` | `/api/auth/status` | `ui\dashboard.py` |
| `GET` | `/api/config/summary` | `apps\dashboard.py` |
| `GET` | `/api/config/summary` | `ui\dashboard.py` |
| `GET` | `/api/debug/auth` | `ui\dashboard.py` |
| `GET` | `/api/engines/status` | `ui\dashboard.py` |
| `GET` | `/api/health` | `ui\dashboard.py` |
| `GET` | `/api/logs` | `ui\dashboard.py` |
| `GET` | `/api/logs/recent` | `ui\dashboard.py` |
| `GET` | `/api/margins` | `ui\dashboard.py` |
| `GET` | `/api/meta` | `apps\dashboard.py` |
| `GET` | `/api/meta` | `ui\dashboard.py` |
| `GET` | `/api/monitor/trade_flow` | `ui\dashboard.py` |
| `GET` | `/api/orders` | `ui\dashboard.py` |
| `GET` | `/api/orders/recent` | `ui\dashboard.py` |
| `GET` | `/api/pm/log` | `ui\dashboard.py` |
| `GET` | `/api/portfolio/summary` | `ui\dashboard.py` |
| `GET` | `/api/positions/open` | `ui\dashboard.py` |
| `GET` | `/api/positions_normalized` | `ui\dashboard.py` |
| `GET` | `/api/quality/summary` | `ui\dashboard.py` |
| `GET` | `/api/quotes` | `ui\dashboard.py` |
| `POST` | `/api/resync` | `ui\dashboard.py` |
| `GET` | `/api/signals` | `ui\dashboard.py` |
| `GET` | `/api/signals/recent` | `ui\dashboard.py` |
| `GET` | `/api/state` | `ui\dashboard.py` |
| `GET` | `/api/stats/equity` | `ui\dashboard.py` |
| `GET` | `/api/stats/strategies` | `ui\dashboard.py` |
| `GET` | `/api/strategy_performance` | `ui\dashboard.py` |
| `GET` | `/api/summary/today` | `ui\dashboard.py` |
| `GET` | `/api/system/time` | `ui\dashboard.py` |
| `GET` | `/api/trade_flow` | `ui\dashboard.py` |

## Frontend fetch() Usage

| Frontend File | fetch() path | Backend route |
| ------------- | ------------ | ------------- |
| `static\dashboard.js` | `/api/config/summary` | GET (apps\dashboard.py), GET (ui\dashboard.py) |
| `static\dashboard.js` | `/api/engines/status` | GET (ui\dashboard.py) |
| `static\dashboard.js` | `/api/health` | GET (ui\dashboard.py) |
| `static\dashboard.js` | `/api/logs/recent?limit=120` | _not found_ |
| `static\dashboard.js` | `/api/meta` | GET (apps\dashboard.py), GET (ui\dashboard.py) |
| `static\dashboard.js` | `/api/orders/recent?limit=50` | _not found_ |
| `static\dashboard.js` | `/api/portfolio/summary` | GET (ui\dashboard.py) |
| `static\dashboard.js` | `/api/positions/open` | GET (ui\dashboard.py) |
| `static\dashboard.js` | `/api/signals/recent?limit=50` | _not found_ |
| `static\dashboard.js` | `/api/state` | GET (ui\dashboard.py) |
| `static\dashboard.js` | `/api/stats/equity?days=1` | _not found_ |
| `static\dashboard.js` | `/api/stats/strategies?days=1` | _not found_ |
| `static\dashboard.js` | `/api/summary/today` | GET (ui\dashboard.py) |

## Data Sources & Artifacts

| Artifact | Role |
| -------- | ---- |
| `live_quotes.json` | Cached quotes served by `/api/quotes`. |
| `live_state.json` | General artifact consumed by dashboard endpoints. |
| `orders.csv` | Order log powering `/api/orders*`. |
| `paper_state.json` | Paper trading checkpoint consumed by `/api/state` and status endpoints. |
| `signals.csv` | Signal history powering `/api/signals*`. |

### Example `live_quotes.json` snapshot

```json
{
  "NFO:NIFTY24JANFUT": { "last_price": 22425.5, "timestamp": "2025-01-10T09:30:00+05:30" },
  "NFO:BANKNIFTY24JANFUT": { "last_price": 48900.0 }
}
```

## How to Run

```bash
# start dashboard (dev)
uvicorn apps.server:app --reload --port 8765

# helper scripts
python -m scripts.run_dashboard --reload
python -m scripts.run_day --login --engines all
```

## Troubleshooting

- Call `/api/debug/auth` if tokens look stale.
- Use `/api/resync` (or dashboard button) to rebuild paper checkpoints when data drifts.
- Watch `logs/app.log` (or `artifacts/logs`) and `artifacts/live_quotes.json` when the UI shows stale numbers.

_Generated by `tools/docs/repo_audit.py`._
