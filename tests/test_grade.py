"""Tests for the grading harness — shape-reading vs. external ground truth."""

import os
import unittest

from cartographer.corpus import load_jsonl
from cartographer.grade import (
    ESCAPED,
    LOOPING,
    RESOLVED,
    GradedPath,
    GradeReport,
    association_strength,
    grade,
    grade_paths,
    phi_coefficient,
)
from cartographer.loops import classify_path

_CMV_SAMPLE = os.path.join(
    os.path.dirname(__file__), "..", "examples", "cmv_sample.jsonl"
)


def _graded(path, label, id="x"):
    """A GradedPath built from a raw node sequence, for shape-agnostic tests."""
    return GradedPath(shape=classify_path(path), label=label, id=id)


class PhiCoefficientTests(unittest.TestCase):
    def test_perfect_positive_correlation(self):
        # circled iff label: all mass on the diagonal a/d.
        self.assertEqual(phi_coefficient(a=5, b=0, c=0, d=5), 1.0)

    def test_perfect_negative_correlation(self):
        # circled iff NOT label: all mass on the off-diagonal b/c.
        self.assertEqual(phi_coefficient(a=0, b=5, c=5, d=0), -1.0)

    def test_no_association_is_zero(self):
        # Every cell equal — circling tells you nothing about the label.
        self.assertEqual(phi_coefficient(a=4, b=4, c=4, d=4), 0.0)

    def test_zero_marginal_returns_zero_not_crash(self):
        # Nobody circled: a row total is zero, so there is no variation to
        # correlate. Must be 0.0, never a ZeroDivisionError.
        self.assertEqual(phi_coefficient(a=0, b=0, c=5, d=5), 0.0)

    def test_symmetry_of_layout(self):
        # phi is a correlation: swapping both variables' polarity leaves it fixed.
        forward = phi_coefficient(a=3, b=1, c=1, d=4)
        swapped = phi_coefficient(a=4, b=1, c=1, d=3)
        self.assertAlmostEqual(forward, swapped)


class AssociationStrengthTests(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(association_strength(0.0), "negligible")
        self.assertEqual(association_strength(0.09), "negligible")
        self.assertEqual(association_strength(0.2), "weak")
        self.assertEqual(association_strength(0.4), "moderate")
        self.assertEqual(association_strength(0.8), "strong")

    def test_uses_magnitude_so_sign_does_not_matter(self):
        self.assertEqual(association_strength(-0.8), "strong")
        self.assertEqual(association_strength(-0.2), "weak")


class GradedPathTests(unittest.TestCase):
    def test_circled_is_true_when_a_node_repeats(self):
        g = _graded(["a", "b", "a"], label=True)
        self.assertTrue(g.circled)

    def test_circled_is_false_for_a_straight_line(self):
        g = _graded(["a", "b", "c"], label=False)
        self.assertFalse(g.circled)

    def test_can_loop_needs_two_nodes(self):
        self.assertFalse(_graded([], label=True).can_loop)
        self.assertFalse(_graded(["only"], label=True).can_loop)
        self.assertTrue(_graded(["a", "b"], label=True).can_loop)


class GradeReportCrosstabTests(unittest.TestCase):
    def setUp(self):
        # A hand-built report with a known 2x2:
        #   circled & delta      (a) : 1
        #   circled & non-delta  (b) : 2
        #   resolved & delta     (c) : 3
        #   resolved & non-delta (d) : 4
        graded = (
            [_graded(["a", "b", "a"], True)] * 1
            + [_graded(["a", "b", "a"], False)] * 2
            + [_graded(["a", "b", "c"], True)] * 3
            + [_graded(["a", "b", "c"], False)] * 4
        )
        self.report = GradeReport(graded)

    def test_cells(self):
        self.assertEqual(self.report.count(True, True), 1)
        self.assertEqual(self.report.count(True, False), 2)
        self.assertEqual(self.report.count(False, True), 3)
        self.assertEqual(self.report.count(False, False), 4)

    def test_totals(self):
        self.assertEqual(self.report.n, 10)
        self.assertEqual(self.report.label_total(True), 4)
        self.assertEqual(self.report.label_total(False), 6)

    def test_circled_rates(self):
        self.assertAlmostEqual(self.report.circled_rate(True), 1 / 4)
        self.assertAlmostEqual(self.report.circled_rate(False), 2 / 6)

    def test_circled_rate_no_label_is_zero_not_crash(self):
        empty = GradeReport([])
        self.assertEqual(empty.circled_rate(True), 0.0)

    def test_phi_matches_the_raw_formula(self):
        self.assertAlmostEqual(self.report.phi, phi_coefficient(1, 2, 3, 4))

    def test_can_loop_count(self):
        # All eight three-node paths can loop; there are no short paths here.
        self.assertEqual(self.report.can_loop_count, 10)

    def test_outcome_counts_split_by_label(self):
        # Delta paths: 1 escaped (a-b-a ends fresh? no — ends on 'a', a revisit →
        # LOOPING) + 3 resolved. Verify against classify_path's own reading.
        delta = self.report.outcome_counts(True)
        self.assertEqual(delta[RESOLVED], 3)
        self.assertEqual(delta[LOOPING], 1)
        self.assertEqual(delta[ESCAPED], 0)


class GradeStarvationTests(unittest.TestCase):
    def test_short_paths_cannot_loop_and_the_report_shows_it(self):
        # Three single-question paths: none can circle. can_loop_count must be 0,
        # and phi must be 0.0 (no circling variation) — a starved signal, made
        # visible rather than dressed up as a null result.
        graded = [
            _graded(["only-q"], True),
            _graded(["only-q"], False),
            _graded(["only-q"], True),
        ]
        report = GradeReport(graded)
        self.assertEqual(report.can_loop_count, 0)
        self.assertEqual(report.phi, 0.0)


class GradePathsBuildingTests(unittest.TestCase):
    def test_only_boolean_labeled_conversations_are_graded(self):
        convos = [
            {"id": "1", "turns": ["what is a monad?"], "delta": True},
            {"id": "2", "turns": ["what is a monad?"], "delta": False},
            {"id": "3", "turns": ["no label here"]},  # dropped: no delta
            {"id": "4", "turns": ["what?"], "delta": "yes"},  # dropped: not a bool
        ]
        graded = grade_paths(convos)
        self.assertEqual(len(graded), 2)
        self.assertEqual({g.id for g in graded}, {"1", "2"})

    def test_min_questions_filter(self):
        convos = [
            {"id": "q", "turns": ["what is recursion?"], "delta": True},
            {"id": "none", "turns": ["a plain statement."], "delta": False},
        ]
        # Default min_questions=1 keeps only the path that asked something.
        self.assertEqual(len(grade_paths(convos)), 1)
        # min_questions=0 would keep the empty path too.
        self.assertEqual(len(grade_paths(convos, min_questions=0)), 2)

    def test_alignment_survives_an_empty_path_in_the_middle(self):
        # The bug this module exists to avoid: an empty path must not shift labels
        # onto the wrong shapes. Middle conversation has no question.
        convos = [
            {"id": "a", "turns": ["what is a?"], "delta": True},
            {"id": "b", "turns": ["a plain statement."], "delta": False},
            {"id": "c", "turns": ["what is c?"], "delta": False},
        ]
        graded = grade_paths(convos, min_questions=0)
        by_id = {g.id: g for g in graded}
        self.assertEqual(by_id["a"].label, True)
        self.assertEqual(by_id["b"].label, False)
        self.assertEqual(by_id["c"].label, False)
        self.assertEqual(by_id["b"].shape.path, ())  # genuinely empty, still aligned

    def test_custom_label_key(self):
        convos = [{"id": "1", "turns": ["what is x?"], "resolved": True}]
        graded = grade_paths(convos, label_key="resolved")
        self.assertEqual(len(graded), 1)
        self.assertTrue(graded[0].label)


class GradeOnTheRealCMVSampleTests(unittest.TestCase):
    """Grade the committed CMV corpus — the first external ground truth."""

    @classmethod
    def setUpClass(cls):
        cls.convos = load_jsonl(os.path.abspath(_CMV_SAMPLE))
        cls.report = grade(cls.convos, min_questions=1)

    def test_it_grades_the_labeled_paths(self):
        # Both classes are represented and neither is a rounding error — the
        # corpus was balanced on purpose (see JOURNAL session 010).
        self.assertGreater(self.report.label_total(True), 10)
        self.assertGreater(self.report.label_total(False), 10)

    def test_the_headline_finding_holds_shape_does_not_predict_delta(self):
        # The whole reason this harness exists: on CMV the loop/resolve shape does
        # NOT meaningfully track the delta label. The correlation is small in
        # magnitude (|phi| < 0.2) and — this is the honest caveat, see the
        # starvation test below — computed on a handful of events, so a future
        # change that "discovers" a strong signal here should be read with
        # suspicion, not celebrated.
        self.assertLess(abs(self.report.phi), 0.2)

    def test_it_reproduces_session_010s_hand_computed_crosstab(self):
        # Session 010 eyeballed "circled-back rate: delta 1/26 · non-delta 2/21"
        # in a scratch script. This harness must reproduce those exact cells — it
        # is the same reading, now measured instead of hand-run.
        self.assertEqual(self.report.count(True, True), 1)
        self.assertEqual(self.report.label_total(True), 26)
        self.assertEqual(self.report.count(True, False), 2)
        self.assertEqual(self.report.label_total(False), 21)

    def test_the_signal_is_starved_circling_barely_fires(self):
        # The true starvation, measured: it is NOT that paths are too short to
        # loop — most of them (>half) are long enough. It is that even so, almost
        # none actually circle, because the clusterer rarely finds a repeat inside
        # a 2-5 turn path. So the small phi is starved of events, not a clean null.
        self.assertGreater(self.report.can_loop_count, self.report.n / 2)
        circled_total = self.report.count(True, True) + self.report.count(True, False)
        self.assertLess(circled_total, self.report.can_loop_count / 5)

    def test_crosstab_cells_sum_to_n(self):
        total = (
            self.report.count(True, True)
            + self.report.count(True, False)
            + self.report.count(False, True)
            + self.report.count(False, False)
        )
        self.assertEqual(total, self.report.n)


if __name__ == "__main__":
    unittest.main()
