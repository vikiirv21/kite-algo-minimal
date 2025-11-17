# Quick Start: React Dashboard

## Installation

### 1. Install Dependencies

**Python:**
```bash
pip install -r requirements.txt
```

**Node.js (for dashboard):**
- Install Node.js 20.x or later from https://nodejs.org/
- Or use nvm: `nvm install 20`

### 2. Build the Dashboard

```bash
./build-dashboard.sh
```

Or manually:
```bash
cd ui/frontend
npm install
npm run build
cd ../..
```

### 3. Start the Server

```bash
python -m uvicorn apps.server:app --host 0.0.0.0 --port 9000
```

Or with reload for development:
```bash
python -m uvicorn apps.server:app --host 0.0.0.0 --port 9000 --reload
```

### 4. Access Dashboard

Open http://localhost:9000 in your browser.

## Development

### Frontend Development

```bash
cd ui/frontend
npm run dev
```

This starts a development server at http://localhost:3000 with:
- Hot module replacement (HMR)
- API proxy to http://localhost:9000
- Fast refresh

Make your changes, then build:
```bash
npm run build
```

### Backend API

The dashboard consumes FastAPI endpoints at `/api/*`. See:
- `ui/dashboard.py` for all API routes
- `docs/dashboard_new_ui.md` for API documentation

## Pages

| Route | Description |
|-------|-------------|
| `/` | Overview - summary cards, recent signals |
| `/trading` | Active and completed orders |
| `/portfolio` | Portfolio summary, open positions |
| `/signals` | Strategies list, signal stream |
| `/analytics` | Equity curve, performance charts |
| `/system` | System info, configuration |
| `/logs` | Engine logs with filtering |

## Features

- **Real-time Updates**: Auto-polling every 1-5 seconds
- **Dark Theme**: Professional dark UI optimized for trading
- **P&L Coloring**: Green for profits, red for losses
- **Responsive**: Works on desktop and tablet
- **Type-safe**: Full TypeScript coverage
- **Fast**: Optimized bundle size (~187KB gzipped)

## Troubleshooting

### Dashboard shows "Failed to fetch"

Check that:
1. FastAPI server is running on port 9000
2. No CORS errors in browser console
3. Check server logs for API errors

### Build fails

Make sure:
1. Node.js 20.x or later is installed
2. Run `npm install` in `ui/frontend` first
3. Check for TypeScript errors: `npm run type-check`

### Old dashboard shows instead

React build might not exist:
1. Run `./build-dashboard.sh`
2. Check `ui/static-react/` exists
3. Restart FastAPI server

## Architecture

```
┌─────────────────────────────────────────┐
│         Browser (React SPA)              │
│  ┌──────────────────────────────────┐   │
│  │  React Router                     │   │
│  │  ├─ Overview Page                │   │
│  │  ├─ Trading Page                 │   │
│  │  ├─ Portfolio Page               │   │
│  │  └─ ... (7 pages total)          │   │
│  └──────────────────────────────────┘   │
│           │                              │
│           │ React Query (polling)        │
│           │                              │
└───────────┼──────────────────────────────┘
            │
            │ HTTP/JSON
            │
┌───────────▼──────────────────────────────┐
│      FastAPI Backend (Python)            │
│  ┌──────────────────────────────────┐   │
│  │  /api/meta                        │   │
│  │  /api/engines/status             │   │
│  │  /api/portfolio/summary          │   │
│  │  /api/orders                     │   │
│  │  /api/signals                    │   │
│  │  /api/logs                       │   │
│  │  ... (20+ endpoints)             │   │
│  └──────────────────────────────────┘   │
└──────────────────────────────────────────┘
```

## Production Deployment

1. Build optimized frontend:
   ```bash
   cd ui/frontend
   npm run build
   ```

2. Start server with production settings:
   ```bash
   export UVICORN_HOST=0.0.0.0
   export UVICORN_PORT=9000
   export UVICORN_RELOAD=0
   python -m apps.server
   ```

3. Optionally use a process manager:
   ```bash
   # Using systemd, supervisor, or PM2
   pm2 start "python -m apps.server" --name arthayukti
   ```

4. Set up reverse proxy (nginx/caddy) for production

## Documentation

- **Complete Guide**: [docs/dashboard_new_ui.md](dashboard_new_ui.md)
- **Frontend README**: [ui/frontend/README.md](../ui/frontend/README.md)
- **API Docs**: FastAPI auto-docs at http://localhost:9000/docs

## Support

For issues or questions:
1. Check [docs/dashboard_new_ui.md](dashboard_new_ui.md) troubleshooting section
2. Review FastAPI logs for API errors
3. Check browser console for frontend errors
