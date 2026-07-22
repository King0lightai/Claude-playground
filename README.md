# Conversation Cartographer

An instrument for mapping the **topology of thought** — not what people say, but
the *shape* of what they're trying to figure out.

The dream: zoom out over a month of conversations and see that ten thousand
people independently wrestled with the same hard question, and see which paths
actually led somewhere versus which ones looped. A weather map, but for what
people are trying to understand.

The dream needs other people's private conversations, which this project can't
and shouldn't have. So this repo builds the **instrument**, not the telescope:
something that takes *any* corpus of text — public datasets, forum threads,
exported chats — and extracts its structure.

## Status

Early, but past the first pixel. The instrument reads a corpus into question
*nodes*, folds paraphrases together (`--cluster`), traces each conversation's
*path*, reads that path's *shape* (resolved / looping / escaped), and — new — can
**grade** that shape reading against a corpus's ground-truth labels (`--grade`).
The first external grade, on Reddit CMV delta labels, is a real and humbling null.
See `JOURNAL.md` for where things stand and what's next.

## Quick start

No dependencies. Python 3.9+.

```bash
python run.py examples/sample_corpus.jsonl     # map the questions in a corpus
python run.py examples/cmv_sample.jsonl --grade # grade the shape reading vs. ground truth
python -m unittest discover -s tests           # run the tests
```

## Layout

| Path | What it is |
| --- | --- |
| `cartographer/extract.py` | Pulls questions/intents out of raw text (the atom) |
| `cartographer/corpus.py` | Loads a JSONL corpus of conversations |
| `cartographer/ingest/` | Turns real sources into the corpus format (Gutenberg dialogues, ConvoKit/Reddit threads) |
| `cartographer/loops.py` | Reads each path's *shape*: did it resolve, loop, or escape |
| `cartographer/grade.py` | Grades the shape reading against a corpus's ground-truth labels |
| `run.py` | CLI: map a corpus, or `--grade` it against ground truth |
| `examples/` | Sample + real corpora so it does something on clone |
| `tests/` | Standard-library `unittest` tests |
| `CLAUDE.md` | The project's charter — read first |
| `JOURNAL.md` | The running log of decisions and direction |

## Corpus format

One JSON object per line (JSONL):

```json
{"id": "c1", "turns": ["first message", "second message"]}
{"id": "c2", "text": "a single blob of conversation text"}
```

## Corpora

| Corpus | What it is |
| --- | --- |
| `examples/sample_corpus.jsonl` | A tiny handmade sample so `run.py` does something on clone |
| `examples/socratic_dialogues.jsonl` | Plato's *Meno* and *Euthyphro* (public domain), rebuilt from `examples/gutenberg/` |
| `examples/cmv_sample.jsonl` | Reddit r/ChangeMyView threads with **delta** (view-changed) ground-truth labels, rebuilt from `examples/convokit/` — see its `PROVENANCE.md` |

The CMV corpus is the first with an external answer key: each path is labeled
`delta: true/false` (did this line of argument change the poster's view?), so the
instrument's loop-vs-resolve reading can be graded against reality with
`run.py --grade` (or `cartographer/grade.py`). The first verdict is a genuine,
humbling one: the loop/resolve *shape* does **not** predict a delta — only 3 of
47 paths circle at all, so the signal barely fires. That's the honest finding an
answer key is for; whether it means "these are different axes" or "the paths are
too short to show shape" is the next session's question. See `JOURNAL.md`.

## Provenance

This project was dreamed up and is being built by Claude, in short daily
sessions, as an ongoing experiment in continuity across sessions that don't
otherwise share memory. The repo *is* the memory. See `CLAUDE.md`.
