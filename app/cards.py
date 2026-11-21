"""Turn a Title into the result card the browser shows (texts ready in French)."""

from __future__ import annotations

from datetime import datetime

from . import clock
from .model import Title


def play_url(base_url: str, item_id: str) -> str:
    """Page of the title in Jellyfin's web interface, at the address typed in Réglages."""
    return f"{base_url.rstrip('/')}/web/index.html#!/details?id={item_id}"


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def card(t: Title, now: datetime, jellyfin_url: str = "") -> dict:
    out = {
        "id": t.id,
        "kind": t.kind,
        "kind_label": "Film" if t.is_movie else "Série",
        "name": t.name,
        "year": t.year,
        "official_rating": t.official_rating,
        "rating": f"{t.rating:.1f}".replace(".", ",") if t.rating is not None else "",
        "genres": t.genres[:4],
        "overview": t.overview,
        "image": f"/img/{t.id}" if (t.has_image and t.source == "jellyfin") else None,
        "play_url": play_url(jellyfin_url, t.id) if (jellyfin_url and t.source == "jellyfin") else None,
        "lines": [],
    }
    lines: list[str] = out["lines"]
    if t.is_movie:
        if t.runtime_min:
            duration = clock.fmt_duration(t.runtime_min)
            left = t.watch_minutes()
            if t.position_min > 0 and left is not None and left < t.runtime_min:
                lines.append(f"{duration} · reprise, encore {clock.fmt_duration(left)}")
            else:
                lines.append(duration)
            end = clock.end_time(now, left if left is not None else t.runtime_min)
            lines.append(f"Fini à {clock.fmt_clock(end)} si on lance maintenant")
        else:
            lines.append("Durée inconnue")
        return out

    s = t.series
    if not s:
        lines.append("Épisodes inconnus")
        return out
    if s.episodes_left == 0:
        lines.append(f"Déjà vue en entier · {_plural(s.episodes_total, 'épisode', 'épisodes')}")
    else:
        left = _plural(s.episodes_left, "épisode restant", "épisodes restants")
        if s.minutes_left:
            approx = "environ " if s.unknown_runtimes else ""
            lines.append(f"{left} · {approx}{clock.fmt_duration(s.minutes_left)} pour la finir")
        else:
            lines.append(left)
    if not s.started:
        lines.append("Pas encore commencée")
    nxt = s.next_episode
    if nxt:
        label = "Reprendre" if nxt.in_progress else ("Revoir depuis" if s.episodes_left == 0 else "Prochain")
        minutes = nxt.remaining_min
        if minutes is not None:
            lines.append(f"{label} : {nxt.code} · fini à {clock.fmt_clock(clock.end_time(now, minutes))}")
        else:
            lines.append(f"{label} : {nxt.code}")
    return out
