"""Tests for the map renderer — that the DOT is faithful, valid, and honest.

The renderer's whole job is to draw the topology *as it is*: nodes sized by
frequency, edges by weight, self-loops as bends, sticky nodes filled. These tests
pin exactly that, plus the two properties the project has always guarded —
determinism / order-independence, and that pruning prunes but never invents.
"""

import unittest

from cartographer.loops import shape_graph
from cartographer.paths import PathGraph, build_graph
from cartographer.render import _escape, _mix, _scale, to_dot


def _graph_from_paths(paths):
    g = PathGraph()
    for p in paths:
        g.add_path(list(p))
    return g


class DotStructureTests(unittest.TestCase):
    def test_empty_graph_is_a_valid_empty_digraph(self):
        dot = to_dot(PathGraph())
        self.assertTrue(dot.startswith("digraph cartography {"))
        self.assertTrue(dot.rstrip().endswith("}"))
        # No node/edge lines.
        self.assertNotIn(" -> ", dot)
        self.assertNotIn("[label=", dot)

    def test_single_node_renders_one_labelled_box_and_no_edges(self):
        dot = to_dot(_graph_from_paths([["what is recursion"]]))
        self.assertIn("what is recursion", dot)
        self.assertIn("1 asked", dot)
        self.assertNotIn(" -> ", dot)

    def test_an_edge_becomes_an_arrow(self):
        dot = to_dot(_graph_from_paths([["a", "b"]]))
        self.assertIn(" -> ", dot)
        # Two distinct node ids, one arrow between them.
        self.assertEqual(dot.count(" -> "), 1)

    def test_output_always_closes_the_digraph(self):
        dot = to_dot(_graph_from_paths([["a", "b", "c"]]))
        self.assertEqual(dot.rstrip()[-1], "}")


class SelfLoopTests(unittest.TestCase):
    def test_a_reask_draws_a_self_loop(self):
        # The MONAD→MONAD self-edge, the atom of the whole loop reading.
        dot = to_dot(_graph_from_paths([["monad", "monad"]]))
        # Exactly one node, and an arrow from it to itself.
        self.assertEqual(dot.count(" -> "), 1)
        # The self-edge is nX -> nX (same id both sides).
        arrow = [ln for ln in dot.splitlines() if " -> " in ln][0]
        left, right = arrow.split(" -> ")
        src = left.strip()
        dst = right.split(" ")[0]
        self.assertEqual(src, dst)


class ProminenceTests(unittest.TestCase):
    def test_more_asked_node_gets_a_bigger_font(self):
        # 'a' asked 3x, 'z' asked once.
        g = _graph_from_paths([["a", "z"], ["a", "a"]])
        dot = to_dot(g)
        fonts = {}
        for line in dot.splitlines():
            if "label=" in line and " -> " not in line:
                # crude parse: find fontsize=NN
                if "a\\n" in line and "3 asked" in line:
                    fonts["a"] = _fontsize(line)
                if "z\\n" in line and "1 asked" in line:
                    fonts["z"] = _fontsize(line)
        self.assertIn("a", fonts)
        self.assertIn("z", fonts)
        self.assertGreater(fonts["a"], fonts["z"])

    def test_heavier_edge_gets_a_thicker_pen(self):
        # edge (a,b) travelled twice, (b,c) once.
        g = _graph_from_paths([["a", "b", "c"], ["a", "b"]])
        dot = to_dot(g)
        pens = {}
        for line in dot.splitlines():
            if " -> " in line:
                pen = float(line.split("penwidth=")[1].split(",")[0].split("]")[0])
                if 'label="2"' in line:
                    pens["ab"] = pen
                else:
                    pens.setdefault("other", pen)
        self.assertIn("ab", pens)
        self.assertIn("other", pens)
        self.assertGreater(pens["ab"], pens["other"])

    def test_repeated_edge_carries_a_weight_label_single_does_not(self):
        g = _graph_from_paths([["a", "b"], ["a", "b"]])
        dot = to_dot(g)
        self.assertIn('label="2"', dot)  # the doubled transition
        # a weight-1 transition should not be labelled with its weight
        g1 = _graph_from_paths([["a", "b"]])
        self.assertNotIn('label="1"', to_dot(g1))


class StickyNodeTests(unittest.TestCase):
    def test_a_returned_to_node_is_filled_and_annotated(self):
        # a -> b -> a : 'a' is returned to once (escaped path).
        g = _graph_from_paths([["a", "b", "a"]])
        report = shape_graph(g)
        self.assertIn("a", report.revisited_nodes)  # sanity: it is sticky
        dot = to_dot(g, report=report)
        a_line = _node_line(dot, "a")
        b_line = _node_line(dot, "b")
        self.assertIn("filled", a_line)
        self.assertIn("returned", a_line)
        self.assertNotIn("filled", b_line)

    def test_no_sticky_nodes_means_no_fill_anywhere(self):
        # A straight line resolves; nothing is returned to.
        dot = to_dot(_graph_from_paths([["a", "b", "c"]]))
        self.assertNotIn("filled", dot)
        self.assertNotIn("returned", dot)

    def test_more_returned_to_node_fills_more_saturated(self):
        # revisited_nodes counts *paths* that returned to a node. 'a' is returned
        # to in two separate paths, 'x' in one — so 'a' is the heavier returner.
        g = _graph_from_paths([["a", "b", "a"], ["a", "c", "a"], ["x", "y", "x"]])
        report = shape_graph(g)
        dot = to_dot(g, report=report)
        a_fill = _fillcolor(_node_line(dot, "a"))
        x_fill = _fillcolor(_node_line(dot, "x"))
        # 'a' is the heaviest returner → closer to the saturated warm end, so its
        # blue channel is lower than the lighter fill of 'x'.
        self.assertLess(_blue(a_fill), _blue(x_fill))


class EscapingTests(unittest.TestCase):
    def test_quotes_and_backslashes_are_escaped(self):
        raw = 'why say "no" \\ backslash'
        escaped = _escape(raw)
        self.assertNotIn('"no"', escaped)  # the inner quotes got backslashed
        self.assertIn('\\"no\\"', escaped)
        self.assertIn("\\\\", escaped)  # the literal backslash doubled

    def test_a_quoted_question_keeps_the_dot_balanced(self):
        # A label with a raw quote must not break out of its DOT string: the only
        # unescaped quotes are the ones delimiting attribute values, so the count
        # of unescaped double-quotes on the node line stays even.
        g = _graph_from_paths([['is it "real"']])
        line = _node_line(to_dot(g), "is it")
        # Every " in the emitted line is either a delimiter or escaped as \".
        unescaped = _count_unescaped_quotes(line)
        self.assertEqual(unescaped % 2, 0)


class PruningTests(unittest.TestCase):
    def test_max_nodes_keeps_only_the_most_asked(self):
        g = _graph_from_paths([["a", "a", "b", "b", "c"]])  # a:2 b:2 c:1
        dot = to_dot(g, max_nodes=2)
        self.assertIn("a\\n", dot)
        self.assertIn("b\\n", dot)
        self.assertNotIn("c\\n", dot)

    def test_pruned_node_drops_its_edges(self):
        # Keep only 'a'; every edge touches a pruned node, so none survive — and
        # none is invented. (No self-loop on 'a', so nothing legitimately stays.)
        g = _graph_from_paths([["a", "b", "c", "a"]])  # a:2 b:1 c:1
        dot = to_dot(g, max_nodes=1)  # keep only 'a'
        self.assertEqual(dot.count(" -> "), 0)

    def test_min_edge_weight_drops_thin_roads(self):
        g = _graph_from_paths([["a", "b", "c"], ["a", "b"]])  # a->b:2, b->c:1
        dot = to_dot(g, min_edge_weight=2)
        self.assertEqual(dot.count(" -> "), 1)  # only the weight-2 road survives
        self.assertIn('label="2"', dot)


class DeterminismTests(unittest.TestCase):
    def test_same_graph_renders_identically(self):
        g = _graph_from_paths([["a", "b", "a"], ["c", "d"]])
        self.assertEqual(to_dot(g), to_dot(g))

    def test_corpus_order_does_not_change_the_map(self):
        # Order-independence, the invariant guarded since session 003. Build the
        # same paths in two orders; the sorted rendering must be byte-identical.
        paths = [["a", "b"], ["b", "c"], ["a", "b"]]
        forward = to_dot(_graph_from_paths(paths))
        backward = to_dot(_graph_from_paths(list(reversed(paths))))
        self.assertEqual(forward, backward)


class RealCorpusSmokeTest(unittest.TestCase):
    """The renderer must survive the real Socratic corpus, clustered."""

    def test_socratic_map_is_nonempty_valid_and_has_a_loop(self):
        import os

        path = os.path.join(
            os.path.dirname(__file__), "..", "examples", "socratic_dialogues.jsonl"
        )
        if not os.path.exists(path):
            self.skipTest("socratic corpus not present")
        from cartographer.corpus import load_jsonl

        graph = build_graph(load_jsonl(path), cluster=True)
        dot = to_dot(graph)
        self.assertTrue(dot.startswith("digraph"))
        self.assertTrue(dot.rstrip().endswith("}"))
        # The Meno/Euthyphro dialogues circle: there must be at least one filled,
        # returned-to node in the picture — the map's whole reason for being.
        self.assertIn("returned", dot)


# --- small parse helpers for the assertions above --------------------------


def _fontsize(line: str) -> float:
    return float(line.split("fontsize=")[1].split(",")[0].split("]")[0])


def _node_line(dot: str, needle: str) -> str:
    # Match on the label's opening so we hit the node *named* `needle`, not any
    # line that merely contains the letters (e.g. "label" contains "b").
    marker = f'label="{needle}'
    for line in dot.splitlines():
        if marker in line and " -> " not in line:
            return line
    raise AssertionError(f"no node line whose label starts with {needle!r}")


def _fillcolor(line: str) -> str:
    return line.split('fillcolor="')[1].split('"')[0]


def _blue(hex_color: str) -> int:
    return int(hex_color[5:7], 16)


def _count_unescaped_quotes(line: str) -> int:
    count, i = 0, 0
    while i < len(line):
        if line[i] == "\\":
            i += 2
            continue
        if line[i] == '"':
            count += 1
        i += 1
    return count


class ColorMathTests(unittest.TestCase):
    def test_mix_endpoints(self):
        self.assertEqual(_mix("#000000", "#ffffff", 0.0), "#000000")
        self.assertEqual(_mix("#000000", "#ffffff", 1.0), "#ffffff")

    def test_scale_degenerate_range_sits_at_floor(self):
        self.assertEqual(_scale(5, 5, 5, 10.0, 30.0), 10.0)


if __name__ == "__main__":
    unittest.main()
