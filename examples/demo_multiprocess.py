#!/usr/bin/env python3
"""
Demonstration script for multi-process architecture.

This script demonstrates the difference between single-process and multi-process
layouts by showing the process structure.
"""

import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


def show_demo():
    """Show demonstration of both modes."""
    print("=" * 70)
    print("MULTI-PROCESS ARCHITECTURE DEMONSTRATION")
    print("=" * 70)
    print()
    
    print("This demonstration shows the two available layouts:")
    print()
    print("1. SINGLE-PROCESS (default):")
    print("   - All engines run in one Python process")
    print("   - Existing behavior, fully tested")
    print("   - Use: --layout single (or omit the flag)")
    print()
    print("2. MULTI-PROCESS (new):")
    print("   - Each engine runs in its own Python process")
    print("   - Better isolation and scalability")
    print("   - Use: --layout multi")
    print()
    print("=" * 70)
    print()
    
    # Show help for run_session
    print("📋 Session Orchestrator Help:")
    print("-" * 70)
    result = subprocess.run(
        [sys.executable, "-m", "scripts.run_session", "--help"],
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
    )
    print(result.stdout)
    
    print()
    print("=" * 70)
    print("📋 Individual Engine Help:")
    print("-" * 70)
    print()
    
    engines = [
        ("FnO Paper Engine", "apps.run_fno_paper"),
        ("Equity Paper Engine", "apps.run_equity_paper"),
        ("Options Paper Engine", "apps.run_options_paper"),
    ]
    
    for name, module in engines:
        print(f"🔹 {name}:")
        result = subprocess.run(
            [sys.executable, "-m", module, "--help"],
            capture_output=True,
            text=True,
            cwd=BASE_DIR,
        )
        for line in result.stdout.split("\n"):
            if line.strip():
                print(f"   {line}")
        print()
    
    print("=" * 70)
    print("🧪 Example Commands:")
    print("-" * 70)
    print()
    print("# Dry-run with single-process layout (default):")
    print("python -m scripts.run_session --mode paper --config configs/dev.yaml --dry-run")
    print()
    print("# Dry-run with multi-process layout:")
    print("python -m scripts.run_session --mode paper --config configs/dev.yaml --layout multi --dry-run")
    print()
    print("# Run individual FnO engine:")
    print("python -m apps.run_fno_paper --config configs/dev.yaml --mode paper")
    print()
    print("=" * 70)
    print()
    print("✅ For complete documentation, see docs/MULTIPROCESS_ARCHITECTURE.md")
    print()


def main():
    """Main entry point."""
    try:
        show_demo()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
