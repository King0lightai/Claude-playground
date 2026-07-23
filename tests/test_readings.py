"""Tests for the reading bench (:mod:`cartographer.readings`).

The bench's whole reason to exist is to make a leaky reading *visible* next to an
honest one. These tests pin both the mechanics (contingency, phi, shared
population) and — most importantly — the honesty invariant: a reading that scores
strongly on the CMV sample must declare a caveat explaining why.
"""

import os
import unittest

from cartographer.corpus import load_jsonl
from cartographer.readings import (
    INQUIRY_CIRCLED,
    OP_HAS_LAST_WORD,
    READINGS,
    Reading,
    ReadingGrade,
    compare_readings,
    grade_reading,
)

CMV = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "examples", "cmv_sample.jsonl"
)


def _tiny(label, speakers, turns):
    """A minimal conversation dict the bench can read."""
    return {"delta": label, "speakers": speakers, "turns": turns}


class ReadingGradeArithmeticTests(unittest.TestCase):
    def test_contingency_cells_and_totals(self):
        grade = ReadingGrade(name="x", question="q?", caveat="", a=3, b=1, c=2, d=4)
        self.assertEqual(grade.n, 10)
        self.assertEqual(grade.positives, 4)

    def test_phi_matches_the_grade_module(self):
        # Perfect positive association -> +1.0.
        grade = ReadingGrade(name="x", question="q?", caveat="", a=5, b=0, c=0, d=5)
        self.assertAlmostEqual(grade.phi, 1.0)

    def test_positive_rate_is_conditional_on_label(self):
        grade = ReadingGrade(name="x", question="q?", caveat="", a=3, b=1, c=1, d=5)
        # fired on 3 of (3+1) label=True, 1 of (1+5) label=False.
        self.assertAlmostEqual(grade.positive_rate(True), 3 / 4)
        self.assertAlmostEqual(grade.positive_rate(False), 1 / 6)

    def test_positive_rate_is_zero_when_label_absent(self):
        grade = ReadingGrade(name="x", question="q?", caveat="", a=0, b=2, c=0, d=3)
        self.assertEqual(grade.positive_rate(True), 0.0)


class GradeReadingTests(unittest.TestCase):
    def test_a_reading_can_be_graded_on_a_tiny_handmade_corpus(self):
        # Two conversations; the OP speaks last only on the delta one.
        convos = [
            _tiny(True, ["op", "chal", "op"], ["...", "...", "..."]),
            _tiny(False, ["op", "chal"], ["...", "..."]),
        ]
        grade = grade_reading(convos, OP_HAS_LAST_WORD, min_questions=0)
        self.assertEqual((grade.a, grade.b, grade.c, grade.d), (1, 0, 0, 1))
        self.assertAlmostEqual(grade.phi, 1.0)

    def test_only_boolean_labeled_conversations_are_graded(self):
        convos = [
            _tiny(True, ["op", "chal", "op"], ["...", "...", "..."]),
            {"speakers": ["op"], "turns": ["..."]},  # no delta key -> skipped
            {"delta": None, "speakers": ["op"], "turns": ["..."]},  # non-bool -> skipped
        ]
        grade = grade_reading(convos, OP_HAS_LAST_WORD, min_questions=0)
        self.assertEqual(grade.n, 1)

    def test_min_questions_filters_the_population(self):
        # A path with no extracted question is dropped at min_questions=1.
        convos = [
            _tiny(True, ["op", "op"], ["what is truth?", "hmm."]),
            _tiny(False, ["op", "chal"], ["I disagree.", "So do I."]),
        ]
        at_zero = grade_reading(convos, INQUIRY_CIRCLED, min_questions=0)
        at_one = grade_reading(convos, INQUIRY_CIRCLED, min_questions=1)
        self.assertLessEqual(at_one.n, at_zero.n)

    def test_speaker_reading_is_false_without_speakers(self):
        # A corpus with no speaker structure -> the reading never fires.
        convos = [
            {"delta": True, "turns": ["what is truth?"]},
            {"delta": False, "turns": ["I disagree."]},
        ]
        grade = grade_reading(convos, OP_HAS_LAST_WORD, min_questions=0)
        self.assertEqual(grade.positives, 0)


class CmvBenchTests(unittest.TestCase):
    """The bench on the real CMV sample — where the leak becomes visible."""

    @classmethod
    def setUpClass(cls):
        cls.convos = load_jsonl(CMV)

    def test_inquiry_shape_is_the_honest_starved_signal(self):
        # Reproduces the grade module's headline: weak, near-zero, negative.
        grade = grade_reading(self.convos, INQUIRY_CIRCLED)
        self.assertLess(abs(grade.phi), 0.2)

    def test_speaker_reading_is_a_near_perfect_leak(self):
        # The OP-last-word reading is (near) tautological with earning a delta.
        grade = grade_reading(self.convos, OP_HAS_LAST_WORD)
        self.assertGreater(grade.phi, 0.9)

    def test_compare_puts_the_strongest_reading_on_top(self):
        grades = compare_readings(self.convos)
        self.assertEqual(grades[0].name, "op_has_last_word")
        self.assertEqual(grades[-1].name, "inquiry_circled")
        # The leak dwarfs the honest reading — that gap is the whole finding.
        self.assertGreater(abs(grades[0].phi), abs(grades[-1].phi))

    def test_the_leak_and_the_honest_reading_share_one_population(self):
        # Apples to apples: both readings grade the same number of paths.
        grades = compare_readings(self.convos)
        self.assertEqual(len({g.n for g in grades}), 1)


class HonestyInvariantTests(unittest.TestCase):
    """The load-bearing guard: a suspiciously strong reading must explain itself."""

    @classmethod
    def setUpClass(cls):
        cls.convos = load_jsonl(CMV)

    def test_a_strong_reading_on_cmv_must_declare_a_caveat(self):
        # For every registered reading, if it scores strongly on the CMV sample
        # (|phi| > 0.5), it is required to carry a non-empty caveat naming why.
        # This is the honesty principle as an executable rule: a reading is not
        # allowed to look too good in silence.
        for reading in READINGS:
            grade = grade_reading(self.convos, reading)
            if abs(grade.phi) > 0.5:
                self.assertTrue(
                    reading.caveat.strip(),
                    f"{reading.name} scores phi={grade.phi:+.3f} but has no caveat",
                )

    def test_the_leaky_readings_caveat_names_the_leak(self):
        # Not just any caveat — it must actually flag the leak.
        self.assertIn("leak", OP_HAS_LAST_WORD.caveat.lower())

    def test_every_registered_reading_is_well_formed(self):
        for reading in READINGS:
            self.assertIsInstance(reading, Reading)
            self.assertTrue(reading.name)
            self.assertTrue(reading.question)


if __name__ == "__main__":
    unittest.main()
