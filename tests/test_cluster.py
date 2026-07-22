import collections
import unittest

from cartographer.cluster import (
    Clustering,
    cluster_questions,
    content_words,
    similarity,
)


class TestContentWords(unittest.TestCase):
    def test_drops_structural_scaffolding(self):
        # Only the topical word survives the stopword strip.
        self.assertEqual(content_words("what is recursion"), frozenset({"recursion"}))

    def test_keeps_content_verbs_and_nouns(self):
        self.assertEqual(
            content_words("how do i tell my partner the truth"),
            frozenset({"tell", "partner", "truth"}),
        )

    def test_light_stemming_folds_inflections(self):
        # "careers" -> "career", so it matches the singular.
        self.assertIn("career", content_words("change careers"))
        self.assertEqual(content_words("telling"), content_words("tell"))

    def test_pure_scaffolding_has_empty_fingerprint(self):
        self.assertEqual(content_words("what is it"), frozenset())


class TestSimilarity(unittest.TestCase):
    def test_identical_fingerprints_are_one(self):
        self.assertEqual(similarity("what is a monad", "explain the monad"), 1.0)

    def test_partial_overlap_is_jaccard(self):
        # {understand, recursion} vs {recursion} -> 1 / 2.
        self.assertAlmostEqual(
            similarity("i want to understand recursion", "what is recursion"), 0.5
        )

    def test_no_shared_content_word_is_zero(self):
        self.assertEqual(similarity("what is recursion", "how do i change careers"), 0.0)

    def test_empty_fingerprint_is_dissimilar(self):
        # No topical evidence -> not the same node, even both being empty.
        self.assertEqual(similarity("what is it", "why is that"), 0.0)


class TestClusterQuestions(unittest.TestCase):
    def test_merges_paraphrases_sharing_topic(self):
        weights = collections.Counter(
            {"what is recursion": 1, "i want to understand recursion": 1}
        )
        clustering = cluster_questions(weights)
        self.assertEqual(
            clustering.label("what is recursion"),
            clustering.label("i want to understand recursion"),
        )
        self.assertEqual(clustering.merged_node_count, 1)

    def test_representative_is_most_frequent(self):
        weights = collections.Counter(
            {"what is recursion": 5, "i want to understand recursion": 1}
        )
        clustering = cluster_questions(weights)
        self.assertEqual(clustering.label("i want to understand recursion"), "what is recursion")

    def test_representative_tie_breaks_to_shortest(self):
        weights = collections.Counter(
            {"explain what a monad is": 1, "what is a monad really": 1}
        )
        clustering = cluster_questions(weights)
        # Equal frequency -> shorter phrasing wins ("what is a monad really" is
        # 22 chars vs "explain what a monad is" at 23).
        self.assertEqual(
            clustering.label("explain what a monad is"), "what is a monad really"
        )

    def test_keeps_unrelated_questions_apart(self):
        weights = collections.Counter(
            {"what is recursion": 1, "how do i change careers": 1}
        )
        clustering = cluster_questions(weights)
        self.assertNotEqual(
            clustering.label("what is recursion"),
            clustering.label("how do i change careers"),
        )
        self.assertEqual(clustering.merged_node_count, 0)

    def test_members_lists_every_phrasing(self):
        weights = collections.Counter(
            {"what is recursion": 2, "i want to understand recursion": 1}
        )
        clustering = cluster_questions(weights)
        self.assertEqual(
            clustering.members["what is recursion"],
            ["i want to understand recursion", "what is recursion"],
        )

    def test_is_order_independent(self):
        forward = cluster_questions(
            collections.Counter({"a b c": 1, "a b d": 1, "a b e": 1})
        )
        reverse = cluster_questions(
            collections.Counter({"a b e": 1, "a b d": 1, "a b c": 1})
        )
        self.assertEqual(forward.members, reverse.members)

    def test_threshold_is_respected(self):
        # {tell, partner, truth} vs {tell, partner, hard}: Jaccard 2/4 = 0.5.
        weights = collections.Counter(
            {"tell my partner the truth": 1, "tell my partner something hard": 1}
        )
        self.assertEqual(cluster_questions(weights, threshold=0.5).merged_node_count, 1)
        self.assertEqual(cluster_questions(weights, threshold=0.6).merged_node_count, 0)

    def test_unlabelled_question_maps_to_itself(self):
        clustering = Clustering({}, {})
        self.assertEqual(clustering.label("never seen"), "never seen")


class TestNegationScaffolding(unittest.TestCase):
    """Negation is sentence machinery, not topic (session 007).

    On the real Socratic corpus, the words ``not``/``no``/``nor``/``neither``
    survived stopword stripping and made every negated, rhetorical, and tag
    question collapse to a fingerprint dominated by ``not``. That turned
    ``"why not"`` into a hub matching anything else carrying a negation, and
    single-linkage welded 23 unrelated questions — the paradox of inquiry among
    them — into one garbage super-node. See JOURNAL.md, sessions 006/007.
    """

    def test_negation_words_are_dropped(self):
        for word in ("not", "no", "nor", "neither"):
            with self.subTest(word=word):
                self.assertNotIn(word, content_words(f"is virtue {word} taught"))

    def test_pure_rhetorical_negation_has_empty_fingerprint(self):
        # "why not" asks nothing on its own — no content word survives.
        self.assertEqual(content_words("why not"), frozenset())
        self.assertEqual(content_words("is it not so"), frozenset())

    def test_bare_negation_prompt_hubs_nothing(self):
        # The failure in miniature: three questions that used to collapse onto
        # {not}. With negation stripped, "why not" is contentless and merges
        # with no one; the other two keep only their real topic word.
        weights = collections.Counter(
            {"why not": 1, "am i not right": 1, "do you not agree": 1}
        )
        clustering = cluster_questions(weights)
        self.assertEqual(clustering.merged_node_count, 0)
        self.assertEqual(clustering.label("why not"), "why not")

    def test_polarity_folds_to_the_same_topic_node(self):
        # A deliberate design call: on a map of *what is being wrestled with*,
        # asserting X and questioning not-X are the same inquiry. The polarity
        # is the answer under test, not a different question.
        weights = collections.Counter(
            {"is virtue taught": 1, "virtue is not taught": 1}
        )
        clustering = cluster_questions(weights)
        self.assertEqual(
            clustering.label("is virtue taught"),
            clustering.label("virtue is not taught"),
        )

    def test_good_partial_merge_is_not_collateral_damage(self):
        # Guard against the tempting-but-wrong "min-fingerprint" fix: a singleton
        # fingerprint matching a doubleton at Jaccard 0.5 is sometimes right
        # ({recursion} ~ {recursion, understand}) and sometimes the old blob
        # ({not} ~ {not, right}). Nothing lexical separates them, so the negation
        # fix must target the *word*, never the fingerprint size — this founding
        # merge has to survive it. (Its bad twin is killed by the test above.)
        weights = collections.Counter(
            {"what is recursion": 1, "i want to understand recursion": 1}
        )
        self.assertEqual(cluster_questions(weights).merged_node_count, 1)


if __name__ == "__main__":
    unittest.main()
