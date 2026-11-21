"""The quiz engine: pure functions, no I/O.

The browser keeps only the list of answers given so far. Each step replays
them on the catalogue, so going back is just "drop the last answer": the
previous list comes back exactly as it was.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .model import Title
from .questions import BY_ID, QUESTIONS, Context, Question

MAX_QUESTIONS = 5
TARGET = 5  # stop as soon as this many titles (or fewer) are left


@dataclass(frozen=True)
class Given:
    question: str  # question id
    choice: str  # "a" or "b"


@dataclass
class Split:
    question: Question
    a: list[Title]
    b: list[Title]

    @property
    def imbalance(self) -> int:
        return abs(len(self.a) - len(self.b))


@dataclass
class State:
    titles: list[Title]  # titles still in the running
    asked: list[Given] = field(default_factory=list)  # answers that were applied
    question: Question | None = None  # next question, or None when done
    results: list[Title] = field(default_factory=list)

    @property
    def done(self) -> bool:
        return self.question is None


def split(question: Question, titles: list[Title], ctx: Context) -> Split:
    return Split(
        question,
        [t for t in titles if question.a.keep(t, ctx)],
        [t for t in titles if question.b.keep(t, ctx)],
    )


def is_useful(s: Split, total: int) -> bool:
    """Both answers must leave at least one title, and the question must
    actually narrow things down (one answer keeps fewer than all titles)."""
    return bool(s.a) and bool(s.b) and (len(s.a) < total or len(s.b) < total)


def choose_question(titles: list[Title], asked_ids: set[str], ctx: Context,
                    catalogue: list[Question] = QUESTIONS) -> Question | None:
    """Among the useful questions not asked yet, the one whose split is the
    closest to 50/50. Ties keep the catalogue order."""
    best: Split | None = None
    for q in catalogue:
        if q.id in asked_ids:
            continue
        s = split(q, titles, ctx)
        if not is_useful(s, len(titles)):
            continue
        if best is None or s.imbalance < best.imbalance:
            best = s
    return best.question if best else None


def apply(titles: list[Title], given: Given, ctx: Context) -> list[Title]:
    q = BY_ID[given.question]
    keep = q.answer(given.choice).keep
    return [t for t in titles if keep(t, ctx)]


def pick(titles: list[Title], count: int, seed: int | str | None) -> list[Title]:
    """`count` titles at random, weighted by their rating, then best rated first."""
    if len(titles) <= count:
        chosen = list(titles)
    else:
        rng = random.Random(seed)
        pool = list(titles)
        chosen = []
        while pool and len(chosen) < count:
            weights = [max(t.rating or 6.0, 1.0) for t in pool]
            i = rng.choices(range(len(pool)), weights=weights)[0]
            chosen.append(pool.pop(i))
    return sorted(chosen, key=lambda t: (-(t.rating or 0), t.name.lower()))


def run(catalogue: list[Title], answers: list[Given], ctx: Context, seed: int | str | None = None,
        excluded: set[str] | frozenset[str] = frozenset()) -> State:
    """Replay the answers on the catalogue and return the next question or the results.

    An answer that is unknown, repeated, or that would leave no title at all
    (the catalogue or the clock changed between two steps) is ignored.
    """
    titles = [t for t in catalogue if t.id not in excluded]
    state = State(titles=titles)
    seen: set[str] = set()
    for given in answers:
        if len(state.asked) >= MAX_QUESTIONS or len(state.titles) <= TARGET:
            break
        if given.question not in BY_ID or given.question in seen or given.choice not in ("a", "b"):
            continue
        filtered = apply(state.titles, given, ctx)
        if not filtered:
            continue
        seen.add(given.question)
        state.asked.append(given)
        state.titles = filtered

    if len(state.asked) < MAX_QUESTIONS and len(state.titles) > TARGET:
        state.question = choose_question(state.titles, seen, ctx)
    if state.question is None:
        state.results = pick(state.titles, TARGET, seed)
    return state
