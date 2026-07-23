from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator, Sequence

from config import DB_PATH


@contextmanager
def database() -> Iterator[sqlite3.Connection]:
    """Yield a transaction-scoped connection to the Fund Insight database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def row_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def fetch_one(query: str, params: Sequence = ()) -> sqlite3.Row | None:
    with database() as db:
        return db.execute(query, params).fetchone()


def fetch_all(query: str, params: Sequence = ()) -> list[sqlite3.Row]:
    with database() as db:
        return db.execute(query, params).fetchall()


def execute(query: str, params: Sequence = ()) -> None:
    with database() as db:
        db.execute(query, params)


def get_settings(keys: Sequence[str]) -> dict[str, str]:
    if not keys:
        return {}
    placeholders = ",".join("?" for _ in keys)
    with database() as db:
        return {
            row["key"]: row["value"]
            for row in db.execute(
                f"SELECT key, value FROM app_settings WHERE key IN ({placeholders})", tuple(keys)
            ).fetchall()
        }


def save_settings(values: dict[str, str]) -> None:
    if not values:
        return
    with database() as db:
        db.executemany(
            """INSERT INTO app_settings(key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            values.items(),
        )


def ensure_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def initialize_database() -> None:
    with database() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS creators (
              id INTEGER PRIMARY KEY, name TEXT NOT NULL, handle TEXT NOT NULL DEFAULT '',
              avatar TEXT NOT NULL DEFAULT '博', color TEXT NOT NULL DEFAULT '#78e8bb',
              tags_json TEXT NOT NULL DEFAULT '[]', priority INTEGER NOT NULL DEFAULT 0,
              platform TEXT NOT NULL DEFAULT '抖音', verified INTEGER NOT NULL DEFAULT 0,
              last_synced TEXT, platform_creator_id TEXT UNIQUE, profile_url TEXT,
              consent INTEGER NOT NULL DEFAULT 0, source_status TEXT NOT NULL DEFAULT '待同步',
              source_message TEXT NOT NULL DEFAULT '', last_crawled_at TEXT, crawler_creator_hash TEXT
            );
            CREATE TABLE IF NOT EXISTS videos (
              id INTEGER PRIMARY KEY, creator_id INTEGER NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
              external_id TEXT UNIQUE, title TEXT NOT NULL, published_at TEXT NOT NULL,
              discovered_at TEXT NOT NULL, duration_seconds INTEGER NOT NULL DEFAULT 0,
              topic TEXT NOT NULL DEFAULT '未分类', summary TEXT NOT NULL DEFAULT '',
              viewpoint TEXT NOT NULL DEFAULT '', fact_status TEXT NOT NULL DEFAULT '未核验',
              risk_note TEXT NOT NULL DEFAULT '内容仅作信息整理，不构成投资建议。',
              source_url TEXT NOT NULL, cover_url TEXT, playback_url TEXT, processing_status TEXT NOT NULL DEFAULT 'unread',
              is_critical INTEGER NOT NULL DEFAULT 0, transcript_status TEXT NOT NULL DEFAULT 'unavailable',
              transcript_progress INTEGER NOT NULL DEFAULT 0, transcript_confidence INTEGER,
              transcript_updated_at TEXT, transcript_text TEXT, tags_json TEXT NOT NULL DEFAULT '[]',
              source_status TEXT NOT NULL DEFAULT '用户提供来源'
            );
            CREATE TABLE IF NOT EXISTS transcript_segments (
              id INTEGER PRIMARY KEY AUTOINCREMENT, video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
              start_time TEXT NOT NULL, end_time TEXT NOT NULL, content TEXT NOT NULL, confidence INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS app_settings (
              key TEXT PRIMARY KEY, value TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_videos_creator_published ON videos(creator_id, published_at DESC);
            """
        )
        for table, column, definition in [
            ("creators", "platform_creator_id", "TEXT"), ("creators", "profile_url", "TEXT"),
            ("creators", "consent", "INTEGER NOT NULL DEFAULT 0"),
            ("creators", "source_status", "TEXT NOT NULL DEFAULT '待同步'"),
            ("creators", "source_message", "TEXT NOT NULL DEFAULT ''"),
            ("creators", "last_crawled_at", "TEXT"), ("creators", "crawler_creator_hash", "TEXT"),
            ("videos", "external_id", "TEXT"), ("videos", "cover_url", "TEXT"),
            ("videos", "playback_url", "TEXT"),
            ("videos", "source_status", "TEXT NOT NULL DEFAULT '用户提供来源'"),
        ]:
            ensure_column(db, table, column, definition)
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_creators_platform_id ON creators(platform_creator_id)")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_videos_external_id ON videos(external_id)")
