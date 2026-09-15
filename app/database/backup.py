"""Local database backup (Section 82). Uses SQLite's own online backup API so
a backup taken while the application is running (WAL mode, possibly mid-
transaction) is still consistent -- a plain file copy of a WAL-mode database
can miss data still sitting in the -wal file.

Run on a schedule via the OS rather than an in-process timer, matching the
systemd-based deployment already described in Section 81/README:

    python -m app.database.backup

A systemd timer unit (or cron) invoking that command daily is the "at
minimum: daily backup" from Section 82; run it more often for "periodic
backup + daily backup" if the factory wants tighter RPO.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def backup_database(source_path: str | Path, backup_dir: str | Path) -> Path:
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Database not found: {source}")

    backup_dir_path = Path(backup_dir)
    backup_dir_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    destination = backup_dir_path / f"{source.stem}_{timestamp}{source.suffix}"

    source_conn = sqlite3.connect(str(source))
    dest_conn = sqlite3.connect(str(destination))
    try:
        source_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        source_conn.close()

    return destination


def main() -> int:
    from app.config.loader import load_config

    config = load_config()
    destination = backup_database(config.database.path, config.database.backup_dir)
    print(f"Backed up database to {destination}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main())
