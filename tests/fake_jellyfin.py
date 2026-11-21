"""A tiny fake Jellyfin server (canned answers) for the integration test and
for trying the app locally without a real server:

    python -m tests.fake_jellyfin 8097   # then: address http://127.0.0.1:8097, key "test-key"
"""

from __future__ import annotations

import sys

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response

KEY = "test-key"
USER = "a" * 32
LIB_MOVIES, LIB_SHOWS, LIB_KIDS, LIB_KIDS_SHOWS, LIB_MUSIC = "1" * 32, "2" * 32, "3" * 32, "4" * 32, "5" * 32
TICK = 600_000_000  # ticks per minute

M1, M2, M3, S1, S2, K1 = "b1" * 16, "b2" * 16, "b3" * 16, "c1" * 16, "c2" * 16, "d1" * 16

ITEMS = {
    LIB_MOVIES: [
        {"Id": M1, "Type": "Movie", "Name": "Film Un", "ProductionYear": 2021, "RunTimeTicks": 98 * TICK,
         "CommunityRating": 7.25, "OfficialRating": "12", "Genres": ["Comedy"], "Overview": "Un film léger.",
         "ImageTags": {"Primary": "x"}, "UserData": {"Played": False, "PlaybackPositionTicks": 0}},
        {"Id": M2, "Type": "Movie", "Name": "Film Deux", "ProductionYear": 2005, "RunTimeTicks": 140 * TICK,
         "CommunityRating": 8.1, "Genres": ["Thriller", "Crime"], "Overview": "Un film intense.",
         "UserData": {"Played": True}},
        {"Id": M3, "Type": "Movie", "Name": "Film Trois", "ProductionYear": 2019, "RunTimeTicks": 120 * TICK,
         "CommunityRating": 6.0, "Genres": [], "UserData": {"Played": False, "PlaybackPositionTicks": 60 * TICK}},
    ],
    LIB_SHOWS: [
        {"Id": S1, "Type": "Series", "Name": "Série Un", "ProductionYear": 2020, "RunTimeTicks": 45 * TICK,
         "CommunityRating": 8.4, "Genres": ["Drama"], "ImageTags": {"Primary": "y"}, "UserData": {}},
        {"Id": S2, "Type": "Series", "Name": "Série vide", "ProductionYear": 2020, "Genres": [], "UserData": {}},
    ],
    LIB_KIDS: [
        {"Id": K1, "Type": "Movie", "Name": "Dessin animé", "ProductionYear": 2022, "RunTimeTicks": 80 * TICK,
         "Genres": ["Animation"], "UserData": {}},
    ],
    LIB_KIDS_SHOWS: [],
}

EPISODES = {
    S1: [
        {"ParentIndexNumber": 0, "IndexNumber": 1, "Name": "Spécial", "RunTimeTicks": 90 * TICK, "UserData": {}},
        {"ParentIndexNumber": 1, "IndexNumber": 1, "Name": "Pilote", "RunTimeTicks": 45 * TICK, "UserData": {"Played": True}},
        {"ParentIndexNumber": 1, "IndexNumber": 2, "Name": "Deux", "RunTimeTicks": 45 * TICK,
         "UserData": {"Played": False, "PlaybackPositionTicks": 20 * TICK}},
        {"ParentIndexNumber": 1, "IndexNumber": 3, "Name": "Trois", "RunTimeTicks": 45 * TICK, "UserData": {}},
        {"ParentIndexNumber": 2, "IndexNumber": 1, "Name": "Quatre", "RunTimeTicks": 50 * TICK, "UserData": {}},
    ],
    S2: [{"ParentIndexNumber": 0, "IndexNumber": 1, "Name": "Bonus", "RunTimeTicks": 10 * TICK, "UserData": {}}],
}

app = FastAPI()
app.state.calls = []  # (path, token) of every request, to check what Quizzarr sends


@app.middleware("http")
async def check_key(request: Request, call_next):
    app.state.calls.append((request.url.path, request.headers.get("x-emby-token"), str(request.url.query)))
    if request.headers.get("x-emby-token") != KEY:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)


@app.get("/System/Info")
async def info():
    return {"ServerName": "Faux NAS", "Version": "10.10.7", "Id": "f" * 32}


@app.get("/Users")
async def users():
    return [
        {"Id": USER, "Name": "François", "Policy": {"IsAdministrator": True}},
        {"Id": "e" * 32, "Name": "Enfants", "Policy": {"IsAdministrator": False}},
    ]


@app.get("/UserViews")
async def views(userId: str):
    return {"Items": [
        {"Id": LIB_MOVIES, "Name": "Films", "CollectionType": "movies"},
        {"Id": LIB_SHOWS, "Name": "Séries & Animes", "CollectionType": "tvshows"},
        {"Id": LIB_KIDS, "Name": "Films-Enfants", "CollectionType": "movies"},
        {"Id": LIB_KIDS_SHOWS, "Name": "séries enfants", "CollectionType": "tvshows"},
        {"Id": LIB_MUSIC, "Name": "Musique", "CollectionType": "music"},
    ]}


@app.get("/Items")
async def items(parentId: str, userId: str, includeItemTypes: str = "", x_emby_token: str = Header("")):
    return {"Items": ITEMS.get(parentId, []), "TotalRecordCount": len(ITEMS.get(parentId, []))}


@app.get("/Shows/{series_id}/Episodes")
async def episodes(series_id: str, userId: str):
    return {"Items": EPISODES.get(series_id, [])}


@app.get("/Items/{item_id}/Images/Primary")
async def image(item_id: str):
    if item_id not in (M1, S1):
        return Response(status_code=404)
    # 1x1 transparent PNG
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
    )
    return Response(png, media_type="image/png")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8097)
