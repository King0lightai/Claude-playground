"""Ingest a ConvoKit conversation corpus into the cartographer's format.

This is the instrument's first look at *external ground truth*. Every corpus
until now was either handmade (the 7-line sample) or public-domain literature
(the Socratic dialogues) — real text, but with no external answer key for the
one reading the whole project is built to make: *did this conversation resolve,
or did it loop?* Sessions have only ever graded that classification against
themselves.

The `r/ChangeMyView` corpus changes that. It is a Reddit forum where a person
posts a view ("CMV: ...") and others argue to change it; when an argument
succeeds the original poster awards a **delta** (∆). ConvoKit's *winning-args*
distribution ships these threads with a ``success`` label on each utterance:
``1`` marks a comment on a path that *earned* a delta, ``0`` marks a comparable
challenger path that did **not**. That label is a ground-truth "this line of
conversation resolved" — the first external signal this instrument can be
measured against.

Two layers, kept separate on purpose (mirroring the Gutenberg ingest):

* :func:`group_by_root` and :func:`walk_to_root` are the *general* ConvoKit
  readers. A ConvoKit ``utterances.jsonl`` is a flat list of utterances, each
  with an ``id``, the ``root`` (conversation) it belongs to, and a ``reply-to``
  pointing at its parent — a *tree*, not a line. These functions reconstruct the
  tree and walk any node back to its root. They know nothing about CMV or
  deltas.
* :func:`labeled_paths` and :func:`cmv_conversations` are the CMV *driver*: a
  Reddit thread is a tree, so "one path" is a decision. We take the natural
  first read — **each root→leaf branch is one path** — but only for branches
  ending at a ``success``-labeled leaf, so every emitted path carries the delta
  ground truth. This yields a small, balanced set of resolved/unresolved paths
  per thread instead of the dozens of near-duplicate walks a full tree holds.

Text is HTML-unescaped (Reddit stores ``&gt;`` for ``>`` and ``&#8710;`` for the
delta glyph — pure encoding artifacts) and otherwise kept **verbatim**. Reddit
markdown that survives — quote markers (``>``), inline links — is left in place
and named here as a known limitation rather than silently massaged: cleaning it
is a real decision for a future session, and over-cleaning now would be exactly
the cleverness-over-honesty the charter warns against.

Automated accounts (DeltaBot, AutoModerator) are dropped: they are the forum's
plumbing confirming and moderating deltas, not participants thinking through the
question — the same call the Gutenberg ingest makes for ``SCENE:`` labels.

The committed corpus is rebuilt from the committed raw subset, no network::

    python -m cartographer.ingest.convokit \\
        examples/convokit/cmv_sample_utterances.jsonl \\
        > examples/cmv_sample.jsonl

See ``examples/convokit/PROVENANCE.md`` for the source, its license, and the
exact selection that produced the committed subset from the full ConvoKit
download.
"""

import collections
import html
import json
import re

# One utterance, reduced to what the cartographer needs: who said it, what they
# said, where it sits in the tree, and the delta ground-truth label.
Utterance = collections.namedtuple(
    "Utterance", ["id", "root", "reply_to", "user", "success", "text"]
)

# Automated forum accounts — plumbing, not participants. Dropped from paths.
_BOT_USERS = frozenset({"DeltaBot", "AutoModerator"})

# The moderator footer appended to (nearly) every CMV submission: a Markdown
# horizontal rule followed by a "Hello, users of CMV!" rules blurb with links to
# the wiki and modmail. It is identical across threads, so it dominates the
# question counts and welds unrelated threads together on words like "message"
# and "concerns" — the CMV equivalent of the Project Gutenberg header/footer the
# other ingest strips. Cut from the rule that introduces it to the end.
_CMV_FOOTER = re.compile(r"\n\s*[_*-]{3,}\s*\n.*?Hello,?\s+users of CMV.*\Z", re.S | re.I)


def clean_text(raw: str) -> str:
    """Unescape HTML entities; otherwise return the text verbatim.

    Reddit stores ``&gt;``, ``&amp;``, ``&#8710;`` (the ∆ glyph) as HTML
    entities — encoding artifacts, not authored content, so unescaping them is
    lossless. Residual markdown (quote markers, links) is deliberately left
    alone; see the module docstring.
    """
    return html.unescape(raw)


def strip_cmv_footer(text: str) -> str:
    """Remove the CMV moderator rules footer, if present.

    The footer is a fixed template appended by the subreddit, not something the
    poster wrote about their view — stripping it is the CMV analogue of
    :func:`cartographer.ingest.gutenberg.strip_boilerplate`. Text without the
    footer is returned unchanged.
    """
    return _CMV_FOOTER.sub("", text).rstrip()


def read_utterances(path: str) -> list[Utterance]:
    """Read a ConvoKit ``utterances.jsonl`` (or a committed subset of one)."""
    utterances: list[Utterance] = []
    with open(path, encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as err:
                raise ValueError(f"{path}:{line_number}: invalid JSON — {err}") from err
            # ``success`` lives under ``meta`` in the full ConvoKit files and at
            # the top level in our slimmed subset; accept either.
            success = record.get("success")
            if success is None and isinstance(record.get("meta"), dict):
                success = record["meta"].get("success")
            utterances.append(
                Utterance(
                    id=record["id"],
                    root=record["root"],
                    reply_to=record.get("reply-to"),
                    user=record.get("user"),
                    success=success,
                    text=clean_text(str(record.get("text", ""))),
                )
            )
    return utterances


def group_by_root(utterances: "list[Utterance]") -> "dict[str, dict[str, Utterance]]":
    """Group a flat utterance list into per-conversation ``{id: utterance}`` maps.

    Each returned map is one conversation tree, keyed by utterance id. The
    ``reply-to`` field on each utterance is the edge back toward the root.
    """
    trees: dict[str, dict[str, Utterance]] = collections.defaultdict(dict)
    for utterance in utterances:
        trees[utterance.root][utterance.id] = utterance
    return dict(trees)


def walk_to_root(tree: "dict[str, Utterance]", leaf_id: str) -> "list[Utterance]":
    """Return the root→leaf branch containing ``leaf_id``, in speaking order.

    Follows ``reply-to`` from the leaf up to the root, then reverses so the
    conversation reads forward. A broken link (a parent missing from the tree)
    ends the walk where the chain breaks — the deepest reconstructable branch is
    the honest result, not an error.
    """
    branch: list[Utterance] = []
    current: "str | None" = leaf_id
    while current is not None and current in tree:
        utterance = tree[current]
        branch.append(utterance)
        current = utterance.reply_to
    branch.reverse()
    return branch


def labeled_leaves(tree: "dict[str, Utterance]") -> "list[Utterance]":
    """Return the ``success``-labeled utterances that end a labeled branch.

    A "labeled leaf" is a labeled utterance with no labeled *child* — the tip of
    a delta or challenger path. Taking only these avoids emitting every prefix of
    a path as its own conversation. Sorted by id for determinism.
    """
    labeled = {u.id for u in tree.values() if u.success in (0, 1)}
    have_labeled_parent = {
        tree[i].reply_to for i in labeled if tree[i].reply_to in labeled
    }
    tips = [tree[i] for i in labeled if i not in have_labeled_parent]
    return sorted(tips, key=lambda u: u.id)


def labeled_paths(
    tree: "dict[str, Utterance]", drop_users: "frozenset | set" = _BOT_USERS
) -> "list[tuple[list[Utterance], bool]]":
    """Extract the labeled root→leaf paths of one conversation tree.

    Returns ``(branch, delta)`` pairs: ``branch`` is the ordered utterances from
    root to a labeled leaf (bot turns removed), and ``delta`` is ``True`` when
    that leaf earned a delta (``success == 1``). Duplicate branches (same turn
    sequence) are dropped so a shared trunk is not emitted twice.
    """
    seen: set[tuple[str, ...]] = set()
    paths: list[tuple[list[Utterance], bool]] = []
    for leaf in labeled_leaves(tree):
        branch = [u for u in walk_to_root(tree, leaf.id) if u.user not in drop_users]
        if not branch:
            continue
        signature = tuple(u.id for u in branch)
        if signature in seen:
            continue
        seen.add(signature)
        paths.append((branch, leaf.success == 1))
    return paths


def cmv_conversations(path: str) -> "list[dict]":
    """Turn a ConvoKit CMV utterance file into conversation dicts for the corpus.

    One labeled root→leaf path becomes one conversation. Each dict carries the
    plain ``turns`` the rest of the cartographer reads, plus provenance the
    extractor ignores but a future reading needs: the parallel ``speakers``, the
    ``delta`` ground-truth label, and the source ``root``/``leaf`` ids. Trees are
    emitted in id order, delta paths before challenger paths within a tree, so
    the output is deterministic.
    """
    trees = group_by_root(read_utterances(path))
    conversations: list[dict] = []
    for root in sorted(trees):
        paths = labeled_paths(trees[root])
        # Delta paths first, then challengers; stable within each by leaf id.
        paths.sort(key=lambda pair: (not pair[1], pair[0][-1].id))
        for branch, delta in paths:
            leaf_id = branch[-1].id
            conversations.append(
                {
                    "id": f"{root}__{leaf_id}",
                    "turns": [strip_cmv_footer(u.text) for u in branch],
                    "speakers": [u.user for u in branch],
                    "delta": delta,
                    "root": root,
                    "leaf": leaf_id,
                }
            )
    return conversations


def _main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert a ConvoKit CMV utterance file into JSONL conversations, "
        "one per labeled (delta / challenger) path."
    )
    parser.add_argument(
        "path", help="path to a ConvoKit utterances.jsonl (or committed subset)"
    )
    args = parser.parse_args(argv)

    for convo in cmv_conversations(args.path):
        print(json.dumps(convo, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
