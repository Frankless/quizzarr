"""Quizzarr against a fake Jellyfin running locally (tests/fake_jellyfin.py)."""

import json
import os
import socket
import stat
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient

from app import main
from app.catalog import catalog
from tests import fake_jellyfin as fake

H = {"X-Quizzarr": "1"}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def jellyfin_url():
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(fake.app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def client(config_dir):
    catalog.snap = type(catalog.snap)()
    catalog.http = None  # a fresh HTTP client for this test's event loop
    main._images.clear()
    with TestClient(main.app) as c:
        yield c


def connect(client, url, key=fake.KEY):
    r = client.put("/api/connections/jellyfin", json={"url": url, "key": key}, headers=H)
    assert r.status_code == 200
    return r.json()


def test_health_and_demo_mode(client):
    assert client.get("/health").status_code == 200
    st = client.get("/api/status").json()
    assert st["mode"] == "demo" and st["catalog"]["total"] == 20
    r = client.post("/api/quiz", json={}, headers=H).json()
    assert r["mode"] == "demo" and "question" in r


def test_writes_need_the_header(client):
    assert client.post("/api/quiz", json={}).status_code == 403
    assert client.put("/api/connections/jellyfin", json={"url": "http://x"}).status_code == 403


def test_connection_test_messages(client, jellyfin_url):
    ok = client.post("/api/connections/jellyfin/test", json={"url": jellyfin_url, "key": fake.KEY}, headers=H).json()
    assert ok["ok"] and "Faux NAS" in ok["message"]
    bad = client.post("/api/connections/jellyfin/test", json={"url": jellyfin_url, "key": "wrong"}, headers=H).json()
    assert not bad["ok"] and bad["kind"] == "auth" and "refusée" in bad["message"]
    down = client.post("/api/connections/jellyfin/test",
                       json={"url": f"http://127.0.0.1:{free_port()}", "key": "k"}, headers=H).json()
    assert not down["ok"] and down["kind"] == "unreachable" and "injoignable" in down["message"]


def test_key_is_stored_privately_and_never_returned(client, config_dir, jellyfin_url):
    body = connect(client, jellyfin_url)
    assert body == {"jellyfin": {"url": jellyfin_url, "has_key": True}}
    path = config_dir / "connections.json"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert json.loads(path.read_text())["jellyfin"]["key"] == fake.KEY
    for url in ("/api/connections", "/api/settings", "/api/status"):
        assert fake.KEY not in client.get(url).text
    # empty key keeps the saved one; a new address drops it
    assert connect(client, jellyfin_url, key="")["jellyfin"]["has_key"]
    assert not connect(client, "http://192.0.2.1:8096", key="")["jellyfin"]["has_key"]


def test_full_flow_with_jellyfin(client, jellyfin_url):
    fake.app.state.calls.clear()
    connect(client, jellyfin_url)
    assert client.get("/api/status").json()["mode"] == "setup"  # no reference user yet

    st = client.get("/api/settings").json()
    assert [u["name"] for u in st["users"]] == ["François", "Enfants"]
    st = client.put("/api/settings", json={"jellyfin_user_id": fake.USER}, headers=H).json()
    libs = {lib["name"]: lib["included"] for lib in st["libraries"]}
    assert libs == {"Films": True, "Séries & Animes": True, "Films-Enfants": False, "séries enfants": False}

    status = client.get("/api/status").json()
    assert status["mode"] == "jellyfin" and not status["catalog"]["error"]
    # 3 movies + 1 series (the series with only specials is dropped, kids library excluded)
    assert status["catalog"] == status["catalog"] | {"total": 4, "movies": 3, "series": 1}

    # every call to Jellyfin carried the key in the header, never in the URL
    assert fake.app.state.calls and all(token == fake.KEY for _, token, _ in fake.app.state.calls)
    assert all(fake.KEY not in query for *_, query in fake.app.state.calls)

    # 4 titles: straight to the results
    r = client.post("/api/quiz", json={"seed": "x"}, headers=H).json()
    cards = {c["name"]: c for c in r["results"]}
    assert set(cards) == {"Film Un", "Film Deux", "Film Trois", "Série Un"}
    s = cards["Série Un"]
    assert s["lines"][0] == "3 épisodes restants · 2 h pour la finir"  # 25 + 45 + 50 (S00 ignored)
    assert s["lines"][1].startswith("Reprendre : S01E02 · fini à")
    assert s["play_url"] == f"{jellyfin_url}/web/index.html#!/details?id={fake.S1}"
    assert s["image"] == f"/img/{fake.S1}"
    assert cards["Film Trois"]["lines"][0] == "2 h · reprise, encore 1 h"
    assert cards["Film Un"]["rating"] == "7,2" or cards["Film Un"]["rating"] == "7,3"

    # kids library ticked on: its movie appears
    client.put("/api/settings", json={"libraries": {fake.LIB_KIDS: True}}, headers=H)
    assert client.get("/api/status").json()["catalog"]["total"] == 5

    # poster proxy: image comes back, unknown ids are refused
    img = client.get(f"/img/{fake.M1}")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert client.get("/img/../../System/Info").status_code == 404
    assert client.get("/img/" + "9" * 32).status_code == 404


def test_jellyfin_down_after_load_keeps_titles(client, jellyfin_url):
    connect(client, jellyfin_url)
    client.put("/api/settings", json={"jellyfin_user_id": fake.USER}, headers=H)
    assert client.get("/api/status").json()["catalog"]["total"] == 4
    # Jellyfin rejects the key from now on: refresh fails, the previous titles stay
    old = fake.KEY
    fake.KEY = "rotated"
    try:
        r = client.post("/api/refresh", headers=H).json()
        assert not r["ok"] and "refusée" in r["error"] and r["catalog"]["total"] == 4
    finally:
        fake.KEY = old
