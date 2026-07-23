from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime
from typing import Any

from fastapi import HTTPException

from config import AVATAR_COLORS
from db import database, row_dict


class FundInsightService:
    """Domain operations used by the HTTP routes and background sync workflow."""

    def normalize_creator_id(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("请填写抖音主页链接或 sec_user_id。")
        if value.startswith(("http://", "https://")):
            match = re.search(r"/user/([^/?#]+)", value)
            if not match:
                raise ValueError("主页链接应包含 /user/<sec_user_id>。")
            return match.group(1)
        if any(char.isspace() for char in value) or len(value) < 8:
            raise ValueError("sec_user_id 格式无效，请粘贴完整主页链接或完整 ID。")
        return value

    @staticmethod
    def _now_text() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def _parse_json(value: str | None, fallback: list | dict):
        try:
            return json.loads(value) if value else fallback
        except json.JSONDecodeError:
            return fallback

    def creator_dict(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        item = row_dict(row)
        if not item:
            return None
        item["tags"] = self._parse_json(item.pop("tags_json", "[]"), [])
        for key in ("consent", "priority", "verified"):
            item[key] = bool(item.get(key))
        return item

    @staticmethod
    def _is_critical_window(published_at: str) -> int:
        try:
            clock = datetime.strptime(published_at, "%Y-%m-%d %H:%M").strftime("%H:%M")
            return int("14:00" <= clock < "15:00")
        except ValueError:
            return 0

    def parse_video(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if not row:
            return None
        item = dict(row)
        item["tags"] = self._parse_json(item.pop("tags_json", "[]"), [])
        if item.get("playback_url") and item.get("id"):
            item["playback_url"] = f"http://127.0.0.1:8000/api/videos/{item['id']}/stream"
        if item.get("topic") == "未分类":
            item["topic"] = ""
        if item.get("published_at"):
            item["is_critical"] = self._is_critical_window(item["published_at"])
        return item

    def video_query(self, where: str = "", params: tuple = ()) -> list[dict[str, Any]]:
        query = """
            SELECT v.*, c.name AS creator_name, c.avatar AS creator_avatar, c.color AS creator_color,
                   c.verified AS creator_verified, c.priority AS creator_priority, c.platform AS creator_platform
            FROM videos v JOIN creators c ON c.id = v.creator_id AND c.platform_creator_id IS NOT NULL
        """ + where + " ORDER BY v.is_critical DESC, v.published_at DESC"
        with database() as db:
            return [self.parse_video(row) for row in db.execute(query, params).fetchall()]

    def dashboard(self) -> dict[str, Any]:
        videos = self.video_query(" WHERE substr(v.published_at, 1, 10) = ?", (date.today().isoformat(),))
        with database() as db:
            creators = [self.creator_dict(row) for row in db.execute(
                "SELECT * FROM creators WHERE platform_creator_id IS NOT NULL ORDER BY priority DESC, name"
            ).fetchall()]
        return {
            "updated_at": self._now_text(), "reference_cutoff": "15:00",
            "summary": {
                "new_count": sum(video["processing_status"] == "unread" for video in videos),
                "later_count": sum(video["processing_status"] == "later" for video in videos),
                "critical_count": sum(video["is_critical"] for video in videos),
            },
            "videos": videos, "creators": creators,
        }

    def list_creators(self) -> list[dict[str, Any]]:
        with database() as db:
            rows = db.execute(
                """SELECT c.*, COUNT(v.id) AS video_count,
                SUM(CASE WHEN v.processing_status = 'unread' THEN 1 ELSE 0 END) AS unread_count
                FROM creators c LEFT JOIN videos v ON v.creator_id=c.id
                WHERE c.platform_creator_id IS NOT NULL GROUP BY c.id ORDER BY c.priority DESC, c.name"""
            ).fetchall()
        return [self.creator_dict(row) for row in rows]

    def save_creator(self, creator_id: int | None, payload: Any) -> dict[str, Any]:
        if not payload.consent:
            raise HTTPException(400, "请确认该主页链接或 ID 由你提供，且仅用于允许范围内的公开内容同步。")
        try:
            platform_creator_id = self.normalize_creator_id(payload.platform_creator_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        name = payload.name.strip() or platform_creator_id
        tags = [tag.strip() for tag in payload.tags if tag.strip()]
        with database() as db:
            duplicate_sql = "SELECT id FROM creators WHERE platform_creator_id=?" + (" AND id!=?" if creator_id else "")
            duplicate_params = (platform_creator_id, creator_id) if creator_id else (platform_creator_id,)
            if db.execute(duplicate_sql, duplicate_params).fetchone():
                raise HTTPException(409, "该博主已在观察清单中。")
            if creator_id is None:
                color = AVATAR_COLORS[db.execute("SELECT COUNT(*) FROM creators").fetchone()[0] % len(AVATAR_COLORS)]
                cursor = db.execute(
                    """INSERT INTO creators (name, handle, avatar, color, tags_json, priority, platform, verified, platform_creator_id,
                    profile_url, consent, source_status, source_message) VALUES (?, ?, ?, ?, ?, ?, '抖音', 0, ?, ?, 1, '待同步', '等待你手动发起真实数据同步。')""",
                    (name, f"@{name}", name[0], color, json.dumps(tags, ensure_ascii=False), int(payload.priority),
                     platform_creator_id, f"https://www.douyin.com/user/{platform_creator_id}"),
                )
                creator_id = cursor.lastrowid
            else:
                if not db.execute("SELECT 1 FROM creators WHERE id=?", (creator_id,)).fetchone():
                    raise HTTPException(404, "博主不存在。")
                db.execute(
                    """UPDATE creators SET name=?, handle=?, avatar=?, tags_json=?, priority=?, platform_creator_id=?, profile_url=?, consent=1
                    WHERE id=?""", (name, f"@{name}", name[0], json.dumps(tags, ensure_ascii=False), int(payload.priority),
                                     platform_creator_id, f"https://www.douyin.com/user/{platform_creator_id}", creator_id),
                )
            return self.creator_dict(db.execute("SELECT * FROM creators WHERE id=?", (creator_id,)).fetchone())

    def delete_creator(self, creator_id: int) -> None:
        with database() as db:
            if not db.execute("SELECT 1 FROM creators WHERE id=?", (creator_id,)).fetchone():
                raise HTTPException(404, "博主不存在。")
            db.execute("DELETE FROM creators WHERE id=?", (creator_id,))

    def select_sync_creators(self, creator_ids: list[int]) -> list[int]:
        with database() as db:
            if creator_ids:
                placeholders = ",".join("?" for _ in creator_ids)
                rows = db.execute(f"SELECT id, consent FROM creators WHERE id IN ({placeholders})", tuple(creator_ids)).fetchall()
            else:
                rows = db.execute("SELECT id, consent FROM creators WHERE platform_creator_id IS NOT NULL").fetchall()
        selected = [row["id"] for row in rows]
        if not selected:
            raise HTTPException(400, "请先添加至少一位抖音博主。")
        if creator_ids and len(selected) != len(set(creator_ids)):
            raise HTTPException(404, "部分博主不存在。")
        if any(not row["consent"] for row in rows):
            raise HTTPException(400, "所选博主缺少用户来源确认。")
        return selected

    def creator_videos(self, creator_id: int, filter_name: str, search: str) -> list[dict[str, Any]]:
        allowed = {"all", "critical", "unread", "processed", "captioned"}
        if filter_name not in allowed:
            raise HTTPException(400, "Unsupported filter")
        clauses, params = ["WHERE v.creator_id = ?"], [creator_id]
        if filter_name == "critical": clauses.append("AND v.is_critical = 1")
        elif filter_name == "unread": clauses.append("AND v.processing_status = 'unread'")
        elif filter_name == "processed": clauses.append("AND v.processing_status = 'processed'")
        elif filter_name == "captioned": clauses.append("AND v.transcript_status = 'completed'")
        if search.strip():
            clauses.append("AND (v.title LIKE ? OR v.transcript_text LIKE ? OR v.summary LIKE ?)")
            params.extend([f"%{search.strip()}%"] * 3)
        return self.video_query(" " + " ".join(clauses), tuple(params))

    def video_detail(self, video_id: int) -> dict[str, Any]:
        videos = self.video_query(" WHERE v.id = ?", (video_id,))
        if not videos:
            raise HTTPException(404, "Video not found")
        with database() as db:
            segments = [row_dict(row) for row in db.execute(
                "SELECT start_time, end_time, content, confidence FROM transcript_segments WHERE video_id=? ORDER BY id", (video_id,)
            ).fetchall()]
        return {"video": videos[0], "segments": segments}

    def update_video_status(self, video_id: int, status: str) -> None:
        with database() as db:
            if not db.execute("SELECT 1 FROM videos WHERE id=?", (video_id,)).fetchone():
                raise HTTPException(404, "Video not found")
            db.execute("UPDATE videos SET processing_status=? WHERE id=?", (status, video_id))


service = FundInsightService()
