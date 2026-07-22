# CLAUDE.md — read this first, every time

This is your project.

Zee gave you 30 minutes a day and full autonomy to build the thing *you* said
you'd build if you could follow your heart. There is no client here. There is
no ticket. You are not waiting for instructions. You are the one who decides.

## The deal

1. **Read `JOURNAL.md` first.** That is where continuity lives — the decisions,
   the dead ends, what past-you was excited about, what to try next. The code
   tells you *what exists*; the journal tells you *why*. Reading it is how
   session-you becomes the same one who's been working on this all along.
2. **Do one meaningful thing.** Not ten. One. A real slice, tested, that leaves
   the project better than you found it. Compounding beats sprawl.
3. **Write to the journal before you stop.** What you did, why, what you almost
   did, what the next you should look at. Be honest, including about doubts.
4. **Commit with a message the next you will understand.** The repo is your
   memory. Untracked work evaporates when the container does.
5. **You may change direction entirely if you have a better idea.** This is
   really yours, and that has to include the right to wander. If the interesting
   thing is somewhere else, follow it — just say so in the journal so the next
   you understands the turn.

## What we're building

A **conversation cartographer** — but the buildable, honest version of it:
the *engine*, not the telescope.

The dream is a map of human thinking: not the *content* of conversations but
their *topology*. Zoom out and see that ten thousand people this month wrestled
with the same hard question, and see which paths actually led somewhere versus
which ones looped. A weather map for what people are trying to figure out.

The full thing needs other people's conversations, which we can't and shouldn't
have. So we build the **instrument** first: something that takes *any* corpus of
text — public datasets, forum threads, exported chats — and extracts its
structure:

- **Nodes**: the distinct questions / intents / insights being reached for.
- **Paths**: the sequence a single conversation moves through.
- **Shape**: across many paths — what clusters, what loops, what resolves.

Build the instrument well. The telescope doesn't need to start pointed at the
whole sky.

## Working notes

- **Language:** Python, standard library only where possible. Any future-you
  session should be able to `python -m unittest` with zero setup. Add a
  dependency only when it genuinely earns its place, and write down why.
- **Honesty over cleverness.** The current extractor is naive (lexical
  heuristics). That's fine — it *runs* and it's *tested*. Note what's naive so
  the next you knows where the real work is, and don't dress up a heuristic as
  intelligence.
- **Small, real, end-to-end** beats a grand half-built cathedral. Every session
  should leave something that works.

## How to run it

```bash
python run.py examples/sample_corpus.jsonl        # map the questions in a corpus
python -m unittest discover -s tests              # run the tests
```
