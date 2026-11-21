"""The question catalogue. Each question has two answers; each answer is a
predicate on a title: the titles it keeps.

To add or change a question, edit this file only: the quiz engine
(quiz.py) picks among whatever is listed in QUESTIONS.

Rule of thumb for missing data (no runtime, no year, no clear genre): the
title is kept on both sides, so a question never hides it by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from . import clock
from .model import Title
from .mood import mood

SHORT_MOVIE_MIN = 105  # under 1 h 45
SHORT_EPISODE_MIN = 40
RECENT_YEARS = 10
DEADLINE_HOUR = 23


@dataclass(frozen=True)
class Context:
    now: datetime


Predicate = Callable[[Title, Context], bool]


@dataclass(frozen=True)
class Answer:
    label: str
    hint: str
    keep: Predicate


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    a: Answer
    b: Answer

    def answer(self, choice: str) -> Answer:
        return self.a if choice == "a" else self.b


def _side(classify: Callable[[Title, Context], str | None], side: str) -> Predicate:
    """Answer `side` keeps titles classified as `side`, plus the undecided ones."""
    return lambda t, ctx: classify(t, ctx) in (side, None)


# --- classifiers: "a", "b" or None (unknown → both sides) -----------------------


def _kind(t: Title, ctx: Context) -> str | None:
    return "a" if t.is_movie else "b"


def _length(t: Title, ctx: Context) -> str | None:
    if t.is_movie:
        if not t.runtime_min:
            return None
        return "a" if t.runtime_min < SHORT_MOVIE_MIN else "b"
    avg = t.series.avg_episode_min if t.series else None
    avg = avg or t.runtime_min
    if not avg:
        return None
    return "a" if avg < SHORT_EPISODE_MIN else "b"


def _mood(t: Title, ctx: Context) -> str | None:
    m = mood(t.genres)
    return {"light": "a", "intense": "b"}.get(m) if m else None


def _seen(t: Title, ctx: Context) -> str | None:
    return "a" if t.played else "b"


def _era(t: Title, ctx: Context) -> str | None:
    if not t.year:
        return None
    return "a" if ctx.now.year - t.year < RECENT_YEARS else "b"


def finishes_before_deadline(t: Title, ctx: Context) -> bool:
    limit = clock.deadline(ctx.now, DEADLINE_HOUR)
    minutes = t.watch_minutes()
    if limit is None or minutes is None:
        return False
    return clock.end_time(ctx.now, minutes) <= limit


QUESTIONS: list[Question] = [
    Question(
        "kind",
        "Un film ou une série ?",
        Answer("Un film", "", _side(_kind, "a")),
        Answer("Une série", "", _side(_kind, "b")),
    ),
    Question(
        "length",
        "Plutôt court ou plutôt long ?",
        Answer("Court", "Film de moins de 1 h 45, épisodes de moins de 40 min", _side(_length, "a")),
        Answer("Long", "On a le temps", _side(_length, "b")),
    ),
    Question(
        "mood",
        "Léger ou intense ?",
        Answer("Léger", "Comédie, animation, romance…", _side(_mood, "a")),
        Answer("Intense", "Thriller, drame, policier…", _side(_mood, "b")),
    ),
    Question(
        "seen",
        "Déjà vu ou jamais vu ?",
        Answer("Déjà vu", "Une valeur sûre", _side(_seen, "a")),
        Answer("Jamais vu", "On découvre", _side(_seen, "b")),
    ),
    Question(
        "era",
        "Récent ou plus ancien ?",
        Answer("Récent", "Moins de 10 ans", _side(_era, "a")),
        Answer("Plus ancien", "Un classique", _side(_era, "b")),
    ),
    Question(
        "finish",
        "On veut avoir fini avant 23 h ?",
        Answer("Fini avant 23 h", "Film entier ou prochain épisode", finishes_before_deadline),
        Answer("Peu importe", "On verra bien", lambda t, ctx: True),
    ),
]

BY_ID = {q.id: q for q in QUESTIONS}
