"""
Run the FastAPI dashboard showing live-ish paper trading state.

Usage:
    python -m scripts.run_dashboard

Then open:
    http://127.0.0.1:8000/

The dashboard reads from:
- artifacts/paper_state.json
- artifacts/signals.csv
"""

from __future__ import annotations

import uvicorn

from apps.dashboard import app


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
