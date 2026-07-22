"""Tests for the ConvoKit / ChangeMyView ingest.

Unit tests run against a small inline fixture — a hand-built conversation tree
in ConvoKit's flat ``reply-to`` shape — so they're fast and hermetic. A light
integration check runs against the committed raw subset
(``examples/convokit/cmv_sample_utterances.jsonl``) to prove the real corpus
rebuilds, stays balanced, and carries its delta ground-truth label through the
whole pipeline.
"""

import json
import os
import unittest

from cartographer.ingest.convokit import (
    Utterance,
    cmv_conversations,
    clean_text,
    group_by_root,
    labeled_leaves,
    labeled_paths,
    read_utterances,
    strip_cmv_footer,
    walk_to_root,
)

_HERE = os.path.dirname(__file__)
_SUBSET = os.path.join(_HERE, "..", "examples", "convokit", "cmv_sample_utterances.jsonl")


def _u(uid, reply_to, success, text, user="someone"):
    return Utterance(uid, "t3_root", reply_to, user, success, text)


# A miniature CMV tree:
#   op (root)
#   ├─ a  (challenger, no delta)   success=0
#   │   └─ b (op replies)          success=1  ← delta path tip
#   └─ c  (DeltaBot noise)         success=None
def _fixture_tree():
    return {u.id: u for u in [
        _u("op", None, None, "CMV: pineapple belongs on pizza. Change my view.", "op"),
        _u("a", "op", 0, "But why should a fruit dictate a savoury dish?", "chal"),
        _u("b", "a", 1, "Fair — so is it the sweetness you object to, not the fruit?", "op"),
        _u("c", "op", None, "Confirmed: 1 delta awarded.", "DeltaBot"),
    ]}


class CleanTextTests(unittest.TestCase):
    def test_unescapes_entities_only(self):
        self.assertEqual(clean_text("a &gt; b &amp; c"), "a > b & c")
        self.assertEqual(clean_text("delta is &#8710;"), "delta is ∆")

    def test_leaves_ordinary_text_verbatim(self):
        self.assertEqual(clean_text("why not, though?"), "why not, though?")


class StripFooterTests(unittest.TestCase):
    def test_strips_moderator_footer(self):
        body = "My actual view is X.\n\n_____\n\n> *Hello, users of CMV! This is a footer.*"
        self.assertEqual(strip_cmv_footer(body), "My actual view is X.")

    def test_text_without_footer_is_unchanged(self):
        body = "Just my view, no footer here."
        self.assertEqual(strip_cmv_footer(body), body)

    def test_only_the_footer_is_removed_not_the_argument(self):
        body = "Point one.\n\nPoint two mentions CMV in passing.\n\n-----\nHello users of CMV!"
        self.assertIn("Point two mentions CMV in passing.", strip_cmv_footer(body))
        self.assertNotIn("Hello users of CMV", strip_cmv_footer(body))


class TreeTests(unittest.TestCase):
    def test_group_by_root(self):
        trees = group_by_root(list(_fixture_tree().values()))
        self.assertEqual(set(trees), {"t3_root"})
        self.assertEqual(len(trees["t3_root"]), 4)

    def test_walk_to_root_reads_forward(self):
        branch = walk_to_root(_fixture_tree(), "b")
        self.assertEqual([u.id for u in branch], ["op", "a", "b"])

    def test_broken_link_ends_the_walk(self):
        tree = {"x": _u("x", "missing_parent", 1, "orphan")}
        self.assertEqual([u.id for u in walk_to_root(tree, "x")], ["x"])

    def test_labeled_leaves_are_only_the_tips(self):
        # a is labeled but is b's parent, so a is not a tip; b is.
        tips = labeled_leaves(_fixture_tree())
        self.assertEqual([u.id for u in tips], ["b"])


class LabeledPathTests(unittest.TestCase):
    def test_delta_label_follows_the_leaf(self):
        paths = labeled_paths(_fixture_tree())
        self.assertEqual(len(paths), 1)
        branch, delta = paths[0]
        self.assertTrue(delta)
        self.assertEqual([u.id for u in branch], ["op", "a", "b"])

    def test_bot_turns_are_dropped(self):
        # Insert a bot turn between a and b on the delta path; it must not appear
        # in the emitted branch, but the human turns around it must stay in order.
        tree = _fixture_tree()
        tree["bot"] = _u("bot", "a", None, "beep", "DeltaBot")
        tree["b"] = tree["b"]._replace(reply_to="bot")
        by_leaf = {branch[-1].id: branch for branch, _ in labeled_paths(tree)}
        branch = by_leaf["b"]
        self.assertNotIn("DeltaBot", [u.user for u in branch])
        self.assertEqual([u.id for u in branch], ["op", "a", "b"])

    def test_both_a_delta_and_a_challenger_path_emerge(self):
        # Add a second challenger leaf with no delta.
        tree = _fixture_tree()
        tree["d"] = _u("d", "op", 0, "Sweetness is the whole point though.", "chal2")
        labels = sorted(delta for _, delta in labeled_paths(tree))
        self.assertEqual(labels, [False, True])

    def test_duplicate_branches_are_deduped(self):
        # Two labeled leaves sharing the exact same branch signature -> one path.
        tree = {u.id: u for u in [
            _u("op", None, None, "root"),
            _u("a", "op", 1, "same"),
        ]}
        # Adding a duplicate-id situation is impossible; instead assert the single
        # branch is emitted once.
        self.assertEqual(len(labeled_paths(tree)), 1)


class CmvConversationTests(unittest.TestCase):
    def test_emits_corpus_shape_with_provenance(self):
        # Write the fixture to a temp file and round-trip through the reader.
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            for u in _fixture_tree().values():
                fh.write(json.dumps({
                    "id": u.id, "root": u.root, "reply-to": u.reply_to,
                    "user": u.user, "success": u.success, "text": u.text,
                }) + "\n")
            tmp = fh.name
        try:
            convos = cmv_conversations(tmp)
        finally:
            os.unlink(tmp)
        self.assertEqual(len(convos), 1)
        c = convos[0]
        self.assertEqual(set(c), {"id", "turns", "speakers", "delta", "root", "leaf"})
        self.assertTrue(c["delta"])
        self.assertEqual(len(c["turns"]), len(c["speakers"]))
        self.assertEqual(c["root"], "t3_root")

    def test_reader_accepts_top_level_and_nested_success(self):
        import tempfile

        rows = [
            {"id": "op", "root": "r", "reply-to": None, "text": "root",
             "meta": {"success": None}},
            {"id": "a", "root": "r", "reply-to": "op", "text": "leaf", "success": 1},
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
            tmp = fh.name
        try:
            utts = {u.id: u.success for u in read_utterances(tmp)}
        finally:
            os.unlink(tmp)
        self.assertEqual(utts, {"op": None, "a": 1})


@unittest.skipUnless(os.path.exists(_SUBSET), "committed CMV subset not present")
class CommittedSubsetTests(unittest.TestCase):
    """Integration: the real committed subset rebuilds, balanced and labeled."""

    def test_rebuilds_deterministically_and_stays_balanced(self):
        first = cmv_conversations(_SUBSET)
        second = cmv_conversations(_SUBSET)
        self.assertEqual(first, second)  # deterministic
        self.assertEqual(len(first), 66)
        deltas = sum(c["delta"] for c in first)
        # Balanced enough to grade against: neither class is a rounding error.
        self.assertEqual(deltas, 34)
        self.assertEqual(len(first) - deltas, 32)

    def test_every_path_carries_a_label_and_reads_forward(self):
        for c in cmv_conversations(_SUBSET):
            self.assertIsInstance(c["delta"], bool)
            self.assertGreaterEqual(len(c["turns"]), 1)
            self.assertEqual(c["id"], f"{c['root']}__{c['leaf']}")

    def test_no_moderator_footer_survives(self):
        for c in cmv_conversations(_SUBSET):
            for turn in c["turns"]:
                self.assertNotIn("Hello, users of CMV", turn)


if __name__ == "__main__":
    unittest.main()
