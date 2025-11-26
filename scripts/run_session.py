"""
Market Session Orchestrator v1

Manages the entire daily lifecycle of the trading system:
- Pre-market checks
- Starting engines (paper/live)
- Monitoring during market hours
- Post-market shutdown
- Running analytics
- Optional daily backtests
- Generating a daily report artifact

Usage:
    python -m scripts.run_session --mode paper --config configs/dev.yaml
    python -m scripts.run_session --mode paper --config configs/dev.yaml --dry-run
    python -m scripts.run_session --mode paper --config configs/dev.yaml --no-backtest --no-analytics
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Any, Dict, Optional

import pytz

from core.config import load_config
from core.logging_utils import setup_logging

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"
ANALYTICS_DIR = ARTIFACTS_DIR / "analytics"
REPORTS_DIR = ARTIFACTS_DIR / "reports" / "daily"
JOURNAL_DIR = ARTIFACTS_DIR / "journal"
LOGS_DIR = ARTIFACTS_DIR / "logs"
CHECKPOINTS_DIR = ARTIFACTS_DIR / "checkpoints"
SECRETS_DIR = BASE_DIR / "secrets"

IST = pytz.timezone("Asia/Kolkata")


def ensure_directories() -> bool:
    """Ensure all required artifact directories exist."""
    try:
        dirs = [
            ANALYTICS_DIR,
            ANALYTICS_DIR / "daily",
            REPORTS_DIR,
            JOURNAL_DIR / datetime.now().strftime("%Y-%m-%d"),
            LOGS_DIR,
            CHECKPOINTS_DIR,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
        logger.info("✓ Ensured artifact directories exist")
        return True
    except Exception as exc:
        logger.error("Failed to create directories: %s", exc)
        return False


def check_secrets_files() -> bool:
    """
    Check that required secret files exist and contain non-empty keys.
    
    Returns:
        True if all checks pass, False otherwise
    """
    kite_env = SECRETS_DIR / "kite.env"
    kite_tokens = SECRETS_DIR / "kite_tokens.env"
    
    if not kite_env.exists():
        logger.error("Missing required file: %s", kite_env)
        return False
    
    if not kite_tokens.exists():
        logger.error("Missing required file: %s", kite_tokens)
        return False
    
    # Check kite.env has KITE_API_KEY
    try:
        with kite_env.open("r") as f:
            content = f.read()
            has_api_key = False
            for line in content.splitlines():
                if line.strip().startswith("KITE_API_KEY=") or line.strip().startswith("API_KEY="):
                    key_value = line.split("=", 1)[1].strip()
                    if key_value:
                        has_api_key = True
                        break
            
            if not has_api_key:
                logger.error("kite.env missing or empty KITE_API_KEY/API_KEY")
                return False
    except Exception as exc:
        logger.error("Failed to read kite.env: %s", exc)
        return False
    
    # Check kite_tokens.env has ACCESS_TOKEN
    try:
        with kite_tokens.open("r") as f:
            content = f.read()
            has_token = False
            for line in content.splitlines():
                if line.strip().startswith("ACCESS_TOKEN=") or line.strip().startswith("KITE_ACCESS_TOKEN="):
                    token_value = line.split("=", 1)[1].strip()
                    if token_value:
                        has_token = True
                        break
            
            if not has_token:
                logger.error("kite_tokens.env missing or empty ACCESS_TOKEN/KITE_ACCESS_TOKEN")
                return False
    except Exception as exc:
        logger.error("Failed to read kite_tokens.env: %s", exc)
        return False
    
    logger.info("✓ Secrets files exist and contain required keys")
    return True


def check_config_validity(config_path: str) -> bool:
    """
    Validate that config file has required sections.
    
    Args:
        config_path: Path to the config file
    
    Returns:
        True if config is valid, False otherwise
    """
    try:
        cfg = load_config(config_path)
        
        # Check required sections
        required_sections = ["trading", "data", "risk"]
        missing = []
        
        if not hasattr(cfg, "trading") or not cfg.trading:
            missing.append("trading")
        if not hasattr(cfg, "data") or not cfg.data:
            missing.append("data")
        if not hasattr(cfg, "risk") or not cfg.risk:
            missing.append("risk")
        
        if missing:
            logger.error("Config missing required sections: %s", ", ".join(missing))
            return False
        
        # Check FnO universe is not empty
        trading = cfg.trading or {}
        fno_universe = trading.get("fno_universe", [])
        if not fno_universe:
            logger.warning("Config has empty fno_universe (may be intentional)")
        
        logger.info("✓ Config validation passed")
        return True
        
    except Exception as exc:
        logger.error("Failed to load or validate config: %s", exc)
        return False


def check_token_authentication(config_path: str) -> bool:
    """
    Perform a preflight check to ensure Kite token is valid.
    
    This reuses the preflight logic from run_day.
    
    Args:
        config_path: Path to the config file
    
    Returns:
        True if token is valid, False otherwise
    """
    try:
        from kiteconnect import KiteConnect
        from kiteconnect import exceptions as kite_exceptions
        from core.kite_env import make_kite_client_from_files
        
        kite = make_kite_client_from_files()
        profile = kite.profile()
        user_id = profile.get("user_id") or profile.get("USER_ID", "")
        logger.info("✓ Kite token authentication successful (user_id=%s)", user_id)
        return True
        
    except Exception as exc:
        # Check if it's specifically a token exception
        exc_name = type(exc).__name__
        exc_str = str(exc)
        
        # Network errors should be treated as warnings for optional checks
        if "resolve" in exc_str.lower() or "connection" in exc_str.lower():
            logger.warning("⚠ Kite API unreachable (network issue): %s", exc)
            logger.warning("  Token check skipped. Ensure network is available for actual trading.")
            return True  # Don't block on network issues
        elif "Token" in exc_name:
            logger.error("✗ Kite token invalid or expired: %s", exc)
            logger.error("  Run: python -m scripts.run_day --login --engines none")
        else:
            logger.error("✗ Kite authentication check failed: %s", exc)
        return False


def check_market_time() -> bool:
    """
    Basic sanity check that we're not too far outside trading hours.
    
    Returns:
        True if time is reasonable, False if significantly outside market hours
    """
    now = datetime.now(IST)
    current_time = now.time()
    
    # Very loose bounds: 6 AM to 11 PM IST
    # This is just a sanity check, not enforcement
    if dt_time(6, 0) <= current_time <= dt_time(23, 0):
        logger.info("✓ Current time %s IST is within reasonable bounds", now.strftime("%H:%M:%S"))
        return True
    else:
        logger.warning("⚠ Current time %s IST is outside typical hours (06:00-23:00)", now.strftime("%H:%M:%S"))
        logger.warning("  (This is only a warning, not blocking execution)")
        return True  # Don't block, just warn


def pre_market_checks(config_path: str) -> bool:
    """
    Perform all pre-market checks.
    
    Args:
        config_path: Path to the config file
    
    Returns:
        True if all critical checks pass, False otherwise
    """
    logger.info("=" * 60)
    logger.info("PRE-MARKET CHECKS")
    logger.info("=" * 60)
    
    checks = [
        ("Time sanity", check_market_time),
        ("Filesystem", ensure_directories),
        ("Secrets", check_secrets_files),
        ("Config", lambda: check_config_validity(config_path)),
        ("Token authentication", lambda: check_token_authentication(config_path)),
    ]
    
    passed = 0
    failed = 0
    
    for name, check_fn in checks:
        try:
            if callable(check_fn):
                # For functions that need no args
                if check_fn.__code__.co_argcount == 0:
                    result = check_fn()
                else:
                    result = check_fn()
            else:
                result = check_fn
            
            if result:
                passed += 1
            else:
                failed += 1
                logger.error("✗ Check failed: %s", name)
        except Exception as exc:
            failed += 1
            logger.error("✗ Check failed with exception: %s - %s", name, exc)
    
    logger.info("=" * 60)
    logger.info("Pre-market checks: %d passed, %d failed", passed, failed)
    logger.info("=" * 60)
    
    return failed == 0


def get_session_config(config_path: str) -> Dict[str, Any]:
    """
    Load session configuration from config file.
    
    Args:
        config_path: Path to the config file
    
    Returns:
        Session config dict with market_open_ist and market_close_ist
    """
    try:
        cfg = load_config(config_path)
        raw_config = getattr(cfg, "raw", {})
        session_config = raw_config.get("session", {})
        
        # Defaults
        return {
            "market_open_ist": session_config.get("market_open_ist", "09:15"),
            "market_close_ist": session_config.get("market_close_ist", "15:30"),
        }
    except Exception as exc:
        logger.warning("Failed to load session config: %s. Using defaults.", exc)
        return {
            "market_open_ist": "09:15",
            "market_close_ist": "15:30",
        }


def is_market_open(session_config: Optional[Dict[str, Any]] = None) -> bool:
    """
    Check if current time is within market hours.
    
    Args:
        session_config: Optional session config with market times
    
    Returns:
        True if market is open, False otherwise
    """
    if session_config is None:
        session_config = {"market_open_ist": "09:15", "market_close_ist": "15:30"}
    
    now = datetime.now(IST)
    current_time = now.time()
    
    open_time_str = session_config.get("market_open_ist", "09:15")
    close_time_str = session_config.get("market_close_ist", "15:30")
    
    try:
        open_hour, open_min = map(int, open_time_str.split(":"))
        close_hour, close_min = map(int, close_time_str.split(":"))
        
        open_time = dt_time(open_hour, open_min)
        close_time = dt_time(close_hour, close_min)
        
        return open_time <= current_time <= close_time
    except Exception as exc:
        logger.warning("Failed to parse market times: %s", exc)
        return True  # Default to allowing execution


def get_allowed_sessions(config_path: str) -> list:
    """
    Load allowed trading sessions from config file.
    
    Reads risk.time_filter.allow_sessions from the config.
    
    Args:
        config_path: Path to config file
    
    Returns:
        List of session dicts with 'start' and 'end' keys (IST times)
    """
    try:
        cfg = load_config(config_path)
        raw_config = getattr(cfg, "raw", {})
        risk_cfg = raw_config.get("risk", {})
        time_filter = risk_cfg.get("time_filter", {})
        allow_sessions = time_filter.get("allow_sessions", [])
        
        if not allow_sessions:
            # Default: single session for entire market hours
            return [{"start": "09:15", "end": "15:30"}]
        
        return allow_sessions
    except (FileNotFoundError, KeyError, TypeError, AttributeError) as exc:
        logger.warning("Failed to load allowed sessions: %s. Using default.", exc)
        return [{"start": "09:15", "end": "15:30"}]


def get_current_session_info(config_path: str) -> Dict[str, Any]:
    """
    Get information about current trading session based on allowed sessions.
    
    Args:
        config_path: Path to config file
    
    Returns:
        Dict with:
            - in_session: bool - whether currently in an allowed session
            - session_name: str - description of current session or gap
            - current_session: dict - current session info if in session
            - next_session: dict - next session info if not in session
    """
    now = datetime.now(IST)
    current_time = now.time()
    
    sessions = get_allowed_sessions(config_path)
    
    for i, session in enumerate(sessions):
        try:
            start_str = session.get("start", "09:15")
            end_str = session.get("end", "15:30")
            
            start_h, start_m = map(int, start_str.split(":"))
            end_h, end_m = map(int, end_str.split(":"))
            
            start_time = dt_time(start_h, start_m)
            end_time = dt_time(end_h, end_m)
            
            if start_time <= current_time <= end_time:
                session_num = i + 1
                if len(sessions) == 1:
                    session_name = "Market Session"
                elif session_num == 1:
                    session_name = "Morning Session"
                elif session_num == 2:
                    session_name = "Afternoon Session"
                else:
                    session_name = f"Session {session_num}"
                
                return {
                    "in_session": True,
                    "session_name": f"{session_name} ({start_str}-{end_str})",
                    "current_session": session,
                    "next_session": sessions[i + 1] if i + 1 < len(sessions) else None,
                }
        except (ValueError, KeyError, AttributeError) as exc:
            logger.debug("Error parsing session %d: %s", i, exc)
            continue
    
    # Not in any session - find next session
    next_session = None
    for session in sessions:
        try:
            start_str = session.get("start", "09:15")
            start_h, start_m = map(int, start_str.split(":"))
            start_time = dt_time(start_h, start_m)
            
            if start_time > current_time:
                next_session = session
                break
        except (ValueError, KeyError, AttributeError):
            continue
    
    # Determine gap name
    if next_session:
        session_name = f"Break (next: {next_session.get('start', '??:??')})"
    else:
        session_name = "Market Closed"
    
    return {
        "in_session": False,
        "session_name": session_name,
        "current_session": None,
        "next_session": next_session,
    }


def log_session_status(config_path: str) -> None:
    """
    Log current trading session status.
    
    Args:
        config_path: Path to config file
    """
    session_info = get_current_session_info(config_path)
    sessions = get_allowed_sessions(config_path)
    
    logger.info("=" * 60)
    logger.info("TRADING SESSION STATUS")
    logger.info("=" * 60)
    logger.info("Current time (IST): %s", datetime.now(IST).strftime("%H:%M:%S"))
    logger.info("Configured sessions: %d", len(sessions))
    
    for i, session in enumerate(sessions, 1):
        start = session.get("start", "??:??")
        end = session.get("end", "??:??")
        logger.info("  Session %d: %s - %s", i, start, end)
    
    if session_info["in_session"]:
        logger.info("Active Session: %s ✓", session_info["session_name"])
    else:
        logger.info("Current Status: %s", session_info["session_name"])
        if session_info["next_session"]:
            next_start = session_info["next_session"].get("start", "??:??")
            next_end = session_info["next_session"].get("end", "??:??")
            logger.info("Next Session: %s - %s", next_start, next_end)
    
    logger.info("=" * 60)


def start_engines_subprocess(mode: str, config_path: str) -> subprocess.Popen:
    """
    Start engines via run_day in a subprocess (single-process mode).
    
    Args:
        mode: Trading mode ("paper" or "live")
        config_path: Path to config file
    
    Returns:
        Popen handle for the subprocess
    """
    cmd = [
        sys.executable,
        "-m",
        "scripts.run_day",
        "--mode", mode,
        "--engines", "all",
        "--config", config_path,
    ]
    
    logger.info("Starting engines (single-process): %s", " ".join(cmd))
    
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        universal_newlines=True,
        cwd=BASE_DIR,
    )
    
    logger.info("Engines started with PID=%d", proc.pid)
    return proc


def _start_engine(cmd: list, log_path: Path, name: str) -> subprocess.Popen:
    """
    Start a single engine process with log redirection.
    
    Args:
        cmd: Command to execute
        log_path: Path to log file
        name: Engine name (for logging)
    
    Returns:
        Popen handle for the subprocess
    """
    # Ensure log directory exists
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Open the log file in append mode
    log_file = open(log_path, "a", buffering=1, encoding="utf-8")
    
    # Start process with stdout/stderr redirected to log file
    proc = subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=log_file,
        bufsize=1,
        universal_newlines=True,
        cwd=BASE_DIR,
    )
    
    # Store log file handle for cleanup
    proc._log_file = log_file  # type: ignore
    
    return proc


def start_multi_process_engines(mode: str, config_path: str) -> Dict[str, subprocess.Popen]:
    """
    Start engines in multi-process mode (one process per engine).
    
    Args:
        mode: Trading mode ("paper" or "live")
        config_path: Path to config file
    
    Returns:
        Dict mapping engine name to Popen handle
    """
    base_cmd = [sys.executable, "-m"]

    cfg = None
    engines_cfg = {}
    live_engines_cfg: Dict[str, Any] = {}
    try:
        cfg = load_config(config_path)
        engines_cfg = cfg.raw.get("engines", {}) if isinstance(cfg.raw, dict) else {}
        live_engines_cfg = cfg.raw.get("live_engines", {}) if isinstance(cfg.raw, dict) else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to read engines config from %s: %s", config_path, exc)

    engines: Dict[str, Dict[str, Any]] = {}

    if mode == "live" and live_engines_cfg:
        logger.info("LIVE mode: engine selection driven by live_engines flags from config.")
        # Live equity (optional)
        if live_engines_cfg.get("equity"):
            engines["live_equity"] = {
                "module": "scripts.run_live_equity",
                "log": LOGS_DIR / "live_equity.log",
            }
        # Live FnO placeholder (reuse paper runner for now)
        if live_engines_cfg.get("fno"):
            engines["live_fno"] = {
                "module": "scripts.run_paper_fno",
                "log": LOGS_DIR / "live_fno.log",
            }
        # Live options (reuse paper options runner with live config)
        if live_engines_cfg.get("options"):
            engines["live_options"] = {
                "module": "scripts.run_paper_options",
                "log": LOGS_DIR / "live_options.log",
            }
        if not engines:
            logger.warning("LIVE mode: no engines enabled under live_engines in config.")
    else:
        mode_engines = engines_cfg.get(mode, {}) if isinstance(engines_cfg, dict) else {}
        if mode_engines:
            for name, eng_cfg in mode_engines.items():
                if not isinstance(eng_cfg, dict):
                    continue
                if not eng_cfg.get("enabled", False):
                    continue
                runner = eng_cfg.get("runner")
                if not runner:
                    continue
                log_file = eng_cfg.get("log") or (LOGS_DIR / f"{name}.log")
                engines[name] = {
                    "module": runner,
                    "log": Path(log_file),
                }
            logger.info("Using config-driven engine matrix for mode=%s", mode)
        else:
            # Fallback to legacy behavior
            if mode == "live":
                engines = {
                    "live_equity": {
                        "module": "scripts.run_live_equity",
                        "log": LOGS_DIR / "live_equity.log",
                    },
                }
                logger.info("LIVE mode: Starting live equity engine only (paper engines skipped)")
            else:
                engines = {
                    "fno": {
                        "module": "apps.run_fno_paper",
                        "log": LOGS_DIR / "fno_paper.log",
                    },
                    "equity": {
                        "module": "apps.run_equity_paper",
                        "log": LOGS_DIR / "equity_paper.log",
                    },
                    "options": {
                        "module": "apps.run_options_paper",
                        "log": LOGS_DIR / "options_paper.log",
                    },
                }
                logger.info("PAPER mode: starting default paper engines (fallback)")

    processes: Dict[str, subprocess.Popen] = {}
    
    logger.info("=" * 60)
    logger.info("Starting multi-process engines (mode=%s)", mode)
    logger.info("=" * 60)
    
    for engine_name, info in engines.items():
        # For live equity, we use --config only (no --mode flag needed)
        if mode == "live" and engine_name == "live_equity":
            cmd = base_cmd + [info["module"], "--config", config_path]
        else:
            cmd = base_cmd + [info["module"], "--mode", mode, "--config", config_path]
        log_path = info["log"]
        
        logger.info("Starting %s engine: %s", engine_name, " ".join(cmd))
        logger.info("  Log file: %s", log_path)
        
        try:
            proc = _start_engine(cmd, log_path, engine_name)
            processes[engine_name] = proc
            logger.info("  %s engine started with PID=%d", engine_name, proc.pid)
        except Exception as exc:
            logger.error("Failed to start %s engine: %s", engine_name, exc)
    
    if not processes:
        logger.error("Failed to start any engines in multi-process mode")
        return {}
    
    logger.info("=" * 60)
    logger.info("Started %d engines: %s", len(processes), ", ".join(
        f"{name} (PID={proc.pid})" for name, proc in processes.items()
    ))
    logger.info("=" * 60)
    
    return processes


def monitor_multi_process_engines(processes: Dict[str, subprocess.Popen]) -> int:
    """
    Monitor multiple engine processes and handle their lifecycle.
    
    Args:
        processes: Dict mapping engine name to Popen handle
    
    Returns:
        Exit code (0 if all processes exited normally, 1 if any failed)
    """
    if not processes:
        logger.error("No processes to monitor")
        return 1
    
    logger.info("Monitoring %d engine processes. Press Ctrl+C to stop.", len(processes))
    
    # Track exit codes and which engines have exited
    exited_engines: Dict[str, int] = {}
    any_failed = False
    last_heartbeat = time.time()
    heartbeat_interval = 30  # seconds
    
    try:
        # Poll all processes periodically
        while True:
            # Check each engine's status
            for engine_name, proc in list(processes.items()):
                # Skip engines that have already exited
                if engine_name in exited_engines:
                    continue
                
                exit_code = proc.poll()
                
                if exit_code is not None:
                    # Engine has exited
                    exited_engines[engine_name] = exit_code
                    
                    if exit_code == 0:
                        logger.info("Engine %s (PID=%d) exited with code 0", engine_name, proc.pid)
                    else:
                        logger.error("Engine %s (PID=%d) exited with code %d", engine_name, proc.pid, exit_code)
                        any_failed = True
                    
                    # Close log file handle
                    if hasattr(proc, '_log_file'):
                        try:
                            proc._log_file.close()
                        except Exception:
                            pass
            
            # Check if all engines have exited
            if len(exited_engines) == len(processes):
                # All engines have stopped
                logger.info("=" * 60)
                logger.info("All engines have stopped")
                logger.info("Exit summary:")
                for name, code in exited_engines.items():
                    status = "OK" if code == 0 else "FAILED"
                    logger.info("  %s: exit_code=%d (%s)", name, code, status)
                logger.info("=" * 60)
                
                if any_failed:
                    logger.error("One or more engines failed")
                    return 1
                else:
                    logger.info("All engines exited successfully")
                    return 0
            
            # Periodic heartbeat
            now = time.time()
            if now - last_heartbeat > heartbeat_interval:
                running_engines = []
                for name, proc in processes.items():
                    if name not in exited_engines:
                        running_engines.append(f"{name}=running(PID={proc.pid})")
                
                if running_engines:
                    logger.info("Still monitoring engines: %s", ", ".join(running_engines))
                
                last_heartbeat = now
            
            # Wait a bit before next check
            time.sleep(2)
            
    except KeyboardInterrupt:
        logger.info("=" * 60)
        logger.info("Received KeyboardInterrupt, terminating all engines...")
        logger.info("=" * 60)
        _stop_all_processes(processes)
        return 0


def _stop_all_processes(processes: Dict[str, subprocess.Popen]) -> None:
    """
    Stop all engine processes gracefully, with force kill as fallback.
    
    Args:
        processes: Dict mapping engine name to Popen handle
    """
    # First, send SIGINT (or CTRL_BREAK_EVENT on Windows) to all
    for engine_name, proc in processes.items():
        if proc.poll() is None:  # Still running
            logger.info("Sending interrupt signal to %s engine (PID=%d)", engine_name, proc.pid)
            try:
                if os.name == "nt":
                    # Windows: use CTRL_BREAK_EVENT
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    # Unix: use SIGINT
                    proc.send_signal(signal.SIGINT)
            except Exception as exc:
                logger.warning("Failed to send interrupt signal to %s engine: %s", engine_name, exc)
    
    # Wait up to 10 seconds for graceful shutdown
    deadline = time.time() + 10
    while time.time() < deadline:
        all_stopped = all(proc.poll() is not None for proc in processes.values())
        if all_stopped:
            logger.info("All engines stopped gracefully")
            # Close log files
            for proc in processes.values():
                if hasattr(proc, '_log_file'):
                    try:
                        proc._log_file.close()
                    except Exception:
                        pass
            return
        time.sleep(0.5)
    
    # Force kill any remaining processes
    for engine_name, proc in processes.items():
        if proc.poll() is None:  # Still running
            logger.warning("Force killing %s engine (PID=%d)", engine_name, proc.pid)
            proc.kill()
            proc.wait()
            
            # Close log file
            if hasattr(proc, '_log_file'):
                try:
                    proc._log_file.close()
                except Exception:
                    pass
    
    logger.info("All engines terminated")


def monitor_engines(proc: subprocess.Popen) -> int:
    """
    Monitor the engines subprocess and stream output.
    
    Args:
        proc: Subprocess handle
    
    Returns:
        Exit code of the subprocess
    """
    logger.info("Monitoring engines (PID=%d). Press Ctrl+C to stop.", proc.pid)
    
    try:
        # Stream output line by line
        if proc.stdout:
            for line in iter(proc.stdout.readline, ""):
                if line:
                    print(line, end="")
        
        # Wait for process to complete
        exit_code = proc.wait()
        
        if exit_code == 0:
            logger.info("Engines exited normally (exit_code=0)")
        else:
            logger.error("Engines exited with error (exit_code=%d)", exit_code)
        
        return exit_code
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal. Stopping engines...")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("Engines did not stop gracefully. Forcing termination...")
            proc.kill()
            proc.wait()
        return 0


def run_analytics(config_path: str, mode: str = "paper") -> bool:
    """
    Run analytics pipeline.
    
    Args:
        config_path: Path to config file (for reference, not passed to script)
        mode: Trading mode (paper or live)
    
    Returns:
        True if successful, False otherwise
    """
    logger.info("Running end-of-day analytics...")
    
    cmd = [
        sys.executable,
        "-m",
        "scripts.run_analytics",
        "--mode", mode,
    ]
    
    logger.info("Command: %s", " ".join(cmd))
    
    try:
        result = subprocess.run(
            cmd,
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )
        
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        if result.returncode == 0:
            logger.info("✓ Analytics completed successfully")
            return True
        else:
            logger.error("✗ Analytics failed with exit code %d", result.returncode)
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("✗ Analytics timed out after 5 minutes")
        return False
    except Exception as exc:
        logger.error("✗ Analytics failed with exception: %s", exc)
        return False


def run_backtest(config_path: str, today: str) -> bool:
    """
    Run daily backtest (integration point for future implementation).
    
    Args:
        config_path: Path to config file
        today: Date string in YYYY-MM-DD format
    
    Returns:
        True if successful, False otherwise
    """
    logger.info("Daily backtest integration point")
    logger.info("  TODO: Implement daily backtest for date=%s", today)
    logger.info("  (This feature is not yet implemented)")
    return True


def generate_daily_report(mode: str, config_path: str, today: str) -> bool:
    """
    Generate daily report in JSON and Markdown formats.
    
    Args:
        mode: Trading mode
        config_path: Path to config file
        today: Date string in YYYY-MM-DD format
    
    Returns:
        True if successful, False otherwise
    """
    logger.info("Generating daily report for %s...", today)
    
    # Load analytics data
    analytics_file = ANALYTICS_DIR / "daily" / f"{today}.json"
    analytics_data = {}
    
    if analytics_file.exists():
        try:
            with analytics_file.open("r") as f:
                analytics_data = json.load(f)
            logger.info("Loaded analytics from %s", analytics_file)
        except Exception as exc:
            logger.warning("Failed to load analytics: %s", exc)
    else:
        logger.warning("No analytics file found at %s", analytics_file)
    
    # Extract key metrics
    daily_metrics = analytics_data.get("daily_metrics", {})
    strategy_metrics = analytics_data.get("strategy_metrics", {})
    
    realized_pnl = daily_metrics.get("realized_pnl", 0.0)
    num_trades = daily_metrics.get("num_trades", 0)
    win_rate = daily_metrics.get("win_rate", 0.0)
    biggest_winner = daily_metrics.get("biggest_winner", 0.0)
    biggest_loser = daily_metrics.get("biggest_loser", 0.0)
    
    # Build report data
    report_data = {
        "date": today,
        "mode": mode.upper(),
        "config": config_path,
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "realized_pnl": realized_pnl,
            "num_trades": num_trades,
            "win_rate": win_rate,
        },
        "strategies": {},
    }
    
    # Sort strategies by PnL
    if strategy_metrics:
        sorted_strategies = sorted(
            strategy_metrics.items(),
            key=lambda x: x[1].get("realized_pnl", 0.0),
            reverse=True,
        )
        for strategy_code, metrics in sorted_strategies:
            report_data["strategies"][strategy_code] = {
                "trades": metrics.get("trades", 0),
                "realized_pnl": metrics.get("realized_pnl", 0.0),
                "win_rate": metrics.get("win_rate", 0.0),
            }
    
    # Save JSON report
    json_file = REPORTS_DIR / f"{today}.json"
    try:
        with json_file.open("w") as f:
            json.dump(report_data, f, indent=2, default=str)
        logger.info("✓ Saved JSON report to %s", json_file)
    except Exception as exc:
        logger.error("Failed to save JSON report: %s", exc)
        return False
    
    # Generate Markdown report
    md_file = REPORTS_DIR / f"{today}.md"
    try:
        md_lines = [
            f"# Daily Report — {today}",
            "",
            f"- Mode: {mode.upper()}",
            f"- Config: {config_path}",
            f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Summary",
            f"- Realized PnL: {realized_pnl:+.2f}",
            f"- Trades: {num_trades}",
        ]
        
        if num_trades > 0:
            md_lines.extend([
                f"- Win Rate: {win_rate:.1f}%",
                f"- Biggest Winner: {biggest_winner:+.2f}",
                f"- Biggest Loser: {biggest_loser:+.2f}",
            ])
        
        if report_data["strategies"]:
            md_lines.extend([
                "",
                "## Strategy Performance",
                "",
            ])
            for strategy_code, metrics in report_data["strategies"].items():
                pnl = metrics["realized_pnl"]
                trades = metrics["trades"]
                md_lines.append(f"- **{strategy_code}**: {trades} trades, PnL: {pnl:+.2f}")
        
        md_lines.extend([
            "",
            "## Notes",
            "",
            "_(Manual notes can be added here)_",
            "",
        ])
        
        with md_file.open("w") as f:
            f.write("\n".join(md_lines))
        
        logger.info("✓ Saved Markdown report to %s", md_file)
        return True
        
    except Exception as exc:
        logger.error("Failed to save Markdown report: %s", exc)
        return False


def run_eod_pipeline(
    config_path: str,
    mode: str,
    run_analytics_flag: bool = True,
    run_backtests: bool = True,
) -> None:
    """
    Run end-of-day pipeline: analytics, backtests, and report generation.
    
    Args:
        config_path: Path to config file
        mode: Trading mode
        run_analytics_flag: Whether to run analytics
        run_backtests: Whether to run backtests
    """
    logger.info("=" * 60)
    logger.info("END-OF-DAY PIPELINE")
    logger.info("=" * 60)
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Run analytics
    if run_analytics_flag:
        run_analytics(config_path, mode)
    else:
        logger.info("Skipping analytics (--no-analytics flag)")
    
    # Run backtests
    if run_backtests:
        run_backtest(config_path, today)
    else:
        logger.info("Skipping backtests (--no-backtest flag)")
    
    # Generate daily report
    generate_daily_report(mode, config_path, today)
    
    logger.info("=" * 60)
    logger.info("END-OF-DAY PIPELINE COMPLETE")
    logger.info("=" * 60)


def main() -> None:
    """Main entry point for the session orchestrator."""
    parser = argparse.ArgumentParser(
        description="Market Session Orchestrator v1 - Manages the daily trading lifecycle"
    )
    parser.add_argument(
        "--mode",
        choices=["paper", "live"],
        default="paper",
        help="Trading mode (default: paper)",
    )
    parser.add_argument(
        "--config",
        default="configs/dev.yaml",
        help="Path to YAML config file (default: configs/dev.yaml)",
    )
    parser.add_argument(
        "--layout",
        choices=["single", "multi"],
        default="single",
        help="Engine layout: single (all in one process) or multi (one process per engine). Default: single",
    )
    parser.add_argument(
        "--no-backtest",
        action="store_true",
        help="Skip end-of-day backtests",
    )
    parser.add_argument(
        "--no-analytics",
        action="store_true",
        help="Skip end-of-day analytics",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pre-checks only, do not start engines",
    )
    
    args = parser.parse_args()
    
    # Setup logging
    try:
        cfg = load_config(args.config)
        setup_logging(cfg.logging)
    except Exception:
        # Fallback logging if config fails
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    
    logger.info("=" * 60)
    logger.info("MARKET SESSION ORCHESTRATOR V1")
    logger.info("=" * 60)
    logger.info("Mode: %s", args.mode.upper())
    logger.info("Config: %s", args.config)
    logger.info("Layout: %s", args.layout)
    logger.info("Dry run: %s", args.dry_run)
    logger.info("=" * 60)
    
    # Pre-market checks
    if not pre_market_checks(args.config):
        logger.error("Pre-market checks failed. Aborting.")
        sys.exit(1)
    
    if args.dry_run:
        logger.info("Dry run mode: Pre-checks completed. Exiting without starting engines.")
        return
    
    # Get session config
    session_config = get_session_config(args.config)
    
    # Log multi-session status
    log_session_status(args.config)
    
    # Optional: Log market status
    if is_market_open(session_config):
        logger.info("Market is currently OPEN")
    else:
        logger.info("Market is currently CLOSED")
        logger.info("  (Session will start engines anyway. Manual timing control is up to the user.)")
    
    # Start engines based on layout choice
    exit_code = 0
    
    if args.layout == "single":
        # Single-process mode (current/default behavior)
        logger.info("Using single-process layout (default)")
        try:
            proc = start_engines_subprocess(args.mode, args.config)
        except Exception as exc:
            logger.error("Failed to start engines: %s", exc)
            sys.exit(1)
        
        # Monitor single process
        exit_code = monitor_engines(proc)
        
    elif args.layout == "multi":
        # Multi-process mode (new architecture)
        logger.info("Using multi-process layout (one process per engine)")
        try:
            processes = start_multi_process_engines(args.mode, args.config)
            if not processes:
                logger.error("Failed to start engines in multi-process mode")
                sys.exit(1)
        except Exception as exc:
            logger.error("Failed to start engines: %s", exc)
            sys.exit(1)
        
        # Monitor multiple processes
        exit_code = monitor_multi_process_engines(processes)
    
    else:
        logger.error("Unknown layout: %s", args.layout)
        sys.exit(1)
    
    # Run EOD pipeline
    run_eod_pipeline(
        args.config,
        args.mode,
        run_analytics_flag=not args.no_analytics,
        run_backtests=not args.no_backtest,
    )
    
    # Exit with same code as engines
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
