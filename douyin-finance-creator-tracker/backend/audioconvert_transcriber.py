from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
from pathlib import Path
from typing import Callable

import requests

API = "https://audioconvert.ai/api/transcribe"
AUDIOCONVERT_TOKEN = os.environ.get("AUDIOCONVERT_TOKEN", "").strip()
logger = logging.getLogger("audioconvert")


def log_response(stage: str, response: requests.Response) -> None:
    """Log API responses without logging the authorization token or media URL."""
    body = response.text.replace("\n", " ").strip()
    if len(body) > 1_000:
        body = f"{body[:1_000]}…"
    logger.info("%s: status=%s body=%s", stage, response.status_code, body or "<empty>")


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


def creator_original_music_url(raw_payload: str | None, stored_music_url: str | None) -> str:
    """Return a music URL only when Douyin identifies its owner as the video creator."""
    try:
        payload = json.loads(raw_payload or "{}")
        author = payload.get("author") or {}
        music = payload.get("music") or {}
        creator_uid = str(author.get("uid") or "").strip()
        music_owner_id = str(music.get("owner_id") or "").strip()
        if not creator_uid or creator_uid != music_owner_id:
            return ""
        play_url = music.get("play_url") or music.get("playUrl") or {}
        urls = play_url.get("url_list") or play_url.get("urlList") or []
        raw_music_url = str(urls[0]).strip() if isinstance(urls, list) and urls else ""
    except (AttributeError, IndexError, TypeError, json.JSONDecodeError):
        return ""
    candidate = str(stored_music_url or "").strip() or raw_music_url
    return candidate if candidate.startswith(("https://", "http://")) else ""


def transcribe(
    media_url: str,
    file_name: str,
    scenario: str = "note",
    on_progress: Callable[[int], None] | None = None,
) -> tuple[str, str]:
    logger.info("Submitting transcription: file=%s scenario=%s", file_name, scenario)
    response = requests.post(
        API,
        headers=headers(),
        json={"audio_url": media_url, "file_link": media_url, "file_name": file_name, "language_code": "", "scenario": scenario},
        timeout=60,
    )
    log_response("Create transcription task", response)
    response.raise_for_status()
    task_id = value(response.json(), "task_id", "taskId", "id")
    if not task_id:
        raise RuntimeError("AudioConvert response did not include a task id.")
    logger.info("Transcription task created: task_id=%s", task_id)
    deadline = time.monotonic() + 900
    result: object = {}
    while time.monotonic() < deadline:
        poll = requests.get(
            f"{API}/{task_id}",
            headers={"Authorization": headers()["Authorization"], "Accept": "application/json"},
            timeout=30,
        )
        log_response("Poll transcription task", poll)
        poll.raise_for_status()
        result = poll.json()
        progress = progress_value(result)
        if progress is not None and on_progress:
            on_progress(min(progress, 99))
        state = value(result, "status", "state").lower()
        logger.info("Transcription task state=%s progress=%s", state or "<missing>", progress)
        if state in {"completed", "complete", "success", "finished", "done"}:
            break
        if state in {"failed", "error"}:
            raise RuntimeError(value(result, "message", "error") or "AudioConvert transcription failed.")
        time.sleep(3)
    else:
        raise TimeoutError("AudioConvert transcription timed out.")
    transcript = value(result, "transcript", "text", "content", "result")
    logger.info("Requesting AI summary: task_id=%s transcript_length=%s", task_id, len(transcript))
    summary = requests.post(
        f"{API}/{task_id}/summary",
        params={"scenario": scenario},
        headers={"Authorization": headers()["Authorization"], "Accept": "text/event-stream"},
        timeout=120,
    )
    log_response("Create AI summary", summary)
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
    logger.info("Transcription completed: transcript_length=%s summary_length=%s", len(transcript), len(summary_text))
    markdown = f"\n{summary_text}\n"
    return transcript, markdown


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[AudioConvert] %(asctime)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-id", type=int, required=True)
    parser.add_argument("--database", default=str(Path(__file__).parent / "data" / "fund_insight.db"))
    args = parser.parse_args()
    import sqlite3
    db = sqlite3.connect(args.database)
    try:
        columns = {item[1] for item in db.execute("PRAGMA table_info(videos)")}
        if "transcript_markdown" not in columns:
            db.execute("ALTER TABLE videos ADD COLUMN transcript_markdown TEXT")
        if "music_download_url" not in columns:
            db.execute("ALTER TABLE videos ADD COLUMN music_download_url TEXT")
        row = db.execute(
            "SELECT title, playback_url, music_download_url, raw_payload_json FROM videos WHERE id=?",
            (args.video_id,),
        ).fetchone()
        if not row or not row[1]:
            raise RuntimeError("Video or playback URL was not found.")
        logger.info("Starting transcription for video_id=%s title=%r", args.video_id, row[0])

        def save_progress(progress: int) -> None:
            db.execute(
                "UPDATE videos SET transcript_status='processing', transcript_progress=?, transcript_updated_at=datetime('now', 'localtime') WHERE id=?",
                (progress, args.video_id),
            )
            db.commit()

        music_url = creator_original_music_url(row[3], row[2])
        if music_url and music_url != row[1]:
            logger.info("Using the creator-original music URL before the video URL.")
            try:
                text, markdown = transcribe(
                    music_url,
                    f"video-{args.video_id}-music.mp3",
                    on_progress=save_progress,
                )
            except Exception:
                logger.exception("Creator-original music transcription failed; retrying with the video URL.")
                text, markdown = transcribe(
                    row[1],
                    f"video-{args.video_id}.mp4",
                    on_progress=save_progress,
                )
        else:
            logger.info("No creator-original music URL; using the video URL only.")
            text, markdown = transcribe(
                row[1],
                f"video-{args.video_id}.mp4",
                on_progress=save_progress,
            )
        db.execute(
            "UPDATE videos SET transcript_text=?, transcript_markdown=?, transcript_status='completed', transcript_progress=100, transcript_updated_at=datetime('now', 'localtime') WHERE id=?",
            (text, markdown, args.video_id),
        )
        db.commit()
        logger.info("Saved transcription for video_id=%s", args.video_id)
    except Exception:
        logger.exception("Transcription failed for video_id=%s", args.video_id)
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()
