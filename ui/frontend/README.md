# Arthayukti React Dashboard

Modern React-based HFT control panel for the Arthayukti trading system.

## Quick Start

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
```

## Development

- Development server runs on `http://localhost:3000`
- API calls are proxied to `http://localhost:9000`
- Hot module replacement (HMR) enabled

## Build

```bash
npm run build
```

Output: `../static-react/`

This directory is served by FastAPI at the root route.

## Stack

- **Vite** - Build tool
- **React 18** - UI framework  
- **TypeScript** - Type safety
- **Tailwind CSS** - Styling
- **React Router** - Routing
- **React Query** - Data fetching
- **Recharts** - Charts

## Documentation

See [docs/dashboard_new_ui.md](../../docs/dashboard_new_ui.md) for complete documentation.

## Pages

- `/` - Overview
- `/trading` - Orders
- `/portfolio` - Positions & P&L
- `/signals` - Signals & Strategies  
- `/analytics` - Charts & Performance
- `/system` - System Info
- `/logs` - Engine Logs
