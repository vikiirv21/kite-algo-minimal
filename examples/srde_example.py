#!/usr/bin/env python
"""
Example: Using SRDE (Strategy Real-Time Diagnostics Engine)

This example demonstrates how to:
1. Create diagnostic records programmatically
2. Store them in JSONL format
3. Retrieve them via the diagnostics API

This can be run standalone without starting the full trading engine.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.diagnostics import (
    append_diagnostic,
    load_diagnostics,
    build_diagnostic_record,
)


def simulate_strategy_decisions():
    """Simulate a series of strategy decisions with diagnostics."""
    
    print("=" * 60)
    print("SRDE Example: Simulating Strategy Decisions")
    print("=" * 60)
    
    symbol = "NIFTY"
    strategy = "EMA_20_50_DEMO"
    
    # Simulate different market scenarios
    scenarios = [
        {
            "price": 18500.0,
            "ema20": 18480.0,
            "ema50": 18450.0,
            "decision": "BUY",
            "reason": "Strong uptrend: EMA20 > EMA50, price above both EMAs",
            "confidence": 0.85,
            "regime": "trend",
            "risk_block": "none",
        },
        {
            "price": 18520.0,
            "ema20": 18495.0,
            "ema50": 18460.0,
            "decision": "HOLD",
            "reason": "Position already open, waiting for exit signal",
            "confidence": 0.7,
            "regime": "trend",
            "risk_block": "none",
        },
        {
            "price": 18505.0,
            "ema20": 18490.0,
            "ema50": 18485.0,
            "decision": "HOLD",
            "reason": "EMAs converging, low trend strength",
            "confidence": 0.3,
            "regime": "compression",
            "risk_block": "none",
        },
        {
            "price": 18495.0,
            "ema20": 18485.0,
            "ema50": 18490.0,
            "decision": "SELL",
            "reason": "EMA bearish crossover detected",
            "confidence": 0.8,
            "regime": "trend",
            "risk_block": "none",
        },
        {
            "price": 18475.0,
            "ema20": 18470.0,
            "ema50": 18480.0,
            "decision": "HOLD",
            "reason": "Max daily loss limit reached",
            "confidence": 0.0,
            "regime": "trend",
            "risk_block": "max_loss",
        },
    ]
    
    print(f"\nSymbol: {symbol}")
    print(f"Strategy: {strategy}")
    print(f"\nSimulating {len(scenarios)} decisions...")
    print()
    
    # Create and store diagnostic records
    for i, scenario in enumerate(scenarios, 1):
        # Calculate trend strength
        ema20 = scenario["ema20"]
        ema50 = scenario["ema50"]
        trend_strength = abs((ema20 - ema50) / ema50) if ema50 != 0 else 0.0
        
        # Build diagnostic record
        record = build_diagnostic_record(
            price=scenario["price"],
            decision=scenario["decision"],
            reason=scenario["reason"],
            confidence=scenario["confidence"],
            ema20=ema20,
            ema50=ema50,
            trend_strength=trend_strength,
            regime=scenario["regime"],
            risk_block=scenario["risk_block"],
            rsi14=65.0 + (i * 2),  # Simulated RSI
            atr14=50.0,  # Simulated ATR
        )
        
        # Append diagnostic
        result = append_diagnostic(symbol, strategy, record)
        
        # Display
        status = "✓" if result else "✗"
        print(f"{status} Decision {i}: {scenario['decision']:4s} | "
              f"Price: {scenario['price']:7.1f} | "
              f"Confidence: {scenario['confidence']:.2f} | "
              f"Risk: {scenario['risk_block']:8s}")
    
    print()
    print("=" * 60)
    print("Diagnostics stored successfully!")
    print("=" * 60)


def retrieve_diagnostics():
    """Retrieve and display stored diagnostics."""
    
    print("\n" + "=" * 60)
    print("Retrieving Stored Diagnostics")
    print("=" * 60)
    
    symbol = "NIFTY"
    strategy = "EMA_20_50_DEMO"
    
    # Load diagnostics
    diagnostics = load_diagnostics(symbol, strategy, limit=10)
    
    print(f"\nFound {len(diagnostics)} diagnostic record(s)")
    print()
    
    # Display each record
    for i, record in enumerate(diagnostics, 1):
        print(f"Record {i}:")
        print(f"  Timestamp:   {record.get('ts', 'N/A')}")
        print(f"  Price:       {record.get('price', 0):.2f}")
        print(f"  Decision:    {record.get('decision', 'N/A')}")
        print(f"  Confidence:  {record.get('confidence', 0):.2f}")
        print(f"  EMA 20:      {record.get('ema20', 0):.2f}")
        print(f"  EMA 50:      {record.get('ema50', 0):.2f}")
        print(f"  Trend Str:   {record.get('trend_strength', 0):.4f}")
        print(f"  Regime:      {record.get('regime', 'N/A')}")
        print(f"  Risk Block:  {record.get('risk_block', 'N/A')}")
        print(f"  Reason:      {record.get('reason', 'N/A')}")
        print()
    
    print("=" * 60)


def analyze_diagnostics():
    """Analyze diagnostic records to extract insights."""
    
    print("\n" + "=" * 60)
    print("Diagnostic Analysis")
    print("=" * 60)
    
    symbol = "NIFTY"
    strategy = "EMA_20_50_DEMO"
    
    diagnostics = load_diagnostics(symbol, strategy, limit=100)
    
    if not diagnostics:
        print("\nNo diagnostics found.")
        return
    
    # Count decisions
    decision_counts = {}
    risk_blocks = {}
    regimes = {}
    avg_confidence = 0.0
    
    for record in diagnostics:
        decision = record.get("decision", "UNKNOWN")
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
        
        risk = record.get("risk_block", "unknown")
        risk_blocks[risk] = risk_blocks.get(risk, 0) + 1
        
        regime = record.get("regime", "unknown")
        regimes[regime] = regimes.get(regime, 0) + 1
        
        avg_confidence += record.get("confidence", 0.0)
    
    avg_confidence /= len(diagnostics)
    
    print(f"\nTotal Records: {len(diagnostics)}")
    print()
    
    print("Decision Breakdown:")
    for decision, count in sorted(decision_counts.items()):
        pct = (count / len(diagnostics)) * 100
        print(f"  {decision:4s}: {count:3d} ({pct:5.1f}%)")
    print()
    
    print("Risk Block Breakdown:")
    for risk, count in sorted(risk_blocks.items()):
        pct = (count / len(diagnostics)) * 100
        print(f"  {risk:10s}: {count:3d} ({pct:5.1f}%)")
    print()
    
    print("Regime Breakdown:")
    for regime, count in sorted(regimes.items()):
        pct = (count / len(diagnostics)) * 100
        print(f"  {regime:12s}: {count:3d} ({pct:5.1f}%)")
    print()
    
    print(f"Average Confidence: {avg_confidence:.2f}")
    print()
    print("=" * 60)


def main():
    """Run the SRDE example."""
    print("\n" + "=" * 60)
    print("SRDE (Strategy Real-Time Diagnostics Engine)")
    print("Example Demonstration")
    print("=" * 60)
    
    # Simulate strategy decisions and store diagnostics
    simulate_strategy_decisions()
    
    # Retrieve and display diagnostics
    retrieve_diagnostics()
    
    # Analyze diagnostics
    analyze_diagnostics()
    
    print("\n" + "=" * 60)
    print("Example Complete!")
    print("=" * 60)
    print("\nDiagnostic files are stored at:")
    print("  artifacts/diagnostics/NIFTY/EMA_20_50_DEMO.jsonl")
    print()
    print("You can query these diagnostics via the dashboard API:")
    print("  GET /api/diagnostics/strategy?symbol=NIFTY&strategy=EMA_20_50_DEMO")
    print()
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
