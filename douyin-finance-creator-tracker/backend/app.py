from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen


def load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from config import BASE_DIR, DB_PATH
from crawler.douyin import DouyinCollector, LoginExpired
from db import database, initialize_database, row_dict
from intraday_scheduler import start_intraday_scheduler
from service import service
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
app = FastAPI(title="Fund Insight Desk API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SYNC_LOCK = threading.Lock()
SYNC_JOB: dict[str, object] = {
    "status": "idle", "message": "尚未同步真实内容。", "started_at": None,
    "finished_at": None, "creator_ids": [], "active_creator_id": None, "imported_count": 0, "log_tail": [], "next_auto_sync_at": None,
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


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


def set_job(**updates: object) -> None:
    with SYNC_LOCK:
        SYNC_JOB.update(updates)


def run_sync(creator_ids: list[int]) -> None:
    imported_total, logs = 0, []
    collector = DouyinCollector()
    try:
        set_job(message="正在连接 Chrome 并检查抖音登录态。")
        collector.start()
    except Exception as exc:
        set_job(status="failed", message=str(exc), active_creator_id=None, finished_at=now_text(), log_tail=logs)
        return
    try:
        for creator_id in creator_ids:
            set_job(active_creator_id=creator_id)
            with database() as db:
                creator = row_dict(db.execute("SELECT * FROM creators WHERE id=?", (creator_id,)).fetchone())
            if not creator:
                continue
            try:
                limit, since = service.sync_since(creator_id)
                set_job(message=f"正在通过同一采集页面同步 {creator['name']}。")
                result = collector.fetch_creator(creator["platform_creator_id"], since, limit)
                imported = service.upsert_collected_creator(result, creator_id)
                imported_total += imported
                logs.append(f"{creator['name']}: 新增 {imported} 条作品")
                enqueue_creator_transcriptions(creator_id)
            except LoginExpired as exc:
                with database() as db:
                    db.execute("UPDATE creators SET source_status=?, source_message=?, last_crawled_at=? WHERE id=?",
                               ("登录失效", str(exc), now_text(), creator_id))
                set_job(status="failed", message=str(exc), active_creator_id=None, finished_at=now_text(), log_tail=logs[-30:])
                return
            except Exception as exc:
                with database() as db:
                    db.execute("UPDATE creators SET source_status=?, source_message=?, last_crawled_at=? WHERE id=?",
                               ("同步失败", str(exc), now_text(), creator_id))
                logs.append(f"{creator['name']}: {exc}")
    finally:
        collector.close()
    set_job(status="completed", message=f"同步完成，新增导入 {imported_total} 条作品", imported_count=imported_total,
            active_creator_id=None, finished_at=now_text(), log_tail=logs[-30:])


@app.on_event("startup")
def startup():
    initialize_database()
    start_intraday_scheduler(sync_lock=SYNC_LOCK, sync_job=SYNC_JOB, database=database, start_sync=start_sync, sync_payload=SyncPayload)


@app.get("/health")
def health():
    return {
        "ok": True, "database": str(DB_PATH), "collector": "direct-cdp",
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
    set_job(status="running", message="正在使用已登录 Chrome 同步抖音公开内容…", started_at=now_text(), finished_at=None,
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
    output = result.stdout.strip()
    if output:
        for line in output.splitlines():
            print(f"[AudioConvert][video={video_id}] {line}", flush=True)
    if result.returncode:
        print(f"[AudioConvert][video={video_id}] transcriber exited with code {result.returncode}", flush=True)
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
