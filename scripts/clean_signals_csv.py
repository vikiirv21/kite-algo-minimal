#!/usr/bin/env python3
"""
Script to clean up and verify existing signals.csv file.

This script:
1. Reads the existing signals.csv
2. Normalizes all signal values using normalize_signal_for_csv()
3. Writes a cleaned version
4. Reports statistics on what was cleaned
"""

from __future__ import annotations

import sys
import csv
import os
from pathlib import Path
from collections import Counter

# Add project root to path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from analytics.trade_recorder import normalize_signal_for_csv


def clean_signals_csv(csv_path: str, dry_run: bool = True) -> dict:
    """
    Clean up signals.csv by normalizing all signal values.
    
    Args:
        csv_path: Path to signals.csv file
        dry_run: If True, don't write changes, just report
        
    Returns:
        Statistics dictionary
    """
    if not os.path.exists(csv_path):
        print(f"Error: File not found: {csv_path}")
        return {}
    
    # Read all rows
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames
    
    print(f"Read {len(rows)} rows from {csv_path}")
    
    # Track changes
    original_signals = []
    normalized_signals = []
    changes = []
    
    # Process each row
    for i, row in enumerate(rows):
        original_signal = row.get('signal', '')
        normalized_signal = normalize_signal_for_csv(original_signal)
        
        original_signals.append(original_signal)
        normalized_signals.append(normalized_signal)
        
        if original_signal != normalized_signal:
            changes.append({
                'row': i,
                'timestamp': row.get('timestamp', ''),
                'original': original_signal,
                'normalized': normalized_signal
            })
        
        # Update the row
        row['signal'] = normalized_signal
    
    # Statistics
    original_counts = Counter(original_signals)
    normalized_counts = Counter(normalized_signals)
    
    stats = {
        'total_rows': len(rows),
        'changes': len(changes),
        'original_counts': original_counts,
        'normalized_counts': normalized_counts,
        'changes_detail': changes
    }
    
    # Report
    print("\n" + "=" * 80)
    print("ORIGINAL SIGNAL VALUES")
    print("=" * 80)
    for signal, count in original_counts.most_common():
        print(f"  {signal!r:30s} : {count:6d}")
    
    print("\n" + "=" * 80)
    print("NORMALIZED SIGNAL VALUES")
    print("=" * 80)
    for signal, count in normalized_counts.most_common():
        print(f"  {signal!r:30s} : {count:6d}")
    
    if changes:
        print("\n" + "=" * 80)
        print(f"CHANGES MADE: {len(changes)} rows")
        print("=" * 80)
        for change in changes[:10]:  # Show first 10
            print(f"  Row {change['row']}: {change['original']!r} -> {change['normalized']!r}")
        if len(changes) > 10:
            print(f"  ... and {len(changes) - 10} more")
    else:
        print("\n✓ No changes needed - all signals already normalized!")
    
    # Write cleaned version
    if not dry_run and changes:
        backup_path = csv_path + '.backup'
        print(f"\nCreating backup: {backup_path}")
        os.rename(csv_path, backup_path)
        
        print(f"Writing cleaned version to: {csv_path}")
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        print("✓ File cleaned successfully!")
    elif dry_run:
        print("\n(DRY RUN - no changes written)")
    
    return stats


def verify_signals_csv(csv_path: str) -> bool:
    """
    Verify that signals.csv only contains valid signal values.
    
    Args:
        csv_path: Path to signals.csv file
        
    Returns:
        True if all signals are valid, False otherwise
    """
    if not os.path.exists(csv_path):
        print(f"Error: File not found: {csv_path}")
        return False
    
    print("\n" + "=" * 80)
    print("VERIFICATION")
    print("=" * 80)
    
    valid_signals = {'BUY', 'SELL', 'HOLD', 'UNKNOWN'}
    invalid_rows = []
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            signal = row.get('signal', '')
            if signal not in valid_signals:
                invalid_rows.append({
                    'row': i,
                    'signal': signal,
                    'timestamp': row.get('timestamp', '')
                })
    
    if invalid_rows:
        print(f"✗ Found {len(invalid_rows)} rows with invalid signals:")
        for item in invalid_rows[:10]:
            print(f"  Row {item['row']}: {item['signal']!r}")
        if len(invalid_rows) > 10:
            print(f"  ... and {len(invalid_rows) - 10} more")
        return False
    else:
        print("✓ All signals are valid (BUY, SELL, HOLD, UNKNOWN)")
        return True


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Clean and verify signals.csv')
    parser.add_argument(
        '--csv-path',
        default='artifacts/signals.csv',
        help='Path to signals.csv file (default: artifacts/signals.csv)'
    )
    parser.add_argument(
        '--no-dry-run',
        action='store_true',
        help='Actually write changes (default is dry-run)'
    )
    
    args = parser.parse_args()
    
    # Resolve path
    csv_path = Path(args.csv_path)
    if not csv_path.is_absolute():
        csv_path = BASE_DIR / csv_path
    
    print(f"Processing: {csv_path}")
    print(f"Mode: {'WRITE' if args.no_dry_run else 'DRY RUN'}")
    print()
    
    # Clean
    stats = clean_signals_csv(str(csv_path), dry_run=not args.no_dry_run)
    
    # Verify
    is_valid = verify_signals_csv(str(csv_path))
    
    if is_valid:
        print("\n✓ SUCCESS: signals.csv is clean")
        return 0
    else:
        print("\n✗ FAILURE: signals.csv has invalid values")
        return 1


if __name__ == '__main__':
    sys.exit(main())
