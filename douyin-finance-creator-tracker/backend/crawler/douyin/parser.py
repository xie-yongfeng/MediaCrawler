from __future__ import annotations

from typing import Any

from .models import AwemeRaw, CreatorRaw


def _text(value: Any) -> str:
    return str(value or "").strip()


def _first_url(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("url_list", "urlList"):
            urls = value.get(key)
            if isinstance(urls, list) and urls:
                return _text(urls[0])
        return _text(value.get("uri"))
    return ""


def parse_creator(sec_user_id: str, payload: dict[str, Any]) -> CreatorRaw:
    user = payload.get("user") or payload.get("user_info") or payload.get("userInfo") or {}
    return CreatorRaw(
        sec_user_id=_text(user.get("sec_uid") or user.get("sec_user_id") or sec_user_id),
        platform_uid=_text(user.get("uid") or user.get("id")),
        nickname=_text(user.get("nickname") or user.get("nick_name")),
        avatar_url=_first_url(user.get("avatar_larger") or user.get("avatar_medium") or user.get("avatar_thumb")),
    )


def parse_aweme(payload: dict[str, Any]) -> AwemeRaw | None:
    aweme_id = _text(payload.get("aweme_id") or payload.get("awemeId"))
    if not aweme_id:
        return None
    video = payload.get("video") or {}
    music = payload.get("music") or {}
    music_url = _first_url(music.get("play_url") or music.get("playUrl"))
    return AwemeRaw(
        aweme_id=aweme_id,
        create_time=int(payload.get("create_time") or payload.get("createTime") or 0),
        desc=_text(payload.get("desc")),
        cover_url=_first_url(video.get("cover") or video.get("origin_cover") or video.get("dynamic_cover")),
        playback_url=_first_url(video.get("play_addr") or video.get("playAddr")),
        music_download_url=music_url if music_url.startswith(("https://", "http://")) else "",
        duration_seconds=max(0, int(video.get("duration") or 0) // 1000),
        raw_payload=payload,
    )
