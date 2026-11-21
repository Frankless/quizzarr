"""In-memory catalogue cache: Jellyfin when it is connected, the demo library
otherwise. Refreshed when a quiz starts and the copy is older than 10 minutes,
or on demand (Réglages → Actualiser)."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx

from . import settings
from .model import Title
from .sources import demo
from .sources.jellyfin import Jellyfin, JellyfinError

log = logging.getLogger("quizzarr")
MAX_AGE = 600  # seconds


@dataclass
class Snapshot:
    titles: list[Title] = field(default_factory=list)
    mode: str = "demo"  # "demo", "jellyfin" or "setup" (connected, reference user not chosen yet)
    loaded_at: float = 0.0
    error: str = ""  # last refresh error (French), the previous titles are kept meanwhile
    key: tuple = ()  # connection + settings the titles were loaded with

    def by_id(self) -> dict[str, Title]:
        return {t.id: t for t in self.titles}


def jellyfin_client(http: httpx.AsyncClient) -> Jellyfin | None:
    conn = settings.load_connections()["jellyfin"]
    if not (conn["url"] and conn["key"]):
        return None
    return Jellyfin(conn["url"], conn["key"], http)


class Catalog:
    def __init__(self):
        self.snap = Snapshot()
        self._lock = asyncio.Lock()
        self.http: httpx.AsyncClient | None = None

    def _client(self) -> httpx.AsyncClient:
        if self.http is None:
            self.http = httpx.AsyncClient(follow_redirects=False)
        return self.http

    @staticmethod
    def _current_key() -> tuple:
        conn = settings.load_connections()["jellyfin"]
        st = settings.load_settings()
        return (conn["url"], bool(conn["key"]), st["jellyfin_user_id"], tuple(sorted(st["libraries"].items())))

    def stale(self, max_age: float = MAX_AGE) -> bool:
        return (
            not self.snap.loaded_at
            or time.time() - self.snap.loaded_at > max_age
            or self.snap.key != self._current_key()
        )

    async def get(self, max_age: float = MAX_AGE, force: bool = False) -> Snapshot:
        if not force and not self.stale(max_age):
            return self.snap
        async with self._lock:
            if not force and not self.stale(max_age):
                return self.snap
            await self._refresh()
            return self.snap

    async def _refresh(self) -> None:
        key = self._current_key()
        jf = jellyfin_client(self._client())
        if jf is None:
            self.snap = Snapshot(titles=demo.catalogue(), mode="demo", loaded_at=time.time(), key=key)
            return
        user_id = settings.load_settings()["jellyfin_user_id"]
        if not user_id:
            self.snap = Snapshot(mode="setup", loaded_at=time.time(), key=key,
                                 error="Choisis l'utilisateur de référence dans Réglages.")
            return
        try:
            st = settings.load_settings()
            libs = await jf.libraries(user_id)
            ids = [lib["id"] for lib in libs if settings.library_included(lib["id"], lib["name"], st)]
            started = time.monotonic()
            titles = await jf.catalogue(user_id, ids)
            log.info("Catalogue Jellyfin chargé : %d titres, %d bibliothèques, %.1f s",
                     len(titles), len(ids), time.monotonic() - started)
            self.snap = Snapshot(titles=titles, mode="jellyfin", loaded_at=time.time(), key=key)
        except JellyfinError as exc:
            log.warning("Catalogue Jellyfin non rafraîchi : %s", exc.kind)
            same_setup = self.snap.mode == "jellyfin" and self.snap.key == key
            # keep the previous titles when we have some for the same setup; retry in a minute
            self.snap = Snapshot(
                titles=self.snap.titles if same_setup else [],
                mode="jellyfin",
                loaded_at=time.time() - MAX_AGE + 60,
                error=exc.message,
                key=key,
            )

    def invalidate(self) -> None:
        self.snap.loaded_at = 0.0

    async def close(self) -> None:
        if self.http is not None:
            await self.http.aclose()
            self.http = None


catalog = Catalog()
