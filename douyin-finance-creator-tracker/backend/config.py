import re
from datetime import time, timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DESK_ROOT = BASE_DIR.parent
MEDIA_CRAWLER_ROOT = DESK_ROOT.parent
DB_PATH = BASE_DIR / "data" / "fund_insight.db"
MEDIA_CRAWLER_DB = MEDIA_CRAWLER_ROOT / "database" / "sqlite_tables.db"

AVATAR_COLORS = ["#78e8bb", "#9b8cff", "#62b8ff", "#ffb67b", "#ff8db4"]
CREATOR_HASH_PATTERN = re.compile(r"\[FundInsight\] creator_hash=([0-9a-f]{16})")
CREATOR_NAME_PATTERN = re.compile(r"\[FundInsight\] creator_name=(.+)")
CREATOR_AVATAR_PATTERN = re.compile(r"\[FundInsight\] creator_avatar=(.+)")


# Each entry begins a time period and defines its sync cooldown.
INTRADAY_SYNC_SCHEDULE: tuple[tuple[time, timedelta], ...] = (
    (time(0, 0), timedelta(minutes=30)),
    (time(14, 0), timedelta(minutes=5)),
    (time(14, 30), timedelta(minutes=1)),
    (time(15, 0), timedelta(minutes=30)),
)
