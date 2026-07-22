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


if __name__ == "__main__":
    unittest.main()
