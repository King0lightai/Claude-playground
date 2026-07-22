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

It is deliberately, honestly lexical. It has two known blind spots, both of
which the sample corpus demonstrates on purpose:

  * **Paraphrase it can't see.** "tell my business partner the truth" and "tell
    my partner something hard" share only two content words; they stay separate
    even though a human reads them as one node. Real paraphrase folding needs
    meaning (embeddings), and that's the next wall — see JOURNAL.md.
  * **Word senses it wrongly merges.** "different from a loop" (recursion) and
    "why does it loop like that" (a stuck writer circling) both reduce to the
    word "loop" and get merged. Lexical clustering can't tell the senses apart.

Both limits are the map showing where the real work is. Naming them is the
point, not a failure to hide.
"""

import collections
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


def similarity(a: str, b: str) -> float:
    """Jaccard overlap of two questions' content words, in ``[0.0, 1.0]``.

    ``1.0`` means identical fingerprints; ``0.0`` means no shared topical word.
    Two questions with no content words at all are treated as dissimilar (0.0) —
    an empty fingerprint carries no evidence that they're the same node.
    """
    fa, fb = content_words(a), content_words(b)
    if not fa or not fb:
        return 0.0
    return len(fa & fb) / len(fa | fb)


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

    Single-linkage: if a~b and b~c, then a, b and c all land in one cluster even
    if a and c never directly matched. That can chain surprising things together
    in a big, noisy corpus — a known lexical-clustering hazard worth remembering
    when this graduates past toy corpora.
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
    """
    questions = sorted(weights)
    uf = _UnionFind(questions)

    # O(n^2) pairwise comparison. Honest and fine for the corpus sizes we map
    # today; when it stops being fine, blocking on a shared word is the first
    # optimization (only questions sharing a content word can possibly match).
    for i, a in enumerate(questions):
        for b in questions[i + 1 :]:
            if similarity(a, b) >= threshold:
                uf.union(a, b)

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
