from __future__ import annotations

import argparse
import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

import requests

API = "https://audioconvert.ai/api/transcribe"
CREATE_API = f"{API}/"
UPLOAD_PRESIGN_API = "https://audioconvert.ai/api/resource/upload/presign"
AUDIOCONVERT_TOKEN = os.environ.get("AUDIOCONVERT_TOKEN", "").strip()
logger = logging.getLogger("audioconvert")


def log_response(stage: str, response: requests.Response) -> None:
    """Log API responses without logging the authorization token or media URL."""
    body = response.text.replace("\n", " ").strip()
    if len(body) > 1_000:
        body = f"{body[:1_000]}…"
    logger.info("%s: status=%s body=%s", stage, response.status_code, body or "<empty>")


def log_payload_error(stage: str, payload: object) -> None:
    """Keep the upstream failure payload visible even when its message is generic."""
    try:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        body = repr(payload)
    logger.error("AudioConvert failure response: stage=%s body=%s", stage, body)


def headers() -> dict[str, str]:
    token = AUDIOCONVERT_TOKEN
    if not token:
        raise RuntimeError("Set AUDIOCONVERT_TOKEN before running transcription.")
    return {"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"}


def auth_headers() -> dict[str, str]:
    return {"Authorization": headers()["Authorization"], "Accept": "application/json"}


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


def response_data(payload: object) -> dict[str, object]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    return {}


def download_media(media_url: str, destination: Path, referer: str | None = None) -> None:
    logger.info("Downloading video fallback to local file: %s", destination.name)
    request_headers = {
        "Accept": "video/*,application/octet-stream;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "identity",
        "Referer": referer or "https://www.douyin.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
    }
    with requests.get(media_url, headers=request_headers, stream=True, timeout=(30, 300)) as response:
        response.raise_for_status()
        with destination.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output.write(chunk)
    if destination.stat().st_size == 0:
        raise RuntimeError("Downloaded video fallback is empty.")
    logger.info("Downloaded local fallback: file=%s bytes=%s", destination.name, destination.stat().st_size)


def extract_audio(video_path: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        logger.warning("ffmpeg was not found; uploading the downloaded MP4 instead.")
        return video_path
    audio_path = video_path.with_suffix(".mp3")
    logger.info("Extracting local audio with ffmpeg: source=%s output=%s", video_path.name, audio_path.name)
    result = subprocess.run(
        [ffmpeg, "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(audio_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=300,
    )
    if result.returncode or not audio_path.exists() or audio_path.stat().st_size == 0:
        logger.warning("ffmpeg audio extraction failed; uploading the downloaded MP4 instead: %s", result.stdout[-1_000:].replace("\n", " "))
        return video_path
    logger.info("Extracted local audio: file=%s bytes=%s", audio_path.name, audio_path.stat().st_size)
    return audio_path


def upload_local_media(media_path: Path) -> str:
    """Upload a local media file through AudioConvert's presigned OSS upload flow."""
    logger.info("Requesting AudioConvert upload URL: file=%s", media_path.name)
    presign = requests.get(UPLOAD_PRESIGN_API, headers=auth_headers(), params={"filename": media_path.name}, timeout=30)
    logger.info("Request AudioConvert upload URL: status=%s", presign.status_code)
    presign.raise_for_status()
    presign_payload = presign.json()
    upload_url = str(response_data(presign_payload).get("upload_url") or "").strip()
    if not upload_url:
        log_payload_error("request upload URL", presign_payload)
        raise RuntimeError("AudioConvert did not return an upload URL.")
    file_size = media_path.stat().st_size
    logger.info("Uploading local media to AudioConvert storage: file=%s bytes=%s", media_path.name, file_size)
    upload: requests.Response | None = None
    for attempt in range(1, 4):
        try:
            with media_path.open("rb") as media_file:
                # The presigned URL is generated without a content-type constraint;
                # match the browser upload by sending no Content-Type header.
                upload = requests.put(upload_url, data=media_file, headers={}, timeout=(30, 600))
            break
        except requests.RequestException as error:
            if attempt == 3:
                raise
            logger.warning("Local media upload interrupted (attempt %s/3): %s", attempt, error)
            time.sleep(2)
    if upload is None:
        raise RuntimeError("AudioConvert local media upload did not return a response.")
    logger.info("Upload local media to AudioConvert storage: status=%s", upload.status_code)
    upload.raise_for_status()
    media_url = upload_url.split("?", 1)[0]
    logger.info("Uploaded local media: file=%s", media_path.name)
    return media_url


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
    scenario: str = "auto",
    on_progress: Callable[[int], None] | None = None,
) -> tuple[str, str]:
    logger.info("Submitting transcription: file=%s scenario=%s", file_name, scenario)
    response = requests.post(
        CREATE_API,
        headers=headers(),
        json={"audio_url": media_url, "file_name": file_name, "language_code": "", "scenario": scenario},
        timeout=60,
    )
    log_response("Create transcription task", response)
    response.raise_for_status()
    create_payload = response.json()
    response_code = value(create_payload, "code")
    if response_code and response_code not in {"0", "100000"}:
        log_payload_error("create transcription task", create_payload)
    task_id = value(create_payload, "task_id", "taskId", "id")
    if not task_id:
        if not response_code or response_code in {"0", "100000"}:
            log_payload_error("create transcription task without task id", create_payload)
        message = value(create_payload, "error", "detail", "reason")
        if not message or message.lower() == "success":
            message = value(create_payload, "message")
        raise RuntimeError(
            f"AudioConvert response did not include a task id (code={response_code or 'unknown'}, message={message or 'unknown'})."
        )
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
            log_payload_error("poll transcription task", result)
            failure_message = value(result.get("data") if isinstance(result, dict) else result, "error", "detail", "reason", "message")
            if not failure_message or failure_message.lower() == "success":
                failure_message = "AudioConvert transcription task failed."
            raise RuntimeError(failure_message)
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
            "SELECT title, playback_url, music_download_url, raw_payload_json, source_url FROM videos WHERE id=?",
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
        direct_error: Exception | None = None
        if music_url and music_url != row[1]:
            logger.info("Using the creator-original music URL before the video URL.")
            try:
                text, markdown = transcribe(
                    music_url,
                    f"video-{args.video_id}-music.mp3",
                    on_progress=save_progress,
                )
            except Exception as error:
                direct_error = error
                logger.exception("Creator-original music transcription failed; retrying with the video URL.")
            else:
                direct_error = None
        else:
            logger.info("No creator-original music URL; using the video URL only.")
        if direct_error is not None or not music_url or music_url == row[1]:
            try:
                text, markdown = transcribe(
                    row[1],
                    f"video-{args.video_id}.mp4",
                    on_progress=save_progress,
                )
            except Exception as error:
                direct_error = error
                logger.exception("Video URL transcription failed; retrying with a local upload.")
            else:
                direct_error = None
        if direct_error is not None:
            temporary_root = Path(__file__).parent / "temp"
            temporary_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix=f"audioconvert-video-{args.video_id}-",
                dir=temporary_root,
            ) as temporary_directory:
                video_path = Path(temporary_directory) / f"video-{args.video_id}.mp4"
                download_media(row[1], video_path, row[4])
                local_media_path = extract_audio(video_path)
                uploaded_media_url = upload_local_media(local_media_path)
                text, markdown = transcribe(
                    uploaded_media_url,
                    local_media_path.name,
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
