from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from typing import Any, Callable

from config import INTRADAY_SYNC_SCHEDULE
from db import get_settings, save_settings


def start_intraday_scheduler(
    *,
    sync_lock: threading.Lock,
    sync_job: dict[str, object],
    database: Callable[[], Any],
    start_sync: Callable[[Any], Any],
    sync_payload: Callable[..., Any],
) -> None:
    """Start the intraday scheduler, syncing all eligible creators per run."""
    settings = get_settings(("intraday.next_run_at",))
    try:
        next_run_at = datetime.fromisoformat(settings["intraday.next_run_at"])
    except (KeyError, ValueError):
        next_run_at = None
    state: dict[str, object] = {"next_run_at": next_run_at}

    def next_run_after(finished_at: datetime) -> datetime:
        active_index = max(
            index
            for index, (start_time, _) in enumerate(INTRADAY_SYNC_SCHEDULE)
            if start_time <= finished_at.time()
        )
        _, interval = INTRADAY_SYNC_SCHEDULE[active_index]
        scheduled_at = finished_at + interval
        if active_index + 1 == len(INTRADAY_SYNC_SCHEDULE):
            return scheduled_at
        next_start_time, _ = INTRADAY_SYNC_SCHEDULE[active_index + 1]
        boundary = finished_at.replace(
            hour=next_start_time.hour,
            minute=next_start_time.minute,
            second=next_start_time.second,
            microsecond=0,
        )
        return min(scheduled_at, boundary)

    def publish_next_run(run_at: datetime | None) -> None:
        with sync_lock:
            sync_job["next_auto_sync_at"] = run_at.isoformat(timespec="seconds") if run_at else None

    def save_state() -> None:
        next_run_at = state["next_run_at"]
        save_settings({
            "intraday.next_run_at": next_run_at.isoformat(timespec="seconds") if isinstance(next_run_at, datetime) else "",
        })

    def set_next_run(run_at: datetime | None) -> None:
        state["next_run_at"] = run_at
        save_state()
        publish_next_run(run_at)

    def run() -> None:
        while True:
            now = datetime.now()
            due = state["next_run_at"]
            if isinstance(due, datetime) and now < due:
                publish_next_run(due)
                time.sleep(min(30, max(1, int((due - now).total_seconds()))))
                continue
            with sync_lock:
                busy = sync_job["status"] == "running"
            if busy:
                publish_next_run(None)
                time.sleep(5)
                continue
            with database() as db:
                creator_ids = [row["id"] for row in db.execute(
                    """
                    SELECT id
                    FROM creators
                    WHERE consent=1 AND platform_creator_id IS NOT NULL
                    ORDER BY last_synced IS NOT NULL, last_synced ASC, id ASC
                    """
                ).fetchall()]
            if not creator_ids:
                set_next_run(None)
                time.sleep(30)
                continue
            try:
                publish_next_run(None)
                start_sync(sync_payload(creator_ids=creator_ids))
            except Exception:
                set_next_run(now + timedelta(seconds=5))
                time.sleep(5)
                continue
            while True:
                with sync_lock:
                    completed = sync_job["status"] != "running"
                if completed:
                    break
                time.sleep(3)
            finished_at = datetime.now()
            set_next_run(next_run_after(finished_at))

    publish_next_run(next_run_at)
    threading.Thread(target=run, name="intraday-sync", daemon=True).start()
