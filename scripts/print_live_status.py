"""
Live Readiness Status CLI.

Prints a human-readable summary of the LIVE trading configuration and readiness.

Usage:
    python -m scripts.print_live_status --config configs/live.yaml

This script:
- Loads config via core.config.load_config
- Prints config summary (mode, dry_run, guardian, risk_engine, capital)
- Fetches broker funds via KiteBroker.get_live_capital()
- Lists enabled strategies from StrategyEngineV2 config
- Does NOT start any engines or place any orders
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.config import load_config
from core.capital_provider import create_capital_provider
from broker.auth import make_kite_client_from_env, token_is_valid

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]


def _safe_get(d: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely traverse nested dict keys."""
    val = d
    for k in keys:
        if not isinstance(val, dict):
            return default
        val = val.get(k, default)
        if val is None:
            return default
    return val


def _get_enabled_strategies(cfg_raw: Dict[str, Any]) -> List[str]:
    """Extract list of enabled strategy IDs from strategy_engine.strategies_v2."""
    strategies_v2 = _safe_get(cfg_raw, "strategy_engine", "strategies_v2", default=[])
    if not isinstance(strategies_v2, list):
        return []
    enabled = []
    for s in strategies_v2:
        if isinstance(s, dict) and s.get("enabled", True):
            sid = s.get("id")
            if sid:
                enabled.append(str(sid))
    return enabled


def _check_broker_token() -> Tuple[bool, str]:
    """
    Check if Kite broker token is valid.
    
    Returns: (token_ok, user_id)
    """
    try:
        kite = make_kite_client_from_env()
        if token_is_valid(kite):
            profile = kite.profile()
            user_id = profile.get("user_id") or profile.get("USER_ID") or "unknown"
            return True, str(user_id)
        else:
            return False, ""
    except Exception as exc:
        logger.debug("Token check failed: %s", exc)
        return False, f"ERROR: {exc}"


def _fetch_broker_capital() -> Dict[str, Any]:
    """
    Fetch live capital from Kite broker.
    
    Returns dict with:
        - available: float
        - net: float
        - cash: float
        - utilized: float
        - error: str (if any)
    """
    result = {
        "available": 0.0,
        "net": 0.0,
        "cash": 0.0,
        "utilized": 0.0,
        "error": None,
    }
    try:
        from broker.kite_bridge import KiteBroker
        broker = KiteBroker({}, logger_instance=logger)
        if not broker.ensure_logged_in():
            result["error"] = "Not logged in to Kite"
            return result
        funds = broker.get_live_capital()
        result["available"] = float(funds.get("available", 0.0))
        result["net"] = float(funds.get("net", 0.0))
        result["cash"] = float(funds.get("cash", 0.0))
        result["utilized"] = float(funds.get("utilized", 0.0))
    except Exception as exc:
        result["error"] = str(exc)
        logger.debug("Failed to fetch broker capital: %s", exc)
    return result


def print_status(config_path: str) -> None:
    """Load config and print live readiness status."""
    print("=" * 60)
    print("LIVE READINESS STATUS")
    print("=" * 60)
    
    # Load config
    try:
        cfg = load_config(config_path)
        raw = cfg.raw
    except Exception as exc:
        print(f"ERROR: Failed to load config: {exc}")
        return
    
    # Basic config info
    print(f"Config file      : {config_path}")
    
    trading = raw.get("trading", {})
    execution = raw.get("execution", {})
    guardian = raw.get("guardian", {})
    risk_engine_cfg = raw.get("risk_engine", {})
    reconciliation = raw.get("reconciliation", {})
    
    mode = trading.get("mode", "paper")
    dry_run = execution.get("dry_run", True)
    engine_type = execution.get("engine", "v3")
    
    print(f"trading.mode     : {mode}")
    print(f"execution.engine : {engine_type}")
    print(f"execution.dry_run: {dry_run}")
    print(f"guardian.enabled : {guardian.get('enabled', False)}")
    print(f"risk_engine.enabled : {risk_engine_cfg.get('enabled', False)}")
    print(f"reconciliation.enabled: {reconciliation.get('enabled', False)}")
    print()
    
    # Broker check
    print("Broker:")
    token_ok, user_id = _check_broker_token()
    print(f"  user_id : {user_id if user_id else 'N/A'}")
    print(f"  token_ok: {token_ok}")
    print()
    
    # Capital
    print("Capital:")
    config_capital = float(trading.get("live_capital", trading.get("paper_capital", 500000)))
    print(f"  config.live_capital      : {config_capital:.2f}")
    
    if token_ok:
        try:
            provider = create_capital_provider(mode="LIVE", config_capital=config_capital)
            effective = provider.get_available_capital()
            source = getattr(provider, "capital_source", "config")
            if source == "broker":
                print("  source                   : broker")
                print(f"  broker.effective_capital : {effective:.2f}")
            else:
                err = getattr(provider, "last_error", "")
                print("  source                   : fallback_config")
                print(f"  config.effective_capital : {effective:.2f}")
                if err:
                    print(f"  last_error               : {err}")
        except Exception as exc:
            print(f"  source                   : ERROR ({exc})")
    else:
        print("  source                   : N/A (token not valid)")
        print("  broker.net               : N/A")
    print()
    
    # Strategies
    print("Strategies (StrategyEngineV2):")
    strategy_cfg = raw.get("strategy_engine", {})
    primary_id = strategy_cfg.get("primary_strategy_id", "")
    print(f"  primary_strategy_id      : {primary_id or 'N/A'}")
    enabled_strategies = _get_enabled_strategies(raw)
    print(f"  strategies_v2.enabled    : {enabled_strategies if enabled_strategies else '[]'}")
    print()
    
    # Regime engine
    regime_cfg = raw.get("regime_engine", {})
    print("Regime engine:")
    print(f"  enabled: {regime_cfg.get('enabled', False)}")
    print()
    
    # Portfolio engine
    portfolio_cfg = raw.get("portfolio", {})
    print("Portfolio engine:")
    print(f"  max_leverage         : {portfolio_cfg.get('max_leverage', 'N/A')}")
    print(f"  max_exposure_pct     : {portfolio_cfg.get('max_exposure_pct', 'N/A')}")
    print(f"  max_risk_per_trade   : {portfolio_cfg.get('max_risk_per_trade_pct', 'N/A')}")
    print()
    
    print("NOTE: This is only a status check. No orders are placed.")
    print("=" * 60)


def main() -> int:
    """Main entry point for the live status CLI."""
    parser = argparse.ArgumentParser(
        description="Print LIVE trading readiness status."
    )
    parser.add_argument(
        "--config",
        default="configs/live.yaml",
        help="Path to YAML config file (default: configs/live.yaml)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    
    args = parser.parse_args()
    
    # Setup basic logging
    log_level = logging.DEBUG if args.debug else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    try:
        print_status(args.config)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
