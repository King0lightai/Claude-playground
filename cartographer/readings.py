"""A bench for grading *competing* readings of a conversation against ground truth.

Session 011 built :mod:`cartographer.grade` to score one reading — the
loop/resolve *shape* — against a corpus's answer key, and left a promise in its
own docstring: "``grade.py`` doesn't care *which* shape feeds ``circled``, so a
new reading plugs straight in." This module makes that promise literally true. A
**reading** is any function that looks at one conversation (its clustered
question path and its raw record) and returns a single boolean; the bench grades
*any* reading against the label with the same phi correlation grading already
uses, over the same corpus-wide merge, so two readings can be compared on equal
footing.

Why this is the tool the project actually needs now. The CMV excursion (sessions
010–012) left an open question the single-reading grade could not answer: is the
instrument's inquiry-shape (loop vs. resolve) *unrelated* to CMV persuasion, or
is its signal merely *starved*? Answering that means putting a second, rival
reading on the same bench and seeing what it can do that the shape cannot. This
module is that bench.

**The honesty lesson baked in — read this before trusting any number here.**
The obvious "persuasion-shaped" reading is speaker structure: on CMV a delta is
awarded when the original poster (OP) replies "∆", so the *labeled leaf of a
delta path is the OP's own reply*. That makes the reading "did the OP get the
last word?" score a **perfect phi ≈ +1.0** on the CMV sample — not because it
discovered anything about persuasion, but because it is reading the label's own
recording mechanism back to itself. A flawless score here is a **red flag, not a
trophy.** So every :class:`Reading` carries an authored ``caveat`` naming its
known confounds, the bench prints phi *beside* that caveat so a high number is
never read naked, and there is a test (see ``tests/test_readings.py``) enforcing
the invariant: *a reading that scores strongly on the CMV sample must declare a
caveat explaining why.* The −0.115 of the honest inquiry shape is worth more than
the +1.0 of the leak.

The bench is corpus-agnostic. ``op_has_last_word`` returns ``False`` on any
corpus without ``speakers``, so it simply reads as a null reading there rather
than erroring; the inquiry reading works on any corpus at all.
"""

from dataclasses import dataclass
from typing import Callable

from .grade import DEFAULT_LABEL_KEY, phi_coefficient, relabel_paths
from .cluster import DEFAULT_THRESHOLD
from .loops import classify_path

# A reading's predicate takes the conversation's clustered node path *and* its
# raw record (for speakers, ids, anything beyond the shape), and returns one bool.
Predicate = Callable[["list[str]", dict], bool]


@dataclass(frozen=True)
class Reading:
    """A named binary reading of a conversation, with an honest self-caveat.

    ``predicate`` maps ``(clustered_path, conversation)`` to ``True``/``False`` —
    the one bit this reading asserts about a conversation. ``question`` is the
    plain-language thing it asks; ``caveat`` names what could confound its score,
    and is *required to be non-empty for any reading that scores strongly* (see
    the module docstring): a reading that looks too good on a corpus owes the
    reader an explanation of why before its number can be believed.
    """

    name: str
    question: str
    predicate: Predicate
    caveat: str = ""

    def read(self, path: "list[str]", conversation: dict) -> bool:
        return bool(self.predicate(path, conversation))


@dataclass(frozen=True)
class ReadingGrade:
    """One reading's 2×2 contingency against the label, plus its correlation.

    Laid out exactly as :func:`cartographer.grade.phi_coefficient` expects::

                        label=True   label=False
        reading=True         a            b
        reading=False        c            d
    """

    name: str
    question: str
    caveat: str
    a: int
    b: int
    c: int
    d: int

    @property
    def n(self) -> int:
        return self.a + self.b + self.c + self.d

    @property
    def phi(self) -> float:
        """Correlation between the reading and the label (−1 … +1)."""
        return phi_coefficient(self.a, self.b, self.c, self.d)

    @property
    def positives(self) -> int:
        """How many graded conversations the reading fired ``True`` on."""
        return self.a + self.b

    def positive_rate(self, label: bool) -> float:
        """Fraction of conversations *with this label* that the reading fired on.

        ``0.0`` when no conversation carries the label. For a reading that tracks
        the label this should be high on ``True`` and low on ``False`` (or the
        reverse for a negatively-correlated reading).
        """
        yes = self.a if label else self.b
        total = (self.a + self.c) if label else (self.b + self.d)
        return yes / total if total else 0.0


def grade_reading(
    conversations: "list[dict]",
    reading: Reading,
    *,
    label_key: str = DEFAULT_LABEL_KEY,
    min_questions: int = 1,
    threshold: float = DEFAULT_THRESHOLD,
) -> ReadingGrade:
    """Grade one reading against a labeled corpus.

    Builds paths exactly as :func:`cartographer.grade.grade` does — corpus-wide
    clustering, alignment preserved — so this reading is scored on the same merge
    the shape grade uses. ``min_questions`` drops paths with fewer than that many
    extracted questions (default 1: every path that asked something, the
    denominator session 010 used), so all readings share one population.
    """
    labeled = [c for c in conversations if isinstance(c.get(label_key), bool)]
    paths = relabel_paths(labeled, threshold)
    a = b = c = d = 0
    for conversation, path in zip(labeled, paths):
        if len(path) < min_questions:
            continue
        fired = reading.read(path, conversation)
        label = bool(conversation[label_key])
        if fired and label:
            a += 1
        elif fired and not label:
            b += 1
        elif not fired and label:
            c += 1
        else:
            d += 1
    return ReadingGrade(
        name=reading.name,
        question=reading.question,
        caveat=reading.caveat,
        a=a,
        b=b,
        c=c,
        d=d,
    )


def compare_readings(
    conversations: "list[dict]",
    readings: "list[Reading] | None" = None,
    *,
    label_key: str = DEFAULT_LABEL_KEY,
    min_questions: int = 1,
    threshold: float = DEFAULT_THRESHOLD,
) -> "list[ReadingGrade]":
    """Grade several readings against the same corpus, strongest |phi| first.

    The point of the bench: put rival readings side by side. The ordering puts
    the most correlated reading on top — which, per the module docstring, is
    exactly where a leaky reading will surface, caveat attached, so a suspicious
    winner is impossible to miss.
    """
    if readings is None:
        readings = READINGS
    grades = [
        grade_reading(
            conversations,
            reading,
            label_key=label_key,
            min_questions=min_questions,
            threshold=threshold,
        )
        for reading in readings
    ]
    grades.sort(key=lambda g: abs(g.phi), reverse=True)
    return grades


# --- The readings themselves ------------------------------------------------


def _inquiry_circled(path: "list[str]", conversation: dict) -> bool:
    """The instrument's original reading: did the path revisit a node?

    ``True`` when the conversation came back onto a question it had already
    reached — the loop/resolve shape's "did not resolve" tell.
    """
    return classify_path(path).looped


def _op_has_last_word(path: "list[str]", conversation: dict) -> bool:
    """Did the first speaker (the OP) also speak the conversation's final turn?

    A crude read of "the person who opened the thread re-engaged and closed it."
    On CMV this is near-tautological with earning a delta — hence its caveat.
    Returns ``False`` on any corpus without a ``speakers`` list.
    """
    speakers = conversation.get("speakers") or []
    return len(speakers) >= 1 and speakers[-1] == speakers[0]


INQUIRY_CIRCLED = Reading(
    name="inquiry_circled",
    question="did the conversation circle back to an earlier question?",
    predicate=_inquiry_circled,
    caveat=(
        "Reads inquiry topology (a re-asked question), which is a different axis "
        "from persuasion; on CMV its signal is starved because rhetorical "
        "questions in an argument rarely recur. A near-zero phi here is honest, "
        "not broken."
    ),
)

OP_HAS_LAST_WORD = Reading(
    name="op_has_last_word",
    question="did the original poster speak the final turn?",
    predicate=_op_has_last_word,
    caveat=(
        "LEAKY on CMV: a delta is recorded as the OP's own reply, so a delta "
        "path ends with the OP by construction. Its near-perfect phi measures "
        "how the label was recorded, not what persuaded anyone — a flawless "
        "score here is a red flag, not a discovery."
    ),
)

# Order is presentational only; compare_readings re-sorts by |phi|.
READINGS: "list[Reading]" = [INQUIRY_CIRCLED, OP_HAS_LAST_WORD]


__all__ = [
    "INQUIRY_CIRCLED",
    "OP_HAS_LAST_WORD",
    "READINGS",
    "Predicate",
    "Reading",
    "ReadingGrade",
    "compare_readings",
    "grade_reading",
]
