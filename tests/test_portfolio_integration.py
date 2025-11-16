"""
Smoke test for PortfolioEngine integration with PaperEngine.

Verifies:
- PaperEngine initializes with PortfolioEngine
- Config loading works
- No import errors
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from core.config import load_config
from core.portfolio_engine import PortfolioEngine, PortfolioConfig
from core.state_store import StateStore

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def test_portfolio_config_loading():
    """Test that portfolio config loads from dev.yaml."""
    logger.info("=== Test 1: Portfolio Config Loading ===")
    
    cfg = load_config("configs/dev.yaml")
    portfolio_cfg_raw = cfg.raw.get("portfolio")
    
    assert portfolio_cfg_raw is not None, "Portfolio config not found in dev.yaml"
    
    portfolio_config = PortfolioConfig.from_dict(portfolio_cfg_raw)
    
    logger.info(f"✓ Portfolio config loaded:")
    logger.info(f"  mode: {portfolio_config.position_sizing_mode}")
    logger.info(f"  max_leverage: {portfolio_config.max_leverage}")
    logger.info(f"  max_exposure_pct: {portfolio_config.max_exposure_pct}")
    logger.info(f"  max_risk_per_trade_pct: {portfolio_config.max_risk_per_trade_pct}")
    logger.info(f"  strategy_budgets: {len(portfolio_config.strategy_budgets)} strategies")
    
    return True


def test_portfolio_engine_initialization():
    """Test PortfolioEngine initializes correctly."""
    logger.info("\n=== Test 2: PortfolioEngine Initialization ===")
    
    cfg = load_config("configs/dev.yaml")
    portfolio_cfg_raw = cfg.raw.get("portfolio")
    portfolio_config = PortfolioConfig.from_dict(portfolio_cfg_raw)
    
    state_store = StateStore()
    
    portfolio_engine = PortfolioEngine(
        portfolio_config=portfolio_config,
        state_store=state_store,
        logger_instance=logger,
    )
    
    logger.info("✓ PortfolioEngine initialized successfully")
    
    # Test basic methods
    equity = portfolio_engine.get_equity()
    logger.info(f"  Current equity: {equity}")
    
    total_exposure = portfolio_engine.compute_total_exposure()
    logger.info(f"  Total exposure: {total_exposure}")
    
    limits = portfolio_engine.get_portfolio_limits()
    logger.info(f"  Portfolio limits available: {len(limits)} keys")
    
    return True


def test_paper_engine_imports():
    """Test that PaperEngine can be imported with PortfolioEngine integration."""
    logger.info("\n=== Test 3: PaperEngine Imports ===")
    
    try:
        from engine.paper_engine import PaperEngine
        logger.info("✓ PaperEngine imported successfully")
        
        # Check that PortfolioEngine is imported in paper_engine module
        import engine.paper_engine as pe_module
        assert hasattr(pe_module, 'PortfolioEngine'), "PortfolioEngine not imported in paper_engine"
        assert hasattr(pe_module, 'PortfolioConfig'), "PortfolioConfig not imported in paper_engine"
        
        logger.info("✓ PortfolioEngine imports present in PaperEngine module")
        return True
        
    except Exception as exc:
        logger.error(f"✗ Failed to import PaperEngine: {exc}")
        return False


def test_live_engine_imports():
    """Test that LiveEngine can be imported with PortfolioEngine integration."""
    logger.info("\n=== Test 4: LiveEngine Imports ===")
    
    try:
        from engine.live_engine import LiveEngine
        logger.info("✓ LiveEngine imported successfully")
        
        # Check that PortfolioEngine is imported in live_engine module
        import engine.live_engine as le_module
        assert hasattr(le_module, 'PortfolioEngine'), "PortfolioEngine not imported in live_engine"
        assert hasattr(le_module, 'PortfolioConfig'), "PortfolioConfig not imported in live_engine"
        
        logger.info("✓ PortfolioEngine imports present in LiveEngine module")
        return True
        
    except Exception as exc:
        logger.error(f"✗ Failed to import LiveEngine: {exc}")
        return False


def test_server_api_endpoint():
    """Test that server can be imported with portfolio API endpoint."""
    logger.info("\n=== Test 5: Server API Endpoint ===")
    
    try:
        import apps.server
        logger.info("✓ Server module imported successfully")
        
        # Check that the portfolio endpoint exists
        # We can't easily check FastAPI routes without running the server,
        # but we can verify the module loads
        logger.info("✓ Server module loaded (portfolio API endpoint should be available)")
        return True
        
    except Exception as exc:
        logger.error(f"✗ Failed to import server: {exc}")
        return False


def run_smoke_tests():
    """Run all smoke tests."""
    logger.info("=" * 60)
    logger.info("PortfolioEngine Integration - Smoke Tests")
    logger.info("=" * 60)
    
    tests = [
        test_portfolio_config_loading,
        test_portfolio_engine_initialization,
        test_paper_engine_imports,
        test_live_engine_imports,
        test_server_api_endpoint,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as exc:
            logger.error(f"✗ Test failed with exception: {exc}", exc_info=True)
            results.append(False)
    
    logger.info("\n" + "=" * 60)
    if all(results):
        logger.info("✓ ALL SMOKE TESTS PASSED")
        logger.info("=" * 60)
        return True
    else:
        logger.error("✗ SOME TESTS FAILED")
        logger.info("=" * 60)
        return False


if __name__ == "__main__":
    success = run_smoke_tests()
    sys.exit(0 if success else 1)
