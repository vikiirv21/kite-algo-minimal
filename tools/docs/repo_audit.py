#!/usr/bin/env python
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

# -------------------- Config --------------------

IGNORE_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
    ".idea",
    ".vscode",
}

BACKEND_DIR_HINTS = {"apps", "core", "engine", "broker", "analytics", "data", "scripts", "services"}
FRONTEND_DIR_HINTS = {"ui", "web", "frontend", "static", "templates"}

REPO_NAME_FALLBACK = "kite-algo-minimal"

# known artifact path fragments to search for in code
ARTIFACT_HINTS = [
    "live_quotes.json",
    "paper_state.json",
    "live_state.json",
    "signals.csv",
    "orders.csv",
]

SECRET_HINTS = [
    "secrets/kite.env",
    "secrets/kite_tokens.env",
]

# -------------------- Helpers --------------------


def build_tree(root: Path, max_depth: int = 3) -> str:
    """
    Build a compact ASCII tree of the repo up to max_depth.
    Skips IGNORE_DIRS and very deep subtrees.
    """
    lines: List[str] = []

    def _walk(dir_path: Path, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return

        entries = [
            p
            for p in sorted(dir_path.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
            if p.name not in IGNORE_DIRS
        ]

        for idx, entry in enumerate(entries):
            connector = "└── " if idx == len(entries) - 1 else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir():
                extension = "    " if idx == len(entries) - 1 else "│   "
                _walk(entry, prefix + extension, depth + 1)

    lines.append(root.name)
    _walk(root, "", 1)
    return "```text\n" + "\n".join(lines) + "\n```"


def classify_dirs(root: Path) -> Dict[str, str]:
    """
    Classify top-level dirs as backend/frontend/shared based on name hints.
    Returns mapping "dir_name" -> "backend" | "frontend" | "shared".
    """
    mapping: Dict[str, str] = {}
    for item in root.iterdir():
        if not item.is_dir() or item.name in IGNORE_DIRS:
            continue
        name = item.name
        if name in BACKEND_DIR_HINTS:
            mapping[name] = "backend"
        elif name in FRONTEND_DIR_HINTS:
            mapping[name] = "frontend"
        else:
            mapping[name] = "shared"
    return mapping


def find_fastapi_routes(root: Path) -> List[Tuple[str, str, str]]:
    """
    Scan .py files for FastAPI routes and return list of (method, path, file_rel).
    Very simple regex-based approach.
    """
    routes: List[Tuple[str, str, str]] = []
    method_pattern = re.compile(r'@(router|app)\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']')
    for py_file in root.rglob("*.py"):
        if any(part in IGNORE_DIRS for part in py_file.parts):
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except Exception:
            continue
        for match in method_pattern.finditer(text):
            _obj, method, path = match.groups()
            rel = os.path.relpath(py_file, root)
            routes.append((method.upper(), path, rel))
    return routes


def find_artifact_paths(root: Path) -> List[str]:
    """Search for known artifact path fragments in .py files."""
    found: List[str] = []
    for py_file in root.rglob("*.py"):
        if any(part in IGNORE_DIRS for part in py_file.parts):
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except Exception:
            continue
        for hint in ARTIFACT_HINTS:
            if hint in text and hint not in found:
                found.append(hint)
    return sorted(found)


def find_secrets_usage(root: Path) -> List[str]:
    """Search for known secret file paths in .py files."""
    found: List[str] = []
    for py_file in root.rglob("*.py"):
        if any(part in IGNORE_DIRS for part in py_file.parts):
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except Exception:
            continue
        for hint in SECRET_HINTS:
            if hint in text and hint not in found:
                found.append(hint)
    return sorted(found)


def find_frontend_calls(root: Path) -> List[Tuple[str, str]]:
    """
    Look for fetch() calls in .html/.js files and associate them with paths.
    Returns list of (path_string, file_rel).
    """
    hits: List[Tuple[str, str]] = []
    fetch_pattern = re.compile(r"fetch\(\s*['\"]([^'\"]+)['\"]")
    for ext in ("*.html", "*.js", "*.ts"):
        for f in root.rglob(ext):
            if any(part in IGNORE_DIRS for part in f.parts):
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except Exception:
                continue
            rel = os.path.relpath(f, root)
            for match in fetch_pattern.finditer(text):
                url = match.group(1)
                hits.append((url, rel))
    return hits


def detect_dashboard_file(root: Path) -> Path | None:
    """
    Guess the dashboard file location: prefer ui/dashboard.py if it exists.
    """
    candidate = root / "ui" / "dashboard.py"
    if candidate.exists():
        return candidate

    # fallback: anything called dashboard.py
    for f in root.rglob("dashboard.py"):
        if any(part in IGNORE_DIRS for part in f.parts):
            continue
        return f
    return None


def inspect_dashboard(dashboard_path: Path, repo_root: Path):
    """
    Inspect dashboard.py to determine:
      - endpoints under /api/*
      - embedded live quotes presence
    """
    try:
        text = dashboard_path.read_text(encoding="utf-8")
    except Exception:
        return {
            "path": os.path.relpath(dashboard_path, repo_root),
            "embedded_live_quotes": False,
            "api_routes": [],
        }

    # Embedded live quotes if we see KiteTicker or LiveQuotesService
    embedded_live_quotes = ("KiteTicker" in text) or ("LiveQuotesService" in text)

    method_pattern = re.compile(r'@(router|app)\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']')
    routes: List[Tuple[str, str]] = []
    for match in method_pattern.finditer(text):
        _obj, method, path = match.groups()
        if path.startswith("/api/") or path == "/":
            routes.append((method.upper(), path))

    # de-duplicate
    seen = set()
    deduped_routes: List[Tuple[str, str]] = []
    for method, path in routes:
        key = (method, path)
        if key not in seen:
            seen.add(key)
            deduped_routes.append((method, path))

    return {
        "path": os.path.relpath(dashboard_path, repo_root),
        "embedded_live_quotes": embedded_live_quotes,
        "api_routes": deduped_routes,
    }


# -------------------- Markdown generators --------------------


def write_repo_overview(
    root: Path,
    repo_name: str,
    routes: List[Tuple[str, str, str]],
    dir_classes: Dict[str, str],
    artifacts: List[str],
    secrets: List[str],
    frontend_calls: List[Tuple[str, str]],
) -> None:
    docs_dir = root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    out_path = docs_dir / "repo_overview.md"

    tree_str = build_tree(root)
    backend_dirs = [d for d, cls in dir_classes.items() if cls == "backend"]
    frontend_dirs = [d for d, cls in dir_classes.items() if cls == "frontend"]
    shared_dirs = [d for d, cls in dir_classes.items() if cls == "shared"]

    unique_routes = sorted(
        {(method, path, rel) for method, path, rel in routes},
        key=lambda r: (r[1], r[0], r[2]),
    )

    routes_md_lines: List[str] = []
    if unique_routes:
        routes_md_lines.append("| Method | Path | File |")
        routes_md_lines.append("| ------ | ---- | ---- |")
        for method, path, rel in unique_routes:
            routes_md_lines.append(f"| `{method}` | `{path}` | `{rel}` |")
    else:
        routes_md_lines.append("_No FastAPI routes detected._")

    fe_calls_lines: List[str] = []
    frontend_set = sorted(set(frontend_calls), key=lambda x: (x[0], x[1]))
    if frontend_set:
        fe_calls_lines.append("| Frontend File | Calls Path |")
        fe_calls_lines.append("| ------------- | ---------- |")
        for url, rel in frontend_set:
            fe_calls_lines.append(f"| `{rel}` | `{url}` |")
    else:
        fe_calls_lines.append("_No fetch() calls detected in frontend files._")

    artifacts_lines: List[str] = []
    if artifacts:
        artifacts_lines.append("| Artifact | Purpose (inferred) |")
        artifacts_lines.append("| -------- | ------------------ |")
        for art in artifacts:
            if "live_quotes" in art:
                purpose = "Live market quotes cache used by the dashboard."
            elif "paper_state" in art:
                purpose = "Paper trading state checkpoint."
            elif "live_state" in art:
                purpose = "Live trading state checkpoint."
            elif "signals" in art:
                purpose = "Strategy signal log."
            elif "orders" in art:
                purpose = "Order journal / trade log."
            else:
                purpose = "Used by the trading engine or dashboard."
            artifacts_lines.append(f"| `{art}` | {purpose} |")
    else:
        artifacts_lines.append("_No known artifact references found in code._")

    secrets_lines: List[str] = []
    if secrets:
        secrets_lines.append("| Secret File | Description (keys only) |")
        secrets_lines.append("| ----------- | ------------------------ |")
        for s in secrets:
            if "kite.env" in s:
                desc = "Holds KITE_API_KEY and KITE_API_SECRET (Zerodha app credential pair)."
            elif "kite_tokens.env" in s:
                desc = "Holds KITE_ACCESS_TOKEN and related tokens from the latest login session."
            else:
                desc = "Sensitive configuration file; do not commit."
            secrets_lines.append(f"| `{s}` | {desc} |")
    else:
        secrets_lines.append(
            "_No explicit secret file references detected (still ensure .env / secrets are gitignored)._"
        )

    backend_dirs_text = (
        ", ".join(f"`{d}`" for d in backend_dirs)
        if backend_dirs
        else "_None detected explicitly; backend likely lives in Python packages under the repo root._"
    )
    frontend_dirs_text = (
        ", ".join(f"`{d}`" for d in frontend_dirs)
        if frontend_dirs
        else "_None detected explicitly; UI may be embedded HTML in FastAPI or templates._"
    )
    shared_dirs_text = (
        ", ".join(f"`{d}`" for d in shared_dirs)
        if shared_dirs
        else "_No shared directories classified._"
    )

    content_lines: List[str] = [
        f"# Repository Overview -- {repo_name}",
        "",
        "This document summarizes the repository layout, backend/frontend split, and runtime artifacts.",
        "",
        "---",
        "",
        "## 1. Repository Tree (top levels)",
        "",
        tree_str,
        "",
        "---",
        "",
        "## 2. Modules by Area",
        "",
        "**Backend directories (inferred):**",
        "",
        backend_dirs_text,
        "",
        "**Frontend/UI directories (inferred):**",
        "",
        frontend_dirs_text,
        "",
        "**Shared/utility directories:**",
        "",
        shared_dirs_text,
        "",
        "---",
        "",
        "## 3. Backend <-> Frontend Wiring",
        "",
        "### 3.1 FastAPI routes",
        "",
    ]
    content_lines.extend(routes_md_lines)
    content_lines.extend(
        [
            "",
            "### 3.2 Frontend fetch() calls",
            "",
            "These are the network calls from HTML/JS that hit your backend:",
            "",
        ]
    )
    content_lines.extend(fe_calls_lines)
    content_lines.extend(
        [
            "",
            "---",
            "",
            "## 4. Data & Artifacts",
            "",
            "The code references these key artifacts (JSON/CSV state and logs):",
            "",
        ]
    )
    content_lines.extend(artifacts_lines)
    content_lines.extend(
        [
            "",
            "## 5. Secrets & Config",
            "",
            "Secret files referenced in code (ensure they stay out of git):",
            "",
        ]
    )
    content_lines.extend(secrets_lines)
    content_lines.extend(
        [
            "",
            "## 6. Ops & Run",
            "",
            "Typical commands (adapt for your environment):",
            "",
            "- `uvicorn scripts.run_dashboard:app --reload` - run the dashboard locally",
            "- `python -m scripts.run_day --login --engines all` - login and start engines",
            "- `python -m scripts.run_day --engines none` - refresh tokens only",
            "- `python -m scripts.replay_from_historical --date YYYY-MM-DD` - replay a historical session",
            "",
            "_Generated by `tools/docs/repo_audit.py`._",
        ]
    )

    out_path.write_text("\n".join(content_lines).rstrip() + "\n", encoding="utf-8")
    print(f"[repo_audit] wrote {out_path.relative_to(root)}")


def write_dashboard_doc(
    root: Path,
    repo_name: str,
    dashboard_meta: dict[str, Any] | None,
    frontend_calls: List[Tuple[str, str]],
    routes: List[Tuple[str, str, str]],
    artifacts: List[str],
) -> None:
    docs_dir = root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    out_path = docs_dir / "dashboard.md"

    summary_lines: List[str] = []
    if dashboard_meta:
        summary_lines.append(
            f"The dashboard entry point lives at `{dashboard_meta['path']}` and is mounted via FastAPI."
        )
        if dashboard_meta["embedded_live_quotes"]:
            summary_lines.append(
                "Live quotes are streamed in-process (KiteTicker/LiveQuotesService references detected)."
            )
        else:
            summary_lines.append(
                "Dashboard code does not embed a ticker; `/api/quotes` is expected to read `artifacts/live_quotes.json`."
            )
        summary_lines.append(
            f"Detected {len(dashboard_meta['api_routes'])} `/api/*` routes inside the dashboard module."
        )
    else:
        summary_lines.append(
            "Dashboard file could not be located. Update `detect_dashboard_file()` if the layout has changed."
        )

    dashboard_routes_lines: List[str] = []
    if dashboard_meta and dashboard_meta["api_routes"]:
        dashboard_routes_lines.append("| Method | Path | Source |")
        dashboard_routes_lines.append("| ------ | ---- | ------ |")
        for method, path in sorted(dashboard_meta["api_routes"], key=lambda r: (r[1], r[0])):
            dashboard_routes_lines.append(f"| `{method}` | `{path}` | `{dashboard_meta['path']}` |")
    else:
        dashboard_routes_lines.append("_No dashboard-local routes detected._")

    repo_api_rows = sorted(
        {
            (method, path, rel)
            for method, path, rel in routes
            if path.startswith("/api") or path == "/"
        },
        key=lambda r: (r[1], r[0], r[2]),
    )
    api_table_lines: List[str] = []
    if repo_api_rows:
        api_table_lines.append("| Method | Path | File |")
        api_table_lines.append("| ------ | ---- | ---- |")
        for method, path, rel in sorted(repo_api_rows, key=lambda r: (r[1], r[0], r[2])):
            api_table_lines.append(f"| `{method}` | `{path}` | `{rel}` |")
    else:
        api_table_lines.append("_No FastAPI API routes detected._")

    route_lookup: Dict[str, List[str]] = {}
    for method, path, rel in repo_api_rows:
        route_lookup.setdefault(path, []).append(f"{method} ({rel})")

    frontend_set = sorted(set(frontend_calls), key=lambda item: (item[0], item[1]))
    fe_table_lines: List[str] = []
    if frontend_set:
        fe_table_lines.append("| Frontend File | fetch() path | Backend route |")
        fe_table_lines.append("| ------------- | ------------ | ------------- |")
        for url, rel in frontend_set:
            backend_hits = route_lookup.get(url)
            mapped = ", ".join(backend_hits) if backend_hits else "_not found_"
            fe_table_lines.append(f"| `{rel}` | `{url}` | {mapped} |")
    else:
        fe_table_lines.append("_No frontend fetch() calls detected._")

    artifact_lines: List[str] = []
    if artifacts:
        artifact_lines.append("| Artifact | Role |")
        artifact_lines.append("| -------- | ---- |")
        for art in artifacts:
            if "live_quotes" in art:
                role = "Cached quotes served by `/api/quotes`."
            elif "paper_state" in art:
                role = "Paper trading checkpoint consumed by `/api/state` and status endpoints."
            elif "signals" in art:
                role = "Signal history powering `/api/signals*`."
            elif "orders" in art:
                role = "Order log powering `/api/orders*`."
            else:
                role = "General artifact consumed by dashboard endpoints."
            artifact_lines.append(f"| `{art}` | {role} |")
    else:
        artifact_lines.append("_No artifacts matched the known hints._")

    json_example_lines = [
        "```json",
        "{",
        '  "NFO:NIFTY24JANFUT": { "last_price": 22425.5, "timestamp": "2025-01-10T09:30:00+05:30" },',
        '  "NFO:BANKNIFTY24JANFUT": { "last_price": 48900.0 }',
        "}",
        "```",
    ]

    lines: List[str] = [
        "# Dashboard -- Architecture & Endpoints",
        "",
        "## Summary",
        "",
    ]
    lines.extend(summary_lines)
    lines.extend(
        [
            "",
            "## Dashboard Router",
            "",
        ]
    )
    lines.extend(dashboard_routes_lines)
    lines.extend(
        [
            "",
            "## FastAPI Endpoints (repo-wide)",
            "",
        ]
    )
    lines.extend(api_table_lines)
    lines.extend(
        [
            "",
            "## Frontend fetch() Usage",
            "",
        ]
    )
    lines.extend(fe_table_lines)
    lines.extend(
        [
            "",
            "## Data Sources & Artifacts",
            "",
        ]
    )
    lines.extend(artifact_lines)
    lines.extend(
        [
            "",
            "### Example `live_quotes.json` snapshot",
            "",
        ]
    )
    lines.extend(json_example_lines)
    lines.extend(
        [
            "",
            "## How to Run",
            "",
            "```bash",
            "# start dashboard (dev)",
            "uvicorn apps.server:app --reload --port 8765",
            "",
            "# helper scripts",
            "python -m scripts.run_dashboard --reload",
            "python -m scripts.run_day --login --engines all",
            "```",
            "",
            "## Troubleshooting",
            "",
            "- Call `/api/debug/auth` if tokens look stale.",
            "- Use `/api/resync` (or dashboard button) to rebuild paper checkpoints when data drifts.",
            "- Watch `logs/app.log` (or `artifacts/logs`) and `artifacts/live_quotes.json` when the UI shows stale numbers.",
            "",
            "_Generated by `tools/docs/repo_audit.py`._",
        ]
    )

    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"[repo_audit] wrote {out_path.relative_to(root)}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    repo_name = repo_root.name or REPO_NAME_FALLBACK

    dir_classes = classify_dirs(repo_root)
    routes = find_fastapi_routes(repo_root)
    artifacts = find_artifact_paths(repo_root)
    secrets = find_secrets_usage(repo_root)
    frontend_calls = find_frontend_calls(repo_root)

    write_repo_overview(
        repo_root,
        repo_name,
        routes,
        dir_classes,
        artifacts,
        secrets,
        frontend_calls,
    )

    dashboard_meta: dict[str, Any] | None = None
    dashboard_path = detect_dashboard_file(repo_root)
    if dashboard_path:
        dashboard_meta = inspect_dashboard(dashboard_path, repo_root)

    write_dashboard_doc(
        repo_root,
        repo_name,
        dashboard_meta,
        frontend_calls,
        routes,
        artifacts,
    )


if __name__ == "__main__":
    main()
