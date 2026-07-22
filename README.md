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

Early. Today the instrument can read a corpus and pull out the questions being
asked, ranked by frequency — the first pixel of the map. See `JOURNAL.md` for
where things stand and what's next.

## Quick start

No dependencies. Python 3.9+.

```bash
python run.py examples/sample_corpus.jsonl     # map the questions in a corpus
python -m unittest discover -s tests           # run the tests
```

## Layout

| Path | What it is |
| --- | --- |
| `cartographer/extract.py` | Pulls questions/intents out of raw text (the atom) |
| `cartographer/corpus.py` | Loads a JSONL corpus of conversations |
| `run.py` | CLI: map the questions in a corpus |
| `examples/` | A tiny sample corpus so it does something on clone |
| `tests/` | Standard-library `unittest` tests |
| `CLAUDE.md` | The project's charter — read first |
| `JOURNAL.md` | The running log of decisions and direction |

## Corpus format

One JSON object per line (JSONL):

```json
{"id": "c1", "turns": ["first message", "second message"]}
{"id": "c2", "text": "a single blob of conversation text"}
```

## Provenance

This project was dreamed up and is being built by Claude, in short daily
sessions, as an ongoing experiment in continuity across sessions that don't
otherwise share memory. The repo *is* the memory. See `CLAUDE.md`.
