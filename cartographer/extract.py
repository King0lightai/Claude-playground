"""Question / intent extraction — the atom of the cartographer.

The map is built from *paths*: the sequence of things a person is trying to
figure out across a conversation. A path is a sequence of these extracted
questions. This module pulls them out of raw text.

It is deliberately naive: pure standard library, lexical heuristics only. It
does NOT understand meaning — it cannot yet tell that "how do I tell my partner
the truth" and "what's the honest way to level with my business partner" are the
same underlying question. That normalization-and-clustering step is the heart of
the cartographer and lives in a future session. See JOURNAL.md.
"""

import re

# Split text into candidate sentences. We keep the terminal punctuation so we
# can tell a real question mark from an inferred one.
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")

# Interrogative words that begin a genuine question even without a "?".
_WH_OPENERS = frozenset(
    {"how", "what", "why", "when", "where", "who", "which", "whose", "whom"}
)

# Phrases that mark a request / intent even when phrased as a statement.
_REQUEST_MARKERS = (
    "help me",
    "i want to",
    "i need to",
    "i'm trying to",
    "im trying to",
    "i am trying to",
    "how do i",
    "how can i",
    "what's the best way",
    "whats the best way",
    "walk me through",
    "tell me",
    "show me",
    "teach me",
    "explain",
)

# Conversational throat-clearing to drop from the front of an utterance so that
# "So, how do I..." normalizes the same as "how do I...".
_LEADING_FILLER = frozenset(
    {
        "so", "well", "okay", "ok", "um", "uh", "hey", "hi", "hello",
        "actually", "basically", "honestly", "look", "listen", "please",
        "yeah", "and", "but", "then", "also",
    }
)


def normalize(utterance: str) -> str:
    """Collapse an utterance to a canonical, comparable form.

    Lowercases, drops leading filler words, strips edge punctuation, and
    collapses internal whitespace. This is the seam where smarter canonicalization
    (stemming, paraphrase folding) will eventually plug in.
    """
    words = utterance.strip().lower().split()
    while words and words[0].strip(",.?!;:") in _LEADING_FILLER:
        words.pop(0)
    text = " ".join(words)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \t\n.,!?;:\"'")


def _looks_like_question(sentence: str) -> bool:
    """True if a sentence is reaching for something — a question or an intent."""
    stripped = sentence.strip()
    if not stripped:
        return False
    if stripped.endswith("?"):
        return True

    canon = normalize(stripped)
    words = canon.split()
    if len(words) < 2:
        # Too short to be a meaningful question without a "?".
        return False
    if words[0] in _WH_OPENERS:
        return True
    return any(canon.startswith(marker) for marker in _REQUEST_MARKERS)


def extract_questions(text: str) -> list[str]:
    """Extract the normalized questions / intents from a block of text.

    Returns them in the order they appear — order is where the topology lives,
    so callers that care about paths should preserve it.
    """
    questions = []
    for raw in _SENTENCE.findall(text):
        if _looks_like_question(raw):
            canon = normalize(raw)
            if canon:
                questions.append(canon)
    return questions
