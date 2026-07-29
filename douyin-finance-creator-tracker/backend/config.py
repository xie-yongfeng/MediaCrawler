from datetime import time, timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "fund_insight.db"

AVATAR_COLORS = ["#78e8bb", "#9b8cff", "#62b8ff", "#ffb67b", "#ff8db4"]

# Each entry begins a time period and defines its sync cooldown.
INTRADAY_SYNC_SCHEDULE: tuple[tuple[time, timedelta], ...] = (
    (time(0, 0), timedelta(minutes=30)),
    (time(14, 0), timedelta(minutes=5)),
    (time(14, 30), timedelta(minutes=1)),
    (time(15, 0), timedelta(minutes=30)),
)
