import collections
import unittest

from cartographer.loops import (
    ESCAPED,
    LOOPING,
    RESOLVED,
    classify_path,
    shape_graph,
)
from cartographer.paths import build_graph


class TestClassifyPath(unittest.TestCase):
    def test_all_distinct_resolves(self):
        shape = classify_path(["a", "b", "c"])
        self.assertEqual(shape.outcome, RESOLVED)
        self.assertFalse(shape.looped)
        self.assertEqual(shape.revisits, ())

    def test_empty_path_resolves_trivially(self):
        shape = classify_path([])
        self.assertEqual(shape.outcome, RESOLVED)
        self.assertFalse(shape.looped)

    def test_single_node_resolves_trivially(self):
        shape = classify_path(["a"])
        self.assertEqual(shape.outcome, RESOLVED)

    def test_ends_on_revisit_is_looping(self):
        # a -> b -> a: came back to old ground and stopped there.
        shape = classify_path(["a", "b", "a"])
        self.assertEqual(shape.outcome, LOOPING)
        self.assertTrue(shape.looped)
        self.assertEqual(shape.revisits, ((2, "a"),))
        self.assertEqual(shape.revisited_nodes, ("a",))

    def test_self_edge_ending_is_looping(self):
        shape = classify_path(["a", "a"])
        self.assertEqual(shape.outcome, LOOPING)
        self.assertEqual(shape.revisits, ((1, "a"),))

    def test_revisit_then_new_ground_is_escaped(self):
        # a -> b -> a -> c: circled back to a, then broke out to a fresh node.
        shape = classify_path(["a", "b", "a", "c"])
        self.assertEqual(shape.outcome, ESCAPED)
        self.assertTrue(shape.looped)
        self.assertEqual(shape.revisits, ((2, "a"),))

    def test_self_edge_then_new_ground_is_escaped(self):
        # The real MONAD->MONAD->burrito shape from the sample corpus: re-asked
        # the same question, then moved on to something new.
        shape = classify_path(["monad", "monad", "burrito"])
        self.assertEqual(shape.outcome, ESCAPED)
        self.assertEqual(shape.revisits, ((1, "monad"),))

    def test_revisited_nodes_are_distinct_and_ordered(self):
        shape = classify_path(["a", "b", "a", "b", "c"])
        # a revisited at 2, b revisited at 3; ends on fresh c -> escaped.
        self.assertEqual(shape.outcome, ESCAPED)
        self.assertEqual(shape.revisits, ((2, "a"), (3, "b")))
        self.assertEqual(shape.revisited_nodes, ("a", "b"))


class TestLoopLength(unittest.TestCase):
    def test_no_revisits_has_no_lengths(self):
        shape = classify_path(["a", "b", "c"])
        self.assertEqual(shape.loop_lengths, ())
        self.assertEqual(shape.widest_loop, 0)

    def test_immediate_reask_has_length_one(self):
        # The same node two turns running is a tight self-circle.
        shape = classify_path(["a", "a"])
        self.assertEqual(shape.loop_lengths, (1,))
        self.assertEqual(shape.widest_loop, 1)

    def test_return_after_a_detour_has_span_of_the_circle(self):
        # a -> b -> a: came back after one intervening node, a circle of 2 steps.
        shape = classify_path(["a", "b", "a"])
        self.assertEqual(shape.loop_lengths, (2,))
        self.assertEqual(shape.widest_loop, 2)

    def test_length_measured_from_previous_visit_not_first(self):
        # a touched at 0, 2, 4. Each return closes a 2-step circle; the length
        # must not grow to 4 by measuring back to the first visit.
        shape = classify_path(["a", "b", "a", "c", "a"])
        self.assertEqual(shape.loop_lengths, (2, 2))
        self.assertEqual(shape.widest_loop, 2)

    def test_lengths_align_with_revisits(self):
        # Two different nodes returned to at different spans; order preserved.
        shape = classify_path(["a", "b", "b", "a"])
        # b re-asked immediately at 2 (span 1); a returned at 3 (span 3).
        self.assertEqual(shape.revisits, ((2, "b"), (3, "a")))
        self.assertEqual(shape.loop_lengths, (1, 3))
        self.assertEqual(len(shape.loop_lengths), len(shape.revisits))
        self.assertEqual(shape.widest_loop, 3)

    def test_monad_shape_is_an_immediate_reask(self):
        # The real sample-corpus loop: re-asked the same question, then moved on.
        shape = classify_path(["monad", "monad", "burrito"])
        self.assertEqual(shape.loop_lengths, (1,))


class TestShapeGraph(unittest.TestCase):
    def test_counts_outcomes_across_paths(self):
        graph = build_graph(
            [
                {"turns": ["What is a?", "What is b?"]},  # resolved
                {"turns": ["What is a?", "What is b?", "What is a?"]},  # looping
            ]
        )
        report = shape_graph(graph)
        self.assertEqual(report.outcome_counts[RESOLVED], 1)
        self.assertEqual(report.outcome_counts[LOOPING], 1)
        self.assertEqual(report.loop_rate, 0.5)

    def test_revisited_nodes_tally_stickiest_questions(self):
        graph = build_graph(
            [
                {"turns": ["What is a?", "What is b?", "What is a?"]},
                {"turns": ["What is a?", "What is c?", "What is a?"]},
            ]
        )
        report = shape_graph(graph)
        # "a" is the node both conversations keep circling back to.
        self.assertEqual(report.revisited_nodes["what is a"], 2)

    def test_empty_graph_has_zero_loop_rate(self):
        report = shape_graph(build_graph([]))
        self.assertEqual(report.loop_rate, 0.0)
        self.assertEqual(report.shapes, [])
        self.assertEqual(report.loop_lengths, collections.Counter())
        self.assertEqual(report.immediate_reask_rate, 0.0)

    def test_loop_lengths_tally_across_the_corpus(self):
        graph = build_graph(
            [
                {"turns": ["What is a?", "What is a?"]},  # length-1 re-ask
                {"turns": ["What is a?", "What is b?", "What is a?"]},  # length-2
            ]
        )
        report = shape_graph(graph)
        self.assertEqual(report.loop_lengths, collections.Counter({1: 1, 2: 1}))
        # One of the two circles was an immediate re-ask.
        self.assertEqual(report.immediate_reask_rate, 0.5)

    def test_clustering_makes_a_loop_visible_that_was_hidden(self):
        # Two phrasings of one question, re-asked. Unclustered they are two
        # distinct nodes and the path looks resolved; clustered they fold into
        # one node and the revisit — the real loop — appears.
        convos = [
            {"turns": ["What is recursion?", "What is recursion, really?"]}
        ]
        unclustered = shape_graph(build_graph(convos))
        self.assertEqual(unclustered.outcome_counts[RESOLVED], 1)

        clustered = shape_graph(build_graph(convos, cluster=True))
        self.assertEqual(clustered.outcome_counts[LOOPING], 1)
        self.assertEqual(clustered.loop_rate, 1.0)


if __name__ == "__main__":
    unittest.main()
