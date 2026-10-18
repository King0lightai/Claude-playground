"""Tests for the move layer — the kind of question, and whether its order means anything.

Pins three things: the classifier's rules (each move, plus the residual), that a
move graph is an ordinary PathGraph whose roads stack across conversations, and
that the persistence test is an honest null — it fires on real momentum, stays
quiet when paths merely differ in their mix of moves (the CMV trap), and is
deterministic.
"""

import unittest

from cartographer.corpus import load_jsonl
from cartographer.moves import (
    CAUSE,
    CHOOSE,
    CONFIRM,
    DEFINE,
    FACT,
    METHOD,
    MOVES,
    PROPOSE,
    SUPPOSE,
    build_move_graph,
    classify_move,
    move_path,
    persistence,
    transition_lift,
)
from cartographer.paths import PathGraph


def build_from(paths):
    g = PathGraph()
    for p in paths:
        g.add_path(p)
    return g


class ClassifyMoveTests(unittest.TestCase):
    def assertMove(self, question, move):
        self.assertEqual(classify_move(question), move, question)

    def test_definition(self):
        self.assertMove("what is recursion", DEFINE)
        self.assertMove("what's a monad, really", DEFINE)
        self.assertMove("explain what a monad is", DEFINE)

    def test_cause(self):
        self.assertMove("why does my code loop like that", CAUSE)

    def test_method(self):
        self.assertMove("how do i tell my partner the truth", METHOD)
        self.assertMove("i want to understand recursion", METHOD)
        self.assertMove("walk me through it", METHOD)

    def test_fact_including_how_many_which_is_not_a_method(self):
        self.assertMove("when does it stop", FACT)
        self.assertMove("who taught him", FACT)
        self.assertMove("how many feet are in this", FACT)

    def test_choose(self):
        self.assertMove("which is the better figure", CHOOSE)
        self.assertMove("is virtue taught or acquired by practice", CHOOSE)

    def test_suppose(self):
        self.assertMove("what if the friend lied", SUPPOSE)
        self.assertMove("what about the person who runs for office", SUPPOSE)
        self.assertMove("suppose that he had never been taught", SUPPOSE)
        self.assertMove("if virtue is knowledge, can it be taught", SUPPOSE)

    def test_confirm_is_an_inverted_yes_no_question(self):
        self.assertMove("do you agree", CONFIRM)
        self.assertMove("is not this the case", CONFIRM)
        self.assertMove("isn't it obvious", CONFIRM)

    def test_propose_is_the_residual_a_statement_offered_for_assent(self):
        self.assertMove("they must be temperate and just", PROPOSE)
        self.assertMove("", PROPOSE)

    def test_leading_connectives_are_stripped(self):
        self.assertMove("or is the nature of health always the same", CONFIRM)
        self.assertMove("and why not", CAUSE)
        self.assertMove("now what is colour", DEFINE)

    def test_tell_me_followed_by_a_wh_word_reads_the_real_question(self):
        self.assertMove("tell me, what is virtue", DEFINE)
        self.assertMove("tell me why", CAUSE)
        self.assertMove("tell me the names of them", METHOD)

    def test_case_and_punctuation_tolerated(self):
        self.assertMove("Why, Socrates?", CAUSE)

    def test_known_blind_spot_a_vocative_before_the_wh_word(self):
        # Documented in the module: the rules read the opener only. A name
        # before the wh-word hides it, and the question falls to the residual.
        self.assertMove("socrates, what is colour", PROPOSE)

    def test_every_answer_is_in_the_vocabulary(self):
        for q in ["what", "why", "how", "which", "if", "do", "zebra", "tell me"]:
            self.assertIn(classify_move(q), MOVES)


class MoveGraphTests(unittest.TestCase):
    def test_move_path_follows_question_order(self):
        convo = {"turns": ["What is recursion?", "Why does it stop? How do I write one?"]}
        self.assertEqual(move_path(convo), [DEFINE, CAUSE, METHOD])

    def test_roads_stack_across_conversations_that_share_no_words(self):
        # The point of the layer: two conversations about different things make
        # the same move, so the transition is one road travelled twice.
        convos = [
            {"turns": ["What is a monad?", "Why does it matter?"]},
            {"turns": ["What is grief?", "Why does it last so long?"]},
        ]
        graph = build_move_graph(convos)
        self.assertEqual(graph.edges[(DEFINE, CAUSE)], 2)

    def test_empty_conversations_are_dropped_like_any_path(self):
        graph = build_move_graph([{"turns": ["no questions here."]}])
        self.assertEqual(graph.path_count, 0)


class TransitionLiftTests(unittest.TestCase):
    def test_lift_is_observed_over_independent_expectation(self):
        # a→b twice, b→a once: out(a)=2, in(b)=2, total=3 → expected 4/3.
        lifts = {(x.src, x.dst): x for x in transition_lift(build_from([["a", "b", "a", "b"]]))}
        self.assertEqual(lifts[("a", "b")].count, 2)
        self.assertAlmostEqual(lifts[("a", "b")].expected, 4 / 3)
        self.assertAlmostEqual(lifts[("a", "b")].lift, 1.5)

    def test_ordered_by_count_then_name(self):
        lifts = transition_lift(build_from([["b", "a"], ["a", "b"], ["a", "b"]]))
        self.assertEqual([(x.src, x.dst) for x in lifts], [("a", "b"), ("b", "a")])

    def test_empty_graph_has_no_lifts(self):
        self.assertEqual(transition_lift(build_from([])), [])


class PersistenceTests(unittest.TestCase):
    def test_runs_of_one_move_are_detected(self):
        # Every path is a block of x's then a block of y's: maximal momentum.
        paths = [["x"] * 6 + ["y"] * 6 for _ in range(10)]
        result = persistence(paths, trials=500)
        self.assertEqual(result.observed, 100)
        self.assertGreater(result.ratio, 1.5)
        self.assertLess(result.p_value, 0.01)

    def test_alternation_is_not_persistence(self):
        paths = [["x", "y"] * 6 for _ in range(10)]
        result = persistence(paths, trials=500)
        self.assertEqual(result.observed, 0)
        self.assertGreater(result.p_value, 0.9)

    def test_paths_differing_in_mix_are_not_mistaken_for_momentum(self):
        # The CMV trap: each path is uniform, so repeats are forced by the path's
        # own mix. Pooled lift would call x→x and y→y strongly persistent; the
        # within-path shuffle knows any order of an all-x path repeats the same.
        paths = [["x"] * 4, ["y"] * 4] * 5
        result = persistence(paths, trials=200)
        self.assertAlmostEqual(result.ratio, 1.0)
        self.assertEqual(result.p_value, 1.0)
        lifts = {(x.src, x.dst): x.lift for x in transition_lift(build_from(paths))}
        self.assertGreater(lifts[("x", "x")], 1.5)  # the pooled number that misleads

    def test_window_counts_repeats_only_inside_chunks(self):
        result = persistence([["x", "x", "x", "x"]], window=2, trials=10)
        # Chunks [x, x] and [x, x]: the repeat across the boundary isn't counted.
        self.assertEqual(result.observed, 2)
        self.assertEqual(result.transitions, 2)

    def test_window_below_two_is_refused(self):
        with self.assertRaises(ValueError):
            persistence([["x", "y"]], window=1)

    def test_deterministic_and_does_not_mutate_input(self):
        paths = [["a", "b", "a", "c", "c", "b"], ["c", "a", "a"]]
        snapshot = [list(p) for p in paths]
        self.assertEqual(persistence(paths, trials=300), persistence(paths, trials=300))
        self.assertEqual(paths, snapshot)

    def test_p_value_is_never_exactly_zero(self):
        result = persistence([["x"] * 5 + ["y"] * 5], trials=50)
        self.assertGreater(result.p_value, 0.0)


class RealCorpusTests(unittest.TestCase):
    """The session-014 readings, pinned so a classifier change that moves them is noticed."""

    def test_socratic_dialogues_show_persistence_that_survives_local_windows(self):
        graph = build_move_graph(load_jsonl("examples/socratic_dialogues.jsonl"))
        whole = persistence(graph.paths)
        local = persistence(graph.paths, window=10)
        self.assertLess(whole.p_value, 0.01)
        self.assertGreater(whole.ratio, 1.15)
        self.assertLess(local.p_value, 0.05)

    def test_cmv_shows_no_persistence_despite_high_diagonal_lifts(self):
        graph = build_move_graph(load_jsonl("examples/cmv_sample.jsonl"))
        result = persistence(graph.paths)
        self.assertGreater(result.p_value, 0.2)
        diagonal = [x for x in transition_lift(graph) if x.src == x.dst and x.count >= 4]
        self.assertTrue(any(x.lift > 1.5 for x in diagonal))

    def test_move_mix_tells_a_help_desk_from_a_dialectic(self):
        # Asking-for-help corpora lead with method; Socrates leads with proposals
        # and yes/no checks. Coarse, but it is the shape of the asking, not the topic.
        sample = build_move_graph(load_jsonl("examples/sample_corpus.jsonl")).nodes
        plato = build_move_graph(load_jsonl("examples/socratic_dialogues.jsonl")).nodes
        self.assertEqual(sample.most_common(1)[0][0], METHOD)
        self.assertEqual([m for m, _ in plato.most_common(2)], [PROPOSE, CONFIRM])


if __name__ == "__main__":
    unittest.main()
