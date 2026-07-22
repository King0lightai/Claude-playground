"""Grade the instrument's shape-reading against external ground truth.

Every session before this one graded the whole project's central reading —
*did this conversation loop, or resolve?* — only against itself. Session 010
changed that: the ConvoKit ChangeMyView ingest gives each path a **delta** label,
an external "this line of argument resolved" answer key (see
``cartographer/ingest/convokit.py``). But that session could only *hand-compute*
the crosstab of shape-vs-label in a throwaway script. This module makes it a
first-class, tested output: the correlation — or, honestly, its absence — is now
*measured*, not eyeballed.

The reading being graded is the loop/resolve *shape* from :mod:`cartographer.loops`.
The instrument's mechanical proxy for "this conversation resolved" is: **the path
did not circle back** (no node was revisited — ``outcome == RESOLVED``). Ground
truth is the label (for CMV, ``delta``: the poster's view changed). Grading is
the 2×2 contingency of those two binaries, plus the correlation between them.

Why this needs its own path-building, not ``paths.build_graph``. The graph drops
empty paths and doesn't keep each path's source conversation, so a path's shape
can't be lined back up with its label through the graph. Here we relabel each
labeled conversation's path *in place* — corpus-wide clustering exactly as
``build_graph`` does it, so the merge is identical — and keep the label welded to
the shape. One :class:`GradedPath` per labeled conversation, alignment preserved.

What this is honest about. (1) The correlation is a **phi coefficient** — Pearson's
r for two binaries, pure arithmetic. Near zero means the shape does not separate
the classes; that is a real finding, not a failure to hide. (2) The correlation
can be *starved of events*: a path needs two questions before it can revisit a
node at all, and on CMV even the paths long enough to circle almost never do (the
clusterer rarely finds a repeat inside a 2-5 turn path).
:attr:`GradeReport.can_loop_count` surfaces how many paths even had the chance;
the crosstab cells show how few took it. A small phi computed on a handful of
circled paths is weak *evidence*, not a clean null — and the report shows the raw
counts beside the coefficient so the reader can tell the difference rather than
trust the number alone.
"""

import collections
import math
from dataclasses import dataclass

from .cluster import DEFAULT_THRESHOLD, cluster_questions
from .corpus import conversation_texts  # noqa: F401  (kept for API discoverability)
from .loops import ESCAPED, LOOPING, RESOLVED, PathShape, classify_path
from .paths import conversation_path

# The conversation-dict field holding the ground-truth boolean. CMV uses "delta";
# any labeled corpus can be graded by naming its own key.
DEFAULT_LABEL_KEY = "delta"


@dataclass(frozen=True)
class GradedPath:
    """One labeled path: its mechanical shape welded to its ground-truth label.

    ``shape`` is the :class:`~cartographer.loops.PathShape` read from the path's
    (clustered) node sequence; ``label`` is the external answer key (``True`` when
    the conversation resolved by the corpus's own standard — a delta, on CMV);
    ``id`` traces it back to the source conversation.
    """

    shape: PathShape
    label: bool
    id: "str | None" = None

    @property
    def circled(self) -> bool:
        """Did the path revisit a node — the instrument's "did not resolve" tell?

        The inverse of the instrument's resolution proxy. A path that never
        circles read as ``RESOLVED`` (walked a line of new questions and stopped);
        any revisit is the instrument saying "this came back on itself."
        """
        return self.shape.looped

    @property
    def can_loop(self) -> bool:
        """Could this path circle *at all* — did it have at least two questions?

        A path of zero or one node can never revisit, so it is a forced
        non-circle. Counting these separately is how the report shows when a
        "no correlation" verdict is really a starved signal, not a null result.
        """
        return len(self.shape.path) >= 2


def _relabel_paths(
    conversations: "list[dict]", threshold: float
) -> "list[list[str]]":
    """Cluster the corpus's questions and relabel each conversation's path.

    Mirrors :func:`cartographer.paths.build_graph` exactly — a corpus-wide
    clustering over every question, then each path rewritten to its nodes'
    representatives — but returns one path per conversation *in order*, keeping
    empty paths as empty lists so alignment with the source conversations (and
    thus their labels) is never lost.
    """
    raw_paths = [conversation_path(c) for c in conversations]
    counts = collections.Counter(q for path in raw_paths for q in path)
    clustering = cluster_questions(counts, threshold)
    return [[clustering.label(q) for q in path] for path in raw_paths]


def grade_paths(
    conversations: "list[dict]",
    *,
    label_key: str = DEFAULT_LABEL_KEY,
    min_questions: int = 1,
    threshold: float = DEFAULT_THRESHOLD,
) -> "list[GradedPath]":
    """Build label-aligned :class:`GradedPath` shapes from labeled conversations.

    Only conversations carrying a boolean ``label_key`` are graded. Paths are
    clustered corpus-wide (over exactly the graded conversations, so the merge is
    self-contained and reproducible) and each is classified into a shape.

    ``min_questions`` drops paths with fewer than that many extracted questions:
    such paths carry no signal for a *shape* reading (with zero questions there is
    nothing to read; the default of 1 keeps every path that asked anything, which
    is the denominator session 010 used). Set it to 2 to grade only paths that
    *could* circle.
    """
    labeled = [c for c in conversations if isinstance(c.get(label_key), bool)]
    paths = _relabel_paths(labeled, threshold)
    graded: "list[GradedPath]" = []
    for conversation, path in zip(labeled, paths):
        if len(path) < min_questions:
            continue
        graded.append(
            GradedPath(
                shape=classify_path(path),
                label=bool(conversation[label_key]),
                id=conversation.get("id"),
            )
        )
    return graded


def phi_coefficient(a: int, b: int, c: int, d: int) -> float:
    """Pearson correlation for a 2×2 table of two binaries (the phi coefficient).

    The table is laid out as::

                    label=True   label=False
        circled=True     a            b
        circled=False    c            d

    ``phi = (a·d − b·c) / sqrt((a+b)(c+d)(a+c)(b+d))``, ranging from −1 to +1.
    Positive means circling tracks the label, negative means circling tracks its
    absence, zero means no linear association. When any row or column total is
    zero there is no variation to correlate, so the denominator is zero and we
    return ``0.0`` rather than dividing by it — "nothing to measure," not an error.
    """
    denominator = math.sqrt((a + b) * (c + d) * (a + c) * (b + d))
    if denominator == 0:
        return 0.0
    return (a * d - b * c) / denominator


def association_strength(phi: float) -> str:
    """A conventional word-band for ``|phi|`` — a naming aid, not a claim.

    Uses the familiar Cohen-style cutoffs (negligible < 0.1 ≤ weak < 0.3 ≤
    moderate < 0.5 ≤ strong). These are a shared vocabulary for effect size, not
    a significance test; on a small corpus a "moderate" phi can still be noise,
    which is why the report always shows the raw counts beside it.
    """
    magnitude = abs(phi)
    if magnitude < 0.1:
        return "negligible"
    if magnitude < 0.3:
        return "weak"
    if magnitude < 0.5:
        return "moderate"
    return "strong"


@dataclass
class GradeReport:
    """The measured verdict: does the instrument's shape predict the label?

    Holds every graded path and derives the crosstab, the conditional circle
    rates, and the phi correlation from them. All reads are properties so the
    report is a thin, honest view over :attr:`graded` — no precomputed numbers to
    drift out of sync with the paths they came from.
    """

    graded: "list[GradedPath]"

    def count(self, circled: bool, label: bool) -> int:
        """One cell of the 2×2 contingency table."""
        return sum(
            1 for g in self.graded if g.circled is circled and g.label is label
        )

    @property
    def n(self) -> int:
        """Total graded paths."""
        return len(self.graded)

    def label_total(self, label: bool) -> int:
        """How many graded paths carry the given label."""
        return sum(1 for g in self.graded if g.label is label)

    @property
    def can_loop_count(self) -> int:
        """How many graded paths were long enough to *possibly* circle (≥2 nodes).

        The starvation gauge, read against the circled cells: when many paths
        *could* loop but few do, a small phi is starved of events rather than a
        clean null. (On the CMV sample most paths clear this bar yet almost none
        circle — the shortfall is in revisits found, not in path length.)
        """
        return sum(1 for g in self.graded if g.can_loop)

    def circled_rate(self, label: bool) -> float:
        """Fraction of paths *with this label* that circled back.

        The heart of the grade: if circling meant "did not resolve," this rate
        should be low among resolved (delta) paths and high among unresolved ones.
        ``0.0`` when no path carries the label.
        """
        total = self.label_total(label)
        if not total:
            return 0.0
        return self.count(True, label) / total

    @property
    def phi(self) -> float:
        """Correlation between circling back and the ground-truth label.

        Near zero is the honest headline of the CMV reading so far: the shape the
        instrument measures (a *question* was re-asked) and what resolves a CMV
        thread (an *argument* was accepted) may simply be different axes.
        """
        a = self.count(True, True)
        b = self.count(True, False)
        c = self.count(False, True)
        d = self.count(False, False)
        return phi_coefficient(a, b, c, d)

    def outcome_counts(self, label: bool) -> "collections.Counter":
        """Resolved/looping/escaped tally among paths with the given label.

        A richer cut than the circled/didn't boolean: it separates paths that
        ended still circling (``LOOPING``) from those that circled and broke free
        (``ESCAPED``), in case a finer shape reading tracks the label where the
        boolean does not.
        """
        return collections.Counter(
            g.shape.outcome for g in self.graded if g.label is label
        )


def grade(
    conversations: "list[dict]",
    *,
    label_key: str = DEFAULT_LABEL_KEY,
    min_questions: int = 1,
    threshold: float = DEFAULT_THRESHOLD,
) -> GradeReport:
    """Grade a labeled corpus: build aligned shapes, return the measured verdict.

    The one-call entry point. See :func:`grade_paths` for how paths are built and
    which conversations qualify.
    """
    return GradeReport(
        grade_paths(
            conversations,
            label_key=label_key,
            min_questions=min_questions,
            threshold=threshold,
        )
    )


__all__ = [
    "DEFAULT_LABEL_KEY",
    "ESCAPED",
    "LOOPING",
    "RESOLVED",
    "GradedPath",
    "GradeReport",
    "association_strength",
    "grade",
    "grade_paths",
    "phi_coefficient",
]
