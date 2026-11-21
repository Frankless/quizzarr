"""Connections and settings, stored in /config.

- connections.json (mode 600): Jellyfin address and API key. The key never
  leaves the server: the browser only learns whether one is saved.
- settings.json: reference user and libraries to include.

Radarr and Sonarr will get their own entry in SERVICES later.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from pathlib import Path

log = logging.getLogger("quizzarr")

CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "/config"))
CONNECTIONS_FILE = CONFIG_DIR / "connections.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"

SERVICES = ("jellyfin",)  # later: "radarr", "sonarr"

# Libraries left out unless ticked: compared without case, accents, dashes or spaces.
KIDS_LIBRARIES = {"filmsenfants", "seriesenfants"}


def clean_url(value) -> str:
    value = str(value or "").strip().rstrip("/")
    if value and "://" not in value:
        value = "http://" + value
    return value


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        log.warning("%s illisible, ignoré", path.name)
        return {}


def _write(path: Path, data: dict, private: bool = False) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    # create the file with restricted rights from the start (no window where it is world-readable)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600 if private else 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    if private:
        os.chmod(tmp, 0o600)
    tmp.replace(path)


# --------------------------------------------------------------------------- #
# Connections
# --------------------------------------------------------------------------- #


def load_connections() -> dict:
    saved = _read(CONNECTIONS_FILE)
    out = {}
    for svc in SERVICES:
        entry = saved.get(svc) if isinstance(saved.get(svc), dict) else {}
        out[svc] = {"url": clean_url(entry.get("url")), "key": str(entry.get("key") or "").strip()}
    return out


def save_connection(service: str, url, key=None) -> dict:
    """Save one service. An empty key keeps the saved one, unless the address
    changed: the old key is never sent to a new server."""
    conns = load_connections()
    current = conns[service]
    url = clean_url(url)
    key = str(key or "").strip()
    if not key:
        key = current["key"] if url == current["url"] else ""
    if not url:
        key = ""
    conns[service] = {"url": url, "key": key}
    _write(CONNECTIONS_FILE, conns, private=True)
    return conns[service]


def key_for(service: str, url) -> str:
    """Saved key, only if it belongs to this exact address."""
    current = load_connections()[service]
    return current["key"] if clean_url(url) == current["url"] else ""


def public_connections() -> dict:
    """What the browser may see: address and 'key present', never the key."""
    return {svc: {"url": c["url"], "has_key": bool(c["key"])} for svc, c in load_connections().items()}


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #


def norm_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text.lower())


def default_included(library_name: str) -> bool:
    return norm_name(library_name) not in KIDS_LIBRARIES


def load_settings() -> dict:
    saved = _read(SETTINGS_FILE)
    libs = saved.get("libraries") if isinstance(saved.get("libraries"), dict) else {}
    return {
        "jellyfin_user_id": str(saved.get("jellyfin_user_id") or ""),
        "libraries": {str(k): bool(v) for k, v in libs.items()},
    }


def save_settings(data: dict) -> dict:
    current = load_settings()
    if "jellyfin_user_id" in data:
        uid = str(data.get("jellyfin_user_id") or "")
        current["jellyfin_user_id"] = uid if re.fullmatch(r"[0-9a-fA-F-]{0,64}", uid) else ""
    if isinstance(data.get("libraries"), dict):
        for k, v in data["libraries"].items():
            current["libraries"][str(k)[:64]] = bool(v)
    _write(SETTINGS_FILE, current)
    return current


def library_included(lib_id: str, name: str, settings: dict) -> bool:
    choice = settings["libraries"].get(lib_id)
    return default_included(name) if choice is None else choice
