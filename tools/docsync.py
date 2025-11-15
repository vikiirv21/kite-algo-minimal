#!/usr/bin/env python3
"""
docsync.py

Utility to keep documentation files in sync with the current repository state.

Features:
    * Generates/updates core docs under docs/.
    * Creates module-level references for touched Python files.
    * Prepends an entry to CHANGELOG.md summarising touched files.
    * Keeps manual notes protected between <!-- DOCSYNC:BEGIN:KEY --> markers.
"""

from __future__ import annotations

import ast
import datetime as _dt
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
MODULE_DOCS_DIR = DOCS_DIR / "modules"
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"

DOC_FILES = {
    "README.md": "Project Overview",
    "architecture.md": "Architecture",
    "config.md": "Configuration",
    "runbook.md": "Runbook",
    "apis.md": "API Reference",
    "state.md": "State Files",
    "strategy.md": "Strategy Notes",
    "index.md": "Documentation Index",
}


def run_cmd(args: Sequence[str]) -> str:
    return subprocess.check_output(args, cwd=REPO_ROOT, text=True).strip()


def get_changed_paths() -> List[str]:
    git_cmd = ["git", "diff", "--name-only", "HEAD"]
    try:
        output = run_cmd(git_cmd)
        if not output:
            return []
        return [line.strip() for line in output.splitlines() if line.strip()]
    except subprocess.CalledProcessError:
        fallback = run_cmd(["git", "ls-files"])
        return [line.strip() for line in fallback.splitlines() if line.strip()]


def ensure_dirs() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    MODULE_DOCS_DIR.mkdir(parents=True, exist_ok=True)


def replace_section(text: str, key: str, body: str) -> str:
    marker_start = f"<!-- DOCSYNC:BEGIN:{key} -->"
    marker_end = f"<!-- DOCSYNC:END:{key} -->"
    section = f"{marker_start}\n{body.rstrip()}\n{marker_end}"
    pattern = re.compile(
        rf"{re.escape(marker_start)}.*?{re.escape(marker_end)}",
        re.DOTALL,
    )
    if pattern.search(text):
        text = pattern.sub(section, text, count=1)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        if text:
            text += "\n"
        text += f"{section}\n"
    return text


def update_doc(path: Path, header: str, sections: Dict[str, str]) -> None:
    if path.exists():
        content = path.read_text(encoding="utf-8")
    else:
        content = header.rstrip() + "\n\n"
    for key, body in sections.items():
        content = replace_section(content, key, body.strip() + "\n")
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def summarize_module(path: Path) -> Tuple[str, List[str], List[Tuple[str, str]]]:
    source = path.read_text(encoding="utf-8")
    module_ast = ast.parse(source)
    module_doc = ast.get_docstring(module_ast) or "No module docstring available."
    functions: List[Tuple[str, str]] = []
    classes: List[Tuple[str, str]] = []

    for node in module_ast.body:
        if isinstance(node, ast.FunctionDef):
            if node.name.startswith("_"):
                continue
            signature = _format_signature(node.args)
            doc = _summarize_docstring(ast.get_docstring(node))
            functions.append((f"{node.name}{signature}", doc))
        elif isinstance(node, ast.AsyncFunctionDef):
            if node.name.startswith("_"):
                continue
            signature = _format_signature(node.args)
            doc = _summarize_docstring(ast.get_docstring(node))
            functions.append((f"async {node.name}{signature}", doc))
        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue
            doc = _summarize_docstring(ast.get_docstring(node))
            classes.append((node.name, doc))
    return module_doc.strip(), classes, functions


def _format_signature(args: ast.arguments) -> str:
    params: List[str] = []

    def fmt(arg: ast.arg) -> str:
        return arg.arg

    all_args = list(args.posonlyargs) + list(args.args)
    defaults = list(args.defaults)
    default_offset = len(all_args) - len(defaults)

    for idx, arg in enumerate(all_args):
        param = fmt(arg)
        if idx >= default_offset:
            param += "=" + _default_placeholder(defaults[idx - default_offset])
        params.append(param)

    if args.vararg:
        params.append("*" + fmt(args.vararg))
    elif args.kwonlyargs:
        params.append("*")

    for idx, arg in enumerate(args.kwonlyargs):
        param = fmt(arg)
        default = args.kw_defaults[idx]
        if default is not None:
            param += "=" + _default_placeholder(default)
        params.append(param)

    if args.kwarg:
        params.append("**" + fmt(args.kwarg))

    return "(" + ", ".join(params) + ")"


def _default_placeholder(node: ast.AST) -> str:
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.NameConstant):
        return repr(node.value)
    if isinstance(node, ast.Name):
        return node.id
    return "..."


def _summarize_docstring(doc: Optional[str]) -> str:
    if not doc:
        return "No documentation."
    return " ".join(doc.strip().splitlines()[:2])


def write_module_doc(py_path: Path) -> None:
    rel_path = py_path.relative_to(REPO_ROOT)
    target = MODULE_DOCS_DIR / rel_path.with_suffix(".md")
    target.parent.mkdir(parents=True, exist_ok=True)

    module_doc, classes, functions = summarize_module(py_path)
    lines = [f"# Module `{rel_path.as_posix()}`", ""]
    lines.append("## Overview")
    lines.append(module_doc)
    lines.append("")
    if classes:
        lines.append("## Public Classes")
        for name, doc in classes:
            lines.append(f"- **{name}** — {doc}")
        lines.append("")
    if functions:
        lines.append("## Public Functions")
        for name, doc in functions:
            lines.append(f"- `{name}` — {doc}")
        lines.append("")
    sections = {"MODULE": "\n".join(lines).strip()}
    header = f"# Module {rel_path.stem}\n"
    update_doc(target, header, sections)


def prepend_changelog(changed: Sequence[str]) -> None:
    timestamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"## {timestamp}", "", "Generated via docsync covering:", ""]
    if changed:
        for path in changed:
            lines.append(f"- {path}")
    else:
        lines.append("- No file changes detected (full refresh).")
    lines.append("")
    entry = "\n".join(lines)
    if CHANGELOG_PATH.exists():
        existing = CHANGELOG_PATH.read_text(encoding="utf-8")
    else:
        existing = ""
    content = entry + "\n" + existing
    CHANGELOG_PATH.write_text(content.strip() + "\n", encoding="utf-8")


def generate_docs() -> None:
    update_doc(
        DOCS_DIR / "README.md",
        "# Documentation\n",
        {
            "README_BODY": textwrap.dedent(
                """
                ## Overview
                Arthayukti combines FastAPI dashboards, market data services, and strategy engines to
                support paper and live trading with Zerodha Kite.

                ## Quickstart
                1. Install dependencies: `pip install -r requirements.txt`.
                2. Populate `secrets/kite.env` and `secrets/kite_tokens.env`.
                3. Run the dashboard/server: `python -m apps.server`.
                4. Launch paper engines: `python -m scripts.run_day --engines all`.
                5. Use `/admin/login` then `/admin/mode` to switch between PAPER/LIVE.
                """
            ).strip(),
        },
    )

    update_doc(
        DOCS_DIR / "architecture.md",
        "# Architecture\n",
        {
            "ARCHITECTURE_BODY": textwrap.dedent(
                """
                ## Components
                - **Dashboard (`ui.dashboard`)** – FastAPI router serving the SPA and `/api/*`.
                - **QuotesService (`ui.dashboard.LiveQuotesService`)** – KiteTicker based writer for `artifacts/live_quotes.json`.
                - **EngineSupervisor (`apps.server.EngineSupervisor`)** – starts/stops paper engines or live watchers.
                - **Reconciler (`apps.server.Reconciler`)** – pulls orders/positions from Kite and persists checkpoints.
                - **StateStore (`core.state_store.StateStore`)** – journaling engine for checkpoints, snapshots, and FIFO PnL.
                - **LiveBroker (`broker.live_broker.LiveBroker`)** – streams order updates and runs pre-trade margin checks.
                """
            ).strip(),
        },
    )

    update_doc(
        DOCS_DIR / "config.md",
        "# Configuration\n",
        {
            "CONFIG_BODY": textwrap.dedent(
                """
                ## Secrets
                - `secrets/kite.env`
                  - `KITE_API_KEY`
                  - `KITE_API_SECRET`
                - `secrets/kite_tokens.env`
                  - `KITE_ACCESS_TOKEN`

                ## Environment
                - `KITE_ALGO_ARTIFACTS` – override artifacts directory.
                - `KITE_DASHBOARD_CONFIG` – path to YAML config (defaults to `configs/dev.yaml`).
                - `ENABLE_LIVE_QUOTES_IN_APP` – boolean flag to toggle embedded quote streamer.

                ## Ports
                - `apps.server` defaults to `0.0.0.0:9000` (override via `UVICORN_HOST`, `UVICORN_PORT`).
                """
            ).strip(),
        },
    )

    update_doc(
        DOCS_DIR / "runbook.md",
        "# Runbook\n",
        {
            "RUNBOOK_BODY": textwrap.dedent(
                """
                ## Daily Operations
                1. `python -m apps.server` → brings up dashboard + background services.
                2. `POST /admin/login` with `{"request_token": "..."}` when tokens expire.
                3. `POST /admin/mode` to set `paper` or `live`.
                4. `POST /admin/start` / `POST /admin/stop` to control supervisors.
                5. Use `python -m scripts.run_day --engines all` for paper strategy loops.

                ## Resync & Recovery
                - `/api/resync` rebuilds state from journals (paper) or Kite (live).
                - `/admin/resync` runs the same routine server-side with logging.
                - State checkpoints stored under `artifacts/checkpoints/`.

                ## Replay & Backfill
                - `python -m scripts.backfill_history --date YYYY-MM-DD --engines all`.
                - `python -m scripts.replay_from_historical --help` for playback utilities.

                ## Troubleshooting
                - Review `artifacts/logs/server.log` for service issues.
                - Validate Kite access via `/healthz` (token_ok flag).
                - Check `artifacts/journal/` for order ingestion problems.
                """
            ).strip(),
        },
    )

    update_doc(
        DOCS_DIR / "apis.md",
        "# API Reference\n",
        {
            "APIS_BODY": textwrap.dedent(
                """
                ## Public Endpoints
                - `GET /api/state` → dashboard snapshot.
                - `GET /api/signals?limit=&date=` → signal feed.
                - `GET /api/orders?limit=&date=` → order history.
                - `GET /api/strategy_performance` → aggregated stats.
                - `GET /api/quotes?keys=A,B` → live quote cache.
                - `GET /api/positions_normalized` → normalized positions.
                - `GET /api/margins` → available funds (live mode only).
                - `POST /api/resync` → rebuilds latest state.

                ## Admin Endpoints
                - `GET /healthz` → `{ok, mode, token_ok, last_sync}`.
                - `POST /admin/login` → `{"request_token": "..."}`.
                - `POST /admin/mode` → `{"mode": "paper"|"live"}`.
                - `POST /admin/start` / `POST /admin/stop`.
                - `POST /admin/resync` → server-side resync.
                """
            ).strip(),
        },
    )

    update_doc(
        DOCS_DIR / "state.md",
        "# State Files\n",
        {
            "STATE_BODY": textwrap.dedent(
                """
                ## Artifacts Layout
                ```
                artifacts/
                  checkpoints/
                    paper_state_latest.json
                    live_state_latest.json
                  journal/
                    YYYY-MM-DD/orders.csv
                    index.json
                  snapshots/
                    positions_YYYYMMDD_HHMMSS.json
                  live_quotes.json
                  paper_state.json
                  live_state.json
                ```

                ## Checkpoint Format
                ```
                {
                  "timestamp": "...",
                  "broker": {
                    "orders": [...],
                    "positions": [...]
                  },
                  "meta": {
                    "mode": "paper|live",
                    "total_realized_pnl": ...,
                    "total_unrealized_pnl": ...,
                    "equity": ...
                  }
                }
                ```

                ## Journal Format
                CSV with headers managed by `StateStore.append_orders`. Rows remain idempotent via `order_id`.
                """
            ).strip(),
        },
    )

    update_doc(
        DOCS_DIR / "strategy.md",
        "# Strategy Notes\n",
        {
            "STRATEGY_BODY": textwrap.dedent(
                """
                ## Engines & Timeframes
                - `engine.paper_engine.PaperEngine` – FnO futures strategies with Multi-TF configs.
                - `engine.options_paper_engine.OptionsPaperEngine` – index options book.
                - `engine.equity_paper_engine.EquityPaperEngine` – cash equity intraday plays.

                Strategies rely on `strategies.fno_intraday_trend` with EMA/RSI/ATR indicators and pattern filters.

                ## Signals
                Signals are logged to `artifacts/signals.csv` via `TradeRecorder`, tagged as `{logical}|{strategy}` with HOLD/BUY/SELL semantics.
                """
            ).strip(),
        },
    )

    update_doc(
        DOCS_DIR / "index.md",
        "# Documentation Index\n",
        {
            "INDEX_BODY": textwrap.dedent(
                """
                - [README](README.md)
                - [Architecture](architecture.md)
                - [Configuration](config.md)
                - [Runbook](runbook.md)
                - [API Reference](apis.md)
                - [State Files](state.md)
                - [Strategy Notes](strategy.md)
                - [Module Docs](modules/)
                """
            ).strip(),
        },
    )


def main() -> None:
    ensure_dirs()
    changed_paths = get_changed_paths()
    generate_docs()

    python_paths = [
        (REPO_ROOT / path)
        for path in changed_paths
        if path.endswith(".py") and (REPO_ROOT / path).exists()
    ]
    for py_path in python_paths:
        write_module_doc(py_path)

    prepend_changelog(changed_paths)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"[docsync] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
