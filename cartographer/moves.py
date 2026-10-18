"""Moves — the *kind* of question, a coarser layer where roads can finally stack.

Thirteen sessions mapped questions by their *content*: "what is virtue" and "is
virtue taught" are nodes, and a path is the sequence of them. That layer has one
stubborn property, visible on every corpus so far: two *different* conversations
almost never share a transition. Session 013 drew the Socratic map and found 449
edges, every one weight 1. The founding dream — "ten thousand people wrestled with
the same question" — needs roads that many paths travel, and content nodes are too
fine-grained for that to happen on any corpus we can honestly hold.

The charter says the map is of *topology*, not content. So this module asks a
different question of each question: not *what* is being asked but *what kind of
move* the asker is making. A definition ("what is X") is a different act of
thinking from a yes/no check ("is it not so?"), a causal probe ("why"), a
counterfactual ("what if", "suppose"), a request for a method ("how do I"). Moves
are a small closed vocabulary, so paths over moves *do* overlap — the same
transition (say, ``define → confirm``) recurs across conversations and corpora —
and the shape of an inquiry becomes comparable across topics that share no words.

The vocabulary (``MOVES``), each decided from the opening words only:

  * ``define``  — what is / what does / explain / define
  * ``cause``   — why
  * ``method``  — how (not how-many), help me, i want to, walk me through
  * ``fact``    — when / where / who / how many / how much
  * ``choose``  — which, or an inverted question holding an "or" (X or Y?)
  * ``suppose`` — what if / what about / suppose / imagine / if
  * ``confirm`` — an inverted yes/no question (is / do / can / would ...)
  * ``propose`` — the **residual**: no opener the rules recognize. In practice
    mostly a statement offered with a question mark for assent ("they must be
    temperate and just?") — Socrates' signature move — but it also catches
    anything the rules miss (a vocative before the wh-word, "to what then do we
    give the name of figure"). It is named for the common case; read it as
    "everything else", and read a large ``propose`` share as partly the
    classifier's blind spot.

Honest about what this is: **a lexical opener heuristic**, not a model of speech
acts. It reads the first few words after stripping connectives ("or", "but",
"now") and nothing else. A rhetorical "why would anyone do that" is a ``cause``
move here even though no cause is sought. It is coarse on purpose — coarse is
what lets roads stack — and every rule is a line you can read below.

The reading this layer earns is about **order**, not loops. With eight nodes, any
path of nine questions revisits a node by pigeonhole, so loop-vs-resolve (see
:mod:`cartographer.loops`) means nothing at this resolution and is not offered.
Instead:

  * :func:`transition_lift` — for each move→move transition, observed count over
    the count expected if the next move were independent of the current one. A
    lift above 1 is a real sequential tendency; a weight-40 edge between two
    common moves can have lift below 1 (it happens *less* than chance).
  * :func:`persistence` — do askers stay on the same move (a run of yes/no checks,
    a barrage of what-ifs) more than the composition of their own paths implies?
    Tested against a **within-path shuffle**: the moves of each path are
    permuted, which keeps every path's mix of moves and destroys only their
    order. If real paths repeat moves more than almost all shuffles do, the
    *order* is carrying signal. The p-value is a permutation p-value with a fixed
    seed, so the result is deterministic.

What it found when first run (session 014): the Socratic dialogues repeat moves
back-to-back 141 times against ~111 expected from shuffling (p ≈ 0.001), and
the excess survives shuffling within 10-question windows (ratio ~1.13, p ≈
0.02) — Socrates strings yes/no checks and suppositions together. The CMV
sample, whose pooled lifts *look* even more persistent, shows none (ratio 1.00,
p ≈ 0.5): its apparent momentum was each comment's own mix, not order.

The shuffle is an honest null but not a complete one. It controls for each
path's composition, not for *sections within* a path: a Socratic dialogue is one
path of 300+ questions, and its geometry lesson asks "how many" over and over
because the topic is counting, not because the asker has momentum. Persistence
can't tell those apart. Name it; don't hide it.
"""

import collections
import random
import re
from dataclasses import dataclass

from .paths import PathGraph, conversation_path

DEFINE = "define"
CAUSE = "cause"
METHOD = "method"
FACT = "fact"
CHOOSE = "choose"
SUPPOSE = "suppose"
CONFIRM = "confirm"
PROPOSE = "propose"

MOVES = (DEFINE, CAUSE, METHOD, FACT, CHOOSE, SUPPOSE, CONFIRM, PROPOSE)

# Inverted-question openers: an auxiliary or modal first means a yes/no question
# ("is it", "do you", "would you not", "isn't it").
_AUXILIARIES = frozenset(
    """
    do does did is are was were am can could would will shall should may might
    must have has had isn't aren't don't doesn't didn't wasn't weren't won't
    wouldn't can't couldn't shouldn't haven't hasn't
    """.split()
)

# Connectives stripped from the front before reading the opener, so "or is the
# nature of health always the same" reads as the yes/no question it is.
_CONNECTIVES = frozenset(
    {"or", "and", "but", "now", "then", "yet", "so", "well", "besides", "still",
     "again", "nay"}
)

# "how" + one of these asks for a quantity, not a method.
_QUANTITY = frozenset({"many", "much", "long", "often", "far", "old", "big"})

_FACT_OPENERS = frozenset({"when", "where", "who", "whom", "whose"})
_DEFINE_OPENERS = frozenset({"what", "what's", "whats"})

# After "tell me", a wh-word means the real question follows ("tell me, what is
# virtue"); otherwise "tell me X" is a request, read as method.
_EMBEDDED_WH = frozenset({"what", "why", "how", "which", "whether", "who", "when", "where"})

_SUPPOSE_PREFIXES = ("what if", "what about", "suppose", "imagine", "let us suppose")
_METHOD_PREFIXES = (
    "help me", "walk me through", "i want to", "i need to", "i'm trying to",
    "im trying to", "i am trying to", "show me", "teach me", "tell me",
    "what's the best way", "whats the best way", "what should i",
)

_NON_WORD = re.compile(r"[^\w\s']")


def classify_move(question: str) -> str:
    """The move a question makes, read from its opening words. Always one of MOVES.

    Takes an extracted question (any case, punctuation tolerated). Rule order
    matters and is the whole classifier: cause, suppose, choose, fact, method,
    define, confirm, and ``propose`` for anything left.
    """
    words = _NON_WORD.sub(" ", question.lower()).split()
    while words and words[0] in _CONNECTIVES:
        words.pop(0)
    if words[:2] == ["tell", "me"] and len(words) > 2 and words[2] in _EMBEDDED_WH:
        words = words[2:]
    if not words:
        return PROPOSE

    first = words[0]
    second = words[1] if len(words) > 1 else ""
    text = " ".join(words)

    if first == "why":
        return CAUSE
    if first == "if" or text.startswith(_SUPPOSE_PREFIXES):
        return SUPPOSE
    if first == "which" or (first in _AUXILIARIES and "or" in words[1:]):
        return CHOOSE
    if first in _FACT_OPENERS or (first == "how" and second in _QUANTITY):
        return FACT
    if first == "how" or text.startswith(_METHOD_PREFIXES):
        return METHOD
    if first in _DEFINE_OPENERS or first in {"explain", "define"}:
        return DEFINE
    if first in _AUXILIARIES:
        return CONFIRM
    return PROPOSE


def move_path(conversation: dict) -> list[str]:
    """A conversation's path re-read as moves: one move per extracted question."""
    return [classify_move(q) for q in conversation_path(conversation)]


def build_move_graph(conversations: list[dict]) -> PathGraph:
    """A :class:`PathGraph` whose nodes are moves instead of questions.

    Same structure as :func:`cartographer.paths.build_graph`, so anything that
    reads a PathGraph reads this — but read loop shapes off it with care: with
    eight nodes, long paths revisit by pigeonhole (see the module docstring).
    """
    graph = PathGraph()
    for conversation in conversations:
        graph.add_path(move_path(conversation))
    return graph


@dataclass(frozen=True)
class Lift:
    """One move→move transition against independence."""

    src: str
    dst: str
    count: int
    expected: float

    @property
    def lift(self) -> float:
        """Observed over expected. Above 1: this transition happens more than chance."""
        return self.count / self.expected if self.expected else 0.0


def transition_lift(graph: PathGraph) -> list[Lift]:
    """Every observed transition with its lift, most-travelled first.

    Expected count for ``a → b`` is ``out(a) · in(b) / total``, where ``out`` and
    ``in`` count how often a move starts and ends a transition — the count you'd
    see if the next move ignored the current one. Ties break on (src, dst) so the
    order is deterministic.

    Caution, learned on CMV: this is independence *pooled across the corpus*.
    When paths differ in their mix — one comment is all what-ifs, another all
    yes/no checks — pooled independence underestimates same-move transitions, so
    the diagonal (``a → a``) lifts above 1 even if no asker has any momentum. On
    the CMV sample ``suppose → suppose`` lifts 3.3 while the within-path shuffle
    finds no persistence at all. Read diagonal lifts through :func:`persistence`.
    """
    total = sum(graph.edges.values())
    out_counts: "collections.Counter[str]" = collections.Counter()
    in_counts: "collections.Counter[str]" = collections.Counter()
    for (src, dst), weight in graph.edges.items():
        out_counts[src] += weight
        in_counts[dst] += weight
    lifts = [
        Lift(src, dst, weight, out_counts[src] * in_counts[dst] / total)
        for (src, dst), weight in graph.edges.items()
    ]
    lifts.sort(key=lambda item: (-item.count, item.src, item.dst))
    return lifts


def _repeats(path: list[str]) -> int:
    return sum(1 for a, b in zip(path, path[1:]) if a == b)


@dataclass(frozen=True)
class Persistence:
    """Same-move repeats in real paths vs. within-path shuffles of the same moves."""

    observed: int        # transitions where the move repeated (a → a)
    transitions: int     # all transitions
    shuffled_mean: float # mean repeats over the shuffles
    p_value: float       # share of shuffles with repeats >= observed (add-one)
    trials: int

    @property
    def ratio(self) -> float:
        """Observed repeats over the shuffle mean. Above 1: askers stay on a move."""
        return self.observed / self.shuffled_mean if self.shuffled_mean else 0.0


def persistence(
    paths: list[list[str]],
    *,
    window: int | None = None,
    trials: int = 2000,
    seed: int = 0,
) -> Persistence:
    """Permutation test: do moves repeat back-to-back more than order-free chance?

    Each trial shuffles a copy of every path (never the caller's lists)
    and counts back-to-back repeats. The p-value uses
    the add-one convention ``(hits + 1) / (trials + 1)`` so it is never reported as
    exactly zero from a finite number of shuffles. Seeded: same input, same answer.

    ``window`` cuts every path into consecutive chunks of that many moves before
    testing, so moves are only shuffled *within* a chunk — a tighter null that
    absorbs topical sections (a run of "how many" questions during a geometry
    lesson). Repeats across a chunk boundary are not counted, in the real paths
    or the shuffles, so the comparison stays like-for-like.
    """
    if window is not None:
        if window < 2:
            raise ValueError("window must be at least 2 (a 1-move chunk has no transitions)")
        paths = [p[i:i + window] for p in paths for i in range(0, len(p), window)]
    rng = random.Random(seed)
    observed = sum(_repeats(p) for p in paths)
    transitions = sum(max(len(p) - 1, 0) for p in paths)
    shuffled_total = 0
    hits = 0
    for _ in range(trials):
        repeats = 0
        for path in paths:
            shuffled = list(path)
            rng.shuffle(shuffled)
            repeats += _repeats(shuffled)
        shuffled_total += repeats
        if repeats >= observed:
            hits += 1
    return Persistence(
        observed=observed,
        transitions=transitions,
        shuffled_mean=shuffled_total / trials if trials else 0.0,
        p_value=(hits + 1) / (trials + 1),
        trials=trials,
    )
