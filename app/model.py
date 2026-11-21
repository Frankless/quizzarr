"""Normalised catalogue entries, shared by every source (Jellyfin today,
Radarr/Sonarr later). The quiz and the result cards only know this format."""

from __future__ import annotations

from dataclasses import dataclass, field

TICKS_PER_MINUTE = 600_000_000  # Jellyfin ticks are 100 ns


def ticks_to_minutes(ticks) -> float | None:
    if not ticks:
        return None
    try:
        return int(ticks) / TICKS_PER_MINUTE
    except (TypeError, ValueError):
        return None


@dataclass
class Episode:
    season: int | None
    number: int | None
    name: str = ""
    runtime_min: float | None = None
    played: bool = False
    position_min: float = 0.0
    last_played: str = ""  # ISO date string, only used to pick the episode in progress

    @property
    def code(self) -> str:
        s = f"S{self.season:02d}" if self.season is not None else "S??"
        e = f"E{self.number:02d}" if self.number is not None else "E??"
        return s + e

    @property
    def in_progress(self) -> bool:
        return not self.played and self.position_min > 0

    @property
    def remaining_min(self) -> float | None:
        if self.runtime_min is None:
            return None
        return max(0.0, self.runtime_min - (self.position_min if self.in_progress else 0.0))


@dataclass
class SeriesProgress:
    episodes_total: int
    episodes_left: int
    minutes_left: float  # sum of the remaining unwatched time (episodes without a runtime count as 0)
    started: bool  # at least one episode watched or in progress
    next_episode: Episode | None
    avg_episode_min: float | None
    unknown_runtimes: int = 0  # remaining episodes without a known runtime


@dataclass
class Title:
    id: str
    kind: str  # "movie" or "series"
    name: str
    source: str = "jellyfin"
    year: int | None = None
    rating: float | None = None  # community rating, /10
    official_rating: str = ""
    genres: list[str] = field(default_factory=list)
    overview: str = ""
    runtime_min: float | None = None  # movie: full length; series: average episode
    played: bool = False  # movie: Played; series: at least one episode watched
    position_min: float = 0.0  # movie resume point
    has_image: bool = False
    library_id: str = ""
    series: SeriesProgress | None = None

    @property
    def is_movie(self) -> bool:
        return self.kind == "movie"

    def watch_minutes(self) -> float | None:
        """Minutes needed if we press Play now: what is left of the movie,
        or the next episode of a series."""
        if self.is_movie:
            if self.runtime_min is None:
                return None
            return max(0.0, self.runtime_min - self.position_min)
        if self.series and self.series.next_episode:
            return self.series.next_episode.remaining_min
        return None


def _order_key(ep: Episode):
    big = 10**6
    return (ep.season if ep.season is not None else big, ep.number if ep.number is not None else big)


def series_progress(episodes: list[Episode]) -> SeriesProgress:
    """Remaining episodes, remaining time and next episode of a series.

    - Season 0 (specials) is ignored.
    - Remaining = not played. An episode in progress only counts for what is left of it.
    - Next episode = the episode in progress (most recently played one if several),
      otherwise the first unwatched one in season/episode order. When everything has been
      watched, the next episode is the first one (a rewatch).
    """
    eps = sorted((e for e in episodes if e.season != 0), key=_order_key)
    left = [e for e in eps if not e.played]
    minutes_left = sum(e.remaining_min or 0.0 for e in left)
    unknown = sum(1 for e in left if e.remaining_min is None)
    started = any(e.played or e.in_progress for e in eps)

    in_progress = [e for e in left if e.in_progress]
    if in_progress:
        # most recent first; ties keep the season/episode order
        nxt = max(in_progress, key=lambda e: (e.last_played or "", -eps.index(e)))
    elif left:
        nxt = left[0]
    else:
        nxt = eps[0] if eps else None

    runtimes = [e.runtime_min for e in eps if e.runtime_min]
    avg = sum(runtimes) / len(runtimes) if runtimes else None
    return SeriesProgress(
        episodes_total=len(eps),
        episodes_left=len(left),
        minutes_left=minutes_left,
        started=started,
        next_episode=nxt,
        avg_episode_min=avg,
        unknown_runtimes=unknown,
    )
