"""Light / intense mood from Jellyfin genres. The table lives in moods.json
(or /config/moods.json if François made his own copy)."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from .settings import CONFIG_DIR

log = logging.getLogger("quizzarr")
DEFAULT_FILE = Path(__file__).parent / "moods.json"


def normalise(text: str) -> str:
    """'Science-Fiction' -> 'sciencefiction', 'Épouvante' -> 'epouvante'."""
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text.lower())


@lru_cache(maxsize=1)
def table() -> tuple[frozenset[str], frozenset[str]]:
    for path in (CONFIG_DIR / "moods.json", DEFAULT_FILE):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text("utf-8"))
            return (
                frozenset(normalise(g) for g in data.get("light", [])),
                frozenset(normalise(g) for g in data.get("intense", [])),
            )
        except (OSError, ValueError, AttributeError):
            log.warning("Fichier d'ambiances illisible : %s, ignoré", path)
    return frozenset(), frozenset()


def mood(genres: list[str], light: frozenset[str] | None = None, intense: frozenset[str] | None = None) -> str | None:
    """'light', 'intense', or None when the genres do not tell (no known genre, or a tie)."""
    if light is None or intense is None:
        light, intense = table()
    keys = {normalise(g) for g in genres or []}
    score = len(keys & light) - len(keys & intense)
    if score > 0:
        return "light"
    if score < 0:
        return "intense"
    return None
