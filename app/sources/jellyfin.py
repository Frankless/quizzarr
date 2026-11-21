"""Jellyfin: the only source of Quizzarr V1.

Every request carries the API key in the X-Emby-Token header (never in the
URL, so it does not end up in a log)."""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

from ..model import Episode, Title, series_progress, ticks_to_minutes

log = logging.getLogger("quizzarr")

TIMEOUT = httpx.Timeout(15.0, connect=5.0)
EPISODE_CONCURRENCY = 6
LIBRARY_TYPES = {"movies", "tvshows", None, "", "mixed"}
ITEM_FIELDS = "Genres,Overview,RunTimeTicks,CommunityRating,OfficialRating,ProductionYear,ProviderIds,Tags"
ID_RE = re.compile(r"^[0-9a-fA-F]{32}$|^[0-9a-fA-F-]{36}$")


class JellyfinError(Exception):
    """kind: 'unreachable', 'auth', 'not_jellyfin' or 'error'. message: French, for the UI."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def valid_id(value: str) -> bool:
    return bool(ID_RE.match(value or ""))


class Jellyfin:
    def __init__(self, url: str, key: str, client: httpx.AsyncClient):
        self.url = url.rstrip("/")
        self.key = key
        self.client = client

    @property
    def headers(self) -> dict:
        return {"X-Emby-Token": self.key, "Accept": "application/json"}

    async def _request(self, path: str, params: dict | None = None) -> httpx.Response:
        try:
            r = await self.client.get(self.url + path, params=params, headers=self.headers, timeout=TIMEOUT)
        except httpx.InvalidURL:
            raise JellyfinError("unreachable", "Adresse invalide. Exemple : http://192.168.2.239:8096")
        except httpx.TimeoutException:
            raise JellyfinError("unreachable", "Adresse injoignable : Jellyfin ne répond pas (délai dépassé).")
        except (httpx.ConnectError, httpx.NetworkError, httpx.UnsupportedProtocol):
            raise JellyfinError("unreachable", "Adresse injoignable : vérifie l'adresse IP et le port (8096 par défaut).")
        except httpx.HTTPError:
            raise JellyfinError("unreachable", "Adresse injoignable.")
        if r.status_code in (401, 403):
            raise JellyfinError("auth", "Clé API refusée par Jellyfin.")
        if r.status_code == 404:
            raise JellyfinError("not_jellyfin", "Cette adresse répond, mais ce n'est pas Jellyfin (ou l'élément n'existe plus).")
        if r.status_code >= 400:
            raise JellyfinError("error", f"Jellyfin a répondu par une erreur ({r.status_code}).")
        return r

    async def get_json(self, path: str, params: dict | None = None):
        r = await self._request(path, params)
        try:
            return r.json()
        except ValueError:
            raise JellyfinError("not_jellyfin", "Cette adresse répond, mais ce n'est pas Jellyfin.")

    # ------------------------------------------------------------------ #

    async def test(self) -> str:
        info = await self.get_json("/System/Info")
        if not isinstance(info, dict) or "Version" not in info:
            raise JellyfinError("not_jellyfin", "Cette adresse répond, mais ce n'est pas Jellyfin.")
        name = info.get("ServerName") or "Jellyfin"
        return f"Connexion réussie : {name} (Jellyfin {info.get('Version')})."

    async def users(self) -> list[dict]:
        data = await self.get_json("/Users")
        return [
            {"id": u.get("Id"), "name": u.get("Name") or "?", "admin": bool((u.get("Policy") or {}).get("IsAdministrator"))}
            for u in data or []
            if u.get("Id")
        ]

    async def libraries(self, user_id: str) -> list[dict]:
        data = await self.get_json("/UserViews", {"userId": user_id})
        out = []
        for v in (data or {}).get("Items", []):
            ctype = v.get("CollectionType")
            if ctype not in LIBRARY_TYPES:
                continue  # music, books, live TV, playlists, collections…
            out.append({"id": v.get("Id"), "name": v.get("Name") or "?", "type": ctype or "mixed"})
        return out

    async def items(self, user_id: str, library_id: str) -> list[dict]:
        data = await self.get_json(
            "/Items",
            {
                "userId": user_id,
                "recursive": "true",
                "includeItemTypes": "Movie,Series",
                "fields": ITEM_FIELDS,
                "parentId": library_id,
                "enableUserData": "true",
                "enableImageTypes": "Primary",
                "imageTypeLimit": "1",
            },
        )
        return (data or {}).get("Items", [])

    async def episodes(self, series_id: str, user_id: str) -> list[Episode]:
        data = await self.get_json(
            f"/Shows/{series_id}/Episodes",
            {"userId": user_id, "fields": "RunTimeTicks", "enableUserData": "true"},
        )
        out = []
        for e in (data or {}).get("Items", []):
            ud = e.get("UserData") or {}
            out.append(
                Episode(
                    season=e.get("ParentIndexNumber"),
                    number=e.get("IndexNumber"),
                    name=e.get("Name") or "",
                    runtime_min=ticks_to_minutes(e.get("RunTimeTicks")),
                    played=bool(ud.get("Played")),
                    position_min=ticks_to_minutes(ud.get("PlaybackPositionTicks")) or 0.0,
                    last_played=str(ud.get("LastPlayedDate") or ""),
                )
            )
        return out

    async def image(self, item_id: str) -> tuple[bytes, str]:
        r = await self._request(f"/Items/{item_id}/Images/Primary", {"maxHeight": "720", "quality": "85"})
        return r.content, r.headers.get("content-type", "image/jpeg")

    # ------------------------------------------------------------------ #

    async def catalogue(self, user_id: str, library_ids: list[str]) -> list[Title]:
        titles: dict[str, Title] = {}
        for lib in library_ids:
            for item in await self.items(user_id, lib):
                t = to_title(item, lib)
                if t and t.id not in titles:
                    titles[t.id] = t

        sem = asyncio.Semaphore(EPISODE_CONCURRENCY)

        async def fill(t: Title):
            async with sem:
                try:
                    eps = await self.episodes(t.id, user_id)
                except JellyfinError as exc:
                    if exc.kind in ("unreachable", "auth"):
                        raise
                    log.warning("Épisodes illisibles pour une série (%s), ignorée", exc.kind)
                    t.series = None
                    return
            t.series = series_progress(eps)
            t.played = any(e.played for e in eps if e.season != 0)
            if t.series.avg_episode_min:
                t.runtime_min = t.series.avg_episode_min

        series = [t for t in titles.values() if not t.is_movie]
        await asyncio.gather(*(fill(t) for t in series))
        # a series without any (non-special) episode on disk is no use tonight
        return [t for t in titles.values() if t.is_movie or (t.series and t.series.episodes_total)]


def to_title(item: dict, library_id: str) -> Title | None:
    kind = {"Movie": "movie", "Series": "series"}.get(item.get("Type"))
    if not kind or not item.get("Id"):
        return None
    ud = item.get("UserData") or {}
    rating = item.get("CommunityRating")
    return Title(
        id=item["Id"],
        kind=kind,
        name=item.get("Name") or "Sans titre",
        source="jellyfin",
        year=item.get("ProductionYear"),
        rating=round(float(rating), 1) if isinstance(rating, (int, float)) else None,
        official_rating=item.get("OfficialRating") or "",
        genres=list(item.get("Genres") or []),
        overview=(item.get("Overview") or "").strip(),
        runtime_min=ticks_to_minutes(item.get("RunTimeTicks")),
        played=bool(ud.get("Played")),
        position_min=(ticks_to_minutes(ud.get("PlaybackPositionTicks")) or 0.0) if kind == "movie" else 0.0,
        has_image=bool((item.get("ImageTags") or {}).get("Primary")),
        library_id=library_id,
    )
