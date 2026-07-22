import unittest

from cartographer.paths import (
    PathGraph,
    build_graph,
    conversation_path,
    path_edges,
)


class TestConversationPath(unittest.TestCase):
    def test_orders_questions_across_turns(self):
        convo = {
            "id": "c1",
            "turns": [
                "How do I start?",
                "I got stuck.",
                "Why does it loop back?",
            ],
        }
        self.assertEqual(
            conversation_path(convo),
            ["how do i start", "why does it loop back"],
        )

    def test_handles_single_text_blob(self):
        convo = {"text": "What is recursion? And how is it different from a loop?"}
        self.assertEqual(
            conversation_path(convo),
            ["what is recursion", "how is it different from a loop"],
        )

    def test_empty_when_no_questions(self):
        self.assertEqual(conversation_path({"turns": ["The cat sat."]}), [])


class TestPathEdges(unittest.TestCase):
    def test_consecutive_pairs(self):
        self.assertEqual(
            path_edges(["a", "b", "c"]),
            [("a", "b"), ("b", "c")],
        )

    def test_single_node_has_no_edges(self):
        self.assertEqual(path_edges(["a"]), [])

    def test_empty_path_has_no_edges(self):
        self.assertEqual(path_edges([]), [])

    def test_repeat_produces_self_edge(self):
        # Circling on the same node is real signal, not noise.
        self.assertEqual(path_edges(["a", "a"]), [("a", "a")])


class TestPathGraph(unittest.TestCase):
    def test_accumulates_nodes_edges_and_paths(self):
        graph = PathGraph()
        graph.add_path(["a", "b", "c"])
        graph.add_path(["a", "b"])

        self.assertEqual(graph.path_count, 2)
        self.assertEqual(graph.nodes["a"], 2)
        self.assertEqual(graph.nodes["c"], 1)
        self.assertEqual(graph.edges[("a", "b")], 2)
        self.assertEqual(graph.edges[("b", "c")], 1)

    def test_ignores_empty_paths(self):
        graph = PathGraph()
        graph.add_path([])
        self.assertEqual(graph.path_count, 0)
        self.assertEqual(graph.node_count, 0)
        self.assertEqual(graph.edge_count, 0)

    def test_successors_ranks_next_questions(self):
        graph = PathGraph()
        graph.add_path(["start", "middle"])
        graph.add_path(["start", "middle"])
        graph.add_path(["start", "detour"])

        succ = graph.successors("start")
        self.assertEqual(succ["middle"], 2)
        self.assertEqual(succ["detour"], 1)
        self.assertEqual(succ.most_common(1), [("middle", 2)])

    def test_most_common_transitions(self):
        graph = PathGraph()
        graph.add_path(["a", "b", "a", "b"])
        self.assertEqual(
            graph.most_common_transitions(1),
            [(("a", "b"), 2)],
        )

    def test_build_graph_from_conversations(self):
        convos = [
            {"turns": ["What is recursion?", "How does it stop?"]},
            {"turns": ["What is recursion?", "Why does it loop?"]},
        ]
        graph = build_graph(convos)
        self.assertEqual(graph.path_count, 2)
        self.assertEqual(graph.nodes["what is recursion"], 2)
        self.assertEqual(graph.successors("what is recursion").total(), 2)
        self.assertIsNone(graph.clustering)

    def test_build_graph_without_clustering_keeps_paraphrases_apart(self):
        convos = [
            {"turns": ["What is recursion?"]},
            {"turns": ["I want to understand recursion."]},
        ]
        graph = build_graph(convos)
        # Two phrasings, two nodes — the naive view can't see they're one.
        self.assertEqual(graph.node_count, 2)

    def test_build_graph_with_clustering_merges_paraphrases(self):
        convos = [
            {"turns": ["What is recursion?", "How does it stop?"]},
            {"turns": ["I want to understand recursion.", "How does it stop?"]},
            # Two "understand X" asks establish that "understand" is common
            # framing while "recursion" is the rare, topical word — so the
            # document-frequency-weighted merge fires on the topic, not the
            # scaffolding. (On a bare two-question corpus there is no frequency
            # signal, and the clusterer rightly stays cautious — see test_cluster.)
            {"turns": ["I want to understand closures."]},
            {"turns": ["I want to understand pointers."]},
        ]
        graph = build_graph(convos, cluster=True)
        # The two recursion phrasings collapse to one node, so it stacks to 2...
        self.assertEqual(graph.nodes["what is recursion"], 2)
        # ...and the shared transition now stacks too — the map showing weather.
        self.assertEqual(graph.edges[("what is recursion", "how does it stop")], 2)
        self.assertIsNotNone(graph.clustering)
        self.assertEqual(graph.clustering.merged_node_count, 1)


if __name__ == "__main__":
    unittest.main()
