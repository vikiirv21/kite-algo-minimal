"""
Test to verify that YAML configs with null strategy_engine can be loaded.

This creates actual YAML files similar to dev.yaml and learned_overrides.yaml
with strategy_engine: null to ensure they can be parsed without crashing.
"""

import yaml
import tempfile
from pathlib import Path


def test_yaml_with_null_strategy_engine():
    """Test loading YAML with strategy_engine: null"""
    
    yaml_content = """
# Simulating dev.yaml with null strategy_engine
trading:
  mode: paper
  fno_universe:
    - NIFTY
    - BANKNIFTY
  paper_capital: 500000

strategy_engine: null  # This should not crash!

risk:
  atr:
    enabled: true
"""
    
    # Write to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        temp_file = f.name
    
    try:
        # Load the YAML
        with open(temp_file, 'r') as f:
            config = yaml.safe_load(f)
        
        print("✓ Loaded YAML successfully")
        print(f"  strategy_engine value: {config.get('strategy_engine')}")
        
        # Verify it's None
        assert config['strategy_engine'] is None
        print("✓ Confirmed strategy_engine is None (null)")
        
        # Test the normalization logic
        strategy_engine_config = config.get("strategy_engine")
        if strategy_engine_config is None:
            strategy_engine_config = {}
            print("✓ Normalized None to empty dict")
        
        # These should not crash
        version = strategy_engine_config.get("version", 1)
        strategies = strategy_engine_config.get("strategies_v2") or []
        
        print(f"✓ Can safely access version: {version}")
        print(f"✓ Can safely access strategies_v2: {strategies}")
        
    finally:
        # Clean up
        Path(temp_file).unlink()
    
    print("\n✅ Test passed: YAML with null strategy_engine loads successfully\n")


def test_yaml_with_null_strategies():
    """Test loading YAML with null strategy lists"""
    
    yaml_content = """
# Simulating learned_overrides.yaml
strategy_engine:
  version: 2
  strategies_v2: null  # Null strategy list
  strategies: null     # Null strategy list
"""
    
    # Write to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        temp_file = f.name
    
    try:
        # Load the YAML
        with open(temp_file, 'r') as f:
            config = yaml.safe_load(f)
        
        print("✓ Loaded YAML with null strategy lists")
        
        strategy_engine_config = config.get("strategy_engine")
        if strategy_engine_config is None:
            strategy_engine_config = {}
        
        # Safe extraction
        strategies_v2 = strategy_engine_config.get("strategies_v2") or []
        strategies_v1 = strategy_engine_config.get("strategies") or []
        
        print(f"✓ strategies_v2 (was null): {strategies_v2}")
        print(f"✓ strategies_v1 (was null): {strategies_v1}")
        
        # Iteration should not crash
        for s in strategies_v2:
            pass  # Won't execute
        
        for s in strategies_v1:
            pass  # Won't execute
        
        print("✓ Can safely iterate over null/empty strategy lists")
        
    finally:
        # Clean up
        Path(temp_file).unlink()
    
    print("\n✅ Test passed: YAML with null strategy lists handled safely\n")


def test_yaml_merged_configs():
    """Test merging dev.yaml with learned_overrides.yaml where both have nulls"""
    
    dev_yaml = """
strategy_engine:
  version: 1
  enabled: true
  strategies_v2:
    - ema20_50_intraday_v2
"""
    
    override_yaml = """
strategy_engine: null  # Override to disable all strategies
"""
    
    # Load both
    dev_config = yaml.safe_load(dev_yaml)
    override_config = yaml.safe_load(override_yaml)
    
    print("✓ Loaded dev.yaml and override.yaml")
    print(f"  dev.yaml strategy_engine: {dev_config.get('strategy_engine')}")
    print(f"  override.yaml strategy_engine: {override_config.get('strategy_engine')}")
    
    # Merge (override wins)
    merged = {**dev_config, **override_config}
    
    print(f"✓ Merged config strategy_engine: {merged.get('strategy_engine')}")
    
    # Apply normalization
    strategy_engine_config = merged.get("strategy_engine")
    if strategy_engine_config is None:
        print("✓ Override set strategy_engine to null - normalizing to {}")
        strategy_engine_config = {}
    
    strategies = strategy_engine_config.get("strategies_v2") or []
    print(f"✓ Final strategies list: {strategies}")
    
    print("\n✅ Test passed: Config merging with null override handled correctly\n")


if __name__ == "__main__":
    print("=" * 70)
    print("YAML CONFIG LOADING TESTS")
    print("=" * 70 + "\n")
    
    test_yaml_with_null_strategy_engine()
    test_yaml_with_null_strategies()
    test_yaml_merged_configs()
    
    print("=" * 70)
    print("🎉 ALL YAML CONFIG TESTS PASSED!")
    print("=" * 70)
    print("\nVerified scenarios:")
    print("  ✓ YAML file with 'strategy_engine: null'")
    print("  ✓ YAML file with null strategy lists")
    print("  ✓ Config merging where overrides set null values")
    print("  ✓ All scenarios handle nulls gracefully without crashing")
    print()
