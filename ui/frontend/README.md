# Arthayukti React Dashboard

Modern React-based HFT control panel for the Arthayukti trading system.

## Quick Start

```bash
# Install dependencies
npm install

# Start development server (port 3000)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Development

- Development server runs on `http://localhost:3000`
- API calls are proxied to `http://localhost:9000` (or port 8765 if FastAPI is running there)
- Hot module replacement (HMR) enabled for fast development
- TypeScript compilation with strict mode

## Production Build

```bash
npm run build
```

**Output:** `../static-react/`

This directory is served by FastAPI at the root route (`/`).

**Build includes:**
- Optimized JS bundle (~631 KB, gzipped ~189 KB)
- Optimized CSS bundle (~11 KB, gzipped ~3 KB)
- Static assets (images, icons)

## Stack

- **Vite 7.2** - Build tool and dev server
- **React 19.2** - UI framework  
- **TypeScript 5.9** - Type safety
- **Tailwind CSS 4.1** - Utility-first styling
- **React Router DOM 7.9** - Client-side routing
- **TanStack Query 5.90** - Data fetching and caching
- **Recharts 3.4** - Charts and visualizations

## Documentation

- Visual Guide: [docs/dashboard_visual_guide.md](../../docs/dashboard_visual_guide.md)
- API Endpoints: [docs/API_ENDPOINTS.md](../../docs/API_ENDPOINTS.md)
- UI Documentation: [docs/UI.md](../../docs/UI.md)

## Pages

- `/` - Overview (4-card grid + recent signals)
- `/trading` - Active & Recent Orders
- `/portfolio` - Portfolio Summary + Positions
- `/signals` - Strategies + Signal Stream
- `/analytics` - Equity Curve + Performance Metrics
- `/risk` - Risk Gauges + Monitoring
- `/system` - System Info + Configuration
- `/logs` - Real-time Logs with Filters

## Key Features

- 🎨 Dark theme matching design spec (#0a0e1a navy background)
- ⚡ Real-time updates with configurable polling intervals (2-10s)
- 🔌 Connection status indicator (green pulsing when connected)
- 📊 Interactive charts with Recharts
- 🎯 TypeScript types for all API responses
- 📱 Responsive layout for desktop/tablet
- ⏱️ IST timezone for all timestamps
- 🎭 Loading skeletons and error states
- 🔄 Auto-refresh with React Query

## Running with FastAPI

Start the FastAPI backend:

```bash
# From project root
python3 -m uvicorn ui.dashboard:app --host 127.0.0.1 --port 8765
```

Then access the dashboard at `http://127.0.0.1:8765/`

## Development Workflow

1. Start FastAPI backend (port 8765)
2. Start Vite dev server: `npm run dev` (port 3000)
3. Make changes to React components
4. Vite auto-reloads on file changes
5. When ready, build for production: `npm run build`
6. Restart FastAPI to serve new build

## Environment

The Vite dev server proxies API requests to FastAPI:

```typescript
// vite.config.ts
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:9000',
      changeOrigin: true,
    },
  },
}
```

Update target if FastAPI runs on a different port (e.g., 8765).

## Linting

```bash
npm run lint
```

Fixes most issues automatically with ESLint.
