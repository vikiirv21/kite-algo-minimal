"""Tests for analytics/performance_v2.py"""

import sys
import json
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.performance_v2 import (
    load_orders,
    reconstruct_trades,
    compute_metrics,
    write_metrics,
    Trade,
)


def test_load_orders_empty():
    """Test loading orders from non-existent file"""
    orders = load_orders(Path("/tmp/nonexistent_orders.csv"))
    assert orders == []


def test_load_orders_with_data():
    """Test loading orders from CSV file"""
    # Create a temporary CSV file with test data
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("timestamp,symbol,side,quantity,price,status,profile,strategy,mode,parent_signal_timestamp\n")
        f.write("2025-11-17T10:00:00,NIFTY24DECFUT,BUY,50,24500.0,FILLED,INTRADAY,test_strategy,paper,2025-11-17T10:00:00\n")
        f.write("2025-11-17T10:05:00,NIFTY24DECFUT,SELL,50,24600.0,FILLED,INTRADAY,test_strategy,paper,2025-11-17T10:05:00\n")
        f.write("2025-11-17T10:10:00,NIFTY24DECFUT,BUY,25,24550.0,PENDING,INTRADAY,test_strategy,paper,2025-11-17T10:10:00\n")
        temp_path = Path(f.name)
    
    try:
        orders = load_orders(temp_path)
        # Should only load FILLED orders (2 out of 3)
        assert len(orders) == 2
        assert orders[0]["symbol"] == "NIFTY24DECFUT"
        assert orders[0]["side"] == "BUY"
        assert orders[1]["side"] == "SELL"
    finally:
        temp_path.unlink()


def test_reconstruct_trades_simple():
    """Test trade reconstruction with simple buy-sell"""
    orders = [
        {
            "timestamp": "2025-11-17T10:00:00",
            "symbol": "NIFTY24DECFUT",
            "side": "BUY",
            "quantity": "50",
            "price": "24500.0",
            "strategy": "test_strategy",
            "mode": "paper",
            "profile": "INTRADAY",
        },
        {
            "timestamp": "2025-11-17T10:05:00",
            "symbol": "NIFTY24DECFUT",
            "side": "SELL",
            "quantity": "50",
            "price": "24600.0",
            "strategy": "test_strategy",
            "mode": "paper",
            "profile": "INTRADAY",
        },
    ]
    
    trades = reconstruct_trades(orders)
    assert len(trades) == 1
    
    trade = trades[0]
    assert trade.symbol == "NIFTY24DECFUT"
    assert trade.strategy == "test_strategy"
    assert trade.side == "BUY"
    assert trade.qty == 50.0
    assert trade.entry_price == 24500.0
    assert trade.exit_price == 24600.0
    assert trade.pnl == (24600.0 - 24500.0) * 50.0  # 5000.0


def test_reconstruct_trades_partial_close():
    """Test partial position closing"""
    orders = [
        {
            "timestamp": "2025-11-17T10:00:00",
            "symbol": "NIFTY24DECFUT",
            "side": "BUY",
            "quantity": "100",
            "price": "24500.0",
            "strategy": "test_strategy",
            "mode": "paper",
            "profile": "INTRADAY",
        },
        {
            "timestamp": "2025-11-17T10:05:00",
            "symbol": "NIFTY24DECFUT",
            "side": "SELL",
            "quantity": "50",
            "price": "24600.0",
            "strategy": "test_strategy",
            "mode": "paper",
            "profile": "INTRADAY",
        },
        {
            "timestamp": "2025-11-17T10:10:00",
            "symbol": "NIFTY24DECFUT",
            "side": "SELL",
            "quantity": "50",
            "price": "24550.0",
            "strategy": "test_strategy",
            "mode": "paper",
            "profile": "INTRADAY",
        },
    ]
    
    trades = reconstruct_trades(orders)
    assert len(trades) == 2
    
    # First trade: 50@24500 -> 50@24600 = +5000
    assert trades[0].qty == 50.0
    assert trades[0].pnl == 5000.0
    
    # Second trade: 50@24500 -> 50@24550 = +2500
    assert trades[1].qty == 50.0
    assert trades[1].pnl == 2500.0


def test_reconstruct_trades_short():
    """Test short position reconstruction"""
    orders = [
        {
            "timestamp": "2025-11-17T10:00:00",
            "symbol": "NIFTY24DECFUT",
            "side": "SELL",
            "quantity": "50",
            "price": "24600.0",
            "strategy": "test_strategy",
            "mode": "paper",
            "profile": "INTRADAY",
        },
        {
            "timestamp": "2025-11-17T10:05:00",
            "symbol": "NIFTY24DECFUT",
            "side": "BUY",
            "quantity": "50",
            "price": "24500.0",
            "strategy": "test_strategy",
            "mode": "paper",
            "profile": "INTRADAY",
        },
    ]
    
    trades = reconstruct_trades(orders)
    assert len(trades) == 1
    
    trade = trades[0]
    assert trade.side == "SELL"
    assert trade.pnl == (24600.0 - 24500.0) * 50.0  # 5000.0


def test_compute_metrics_empty():
    """Test metrics computation with no trades"""
    metrics = compute_metrics([], starting_capital=100000.0)
    
    assert metrics["equity"]["starting_capital"] == 100000.0
    assert metrics["equity"]["current_equity"] == 100000.0
    assert metrics["equity"]["realized_pnl"] == 0.0
    assert metrics["overall"]["total_trades"] == 0
    assert metrics["overall"]["win_rate"] == 0.0
    assert metrics["per_strategy"] == {}
    assert metrics["per_symbol"] == {}


def test_compute_metrics_with_trades():
    """Test metrics computation with trades"""
    trades = [
        Trade(
            symbol="NIFTY24DECFUT",
            strategy="strategy_a",
            side="BUY",
            qty=50.0,
            entry_price=24500.0,
            exit_price=24600.0,
            pnl=5000.0,
            open_ts="2025-11-17T10:00:00",
            close_ts="2025-11-17T10:05:00",
            mode="paper",
            profile="INTRADAY",
        ),
        Trade(
            symbol="NIFTY24DECFUT",
            strategy="strategy_a",
            side="BUY",
            qty=50.0,
            entry_price=24500.0,
            exit_price=24450.0,
            pnl=-2500.0,
            open_ts="2025-11-17T10:10:00",
            close_ts="2025-11-17T10:15:00",
            mode="paper",
            profile="INTRADAY",
        ),
        Trade(
            symbol="BANKNIFTY24DECFUT",
            strategy="strategy_b",
            side="SELL",
            qty=15.0,
            entry_price=51000.0,
            exit_price=50900.0,
            pnl=1500.0,
            open_ts="2025-11-17T10:20:00",
            close_ts="2025-11-17T10:25:00",
            mode="paper",
            profile="INTRADAY",
        ),
    ]
    
    metrics = compute_metrics(trades, starting_capital=500000.0)
    
    # Check equity
    assert metrics["equity"]["starting_capital"] == 500000.0
    assert metrics["equity"]["realized_pnl"] == 4000.0  # 5000 - 2500 + 1500
    assert metrics["equity"]["current_equity"] == 504000.0
    
    # Check overall metrics
    assert metrics["overall"]["total_trades"] == 3
    assert metrics["overall"]["win_trades"] == 2
    assert metrics["overall"]["loss_trades"] == 1
    assert metrics["overall"]["win_rate"] == (2 / 3 * 100)
    assert metrics["overall"]["gross_profit"] == 6500.0  # 5000 + 1500
    assert metrics["overall"]["gross_loss"] == 2500.0
    assert metrics["overall"]["net_pnl"] == 4000.0
    
    # Check per-strategy
    assert "strategy_a" in metrics["per_strategy"]
    assert metrics["per_strategy"]["strategy_a"]["trades"] == 2
    assert metrics["per_strategy"]["strategy_a"]["net_pnl"] == 2500.0  # 5000 - 2500
    assert metrics["per_strategy"]["strategy_a"]["win_rate"] == 50.0  # 1 win, 1 loss
    
    assert "strategy_b" in metrics["per_strategy"]
    assert metrics["per_strategy"]["strategy_b"]["trades"] == 1
    assert metrics["per_strategy"]["strategy_b"]["net_pnl"] == 1500.0
    
    # Check per-symbol
    assert "NIFTY24DECFUT" in metrics["per_symbol"]
    assert metrics["per_symbol"]["NIFTY24DECFUT"]["trades"] == 2
    assert metrics["per_symbol"]["NIFTY24DECFUT"]["net_pnl"] == 2500.0
    
    assert "BANKNIFTY24DECFUT" in metrics["per_symbol"]
    assert metrics["per_symbol"]["BANKNIFTY24DECFUT"]["trades"] == 1
    assert metrics["per_symbol"]["BANKNIFTY24DECFUT"]["net_pnl"] == 1500.0


def test_write_metrics_integration():
    """Test complete pipeline: orders -> trades -> metrics -> JSON"""
    # Create temporary orders file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("timestamp,symbol,side,quantity,price,status,profile,strategy,mode,parent_signal_timestamp\n")
        f.write("2025-11-17T10:00:00,NIFTY24DECFUT,BUY,50,24500.0,FILLED,INTRADAY,test_strategy,paper,\n")
        f.write("2025-11-17T10:05:00,NIFTY24DECFUT,SELL,50,24600.0,FILLED,INTRADAY,test_strategy,paper,\n")
        orders_path = Path(f.name)
    
    # Create temporary output file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        output_path = Path(f.name)
    
    try:
        # Write metrics
        write_metrics(orders_path, None, output_path, starting_capital=500000.0)
        
        # Verify output file exists and contains valid JSON
        assert output_path.exists()
        
        with output_path.open("r", encoding="utf-8") as f:
            metrics = json.load(f)
        
        # Verify structure
        assert "equity" in metrics
        assert "overall" in metrics
        assert "per_strategy" in metrics
        assert "per_symbol" in metrics
        
        # Verify values
        assert metrics["equity"]["starting_capital"] == 500000.0
        assert metrics["overall"]["total_trades"] == 1
        assert metrics["overall"]["net_pnl"] == 5000.0
        assert "test_strategy" in metrics["per_strategy"]
        
    finally:
        orders_path.unlink()
        output_path.unlink()


if __name__ == "__main__":
    # Run tests
    print("Running performance_v2 tests...")
    
    test_load_orders_empty()
    print("✓ test_load_orders_empty")
    
    test_load_orders_with_data()
    print("✓ test_load_orders_with_data")
    
    test_reconstruct_trades_simple()
    print("✓ test_reconstruct_trades_simple")
    
    test_reconstruct_trades_partial_close()
    print("✓ test_reconstruct_trades_partial_close")
    
    test_reconstruct_trades_short()
    print("✓ test_reconstruct_trades_short")
    
    test_compute_metrics_empty()
    print("✓ test_compute_metrics_empty")
    
    test_compute_metrics_with_trades()
    print("✓ test_compute_metrics_with_trades")
    
    test_write_metrics_integration()
    print("✓ test_write_metrics_integration")
    
    print("\nAll tests passed! ✓")
