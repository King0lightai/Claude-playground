# ChangeMyView (CMV) corpus — provenance

## What this is

`cmv_sample_utterances.jsonl` is a committed **subset** of the ConvoKit
*winning-args* corpus: threads from Reddit's [r/ChangeMyView][cmv], where a
person posts a view ("CMV: ...") and others argue to change it. When an argument
succeeds, the original poster awards a **delta** (∆). ConvoKit ships these
threads with a `success` label on each comment: `1` marks a comment on a path
that *earned* a delta, `0` marks a comparable challenger path that did **not**.

That label is the reason this corpus is here. Every corpus before it (the
handmade sample, the Socratic dialogues) was real text but had no external answer
key for the one reading this whole project is built to make — *did this
conversation resolve, or did it loop?* CMV's delta is exactly that answer key.

## Source and license

- **Dataset:** ConvoKit "Winning Arguments" corpus.
- **Download:** <https://zissou.infosci.cornell.edu/convokit/datasets/winning-args-corpus/winning-args-corpus.zip>
- **Documentation:** <https://convokit.cornell.edu/documentation/winning.html>
- **Underlying paper:** Tan, Niculae, Danescu-Niculescu-Mizil & Lee, *"Winning
  Arguments: Interaction Dynamics and Persuasion Strategies in Good-faith Online
  Discussions"* (WWW 2016).
- **License / terms:** the corpus is published by the Cornell Conversational
  Analysis Toolkit for research use, derived from publicly posted Reddit content.
  It is redistributed here as a small research subset with attribution. Reddit
  content remains subject to Reddit's user agreement; usernames are as published
  by ConvoKit (already the public Reddit handles).

## The committed subset — and how to reproduce it exactly

The full corpus is ~344 MB unpacked (293k utterances across 3,051 threads) — far
too large to commit. This repo commits only the **30 smallest threads that have
both a delta path and a challenger path**, with all their utterances, so the
conversation trees are fully reconstructable offline. That is 483 utterances /
~390 KB, yielding **66 labeled paths (34 delta, 32 non-delta)** — small enough to
commit, balanced enough to grade against.

The selection is deterministic. To reproduce `cmv_sample_utterances.jsonl` from a
fresh download:

```python
import json
from collections import defaultdict

# after unzipping winning-args-corpus.zip:
src = "winning-args-corpus/utterances.jsonl"
by_root = defaultdict(list)
with open(src) as f:
    for line in f:
        d = json.loads(line)
        by_root[d["root"]].append(d)

def paired(us):
    ss = {u["meta"].get("success") for u in us}
    return 1 in ss and 0 in ss

paired_roots = [r for r, us in by_root.items() if paired(us)]
chosen = sorted(paired_roots, key=lambda r: (len(by_root[r]), r))[:30]

with open("cmv_sample_utterances.jsonl", "w", encoding="utf-8") as w:
    for root in sorted(chosen):
        for u in sorted(by_root[root], key=lambda x: (x.get("timestamp") or 0, x["id"])):
            w.write(json.dumps({
                "id": u["id"], "root": u["root"], "reply-to": u["reply-to"],
                "timestamp": u.get("timestamp"), "user": u["user"],
                "success": u["meta"].get("success"), "text": u["text"],
            }, ensure_ascii=False) + "\n")
```

Only the fields the cartographer needs are kept; ConvoKit's many always-null
`meta` fields are dropped, and `success` is lifted to the top level. The ingest
(`cartographer.ingest.convokit`) accepts either the top-level `success` used here
or the nested `meta.success` of the full ConvoKit files.

## Rebuild the mapped corpus (no network)

```bash
python -m cartographer.ingest.convokit \
    examples/convokit/cmv_sample_utterances.jsonl \
    > examples/cmv_sample.jsonl
```

[cmv]: https://www.reddit.com/r/changemyview/
