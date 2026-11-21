"""Time helpers. Every end time is computed in Europe/Brussels (or TZ)."""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def zone() -> ZoneInfo:
    try:
        return ZoneInfo(os.environ.get("TZ") or "Europe/Brussels")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Europe/Brussels")


def now() -> datetime:
    return datetime.now(zone())


def end_time(start: datetime, minutes: float) -> datetime:
    """When a programme of `minutes` started at `start` ends (rounded up to the minute)."""
    return start + timedelta(minutes=math.ceil(minutes))


def fmt_clock(dt: datetime) -> str:
    """22 h 47, 0 h 05 (Belgian French)."""
    return f"{dt.hour} h {dt.minute:02d}"


def fmt_duration(minutes: float | None) -> str:
    """45 min, 1 h 52, 8 h 40, 2 h."""
    if minutes is None:
        return ""
    total = max(0, math.ceil(minutes))
    h, m = divmod(total, 60)
    if h == 0:
        return f"{m} min"
    if m == 0:
        return f"{h} h"
    return f"{h} h {m:02d}"


def deadline(now_: datetime, hour: int = 23) -> datetime | None:
    """Tonight's deadline (23:00). Between midnight and 5 a.m. tonight's
    deadline is already behind us, so there is none."""
    if now_.hour < 5:
        return None
    return now_.replace(hour=hour, minute=0, second=0, microsecond=0)
