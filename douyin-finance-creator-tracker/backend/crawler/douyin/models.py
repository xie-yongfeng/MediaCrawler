from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CreatorRaw:
    sec_user_id: str
    platform_uid: str
    nickname: str
    avatar_url: str


@dataclass(frozen=True)
class AwemeRaw:
    aweme_id: str
    create_time: int
    desc: str
    cover_url: str
    playback_url: str
    music_download_url: str
    duration_seconds: int
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class CollectResult:
    creator: CreatorRaw
    awemes: list[AwemeRaw]
    reached_cursor: bool
