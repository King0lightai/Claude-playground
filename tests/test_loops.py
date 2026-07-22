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
