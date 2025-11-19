# Engine Logs Tail API

## Overview

The `/api/logs/tail` endpoint provides real-time access to engine log files for the FNO, Equity, and Options trading engines.

## Endpoint

```
GET /api/logs/tail
```

## Query Parameters

| Parameter | Type   | Required | Default | Range    | Description                           |
|-----------|--------|----------|---------|----------|---------------------------------------|
| `engine`  | string | Yes      | -       | -        | Engine name: `fno`, `equity`, or `options` |
| `lines`   | int    | No       | 200     | 1-2000   | Number of lines to return from end of file |

## Response Format

Returns JSON with the following structure:

```typescript
{
  engine: string;          // The engine name (normalized to lowercase)
  lines: string[];         // Array of log line strings (newest last)
  count: number;           // Number of lines returned
  file: string;            // Relative path to log file
  exists: boolean;         // Whether the log file exists
  warning: string | null;  // Warning message if file doesn't exist
}
```

## Examples

### Get last 20 lines from FNO engine
```bash
curl "http://localhost:8765/api/logs/tail?engine=fno&lines=20"
```

Response:
```json
{
  "engine": "fno",
  "lines": [
    "2025-01-19 10:00:00 [INFO] Engine started",
    "2025-01-19 10:00:01 [INFO] Processing signal..."
  ],
  "count": 2,
  "file": "artifacts/logs/fno_paper.log",
  "exists": true,
  "warning": null
}
```

### Get default 200 lines from Equity engine
```bash
curl "http://localhost:8765/api/logs/tail?engine=equity"
```

### Non-existent log file
If the engine hasn't been started yet or the log file doesn't exist:

```json
{
  "engine": "options",
  "lines": [],
  "count": 0,
  "file": "artifacts/logs/options_paper.log",
  "exists": false,
  "warning": "Log file options_paper.log does not exist. Engine may not be running."
}
```

## Error Responses

### Invalid engine name (400 Bad Request)
```bash
curl "http://localhost:8765/api/logs/tail?engine=invalid"
```

Response:
```json
{
  "detail": "Invalid engine name. Must be one of: fno, equity, options"
}
```

### Invalid line count (422 Unprocessable Entity)
```bash
curl "http://localhost:8765/api/logs/tail?engine=fno&lines=3000"
```

Response:
```json
{
  "detail": [
    {
      "type": "less_than_equal",
      "loc": ["query", "lines"],
      "msg": "Input should be less than or equal to 2000",
      "input": "3000",
      "ctx": {"le": 2000}
    }
  ]
}
```

## Log File Locations

The endpoint reads from these log files:

- FNO: `artifacts/logs/fno_paper.log`
- Equity: `artifacts/logs/equity_paper.log`
- Options: `artifacts/logs/options_paper.log`

## Implementation Details

- Uses `collections.deque` with `maxlen` for memory-efficient tailing
- Files are read with UTF-8 encoding and ignore decoding errors
- Empty lines are filtered out from the response
- Maximum 2000 lines to prevent excessive memory usage
- Logs are returned in chronological order (oldest to newest)

## Frontend Integration

The React frontend uses this endpoint via:

```typescript
// From ui/frontend/src/api/client.ts
getEngineLogs: (engine: string, lines = 200) => 
  fetchApi<EngineLogsTailResponse>(`/logs/tail?engine=${engine}&lines=${lines}`)
```

The `EngineLogsPanel` component polls this endpoint every 2 seconds to display live logs for each engine.

## Testing

Run the manual test suite:

```bash
python tests/manual_test_logs_api.py
```

This will verify:
- ✅ Valid engine names work correctly
- ✅ Invalid engine names return 400 error
- ✅ Line count validation (1-2000)
- ✅ Missing log files return appropriate warnings
- ✅ Response structure matches TypeScript interface
