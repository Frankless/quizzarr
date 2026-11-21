from datetime import datetime

import pytest

from app import clock, quiz
from app.model import Episode, Title, series_progress
from app.mood import mood
from app.questions import BY_ID, Context, finishes_before_deadline
from app.quiz import Given
from app.sources import demo

TZ = clock.zone()
EVENING = Context(now=datetime(2026, 11, 21, 20, 30, tzinfo=TZ))


def movie(id_, minutes=100, year=2020, genres=("Comédie",), played=False, rating=7.0):
    return Title(id=id_, kind="movie", name=id_, year=year, runtime_min=minutes, genres=list(genres),
                 played=played, rating=rating)


def series(id_, ep_minutes=30, count=10, watched=0, year=2020, genres=("Drame",), rating=7.0):
    eps = [Episode(1, i + 1, runtime_min=ep_minutes, played=i < watched) for i in range(count)]
    prog = series_progress(eps)
    return Title(id=id_, kind="series", name=id_, year=year, runtime_min=ep_minutes, genres=list(genres),
                 played=watched > 0, rating=rating, series=prog)


# --- question choice ----------------------------------------------------------


def test_choose_most_balanced_question():
    # 6 movies vs 2 series (kind: 6/2), comedies 4 vs dramas 4 (mood: 4/4) -> mood is the most balanced
    titles = [movie(f"m{i}", genres=("Comédie",) if i < 4 else ("Drame",)) for i in range(6)]
    titles += [series("s1", genres=("Drame",)), series("s2", genres=("Drame",))]
    for t in titles:
        t.year, t.played = 2020, False
    q = quiz.choose_question(titles, set(), EVENING)
    assert q.id == "mood"


def test_tie_keeps_catalogue_order():
    titles = [movie("m1", genres=("Comédie",)), movie("m2", genres=("Drame",)),
              series("s1", genres=("Comédie",)), series("s2", genres=("Drame",))]
    # kind 2/2 and mood 2/2: "kind" comes first in the catalogue
    assert quiz.choose_question(titles, set(), EVENING).id == "kind"
    assert quiz.choose_question(titles, {"kind"}, EVENING).id == "mood"


def test_question_leaving_zero_titles_is_never_proposed():
    titles = [movie(f"m{i}") for i in range(8)]  # only movies, all comedies, all recent, none seen
    q = quiz.choose_question(titles, set(), EVENING)
    assert q is None or q.id not in ("kind", "mood", "era", "seen")


def test_unknown_genre_stays_on_both_sides():
    t = movie("x", genres=("Aventure",))
    q = BY_ID["mood"]
    assert q.a.keep(t, EVENING) and q.b.keep(t, EVENING)
    assert mood(["Comédie", "Drame"]) is None  # tie
    assert mood(["Science-Fiction"]) == "intense"
    assert mood(["comedie"]) == "light"


# --- filtering, stop, back ------------------------------------------------------


def test_filter_and_stop_at_five_or_less():
    cat = demo.catalogue()
    state = quiz.run(cat, [], EVENING, seed=1)
    assert state.question is not None and len(state.titles) == len(cat)
    first = state.question.id
    state = quiz.run(cat, [Given(first, "a")], EVENING, seed=1)
    assert len(state.titles) < len(cat)
    # keep answering "a" until the end
    answers = [Given(first, "a")]
    while state.question:
        answers.append(Given(state.question.id, "a"))
        state = quiz.run(cat, answers, EVENING, seed=1)
    assert len(state.asked) <= quiz.MAX_QUESTIONS
    assert 1 <= len(state.results) <= quiz.TARGET
    assert all(t in state.titles for t in state.results)


def test_stops_after_five_questions_and_picks_five():
    # 40 nearly identical titles: questions barely narrow things down
    titles = [movie(f"m{i}", minutes=90 + (i % 2) * 60, year=2020 - (i % 3) * 15,
                    genres=("Comédie",) if i % 4 else ("Drame",), played=i % 5 == 0, rating=5 + i % 5)
              for i in range(40)]
    answers = []
    state = quiz.run(titles, answers, EVENING, seed="abc")
    while state.question:
        answers.append(Given(state.question.id, "b"))
        state = quiz.run(titles, answers, EVENING, seed="abc")
    assert len(state.asked) <= quiz.MAX_QUESTIONS
    if len(state.titles) > quiz.TARGET:
        assert len(state.results) == quiz.TARGET
    # same seed, same pick (stable when going back and forth)
    again = quiz.run(titles, answers, EVENING, seed="abc")
    assert [t.id for t in again.results] == [t.id for t in state.results]


def test_back_restores_previous_list():
    cat = demo.catalogue()
    s0 = quiz.run(cat, [], EVENING)
    s1 = quiz.run(cat, [Given(s0.question.id, "b")], EVENING)
    s2 = quiz.run(cat, [Given(s0.question.id, "b"), Given(s1.question.id, "a")], EVENING)
    back = quiz.run(cat, [Given(s0.question.id, "b")], EVENING)  # last answer dropped
    assert [t.id for t in back.titles] == [t.id for t in s1.titles]
    assert back.question.id == s1.question.id
    assert len(s2.titles) <= len(s1.titles)


def test_answer_that_would_leave_nothing_is_ignored():
    titles = [movie(f"m{i}") for i in range(8)]
    state = quiz.run(titles, [Given("kind", "b")], EVENING)  # no series at all
    assert state.asked == [] and len(state.titles) == 8


def test_bad_answers_are_ignored():
    cat = demo.catalogue()
    state = quiz.run(cat, [Given("nope", "a"), Given("kind", "z"), Given("kind", "a"), Given("kind", "b")], EVENING)
    assert [g.question for g in state.asked] == ["kind"]
    assert all(t.is_movie for t in state.titles)


def test_empty_catalogue_gives_empty_results():
    state = quiz.run([], [], EVENING)
    assert state.done and state.results == []


def test_excluded_titles_disappear():
    cat = demo.catalogue()
    ids = {t.id for t in cat[:5]}
    state = quiz.run(cat, [], EVENING, excluded=ids)
    assert not ids & {t.id for t in state.titles}


def test_few_titles_go_straight_to_results():
    titles = [movie("a", rating=6), movie("b", rating=8), movie("c", rating=7)]
    state = quiz.run(titles, [], EVENING)
    assert state.done and [t.id for t in state.results] == ["b", "c", "a"]


def test_pick_is_weighted_by_rating():
    titles = [movie("good", rating=10)] + [movie(f"bad{i}", rating=1) for i in range(30)]
    hits = sum("good" in [t.id for t in quiz.pick(titles, 5, seed)] for seed in range(200))
    assert hits > 120  # chance of a 10/10 title vs uniform 5/31 ≈ 16 %


# --- time-based question ----------------------------------------------------------


@pytest.mark.parametrize("hour,minute,minutes,expected", [
    (21, 0, 120, True),   # ends 23:00 exactly
    (21, 1, 120, False),  # ends 23:01
    (22, 30, 25, True),
    (23, 10, 5, False),   # already past 23:00
    (1, 0, 20, False),    # after midnight: tonight's 23:00 is gone
])
def test_finishes_before_23(hour, minute, minutes, expected):
    ctx = Context(now=datetime(2026, 11, 21, hour, minute, tzinfo=TZ))
    assert finishes_before_deadline(movie("m", minutes=minutes), ctx) is expected


def test_series_uses_next_episode_for_deadline():
    ctx = Context(now=datetime(2026, 11, 21, 22, 30, tzinfo=TZ))
    assert finishes_before_deadline(series("short", ep_minutes=25), ctx)
    assert not finishes_before_deadline(series("long", ep_minutes=45), ctx)


def test_finish_question_not_proposed_late():
    late = Context(now=datetime(2026, 11, 21, 23, 30, tzinfo=TZ))
    titles = demo.catalogue()
    split = quiz.split(BY_ID["finish"], titles, late)
    assert not quiz.is_useful(split, len(titles))


def test_length_question_series_uses_average_episode():
    q = BY_ID["length"]
    assert q.a.keep(series("sitcom", ep_minutes=24), EVENING)
    assert not q.a.keep(series("drama", ep_minutes=55), EVENING)
    assert q.a.keep(movie("short", minutes=104), EVENING)
    assert not q.a.keep(movie("long", minutes=105), EVENING)
