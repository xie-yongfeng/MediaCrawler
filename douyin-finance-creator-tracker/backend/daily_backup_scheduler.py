from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path


def backup_database(database_path: Path, backup_dir: Path, backup_date: datetime | None = None) -> Path:
    """Create a consistent SQLite backup named for the day it was made."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    date_text = (backup_date or datetime.now()).strftime("%Y-%m-%d")
    backup_path = backup_dir / f"fund_insight_{date_text}.db"
    temporary_path = backup_path.with_suffix(".tmp")

    try:
        with sqlite3.connect(database_path) as source, sqlite3.connect(temporary_path) as destination:
            source.backup(destination)
        temporary_path.replace(backup_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return backup_path


def start_daily_backup_scheduler(database_path: Path, backup_dir: Path) -> None:
    """Start a daemon that backs up the database once per day at local midnight."""
    def run() -> None:
        while True:
            now = datetime.now()
            next_run = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            time.sleep(max(1, (next_run - now).total_seconds()))
            try:
                backup_database(database_path, backup_dir)
            except sqlite3.Error:
                # Leave the service running; the next midnight will retry the backup.
                pass

    threading.Thread(target=run, name="daily-database-backup", daemon=True).start()
