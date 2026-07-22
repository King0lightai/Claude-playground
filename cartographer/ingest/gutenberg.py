"""Ingest a Project Gutenberg dialogue into the corpus format.

This is the cartographer's first look at *real* text. Every session until now
built the instrument sharper against a 7-line handmade sample (see JOURNAL.md);
the sample can never loop or stack, because it was written not to. A Socratic
dialogue is the honest first corpus: genuinely external, unimpeachably licensed
(public domain), small enough to commit — and *thematically exact*. It is
literally a mind moving through questions, and Plato's *Meno* famously loops:
Meno raises the paradox of inquiry ("you cannot search for what you know, nor
for what you don't"), and the conversation circles back onto the same ground.

The parser has two layers, kept separate on purpose:

* :func:`parse_turns` is a *general* play-text reader — given text in
  ``SPEAKER: line`` form it returns the ordered speaker turns, joining the
  wrapped continuation lines of each turn. It knows nothing about Gutenberg or
  Plato.
* :func:`dialogue_to_conversation` is the Gutenberg/Plato *driver*: it strips
  the Project Gutenberg boilerplate, drops the scholarly introduction that
  precedes the dialogue proper, discards structural labels like ``SCENE:``, and
  hands the real dialogue to :func:`parse_turns`.

One dialogue becomes one conversation — one path through the instrument. We keep
*every* speaker, not just Socrates: the loop the whole project points at is
opened by Meno's paradox, not by Socrates, so filtering to the questioner would
throw away the very thing we came to see. (A ``speakers`` allow-list is offered
for callers who want a single voice anyway.)

Rebuild the committed corpus from the committed raw texts (no network needed)::

    python -m cartographer.ingest.gutenberg examples/gutenberg/meno.txt meno \\
        > examples/socratic_dialogues.jsonl
    python -m cartographer.ingest.gutenberg examples/gutenberg/euthyphro.txt \\
        euthyphro >> examples/socratic_dialogues.jsonl
"""

import collections
import json
import re

# One speaker turn: who spoke, and the text they spoke (continuation lines
# already joined into a single string).
Turn = collections.namedtuple("Turn", ["speaker", "text"])

# The Project Gutenberg header/footer fences. Everything of interest lives
# strictly between them.
_PG_START = re.compile(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", re.I)
_PG_END = re.compile(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", re.I)

# The line that opens the dialogue proper in the Plato/Jowett texts. Everything
# before it is the translator's introduction and analysis — real scholarship,
# but not the conversation we are mapping.
_PERSONS = re.compile(r"^PERSONS OF THE DIALOGUE\b.*$", re.I | re.M)

# A speaker label at the start of a line: up to three ALL-CAPS words then a
# colon (e.g. "SOCRATES:", "A SLAVE:", "BOY:"). The three-word cap keeps a
# genuine turn from being confused with a sentence that merely opens in capitals,
# and is why a four-word header like "PERSONS OF THE DIALOGUE:" is not mistaken
# for a speaker even if it survives into the region.
_SPEAKER_LINE = re.compile(r"^([A-Z][A-Z'.]*(?: [A-Z][A-Z'.]*){0,2}):\s?(.*)$")

# Structural / stage labels that match the speaker shape but are not people.
_NON_SPEAKERS = frozenset({"SCENE", "ACT", "PROLOGUE", "EPILOGUE", "PERSONS"})


def strip_boilerplate(raw: str) -> str:
    """Return the text between the Project Gutenberg START and END fences.

    If a fence is missing (some other source, or a hand-trimmed file) the
    corresponding end of the text is kept as-is — the parser downstream is
    forgiving of extra prose because it only ever emits recognized turns.
    """
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    start = _PG_START.search(text)
    if start:
        text = text[start.end():]
    end = _PG_END.search(text)
    if end:
        text = text[: end.start()]
    return text


def _dialogue_region(text: str) -> str:
    """Drop the translator's introduction: keep from the cast list onward.

    The Plato/Jowett texts announce the dialogue with a ``PERSONS OF THE
    DIALOGUE`` line; everything before it is prefatory analysis. If that line is
    absent we return the text unchanged and rely on :func:`parse_turns` to skip
    whatever leads up to the first real speaker.
    """
    match = _PERSONS.search(text)
    if match:
        return text[match.end():]
    return text


def parse_turns(text: str) -> list[Turn]:
    """Parse play-formatted text into ordered speaker turns.

    A turn begins on a line shaped like ``SPEAKER: ...`` and continues across the
    wrapped lines beneath it until the next speaker or a blank line; the
    continuation lines are joined with single spaces. Anything before the first
    recognized speaker (a cast list, a stage note) is skipped. This function is
    source-agnostic — it knows nothing of Gutenberg or Plato.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    turns: list[Turn] = []
    speaker: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if speaker is not None:
            joined = " ".join(buffer).strip()
            if joined:
                turns.append(Turn(speaker, joined))

    for line in text.split("\n"):
        stripped = line.strip()
        match = _SPEAKER_LINE.match(stripped)
        if match:
            flush()
            speaker = match.group(1)
            buffer = [match.group(2).strip()]
        elif not stripped:
            # Blank line ends the current turn but does not start a new one.
            flush()
            speaker = None
            buffer = []
        elif speaker is not None:
            buffer.append(stripped)
        # else: prose before the first speaker — ignore it.
    flush()
    return turns


def dialogue_turns(raw: str, drop_labels: frozenset = _NON_SPEAKERS) -> list[Turn]:
    """Full pipeline: raw Gutenberg dialogue text → real speaker turns.

    Strips the Gutenberg boilerplate, drops the scholarly introduction, parses
    the turns, and removes structural labels (``SCENE:`` and friends) that share
    the speaker shape but are not participants.
    """
    region = _dialogue_region(strip_boilerplate(raw))
    turns = parse_turns(region)
    return [t for t in turns if t.speaker.upper() not in drop_labels]


def dialogue_to_conversation(
    raw: str, conv_id: str, speakers: "frozenset | set | None" = None
) -> dict:
    """Turn a raw Gutenberg dialogue into one conversation dict for the corpus.

    ``speakers``, if given, keeps only turns spoken by those names (case-
    insensitive) — e.g. ``{"SOCRATES"}`` for the questioner's voice alone. The
    default keeps everyone, which is the honest choice: the paradox that makes
    *Meno* loop is spoken by Meno, not Socrates.

    The returned dict carries the plain ``turns`` the rest of the cartographer
    reads, plus a parallel ``speakers`` list as provenance (extra keys are
    ignored by :func:`cartographer.corpus.conversation_texts`).
    """
    turns = dialogue_turns(raw)
    if speakers is not None:
        allowed = {s.upper() for s in speakers}
        turns = [t for t in turns if t.speaker.upper() in allowed]
    return {
        "id": conv_id,
        "turns": [t.text for t in turns],
        "speakers": [t.speaker for t in turns],
    }


def _main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert a Project Gutenberg dialogue into one JSONL corpus line."
    )
    parser.add_argument("path", help="path to the raw Gutenberg .txt dialogue")
    parser.add_argument("id", help="conversation id to stamp on the output")
    parser.add_argument(
        "--only",
        metavar="SPEAKER",
        action="append",
        help="keep only turns by this speaker (repeatable); default keeps all",
    )
    args = parser.parse_args(argv)

    with open(args.path, encoding="utf-8") as handle:
        raw = handle.read()
    speakers = frozenset(args.only) if args.only else None
    convo = dialogue_to_conversation(raw, args.id, speakers=speakers)
    print(json.dumps(convo, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
