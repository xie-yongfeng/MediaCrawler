from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path
from typing import Callable

import requests

API = "https://audioconvert.ai/api/transcribe"
AUDIOCONVERT_TOKEN = os.environ.get("AUDIOCONVERT_TOKEN", "").strip()


def headers() -> dict[str, str]:
    token = AUDIOCONVERT_TOKEN
    if not token:
        raise RuntimeError("Set AUDIOCONVERT_TOKEN before running transcription.")
    return {"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"}


def value(data: object, *keys: str) -> str:
    if isinstance(data, dict):
        for key in keys:
            item = data.get(key)
            if isinstance(item, (str, int, float)):
                return str(item)
        for item in data.values():
            found = value(item, *keys)
            if found:
                return found
    if isinstance(data, list):
        for item in data:
            found = value(item, *keys)
            if found:
                return found
    return ""


def progress_value(data: object) -> int | None:
    raw_value = value(data, "progress", "percentage", "percent", "completion")
    if not raw_value:
        return None
    try:
        progress = float(raw_value.strip().rstrip("%"))
    except ValueError:
        return None
    if not math.isfinite(progress):
        return None
    if 0 <= progress <= 1:
        progress *= 100
    return max(0, min(100, round(progress)))


def transcribe(
    media_url: str,
    file_name: str,
    scenario: str = "note",
    on_progress: Callable[[int], None] | None = None,
) -> tuple[str, str]:
    response = requests.post(API, headers=headers(), json={"audio_url": media_url, "file_link": media_url, "file_name": file_name, "language_code": "", "scenario": scenario}, timeout=60)
    response.raise_for_status()
    task_id = value(response.json(), "task_id", "taskId", "id")
    if not task_id:
        raise RuntimeError("AudioConvert response did not include a task id.")
    deadline = time.monotonic() + 900
    result: object = {}
    while time.monotonic() < deadline:
        poll = requests.get(f"{API}/{task_id}", headers={"Authorization": headers()["Authorization"], "Accept": "application/json"}, timeout=30)
        poll.raise_for_status()
        result = poll.json()
        progress = progress_value(result)
        if progress is not None and on_progress:
            on_progress(min(progress, 99))
        state = value(result, "status", "state").lower()
        if state in {"completed", "complete", "success", "finished", "done"}:
            break
        if state in {"failed", "error"}:
            raise RuntimeError(value(result, "message", "error") or "AudioConvert transcription failed.")
        time.sleep(3)
    else:
        raise TimeoutError("AudioConvert transcription timed out.")
    transcript = value(result, "transcript", "text", "content", "result")
    summary = requests.post(f"{API}/{task_id}/summary", params={"scenario": scenario}, headers={"Authorization": headers()["Authorization"], "Accept": "text/event-stream"}, timeout=120)
    summary.raise_for_status()
    summary_parts = []
    for line in summary.text.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload in {"[DONE]", "{}"}:
            continue
        try:
            item = json.loads(payload)
        except json.JSONDecodeError:
            summary_parts.append(payload)
        else:
            if isinstance(item, dict) and isinstance(item.get("t"), str):
                summary_parts.append(item["t"])
    summary_text = "".join(summary_parts).strip()
    markdown = f"\n{summary_text}\n"
    return transcript, markdown


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-id", type=int, required=True)
    parser.add_argument("--database", default=str(Path(__file__).parent / "data" / "fund_insight.db"))
    args = parser.parse_args()
    import sqlite3
    db = sqlite3.connect(args.database)
    try:
        row = db.execute("SELECT title, playback_url FROM videos WHERE id=?", (args.video_id,)).fetchone()
        if not row or not row[1]:
            raise RuntimeError("Video or playback URL was not found.")
        db.execute("ALTER TABLE videos ADD COLUMN transcript_markdown TEXT") if "transcript_markdown" not in {r[1] for r in db.execute("PRAGMA table_info(videos)")} else None

        def save_progress(progress: int) -> None:
            db.execute(
                "UPDATE videos SET transcript_status='processing', transcript_progress=?, transcript_updated_at=datetime('now', 'localtime') WHERE id=?",
                (progress, args.video_id),
            )
            db.commit()

        text, markdown = transcribe(row[1], f"video-{args.video_id}.mp4", on_progress=save_progress)
        db.execute(
            "UPDATE videos SET transcript_text=?, transcript_markdown=?, transcript_status='completed', transcript_progress=100, transcript_updated_at=datetime('now', 'localtime') WHERE id=?",
            (text, markdown, args.video_id),
        )
        db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    main()
