# Engine Logs Tailing Feature

## Overview
This feature adds real-time log tailing functionality to the dashboard, allowing users to monitor logs from the FNO, Equity, and Options engine processes in real-time through a web interface.

## Backend Implementation

### API Endpoint: `/api/logs/tail`

**File:** `apps/dashboard_logs.py`

Returns the last N lines from engine log files.

**Parameters:**
- `engine` (required): Engine name - one of `fno`, `equity`, or `options`
- `lines` (optional): Number of lines to return (default: 200, max: 1000)

**Response:**
```json
{
  "engine": "fno",
  "lines": ["log line 1", "log line 2", ...],
  "count": 4,
  "file": "artifacts/logs/fno_paper.log",
  "exists": true,
  "warning": null
}
```

**Log File Mapping:**
- `fno` → `artifacts/logs/fno_paper.log`
- `equity` → `artifacts/logs/equity_paper.log`
- `options` → `artifacts/logs/options_paper.log`

### Integration
The router is wired into the main dashboard app in `apps/dashboard.py`:
```python
from apps import dashboard_logs
router.include_router(dashboard_logs.router)
```

## Frontend Implementation

### Component: `EngineLogsPanel`

**File:** `ui/frontend/src/components/EngineLogsPanel.tsx`

A React component that provides:
- **Tabbed Interface**: Switch between FNO, Equity, and Options engines
- **Auto-polling**: Fetches new logs every 2 seconds for the active tab
- **Terminal Styling**: VS Code Dark+ theme with syntax highlighting
- **Auto-scroll**: Automatically scrolls to bottom when new logs arrive
- **Manual Override**: Disable auto-scroll by scrolling up manually
- **Error Handling**: Displays warning when log files don't exist

### Features

1. **Tab Switching**: Click tabs to switch between engines
2. **Polling**: Only polls for the active engine (efficient)
3. **Syntax Highlighting**: 
   - INFO logs: Teal (#4ec9b0)
   - DEBUG logs: Gray (#808080)
   - WARN logs: Yellow (#dcdcaa)
   - ERROR logs: Red (#f48771)
4. **Auto-scroll Control**: 
   - Green indicator when ON
   - Gray indicator when OFF
   - "Jump to bottom" button when OFF
5. **Status Display**: Shows line count and file path

### Integration
Integrated into the System page (`ui/frontend/src/features/system/SystemPage.tsx`):
```tsx
import { EngineLogsPanel } from '../../components/EngineLogsPanel';

// In the component
<div>
  <h2 className="text-2xl font-bold mb-4">Engine Logs</h2>
  <EngineLogsPanel />
</div>
```

## API Client & Hooks

### Type Definition
**File:** `ui/frontend/src/types/api.ts`
```typescript
export interface EngineLogsTailResponse {
  engine: string;
  lines: string[];
  count: number;
  file: string;
  exists: boolean;
  warning: string | null;
}
```

### API Client
**File:** `ui/frontend/src/api/client.ts`
```typescript
getEngineLogs: (engine: string, lines = 200) => 
  fetchApi<EngineLogsTailResponse>(`/logs/tail?engine=${engine}&lines=${lines}`)
```

### React Query Hook
**File:** `ui/frontend/src/hooks/useApi.ts`
```typescript
export function useEngineLogs(engine: string, lines = 200, enabled = true) {
  return useQuery({
    queryKey: ['engine-logs', engine, lines] as const,
    queryFn: () => api.getEngineLogs(engine, lines),
    refetchInterval: 2000, // 2 seconds
    enabled, // Only fetch when enabled (active tab)
  });
}
```

## Usage

### Running the Dashboard
```bash
# Build the frontend
cd ui/frontend
npm install
npm run build

# Start the dashboard server
cd ../..
python3 -m uvicorn ui.dashboard:app --host 127.0.0.1 --port 8765
```

### Accessing the Feature
1. Open http://127.0.0.1:8765 in your browser
2. Navigate to the "System" page
3. Scroll down to the "Engine Logs" section
4. Click on FNO, Equity, or Options tabs to view respective logs

### API Testing
```bash
# Test the API endpoint directly
curl "http://127.0.0.1:8765/api/logs/tail?engine=fno&lines=10"
curl "http://127.0.0.1:8765/api/logs/tail?engine=equity&lines=20"
curl "http://127.0.0.1:8765/api/logs/tail?engine=options&lines=5"
```

## Technical Details

### Polling Strategy
- Only the active tab polls for logs (efficient resource usage)
- 2-second interval balances responsiveness with server load
- React Query handles caching and deduplication

### Auto-scroll Behavior
- Tracks previous line count to detect new content
- Disables automatically when user scrolls up
- Re-enables automatically when user scrolls to bottom
- Smooth scrolling for better UX

### Error Handling
- Gracefully handles missing log files
- Displays user-friendly warning messages
- Continues polling even if file doesn't exist yet
- Shows empty state with helpful message

## Performance Considerations
- Only one engine's logs fetched at a time
- Limited to 200 lines by default (configurable)
- Efficient tail implementation on backend
- No memory buildup (old logs discarded on client)

## Future Enhancements
- Live streaming via WebSocket/SSE
- Log filtering by level (INFO, DEBUG, WARN, ERROR)
- Search functionality within logs
- Download logs as file
- Multi-engine view (side-by-side)
