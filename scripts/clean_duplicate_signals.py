"""Clean duplicate signals from the SQLite signal database.

This script removes duplicate signal entries, keeping only one signal per
(symboldirection, market_data_time, strategy, version, data versions) tuple.

The duplicates arise when the same strategy generates the same signal across
multiple shadow runs, producing different signal_ids due to event_time in
the hash. After fixing deterministic_signal_id to exclude event_time, we
need to deduplicate the existing data.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path


@dataclass(slots=True)
class SignalRecord:
    signal_id: str
    symbol: str
    strategy_name: str
    strategy_version: str
    direction: int
    market_data_time: str
    event_time: str
    data_source_version: str
    as_of_version: str
    payload: str


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _dedup_key(row: SignalRecord) -> tuple:
    """Key for deduplication: everything except event_time and signal_id."""
    return (
        row.symbol,
        row.direction,
        row.market_data_time,
        row.strategy_name,
        row.strategy_version,
        row.data_source_version,
        row.as_of_version,
    )


def load_signals(db_path: Path) -> list[SignalRecord]:
    """Load all signals from the database."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM signals ORDER BY event_time ASC").fetchall()
    conn.close()

    records = []
    for row in rows:
        records.append(SignalRecord(
            signal_id=row["signal_id"],
            symbol=row["symbol"],
            strategy_name=row["strategy_name"],
            strategy_version=row["strategy_version"],
            direction=row["direction"],
            market_data_time=row["market_data_time"],
            event_time=row["event_time"],
            data_source_version=row["data_source_version"],
            as_of_version=row["as_of_version"],
            payload=row["payload"],
        ))
    return records


def find_duplicates(records: list[SignalRecord]) -> dict[tuple, list[SignalRecord]]:
    """Group signals by deduplication key, return only groups with duplicates."""
    groups: dict[tuple, list[SignalRecord]] = defaultdict(list)
    for record in records:
        key = _dedup_key(record)
        groups[key].append(record)

    return {k: v for k, v in groups.items() if len(v) > 1}


def clean_duplicates(db_path: Path, dry_run: bool = True) -> tuple[int, int]:
    """Remove duplicate signals, keeping the first (earliest event_time) entry.

    Returns (signals_removed, signals_kept).
    """
    records = load_signals(db_path)
    duplicates = find_duplicates(records)

    if not duplicates:
        print("No duplicate signals found.")
        return (0, len(records))

    total_to_remove = sum(len(group) - 1 for group in duplicates.values())
    print(f"Found {len(duplicates)} groups of duplicates ({total_to_remove} signals to remove)")

    for key, group in sorted(duplicates.items()):
        print(f"\n  Duplicate group: {key[0]} {['SELL', 'HOLD', 'BUY'][key[1]+1]} @ {key[2]}")
        print(f"    Strategy: {key[3]} v{key[4]}")
        for i, rec in enumerate(group):
            marker = "KEEP" if i == 0 else "REMOVE"
            print(f"    [{marker}] signal_id={rec.signal_id[:12]}... event_time={rec.event_time}")

    if dry_run:
        print(f"\n[Dry run] Would remove {total_to_remove} duplicate signals.")
        return (0, len(records))

    # Remove duplicates, keeping the first (earliest event_time) entry
    conn = sqlite3.connect(str(db_path))
    removed_count = 0
    for key, group in duplicates.items():
        # Keep the first entry, remove the rest
        to_remove = [rec.signal_id for rec in group[1:]]
        placeholders = ", ".join("?" * len(to_remove))
        conn.execute(f"DELETE FROM signals WHERE signal_id IN ({placeholders})", to_remove)
        removed_count += len(to_remove)

        # Also clean up related evaluation_tasks and signal_evaluations
        conn.execute(f"DELETE FROM evaluation_tasks WHERE signal_id IN ({placeholders})", to_remove)
        conn.execute(f"DELETE FROM signal_evaluations WHERE signal_id IN ({placeholders})", to_remove)

    conn.commit()
    conn.close()

    print(f"\nRemoved {removed_count} duplicate signals (and their evaluations).")
    return (removed_count, len(records) - removed_count)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Clean duplicate signals from database")
    parser.add_argument("--db", type=Path, default=Path("reports/dashboard/signals.db"),
                        help="Path to signals.db")
    parser.add_argument("--execute", action="store_true",
                        help="Actually delete duplicates (default is dry-run)")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"Database not found: {args.db}")
        sys.exit(1)

    print(f"Database: {args.db}")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY RUN'}")
    print("=" * 60)

    removed, kept = clean_duplicates(args.db, dry_run=not args.execute)
    print("=" * 60)
    print(f"Done. Removed: {removed}, Kept: {kept}")


if __name__ == "__main__":
    main()
