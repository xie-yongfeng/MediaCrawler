from __future__ import annotations

import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from queue import Empty, Queue
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException, Request
from config import (
    AVATAR_COLORS,
    BASE_DIR,
    CREATOR_AVATAR_PATTERN,
    CREATOR_HASH_PATTERN,
    CREATOR_NAME_PATTERN,
    DB_PATH,
    MEDIA_CRAWLER_DB,
    MEDIA_CRAWLER_ROOT,
)
from db import database, initialize_database, row_dict
from intraday_scheduler import start_intraday_scheduler
from service import service
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

def load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


load_dotenv()
app = FastAPI(title="Fund Insight Desk API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SYNC_LOCK = threading.Lock()
AWEME_DURATION_PATTERN = re.compile(r"\[FundInsight\] aweme_duration=(\{.+?\})")
SYNC_JOB: dict[str, object] = {
    "status": "idle", "message": "尚未同步真实内容。", "started_at": None,
    "finished_at": None, "creator_ids": [], "active_creator_id": None, "imported_count": 0, "log_tail": [], "next_auto_sync_at": None,
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def today_text() -> str:
    return date.today().isoformat()


def parse_json(value: str | None, fallback: list | dict):
    try:
        return json.loads(value) if value else fallback
    except json.JSONDecodeError:
        return fallback


def video_stream_headers(source_url: str, range_header: str | None) -> dict[str, str]:
    """Build the upstream request headers needed by a browser video request."""
    headers = {
        "Accept": "video/*,application/octet-stream;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "identity",
        "Referer": source_url or "https://www.douyin.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
    }
    if range_header:
        headers["Range"] = range_header
    return headers


def asr_configured() -> bool:
    return bool(os.environ.get("AUDIOCONVERT_TOKEN"))


def enqueue_creator_transcriptions(creator_id: int) -> None:
    if not asr_configured():
        return
    with database() as db:
        rows = db.execute(
            "SELECT id FROM videos WHERE creator_id=? AND playback_url IS NOT NULL AND playback_url != '' AND transcript_status != 'completed' ORDER BY published_at DESC LIMIT 5",
            (creator_id,),
        ).fetchall()
        db.executemany(
            "UPDATE videos SET transcript_status='processing', transcript_progress=5, transcript_updated_at=? WHERE id=?",
            [(now_text(), row["id"]) for row in rows],
        )
    for row in rows:
        threading.Thread(target=run_audioconvert_transcription, args=(row["id"],), daemon=True).start()


class CreatorPayload(BaseModel):
    name: str = Field(default="", max_length=80)
    platform_creator_id: str = Field(min_length=1, max_length=300)
    tags: list[str] = Field(default_factory=list, max_length=12)
    priority: bool = False
    consent: bool = False


class StatusPayload(BaseModel):
    status: Literal["unread", "processed", "later", "ignored"]


class SyncPayload(BaseModel):
    creator_ids: list[int] = Field(default_factory=list)


def choose_topic(title: str, tags: list[str]) -> str:
    lowered = title.lower()
    return next((tag for tag in tags if tag.lower() in lowered), tags[0] if tags else "未分类")


def timestamp_text(value: int | str | None) -> str:
    try:
        return datetime.fromtimestamp(int(value)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return now_text()


def is_critical_window(published_at: str) -> int:
    try:
        clock = datetime.strptime(published_at, "%Y-%m-%d %H:%M").strftime("%H:%M")
        return int("14:00" <= clock < "15:00")
    except ValueError:
        return 0


def cdp_browser_is_running() -> bool:
    try:
        with socket.create_connection(('127.0.0.1', 9222), timeout=0.5):
            return True
    except OSError:
        return False


def crawler_command(creator_id: str, headless: bool = True, max_notes_count: int = 15) -> list[str]:
    venv_python = MEDIA_CRAWLER_ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    uv = shutil.which("uv")
    if venv_python.exists():
        command = [str(venv_python), "main.py"]
    elif uv:
        command = [uv, "run", "python", "main.py"]
    else:
        command = [sys.executable, "main.py"]
    return command + [
        "--platform", "dy", "--lt", "qrcode", "--type", "creator", "--headless", str(headless).lower(), "--cdp_connect_existing", str(cdp_browser_is_running()).lower(), "--creator_id", creator_id,
        "--save_data_option", "sqlite", "--get_comment", "false", "--get_sub_comment", "false",
        "--crawler_max_notes_count", str(max_notes_count),
    ]



def creator_sync_window(creator_id: int) -> tuple[int, int, int]:
    """Return crawler limit, crawler cursor, and import cursor for one creator."""
    with database() as db:
        row = db.execute(
            "SELECT COUNT(*) AS count, MAX(published_at) AS latest_published_at FROM videos WHERE creator_id=?",
            (creator_id,),
        ).fetchone()
    if not row or not row["count"]:
        three_days_ago = int((datetime.now() - timedelta(days=3)).timestamp())
        return 15, 0, three_days_ago
    try:
        latest_epoch = int(datetime.strptime(row["latest_published_at"], "%Y-%m-%d %H:%M").timestamp())
    except (TypeError, ValueError, OSError):
        latest_epoch = 0
    return 1000, latest_epoch, latest_epoch

def media_rows_for_creator(creator_hash: str, published_after: int, max_count: int) -> list[sqlite3.Row]:
    """Return only confirmed creator rows newer than the requested publish cursor."""
    if not MEDIA_CRAWLER_DB.exists():
        return []
    connection = sqlite3.connect(MEDIA_CRAWLER_DB)
    connection.row_factory = sqlite3.Row
    try:
        has_table = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='douyin_aweme'").fetchone()
        if not has_table:
            return []
        return connection.execute(
            """SELECT * FROM douyin_aweme
               WHERE creator_hash = ? AND COALESCE(create_time, 0) > ?
               ORDER BY create_time DESC LIMIT ?""",
            (creator_hash, published_after, max_count),
        ).fetchall()
    finally:
        connection.close()


def reconcile_video_ownership() -> int:
    """Repair old rows once watched creators have a confirmed anonymous hash."""
    if not MEDIA_CRAWLER_DB.exists():
        return 0
    with database() as desk:
        owners = {
            row["crawler_creator_hash"]: row["id"]
            for row in desk.execute("SELECT id, crawler_creator_hash FROM creators WHERE crawler_creator_hash IS NOT NULL").fetchall()
        }
        if not owners:
            return 0
        videos = desk.execute("SELECT id, creator_id, external_id FROM videos WHERE external_id IS NOT NULL").fetchall()
        crawler = sqlite3.connect(MEDIA_CRAWLER_DB)
        try:
            crawler.row_factory = sqlite3.Row
            raw_rows = crawler.execute("SELECT aweme_id, creator_hash FROM douyin_aweme").fetchall()
        finally:
            crawler.close()
        raw_owners = {str(row["aweme_id"]): owners.get(row["creator_hash"]) for row in raw_rows}
        repaired = 0
        for video in videos:
            correct_creator_id = raw_owners.get(video["external_id"])
            if correct_creator_id and correct_creator_id != video["creator_id"]:
                desk.execute("UPDATE videos SET creator_id = ? WHERE id = ?", (correct_creator_id, video["id"]))
                repaired += 1
        return repaired


def restore_playback_urls() -> int:
    """Backfill missing playback URLs only when crawler ownership is confirmed."""
    if not MEDIA_CRAWLER_DB.exists():
        return 0
    crawler = sqlite3.connect(MEDIA_CRAWLER_DB)
    crawler.row_factory = sqlite3.Row
    try:
        rows = crawler.execute(
            "SELECT aweme_id, creator_hash, video_download_url FROM douyin_aweme "
            "WHERE video_download_url IS NOT NULL AND video_download_url != ''"
        ).fetchall()
    finally:
        crawler.close()

    with database() as desk:
        owners = {
            row["crawler_creator_hash"]: row["id"]
            for row in desk.execute(
                "SELECT id, crawler_creator_hash FROM creators WHERE crawler_creator_hash IS NOT NULL"
            ).fetchall()
        }
        restored = 0
        for row in rows:
            creator_id = owners.get(row["creator_hash"])
            if not creator_id:
                continue
            cursor = desk.execute(
                """UPDATE videos SET playback_url=?
                   WHERE external_id=? AND creator_id=? AND (playback_url IS NULL OR playback_url = '')""",
                (row["video_download_url"], str(row["aweme_id"]), creator_id),
            )
            restored += cursor.rowcount
        return restored


def remove_legacy_summary_prefix() -> None:
    prefix = "\u7cfb\u7edf\u63d0\u53d6\uff1a\u5df2\u4ece\u7528\u6237\u63d0\u4f9b\u7684\u516c\u5f00\u6765\u6e90\u540c\u6b65\u6807\u9898\u4e0e\u63cf\u8ff0\u3002"
    with database() as db:
        rows = db.execute("SELECT id, summary FROM videos WHERE summary LIKE ?", (f"{prefix}%",)).fetchall()
        for row in rows:
            db.execute("UPDATE videos SET summary=? WHERE id=?", (row["summary"][len(prefix):].strip(), row["id"]))



def update_creator_profile(creator_id: int, display_name: str, avatar_url: str) -> None:
    display_name = display_name.strip()
    avatar_url = avatar_url.strip()
    if not display_name and not avatar_url:
        return
    with database() as db:
        creator = db.execute("SELECT name, platform_creator_id, avatar FROM creators WHERE id=?", (creator_id,)).fetchone()
        if not creator:
            return
        name = display_name if display_name and creator["name"] == creator["platform_creator_id"] else creator["name"]
        avatar = avatar_url or creator["avatar"]
        db.execute("UPDATE creators SET name=?, handle=?, avatar=? WHERE id=?", (name, f"@{name}", avatar, creator_id))



def parse_aweme_durations(crawler_output: str) -> dict[str, int]:
    durations: dict[str, int] = {}
    for payload in AWEME_DURATION_PATTERN.findall(crawler_output):
        try:
            item = json.loads(payload)
            aweme_id = str(item.get("aweme_id") or "").strip()
            duration_seconds = max(0, int(item.get("duration_seconds") or 0))
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if aweme_id:
            durations[aweme_id] = duration_seconds
    return durations


def import_media_rows(
    creator: dict, rows: list[sqlite3.Row], creator_hash: str, aweme_durations: dict[str, int] | None = None
) -> int:
    tags = parse_json(creator.get("tags_json"), [])
    imported = 0
    with database() as db:
        for raw in rows:
            item = dict(raw)
            external_id = str(item.get("aweme_id") or "").strip()
            title = (item.get("title") or item.get("desc") or "").strip()
            if not external_id:
                continue
            published_at = timestamp_text(item.get("create_time"))
            description = (item.get("desc") or "").strip()
            topic = choose_topic(f"{title} {description}", tags)
            source_url = item.get("aweme_url") or f"https://www.douyin.com/video/{external_id}"
            summary = description
            viewpoint = f"创作者原文：{description}" if description else "创作者观点需在原视频中核对。"
            existing = db.execute("SELECT id FROM videos WHERE external_id = ?", (external_id,)).fetchone()
            if existing:
                db.execute(
                    """UPDATE videos SET creator_id=?, title=?, published_at=?, discovered_at=?, topic=?, summary=?, viewpoint=?,
                       source_url=?, cover_url=?, playback_url=?, is_critical=?, tags_json=?, source_status=? WHERE external_id=?""",
                    (creator["id"], title, published_at, now_text(), topic, summary, viewpoint, source_url,
                     item.get("cover_url"), item.get("video_download_url"), is_critical_window(published_at), json.dumps(tags, ensure_ascii=False),
                     "用户提供来源", external_id),
                )
            else:
                duration_seconds = (aweme_durations or {}).get(external_id, 0)
                db.execute(
                    """INSERT INTO videos (creator_id, external_id, title, published_at, discovered_at, duration_seconds, topic,
                    summary, viewpoint, fact_status, risk_note, source_url, cover_url, playback_url, processing_status, is_critical,
                    transcript_status, transcript_progress, transcript_confidence, transcript_updated_at, transcript_text, tags_json,
                    source_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '未核验', ?, ?, ?, ?, 'unread', ?, 'unavailable', 0, NULL, ?, NULL, ?, '用户提供来源')""",
                    (creator["id"], external_id, title, published_at, now_text(), duration_seconds, topic, summary, viewpoint,
                     "内容仅作信息整理；请查看原视频与来源后独立判断。", source_url, item.get("cover_url"), item.get("video_download_url"),
                     is_critical_window(published_at), now_text(), json.dumps(tags, ensure_ascii=False)),
                )
                imported += 1
        db.execute(
            "UPDATE creators SET last_synced=?, last_crawled_at=?, crawler_creator_hash=?, source_status=?, source_message=? WHERE id=?",
            (now_text(), now_text(), creator_hash, "已同步", f"最近同步已导入 {imported} 条作品", creator["id"]),
        )
    return imported


def set_job(**updates: object) -> None:
    with SYNC_LOCK:
        SYNC_JOB.update(updates)


def run_crawler_process(command: list[str], env: dict[str, str], logs: list[str]) -> subprocess.CompletedProcess[str]:
    """Run MediaCrawler and forward its stdout to the API console in real time."""
    process = subprocess.Popen(
        command, cwd=MEDIA_CRAWLER_ROOT, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, env=env,
    )
    lines: list[str] = []
    output_queue: Queue[str | None] = Queue()

    def read_stdout() -> None:
        if process.stdout:
            for raw_line in iter(process.stdout.readline, ""):
                output_queue.put(raw_line)
        output_queue.put(None)

    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()
    deadline = time.monotonic() + 900
    reader_finished = False
    try:
        while not reader_finished or process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                raise subprocess.TimeoutExpired(command, 900, output="\n".join(lines))
            try:
                raw_line = output_queue.get(timeout=min(0.25, remaining))
            except Empty:
                continue
            if raw_line is None:
                reader_finished = True
                continue
            line = raw_line.rstrip()
            if line:
                lines.append(line)
                logs.append(line)
                print(f"[MediaCrawler] {line}", flush=True)
                set_job(log_tail=logs[-30:])
        return subprocess.CompletedProcess(command, process.wait(), stdout="\n".join(lines))
    finally:
        if process.poll() is None:
            process.kill()
        if process.stdout:
            process.stdout.close()

def run_sync(creator_ids: list[int]) -> None:
    imported_total, logs = 0, []
    try:
        for creator_id in creator_ids:
            set_job(active_creator_id=creator_id)
            with database() as db:
                creator = row_dict(db.execute("SELECT * FROM creators WHERE id = ?", (creator_id,)).fetchone())
            if not creator:
                continue
            crawl_limit, crawler_since, import_after = creator_sync_window(creator_id)
            sync_env = os.environ.copy()
            sync_env["FUND_INSIGHT_CREATOR_SINCE"] = str(crawler_since)
            set_job(message=f"正在验证 {creator['name']} 的已保存登录态。")
            result = run_crawler_process(
                crawler_command(creator["platform_creator_id"], max_notes_count=crawl_limit), sync_env, logs,
            )
            if result.returncode != 0 and "[FundInsight] LOGIN_EXPIRED" in (result.stdout or ""):
                set_job(message=f"{creator['name']} 的登录态已过期，正在打开抖音二维码认证。")
                result = run_crawler_process(
                    crawler_command(creator["platform_creator_id"], headless=False, max_notes_count=crawl_limit), sync_env, logs,
                )
            if result.returncode != 0:
                with database() as db:
                    db.execute(
                        "UPDATE creators SET source_status=?, source_message=?, last_crawled_at=? WHERE id=?",
                        ("同步失败", "认证或同步未完成。已自动尝试打开抖音二维码页；请确认扫码、平台权限和该主页是否公开后重试。", now_text(), creator_id),
                    )
                raise RuntimeError(f"{creator['name']} 同步失败（退出码 {result.returncode}）。")
            creator_hashes = CREATOR_HASH_PATTERN.findall(result.stdout or "")
            if not creator_hashes:
                raise RuntimeError("无法确认该博主的匿名身份，已拒绝导入以防止内容错归属。")
            creator_hash = creator_hashes[-1]
            creator_name_matches = CREATOR_NAME_PATTERN.findall(result.stdout or "")
            creator_avatar_matches = CREATOR_AVATAR_PATTERN.findall(result.stdout or "")
            if creator_name_matches or creator_avatar_matches:
                try:
                    creator_name = str(json.loads(creator_name_matches[-1])).strip() if creator_name_matches else ""
                except json.JSONDecodeError:
                    creator_name = ""
                try:
                    creator_avatar = str(json.loads(creator_avatar_matches[-1])).strip() if creator_avatar_matches else ""
                except json.JSONDecodeError:
                    creator_avatar = ""
                update_creator_profile(creator_id, creator_name, creator_avatar)
                with database() as db:
                    creator = row_dict(db.execute("SELECT * FROM creators WHERE id=?", (creator_id,)).fetchone())
            imported_total += import_media_rows(
                creator,
                media_rows_for_creator(creator_hash, import_after, crawl_limit),
                creator_hash,
                parse_aweme_durations(result.stdout or ""),
            )
            reconcile_video_ownership()
            enqueue_creator_transcriptions(creator_id)
        set_job(status="completed", message=f"同步完成，新增导入 {imported_total} 条作品", imported_count=imported_total,
                active_creator_id=None, finished_at=now_text(), log_tail=logs[-30:])
    except subprocess.TimeoutExpired:
        set_job(status="failed", message="同步等待超时。请完成浏览器登录后重新发起同步", active_creator_id=None, finished_at=now_text(), log_tail=logs[-30:])
    except Exception as exc:
        set_job(status="failed", message=str(exc), active_creator_id=None, finished_at=now_text(), log_tail=logs[-30:])


@app.on_event("startup")
def startup():
    initialize_database()
    reconcile_video_ownership()
    restore_playback_urls()
    remove_legacy_summary_prefix()
    start_intraday_scheduler(sync_lock=SYNC_LOCK, sync_job=SYNC_JOB, database=database, start_sync=start_sync, sync_payload=SyncPayload)


@app.get("/health")
def health():
    return {
        "ok": True, "database": str(DB_PATH), "media_crawler_root": str(MEDIA_CRAWLER_ROOT),
        "media_crawler_available": (MEDIA_CRAWLER_ROOT / "main.py").exists(),
    }


@app.get("/api/dashboard")
def dashboard():
    return service.dashboard()


@app.get("/api/creators")
def creators():
    return service.list_creators()


@app.post("/api/creators", status_code=201)
def create_creator(payload: CreatorPayload):
    with SYNC_LOCK:
        if SYNC_JOB["status"] == "running":
            raise HTTPException(409, "正在同步中，请稍后添加博主。")
    creator = service.save_creator(None, payload)
    set_job(status="running", message="正在获取抖音昵称并完成首次同步…", started_at=now_text(), finished_at=None,
            creator_ids=[creator["id"]], active_creator_id=None, imported_count=0, log_tail=[])
    run_sync([creator["id"]])
    with SYNC_LOCK:
        completed = SYNC_JOB["status"] == "completed"
    with database() as db:
        synced_creator = service.creator_dict(db.execute("SELECT * FROM creators WHERE id=?", (creator["id"],)).fetchone())
    if completed and synced_creator and synced_creator["name"] != synced_creator["platform_creator_id"]:
        return synced_creator
    with database() as db:
        db.execute("DELETE FROM creators WHERE id=?", (creator["id"],))
    raise HTTPException(502, "未能完成抖音认证、昵称读取或首次同步，添加失败。")


@app.put("/api/creators/{creator_id}")
def update_creator(creator_id: int, payload: CreatorPayload):
    return service.save_creator(creator_id, payload)


@app.delete("/api/creators/{creator_id}")
def delete_creator(creator_id: int):
    service.delete_creator(creator_id)
    return {"ok": True}


@app.post("/api/sync")
def start_sync(payload: SyncPayload):
    with SYNC_LOCK:
        if SYNC_JOB["status"] == "running":
            raise HTTPException(409, "已有同步任务在运行中。")
    selected = service.select_sync_creators(payload.creator_ids)
    set_job(status="running", message="正在自动启动可视 Chrome/Edge，并准备抖音二维码认证…", started_at=now_text(), finished_at=None,
            creator_ids=selected, active_creator_id=None, imported_count=0, log_tail=[])
    threading.Thread(target=run_sync, args=(selected,), daemon=True).start()
    return {"ok": True, "status": "running", "creator_ids": selected}


@app.get("/api/sync/status")
def sync_status():
    with SYNC_LOCK:
        return dict(SYNC_JOB)


@app.get("/api/creators/{creator_id}/videos")
def creator_videos(creator_id: int, filter: str = "all", search: str = ""):
    return service.creator_videos(creator_id, filter, search)


@app.get("/api/videos/{video_id}")
def video_detail(video_id: int):
    return service.video_detail(video_id)


@app.get("/api/videos/{video_id}/stream")
def stream_video(video_id: int, request: Request):
    """Relay the current signed playback URL without saving the media locally."""
    with database() as db:
        video = db.execute("SELECT playback_url, source_url FROM videos WHERE id=?", (video_id,)).fetchone()
    if not video:
        raise HTTPException(404, "Video not found")
    playback_url = (video["playback_url"] or "").strip()
    if not playback_url.startswith(("https://", "http://")):
        raise HTTPException(409, "The video does not have a playable media URL yet")

    upstream_request = UrlRequest(
        playback_url,
        headers=video_stream_headers(video["source_url"], request.headers.get("range")),
    )
    try:
        upstream = urlopen(upstream_request, timeout=60)
    except HTTPError as exc:
        raise HTTPException(502, f"Upstream video service returned {exc.code}") from exc
    except URLError as exc:
        raise HTTPException(502, "Unable to connect to the upstream video service") from exc
    except TimeoutError as exc:
        raise HTTPException(504, "Upstream video service timed out before playback started") from exc
    except OSError as exc:
        raise HTTPException(502, "Upstream video service connection failed") from exc

    response_headers = {"Cache-Control": "private, no-store", "Accept-Ranges": "bytes"}
    for header in ("Content-Type", "Content-Length", "Content-Range"):
        value = upstream.headers.get(header)
        if value:
            response_headers[header] = value

    def chunks():
        try:
            while data := upstream.read(64 * 1024):
                yield data
        except (TimeoutError, OSError):
            # The upstream signed video stream can stall or expire mid-playback.
            # Headers may already be sent, so end this response cleanly instead of
            # raising an ASGI exception for the client.
            return
        finally:
            upstream.close()

    return StreamingResponse(chunks(), status_code=upstream.status, headers=response_headers)


@app.post("/api/videos/{video_id}/status")
def update_video_status(video_id: int, payload: StatusPayload):
    service.update_video_status(video_id, payload.status)
    return {"ok": True, "id": video_id, "status": payload.status}


def run_audioconvert_transcription(video_id: int) -> None:
    script = BASE_DIR / "audioconvert_transcriber.py"
    result = subprocess.run([sys.executable, str(script), "--video-id", str(video_id)], cwd=BASE_DIR, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        with database() as db:
            db.execute("UPDATE videos SET transcript_status='failed', transcript_progress=0, transcript_updated_at=? WHERE id=?", (now_text(), video_id))


@app.post("/api/videos/{video_id}/transcription/audioconvert")
def start_audioconvert_transcription(video_id: int):
    if not os.environ.get("AUDIOCONVERT_TOKEN"):
        raise HTTPException(400, "AUDIOCONVERT_TOKEN is not configured")
    with database() as db:
        if not db.execute("SELECT 1 FROM videos WHERE id=?", (video_id,)).fetchone():
            raise HTTPException(404, "Video not found")
        db.execute("UPDATE videos SET transcript_status='processing', transcript_progress=5, transcript_updated_at=? WHERE id=?", (now_text(), video_id))
    threading.Thread(target=run_audioconvert_transcription, args=(video_id,), daemon=True).start()
    return {"ok": True}
@app.post("/api/videos/{video_id}/transcription/retry")
def retry_transcription(video_id: int):
    with database() as db:
        if not db.execute("SELECT 1 FROM videos WHERE id=?", (video_id,)).fetchone():
            raise HTTPException(404, "Video not found")
        db.execute("UPDATE videos SET transcript_status='unavailable', transcript_progress=0, transcript_updated_at=? WHERE id=?", (now_text(), video_id))
    return {"ok": True, "message": "未配置获授权的音频转写服务；可在原平台查看视频。"}
