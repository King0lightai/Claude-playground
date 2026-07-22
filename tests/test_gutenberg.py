"""Tests for the Project Gutenberg dialogue ingest.

The unit tests run against small inline fixtures so they're fast and hermetic.
Two light integration checks run against the committed raw texts
(``examples/gutenberg/*.txt``) to prove the real dialogues parse — and that the
paradox of inquiry, the loop this whole corpus was chosen for, survives ingest.
"""

import os
import unittest

from cartographer.corpus import load_jsonl
from cartographer.ingest.gutenberg import (
    Turn,
    dialogue_to_conversation,
    dialogue_turns,
    parse_turns,
    strip_boilerplate,
)
from cartographer.paths import build_graph

_HERE = os.path.dirname(__file__)
_MENO = os.path.join(_HERE, "..", "examples", "gutenberg", "meno.txt")
_EUTHYPHRO = os.path.join(_HERE, "..", "examples", "gutenberg", "euthyphro.txt")
_CORPUS = os.path.join(_HERE, "..", "examples", "socratic_dialogues.jsonl")

# A miniature dialogue in the Gutenberg/Plato shape: boilerplate fences, a
# scholarly preface, a PERSONS line, a SCENE label, and CRLF-wrapped turns.
_FIXTURE = (
    "The Project Gutenberg eBook of Toy\r\n"
    "\r\n"
    "*** START OF THE PROJECT GUTENBERG EBOOK TOY ***\r\n"
    "\r\n"
    "INTRODUCTION. This preface is the translator talking, not the\r\n"
    "dialogue. It should never become a turn.\r\n"
    "\r\n"
    "PERSONS OF THE DIALOGUE: Socrates, Meno.\r\n"
    "\r\n"
    "SCENE: A porch.\r\n"
    "\r\n"
    "MENO: Can virtue be taught, Socrates, or does it come\r\n"
    "some other way?\r\n"
    "\r\n"
    "SOCRATES: I do not even know what virtue is.\r\n"
    "\r\n"
    "MENO: Are you in earnest?\r\n"
    "\r\n"
    "*** END OF THE PROJECT GUTENBERG EBOOK TOY ***\r\n"
    "\r\n"
    "This footer is license text and must be dropped.\r\n"
)


class StripBoilerplateTests(unittest.TestCase):
    def test_keeps_only_between_the_fences(self):
        body = strip_boilerplate(_FIXTURE)
        self.assertIn("PERSONS OF THE DIALOGUE", body)
        self.assertNotIn("Project Gutenberg eBook of Toy", body)
        self.assertNotIn("license text", body)

    def test_normalizes_crlf(self):
        self.assertNotIn("\r", strip_boilerplate(_FIXTURE))

    def test_missing_fences_returns_text_unchanged_in_spirit(self):
        # No fences at all: the whole thing is body.
        raw = "MENO: hello\r\nSOCRATES: hi"
        body = strip_boilerplate(raw)
        self.assertIn("MENO: hello", body)
        self.assertNotIn("\r", body)


class ParseTurnsTests(unittest.TestCase):
    def test_joins_wrapped_continuation_lines(self):
        turns = parse_turns(
            "MENO: Can virtue be taught, Socrates, or does it come\nsome other way?"
        )
        self.assertEqual(len(turns), 1)
        self.assertEqual(
            turns[0].text,
            "Can virtue be taught, Socrates, or does it come some other way?",
        )

    def test_orders_and_attributes_turns(self):
        turns = parse_turns("MENO: one\n\nSOCRATES: two\n\nMENO: three")
        self.assertEqual(
            turns,
            [Turn("MENO", "one"), Turn("SOCRATES", "two"), Turn("MENO", "three")],
        )

    def test_skips_prose_before_the_first_speaker(self):
        turns = parse_turns("A cast list and a stage note.\n\nSOCRATES: first words")
        self.assertEqual(turns, [Turn("SOCRATES", "first words")])

    def test_blank_line_ends_a_turn(self):
        # A line after a blank line is NOT a continuation of the prior turn.
        turns = parse_turns("SOCRATES: a question\n\norphaned prose\n\nMENO: reply")
        self.assertEqual(turns, [Turn("SOCRATES", "a question"), Turn("MENO", "reply")])

    def test_four_word_header_is_not_a_speaker(self):
        # The 3-word cap keeps "PERSONS OF THE DIALOGUE:" from being read as a
        # speaker whose name is "PERSONS OF THE DIALOGUE".
        turns = parse_turns("PERSONS OF THE DIALOGUE: Socrates, Meno.\n\nMENO: hi")
        self.assertEqual([t.speaker for t in turns], ["MENO"])

    def test_two_word_speaker_label_is_kept(self):
        turns = parse_turns("A SLAVE: I do not know.")
        self.assertEqual(turns, [Turn("A SLAVE", "I do not know.")])


class DialogueTurnsTests(unittest.TestCase):
    def test_drops_intro_persons_and_scene(self):
        turns = dialogue_turns(_FIXTURE)
        speakers = [t.speaker for t in turns]
        self.assertEqual(speakers, ["MENO", "SOCRATES", "MENO"])
        self.assertNotIn("SCENE", speakers)
        # None of the introduction prose leaked in as a turn.
        self.assertFalse(any("preface" in t.text for t in turns))


class DialogueToConversationTests(unittest.TestCase):
    def test_shape_matches_corpus_contract(self):
        convo = dialogue_to_conversation(_FIXTURE, "toy")
        self.assertEqual(convo["id"], "toy")
        self.assertEqual(len(convo["turns"]), len(convo["speakers"]))
        self.assertEqual(convo["turns"][0], convo["turns"][0].strip())

    def test_speaker_filter_keeps_only_named_voice(self):
        convo = dialogue_to_conversation(_FIXTURE, "toy", speakers={"socrates"})
        self.assertEqual(convo["speakers"], ["SOCRATES"])
        self.assertEqual(len(convo["turns"]), 1)

    def test_default_keeps_every_voice(self):
        convo = dialogue_to_conversation(_FIXTURE, "toy")
        self.assertEqual(convo["speakers"], ["MENO", "SOCRATES", "MENO"])


@unittest.skipUnless(os.path.exists(_MENO), "committed Meno text not present")
class RealDialogueIntegrationTests(unittest.TestCase):
    def test_meno_parses_and_keeps_all_four_voices(self):
        with open(_MENO, encoding="utf-8") as fh:
            convo = dialogue_to_conversation(fh.read(), "meno")
        self.assertGreater(len(convo["turns"]), 400)
        self.assertEqual(
            set(convo["speakers"]), {"SOCRATES", "MENO", "ANYTUS", "BOY"}
        )
        # No introduction prose leaked in: the first turn is Meno's opening line.
        self.assertTrue(convo["turns"][0].startswith("Can you tell me, Socrates"))

    def test_paradox_of_inquiry_survives_ingest(self):
        # The loop this corpus was chosen for is opened by MENO, not Socrates —
        # so it only survives because we keep every speaker.
        with open(_MENO, encoding="utf-8") as fh:
            convo = dialogue_to_conversation(fh.read(), "meno")
        paradox = [
            (sp, t)
            for sp, t in zip(convo["speakers"], convo["turns"])
            if "enquire" in t and "do not know" in t
        ]
        self.assertTrue(paradox)
        self.assertEqual(paradox[0][0], "MENO")

    def test_euthyphro_parses_two_voices(self):
        if not os.path.exists(_EUTHYPHRO):
            self.skipTest("committed Euthyphro text not present")
        with open(_EUTHYPHRO, encoding="utf-8") as fh:
            convo = dialogue_to_conversation(fh.read(), "euthyphro")
        self.assertEqual(set(convo["speakers"]), {"SOCRATES", "EUTHYPHRO"})
        self.assertGreater(len(convo["turns"]), 150)


@unittest.skipUnless(os.path.exists(_CORPUS), "committed socratic corpus not present")
class OverMergeRegressionTests(unittest.TestCase):
    """Two over-merge walls, cleared across sessions 006-008, guarded on real data.

    Session 006 found a headline node ``"why not"`` (count 26) that had swallowed
    23 unrelated questions because negation scaffolding survived stopword
    stripping; session 007 cleared it by stopwording negation. That left a
    smaller 15-member ``"what do you mean / say / answer"`` hub, welded by the
    low-information vocative "socrates" chaining through single-linkage; session
    008 cleared it with document-frequency weighting. These assert the map's
    headline is a real recurring question, not scaffolding.
    """

    _PARADOX = "how will you enquire, socrates, into that which you do not know"

    @classmethod
    def setUpClass(cls):
        # Clustering the 390-question corpus is O(n^2); build it once and share.
        cls.clustering = build_graph(load_jsonl(_CORPUS), cluster=True).clustering

    def test_why_not_no_longer_hubs(self):
        # "why not" is contentless now: its own node, folding in no one.
        self.assertEqual(self.clustering.label("why not"), "why not")
        self.assertEqual(len(self.clustering.members["why not"]), 1)

    def test_paradox_of_inquiry_survives_as_its_own_node(self):
        # The question the whole corpus was chosen for is a node in its own
        # right, not a phrasing absorbed into a negation blob.
        self.assertEqual(self.clustering.label(self._PARADOX), self._PARADOX)
        self.assertNotEqual(
            self.clustering.label(self._PARADOX), self.clustering.label("why not")
        )

    def test_no_giant_super_node_remains(self):
        # Both hubs are gone: the negation blob (session 007) and the vocative
        # bridge-word hub (session 008). The old blob was 24 phrasings and the
        # bridge hub 15; the largest node is now a handful. Bound set well below
        # the 15-member hub so a regression of the bridge fix trips this.
        largest = max(len(ms) for ms in self.clustering.members.values())
        self.assertLess(largest, 8)

    def test_headline_is_a_real_recurring_question(self):
        # With both hubs dissolved, the stacked nodes are genuine recurring
        # inquiries. The teachability of virtue — the spine of the Meno — folds
        # several distinct phrasings into one node, and every one is about virtue
        # or its being taught (no scaffolding riding along).
        rep = self.clustering.label("virtue cannot be taught")
        members = self.clustering.members[rep]
        self.assertGreaterEqual(len(members), 3)
        self.assertTrue(all("virtue" in m or "taught" in m for m in members))


if __name__ == "__main__":
    unittest.main()
