"""Delete generated comics older than a chosen number of days."""
from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

from app.config import Settings


def cleanup(root: Path, older_than_days: int, dry_run: bool) -> int:
    cutoff = time.time() - older_than_days * 86400
    removed = 0
    if not root.exists():
        return 0
    for path in root.iterdir():
        if path.is_dir() and path.stat().st_mtime < cutoff:
            print(f"{'Would remove' if dry_run else 'Removing'} {path}")
            if not dry_run:
                shutil.rmtree(path)
            removed += 1
    return removed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7, help="Remove comics older than this")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    count = cleanup(settings.storage_dir / "comics", args.days, args.dry_run)
    print(f"Matched {count} comic workspace(s).")
