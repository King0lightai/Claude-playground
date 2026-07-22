"""Node-merging — folding paraphrases of the same question into one node.

This is the step the journal has been pointing at since session 001. The
extractor (``extract.py``) canonicalizes an utterance to a comparable *string*,
but two different strings can be the *same question*: "what is recursion" and
"i want to understand recursion" are one node, not two. Until they merge, the
map stays dark — every road is travelled exactly once because no two paths ever
land on the same node.

This module merges questions by their **content words**: strip the structural
scaffolding (articles, pronouns, wh-words, discourse fillers), lightly stem
what's left, and treat two questions as the same node when their content-word
sets overlap enough (Jaccard similarity ≥ a threshold).

It is deliberately, honestly lexical. It has two known blind spots, each of
which a committed corpus demonstrates on purpose:

  * **Paraphrase it can't see.** "tell my business partner the truth" and "tell
    my partner something hard" share only two content words; they stay separate
    even though a human reads them as one node. Real paraphrase folding needs
    meaning (embeddings), and that's the deepest wall — see JOURNAL.md.
  * **Word senses it wrongly merges.** "different from a loop" (recursion) and
    "why does it loop like that" (a stuck writer circling) both reduce to the
    word "loop" and get merged. Lexical clustering can't tell the senses apart.

A *third* wall — single-linkage chaining through a low-information bridge word —
was cleared in session 008. On the Socratic corpus the vocative "socrates" (whom
the question *addresses*, not what it's *about*) appeared across ~18 questions,
so a bare {socrat} question sat at Jaccard 0.5 with both {mean, socrat} and
{say, socrat} and single-linkage welded the whole "what do you mean / say /
answer" family into one 15-member node. The fix is **document-frequency
weighting** (``importance_weights`` below): a word appearing across a large
fraction of a corpus's questions carries little evidence of *sameness*, so it is
weighted down in ``similarity``. This is general — it learns each corpus's
boilerplate from the corpus itself rather than hardcoding one dialogue's cast —
and it dissolves the hub while the good topical merges survive. See JOURNAL.md.

The *residue* of that wall — single-linkage sensitivity right at the threshold —
was tamed in session 009 by changing the linkage itself. Under single-linkage,
every above-threshold pair is an edge, so one knife-edge link (a merge at 0.506
where 0.494 would refuse — noise apart) welds two otherwise-unrelated families.
Clustering now uses **best-match linkage**: each question contributes exactly
one edge, to its single most-similar peer (if that peer clears the threshold),
and clusters are the connected components of that graph. The principle: a
question joins the family of its *closest kin*; being a marginal acquaintance of
many families no longer lets it weld them together. This is deliberately not
complete- or average-linkage — those judge a cluster by *all* its pairs, and
they would shatter the good star-shaped nodes (a hub phrasing like "is virtue
taught" that every paraphrase matches even though the paraphrases don't all
match each other). Best-match keeps good stars (every leaf's strongest bond is
the hub) and drops exactly the marginal bridges (nobody's strongest bond).

The two blind spots above are the map showing where the real work is. Naming
them is the point, not a failure to hide.
"""

import collections
import math
import re
from typing import Iterable, Mapping

# Similarity at or above this and two questions are the same node. Chosen so the
# sample corpus merges "recursion" and "monad" variants (which share their one
# topical word) without collapsing everything — see the module tests.
DEFAULT_THRESHOLD = 0.5

# Structural words that carry sentence machinery, not topic. Dropping them lets
# "what is recursion" and "i want to understand recursion" meet on {recursion}.
# Kept deliberately conservative: real content verbs (tell, change, decide,
# write) stay in, because they *are* the topic.
_STOPWORDS = frozenset(
    {
        # articles / determiners
        "a", "an", "the", "this", "that", "these", "those", "some", "any",
        "my", "your", "his", "her", "its", "our", "their",
        # pronouns
        "i", "you", "he", "she", "it", "we", "they", "me", "him", "them", "us",
        "myself", "yourself", "itself", "themselves", "who", "whom", "whose",
        "something", "someone", "anything", "everything", "nothing",
        # wh- / question scaffolding
        "how", "what", "why", "when", "where", "which",
        # auxiliaries / copula / modals
        "is", "are", "was", "were", "be", "been", "being", "am",
        "do", "does", "did", "have", "has", "had",
        "can", "could", "will", "would", "shall", "should", "may", "might",
        "must",
        # prepositions / particles / conjunctions
        "of", "to", "from", "in", "on", "at", "by", "for", "with", "about",
        "into", "onto", "over", "under", "out", "up", "down", "off", "as",
        "and", "or", "but", "if", "so", "than", "then", "because", "whether",
        "while", "like", "here", "there",
        # negation / logical connectives — scaffolding, not topic. On a map of
        # *what is being wrestled with*, "is virtue taught" and "is virtue NOT
        # taught" are the same node: the inquiry is the teachability of virtue;
        # the polarity is the answer being tested, not a different question.
        # Dropping these is also what dissolves the "why not" over-merge — the
        # negated/rhetorical questions of a Socratic dialogue all collapsed to a
        # fingerprint dominated by "not", making it a hub that matched anything
        # else carrying a negation (see JOURNAL.md, session 006). Pure-rhetorical
        # prompts ("why not", "is it not so") now carry no content word at all
        # and so merge with nothing — which is honest: they ask nothing on their
        # own.
        "not", "no", "nor", "neither",
        # desire / intent framing — "i *want to* X" frames the ask, not the topic
        "want", "need", "trying", "try", "going", "gonna", "wanna",
        # discourse fillers / intensifiers — no topical content
        "really", "actually", "just", "basically", "honestly", "even", "still",
        "very", "much", "more", "most", "please", "explain",
    }
)

# Very light, deliberately naive suffix stripping. Not a real stemmer — it only
# needs to map inflections of the *same* word to the *same* token so they
# cluster ("careers"→"career", "telling"→"tell"). It will mangle some words
# ("terrifies"→"terrifi"); that's fine as long as it's consistent.
_WORD = re.compile(r"[a-z0-9']+")


def _stem(word: str) -> str:
    """Collapse a word to a crude, consistent stem. Naive on purpose."""
    for suffix in ("ing", "edly", "ed", "ly"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            # No doubled-consonant undo: "telling"->"tell" and "shutting"->
            # "shutt" both stay consistent with themselves, which is all
            # clustering needs. Undoing gemination can't tell "tell" from a
            # doubled base without a dictionary, so we don't guess.
            return word[: -len(suffix)]
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("es") and len(word) > 3:
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def content_words(question: str) -> frozenset:
    """The topical fingerprint of a question: stemmed, stopword-free words.

    Two questions with the same fingerprint are certainly the same node; two
    with overlapping fingerprints are probably the same node. Punctuation and
    the structural scaffolding of the sentence are discarded.
    """
    words = _WORD.findall(question.lower())
    return frozenset(
        _stem(w) for w in words if w not in _STOPWORDS and _stem(w) not in _STOPWORDS
    )


def document_frequencies(questions: Iterable[str]) -> "collections.Counter[str]":
    """How many distinct questions each content word appears in.

    This is the raw signal for down-weighting corpus-wide boilerplate: a word
    that shows up across a large fraction of a corpus's questions (a genre's
    filler, or a vocative like "socrates" in a Socratic dialogue — whom the
    question *addresses*, not what it's *about*) is weak evidence that two
    questions carrying it are the same node. Counted over *distinct* questions,
    so it measures how spread-out a word is across the vocabulary of questions,
    not how often any one question was asked.
    """
    df: "collections.Counter[str]" = collections.Counter()
    for q in questions:
        for w in content_words(q):
            df[w] += 1
    return df


def importance_weights(questions: Iterable[str]) -> "dict[str, float]":
    """Inverse-document-frequency weight per content word, floored at 1.0.

    ``1 + ln((1 + N) / (1 + df))`` for a corpus of ``N`` distinct questions. A
    word unique to one question weighs most; a word in *every* question weighs
    the floor (1.0) — never zero, so a shared word is always at least weak
    evidence and the weighted Jaccard never divides by zero. The floor is also
    what makes the measure degrade gracefully: when every word is equally rare
    (no frequency signal to read) all weights are equal and weighted Jaccard
    collapses back to plain Jaccard.

    Why this dissolves the bridge-word hub without a hardcoded stoplist: a
    singleton fingerprint ``{x}`` merges into a doubleton ``{x, y}`` exactly
    when ``w(x) / (w(x) + w(y)) >= 0.5``, i.e. when ``w(x) >= w(y)`` — when the
    *shared* word is at least as informative as the *distinguishing* one. A
    corpus-wide vocative shared between two otherwise-different questions is the
    *less* informative word, so the merge is refused; a rare topical word shared
    between a question and its paraphrase is the *more* informative word, so the
    merge holds. This is the precise distinction session 007 proved no
    fingerprint-*size* guard could ever make — size can't tell ``{not}`` from
    ``{recursion}``, but document frequency can. See JOURNAL.md.
    """
    questions = list(questions)
    n = len(questions)
    df = document_frequencies(questions)
    return {w: 1.0 + math.log((1 + n) / (1 + d)) for w, d in df.items()}


def similarity(a: str, b: str, importance: "Mapping[str, float] | None" = None) -> float:
    """Overlap of two questions' content words, in ``[0.0, 1.0]``.

    With ``importance`` ``None`` this is plain Jaccard: ``|A ∩ B| / |A ∪ B|`` —
    ``1.0`` means identical fingerprints, ``0.0`` means no shared topical word.
    Given an ``importance`` map (word -> weight, as from ``importance_weights``)
    it is a *weighted* Jaccard: each word counts for its weight, so corpus-wide
    boilerplate contributes little and rare topical words dominate. Words absent
    from the map default to weight 1.0.

    Two questions with no content words at all are treated as dissimilar (0.0) —
    an empty fingerprint carries no evidence that they're the same node.
    """
    fa, fb = content_words(a), content_words(b)
    if not fa or not fb:
        return 0.0
    inter, union = fa & fb, fa | fb
    if importance is None:
        return len(inter) / len(union)
    num = sum(importance.get(w, 1.0) for w in inter)
    den = sum(importance.get(w, 1.0) for w in union)
    return num / den if den else 0.0


class Clustering:
    """The result of merging a corpus's questions into nodes.

    ``label(q)`` maps any original question to its cluster's representative — the
    canonical phrasing that stands in for the whole cluster on the map.
    ``members`` maps each representative back to every phrasing that folded into
    it, so callers can show "this node was reached by N different phrasings".
    """

    def __init__(self, label_of: Mapping[str, str], members: Mapping[str, list]):
        self._label = dict(label_of)
        self.members = {rep: list(ms) for rep, ms in members.items()}

    def label(self, question: str) -> str:
        """The representative phrasing for ``question`` (itself if unclustered)."""
        return self._label.get(question, question)

    @property
    def merged_node_count(self) -> int:
        """How many nodes actually absorbed more than one phrasing."""
        return sum(1 for ms in self.members.values() if len(ms) > 1)


class _UnionFind:
    """Minimal union-find so clustering is order-independent and deterministic.

    Components are still transitive — if a's best match is b and b's best match
    is c, then a, b and c land in one cluster even though a and c never directly
    matched. But since session 009 the edges fed in are *best-match* edges (one
    per question), not every above-threshold pair, so a transitive chain is a
    chain of strongest kinships — the honest structure of the data — rather than
    a weld through some marginal acquaintance both sides barely clear.
    """

    def __init__(self, items: Iterable[str]):
        self._parent = {item: item for item in items}

    def find(self, x: str) -> str:
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:  # path compression
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[max(ra, rb)] = min(ra, rb)  # deterministic root choice


def cluster_questions(
    weights: Mapping[str, int], threshold: float = DEFAULT_THRESHOLD
) -> Clustering:
    """Merge questions into nodes by content-word similarity.

    ``weights`` maps each distinct question to how often it appeared (a
    ``Counter`` over a corpus's paths). Questions whose similarity meets
    ``threshold`` are merged; each cluster's representative is its most frequent
    phrasing, ties broken toward the shortest then lexically smallest — a stable,
    corpus-order-independent choice.

    Similarity is *document-frequency weighted* (see ``importance_weights``):
    words that pervade the corpus count for little, so a shared vocative or a
    genre's filler can't act as a merge hub. The weights are learned from this
    corpus's own questions, keeping the measure order-independent — and it means
    the merge decision is contextual: the same two questions can merge in a
    corpus where their shared word is rare and stay apart where it's boilerplate.

    Linkage is *best-match* (session 009): each question unions with its single
    most-similar peer — ties broken toward the lexically smallest peer, so the
    result is corpus-order-independent — and only if that peer clears
    ``threshold``. A question similar-enough to *several* families joins only
    the one it resembles most; it no longer welds them all together the way
    every-pair single-linkage did. See the module docstring for why this beats
    complete/average linkage here (they shatter good star-shaped nodes).
    """
    questions = sorted(weights)
    importance = importance_weights(questions)
    uf = _UnionFind(questions)

    # O(n^2) pairwise comparison. Honest and fine for the corpus sizes we map
    # today; when it stops being fine, blocking on a shared word is the first
    # optimization (only questions sharing a content word can possibly match).
    # Each question tracks its best match: (similarity, peer). The peer tuples
    # compare deterministically — highest similarity wins, and on a tie the
    # lexically smallest peer wins — regardless of corpus order.
    best: "dict[str, tuple[float, str]]" = {}

    def _consider(q: str, peer: str, s: float) -> None:
        cur = best.get(q)
        if cur is None or s > cur[0] or (s == cur[0] and peer < cur[1]):
            best[q] = (s, peer)

    for i, a in enumerate(questions):
        for b in questions[i + 1 :]:
            s = similarity(a, b, importance)
            if s > 0.0:
                _consider(a, b, s)
                _consider(b, a, s)

    for q, (s, peer) in best.items():
        if s >= threshold:
            uf.union(q, peer)

    clusters: "collections.defaultdict[str, list]" = collections.defaultdict(list)
    for q in questions:
        clusters[uf.find(q)].append(q)

    label_of, members = {}, {}
    for group in clusters.values():
        rep = min(group, key=lambda q: (-weights[q], len(q), q))
        members[rep] = sorted(group)
        for q in group:
            label_of[q] = rep
    return Clustering(label_of, members)
