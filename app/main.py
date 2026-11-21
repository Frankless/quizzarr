"""Quizzarr web server: the API used by the page, the poster proxy and /health.

Local network only, no login (owner's decision). Anything that changes a
setting must carry the X-Quizzarr header, which a foreign web page cannot add
without the browser blocking it (basic CSRF protection)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Body, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import VERSION, cards, clock, quiz, settings
from .catalog import catalog, jellyfin_client
from .questions import Context
from .sources.jellyfin import Jellyfin, JellyfinError, valid_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # no request URLs in the logs
log = logging.getLogger("quizzarr")

STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # warm the catalogue up in the background so the first quiz is quick
    task = asyncio.create_task(_warm_up())
    yield
    task.cancel()
    await catalog.close()


async def _warm_up():
    try:
        await catalog.get()
    except Exception:  # never crash the app on start
        log.exception("Préchargement du catalogue impossible")


app = FastAPI(title="Quizzarr", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def guard(request: Request, call_next):
    if request.method not in ("GET", "HEAD") and request.headers.get("x-quizzarr") != "1":
        return JSONResponse({"detail": "Requête refusée"}, status_code=403)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if not request.url.path.startswith("/img/"):
        # always fresh: no stale page or data on the iPhone
        response.headers["Cache-Control"] = "no-cache"
    return response


def _err(message: str, status: int = 400, kind: str = "error") -> JSONResponse:
    return JSONResponse({"ok": False, "kind": kind, "message": message}, status_code=status)


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html", media_type="text/html")


@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/health")
async def health():
    return {"ok": True, "version": VERSION}


# --------------------------------------------------------------------------- #
# Status, connections, settings
# --------------------------------------------------------------------------- #


def _counts(titles) -> dict:
    movies = sum(1 for t in titles if t.is_movie)
    return {"total": len(titles), "movies": movies, "series": len(titles) - movies}


@app.get("/api/status")
async def status():
    snap = await catalog.get()
    now = clock.now()
    return {
        "version": VERSION,
        "mode": snap.mode,
        "now": clock.fmt_clock(now),
        "catalog": _counts(snap.titles) | {
            "loaded_at": clock.fmt_clock(datetime.fromtimestamp(snap.loaded_at, clock.zone())) if snap.loaded_at else "",
            "error": snap.error,
        },
    }


@app.get("/api/connections")
async def get_connections():
    return settings.public_connections()


@app.put("/api/connections/jellyfin")
async def put_jellyfin(data: dict = Body(...)):
    url = settings.clean_url(data.get("url"))
    if url and not url.startswith(("http://", "https://")):
        return _err("Adresse invalide. Exemple : http://192.168.2.239:8096")
    settings.save_connection("jellyfin", url, data.get("key"))
    catalog.invalidate()
    log.info("Connexion Jellyfin enregistrée")
    return settings.public_connections()


@app.post("/api/connections/jellyfin/test")
async def test_jellyfin(data: dict = Body(default={})):
    """Test the address and key typed in the form (or the saved ones). An empty
    key uses the saved key, only if the address is the saved address."""
    url = settings.clean_url(data.get("url")) or settings.load_connections()["jellyfin"]["url"]
    key = str(data.get("key") or "").strip() or settings.key_for("jellyfin", url)
    if not url:
        return _err("Indique l'adresse du serveur Jellyfin.", kind="missing")
    if not key:
        return _err("Indique la clé API (Jellyfin : Tableau de bord → Clés API).", kind="missing")
    try:
        message = await Jellyfin(url, key, catalog._client()).test()
    except JellyfinError as exc:
        return _err(exc.message, status=200, kind=exc.kind)
    return {"ok": True, "kind": "ok", "message": message}


@app.get("/api/settings")
async def get_settings():
    st = settings.load_settings()
    out = {"jellyfin_user_id": st["jellyfin_user_id"], "users": [], "libraries": [], "error": ""}
    jf = jellyfin_client(catalog._client())
    if jf is None:
        return out
    try:
        out["users"] = await jf.users()
        if st["jellyfin_user_id"]:
            libs = await jf.libraries(st["jellyfin_user_id"])
            out["libraries"] = [
                lib | {"included": settings.library_included(lib["id"], lib["name"], st),
                       "kids": not settings.default_included(lib["name"])}
                for lib in libs
            ]
    except JellyfinError as exc:
        out["error"] = exc.message
    return out


@app.put("/api/settings")
async def put_settings(data: dict = Body(...)):
    settings.save_settings(data)
    catalog.invalidate()
    return await get_settings()


@app.post("/api/refresh")
async def refresh():
    snap = await catalog.get(force=True)
    return {"ok": not snap.error, "mode": snap.mode, "error": snap.error, "catalog": _counts(snap.titles)}


# --------------------------------------------------------------------------- #
# Quiz
# --------------------------------------------------------------------------- #


@app.post("/api/quiz")
async def quiz_step(data: dict = Body(default={})):
    """Body: {answers: [{q, choice}], excluded: [ids], seed}. Replays the answers
    and returns the next question or the result cards."""
    snap = await catalog.get()
    raw_answers = data.get("answers") if isinstance(data.get("answers"), list) else []
    answers = [
        quiz.Given(str(a.get("q", "")), str(a.get("choice", "")))
        for a in raw_answers[:20]
        if isinstance(a, dict)
    ]
    excluded = {str(x) for x in (data.get("excluded") or [])[:2000] if isinstance(x, (str, int))}
    seed = str(data.get("seed") or "")[:64] or None
    now = clock.now()
    state = quiz.run(snap.titles, answers, Context(now=now), seed=seed, excluded=excluded)

    out = {
        "mode": snap.mode,
        "error": snap.error,
        "now": clock.fmt_clock(now),
        "available": len(snap.titles) - len(excluded & set(snap.by_id())),
        "remaining": len(state.titles),
        "answers": [{"q": g.question, "choice": g.choice} for g in state.asked],
        "step": len(state.asked) + 1,
        "max": quiz.MAX_QUESTIONS,
    }
    if state.question:
        q = state.question
        out["question"] = {
            "id": q.id,
            "text": q.text,
            "a": {"label": q.a.label, "hint": q.a.hint},
            "b": {"label": q.b.label, "hint": q.b.hint},
        }
    else:
        base = settings.load_connections()["jellyfin"]["url"] if snap.mode == "jellyfin" else ""
        out["results"] = [cards.card(t, now, base) for t in state.results]
    return out


# --------------------------------------------------------------------------- #
# Posters: proxied so the browser never sees the API key
# --------------------------------------------------------------------------- #

IMAGE_TTL = 600
IMAGE_CACHE_MAX = 200
_images: OrderedDict[str, tuple[float, bytes, str]] = OrderedDict()


@app.get("/img/{item_id}")
async def image(item_id: str):
    if not valid_id(item_id):
        return Response(status_code=404)
    hit = _images.get(item_id)
    if hit and time.time() - hit[0] < IMAGE_TTL:
        _images.move_to_end(item_id)
        return Response(hit[1], media_type=hit[2], headers={"Cache-Control": f"private, max-age={IMAGE_TTL}"})
    snap = catalog.snap
    if snap.mode != "jellyfin" or item_id not in snap.by_id():
        return Response(status_code=404)
    jf = jellyfin_client(catalog._client())
    if jf is None:
        return Response(status_code=404)
    try:
        content, ctype = await jf.image(item_id)
    except JellyfinError:
        return Response(status_code=404)
    if not ctype.startswith("image/"):
        return Response(status_code=404)
    _images[item_id] = (time.time(), content, ctype)
    while len(_images) > IMAGE_CACHE_MAX:
        _images.popitem(last=False)
    return Response(content, media_type=ctype, headers={"Cache-Control": f"private, max-age={IMAGE_TTL}"})
