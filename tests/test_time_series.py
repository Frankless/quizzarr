from datetime import datetime

from app import cards, clock
from app.model import Episode, Title, series_progress

TZ = clock.zone()
NOW = datetime(2026, 11, 21, 21, 3, tzinfo=TZ)


def test_formats():
    assert clock.fmt_clock(datetime(2026, 1, 1, 22, 47, tzinfo=TZ)) == "22 h 47"
    assert clock.fmt_clock(datetime(2026, 1, 1, 0, 5, tzinfo=TZ)) == "0 h 05"
    assert clock.fmt_duration(45) == "45 min"
    assert clock.fmt_duration(112) == "1 h 52"
    assert clock.fmt_duration(520) == "8 h 40"
    assert clock.fmt_duration(120) == "2 h"
    assert clock.fmt_duration(44.2) == "45 min"  # rounded up


def test_end_time_crosses_midnight_and_dst():
    assert clock.fmt_clock(clock.end_time(NOW, 104)) == "22 h 47"
    late = datetime(2026, 11, 21, 23, 30, tzinfo=TZ)
    assert clock.fmt_clock(clock.end_time(late, 50)) == "0 h 20"
    # Night of the switch to winter time (25 Oct 2026, 3:00 -> 2:00): wall clock arithmetic
    assert clock.end_time(datetime(2026, 10, 24, 22, 0, tzinfo=TZ), 30).hour == 22


def eps(spec):
    """spec: list of (season, number, minutes, played, position)."""
    return [Episode(s, n, f"E{n}", m, p, pos) for s, n, m, p, pos in spec]


def test_series_remaining_time_ignores_specials():
    p = series_progress(eps([
        (0, 1, 90, False, 0),          # special: ignored
        (1, 1, 50, True, 0),
        (1, 2, 50, True, 0),
        (1, 3, 50, False, 0),
        (2, 1, 40, False, 0),
        (2, 2, 40, False, 0),
    ]))
    assert p.episodes_total == 5
    assert p.episodes_left == 3
    assert p.minutes_left == 130
    assert p.next_episode.code == "S01E03"
    assert p.started


def test_series_next_is_episode_in_progress():
    p = series_progress(eps([
        (1, 1, 45, True, 0),
        (1, 2, 45, False, 0),
        (1, 3, 45, False, 30),  # watched halfway, out of order
    ]))
    assert p.next_episode.code == "S01E03"
    assert p.next_episode.remaining_min == 15
    assert p.minutes_left == 45 + 15


def test_series_order_is_season_then_episode():
    p = series_progress(eps([(2, 1, 30, False, 0), (1, 10, 30, False, 0), (1, 2, 30, False, 0)]))
    assert p.next_episode.code == "S01E02"
    assert not p.started


def test_series_fully_watched():
    p = series_progress(eps([(1, 1, 30, True, 0), (1, 2, 30, True, 0)]))
    assert p.episodes_left == 0 and p.minutes_left == 0
    assert p.next_episode.code == "S01E01"


def test_movie_card_end_time():
    t = Title(id="m", kind="movie", name="M", runtime_min=104, has_image=True, source="jellyfin")
    c = cards.card(t, NOW, "http://jf:8096")
    assert c["lines"] == ["1 h 44", "Fini à 22 h 47 si on lance maintenant"]
    assert c["play_url"] == "http://jf:8096/web/index.html#!/details?id=m"
    assert c["image"] == "/img/m"


def test_series_card_texts():
    episodes = [Episode(1, i, runtime_min=40, played=i <= 4) for i in range(1, 13)]
    episodes += [Episode(2, i, runtime_min=40) for i in range(1, 6)]
    t = Title(id="s", kind="series", name="S", series=series_progress(episodes), source="demo")
    c = cards.card(t, NOW)
    assert c["lines"][0] == "13 épisodes restants · 8 h 40 pour la finir"
    assert c["lines"][1] == "Prochain : S01E05 · fini à 21 h 43"
    assert c["play_url"] is None  # demo: no Jellyfin link

    fresh = Title(id="f", kind="series", name="F", series=series_progress([Episode(1, 1, runtime_min=30)]))
    assert "Pas encore commencée" in cards.card(fresh, NOW)["lines"]
