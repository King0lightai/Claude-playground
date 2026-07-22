import collections
import unittest

from cartographer.cluster import (
    Clustering,
    cluster_questions,
    content_words,
    document_frequencies,
    importance_weights,
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
    # A little filler that makes "understand" common framing and "recursion" the
    # rare topical word, so the document-frequency-weighted merge has real signal
    # to read. See TestDocumentFrequencyWeighting for why a bare two-question
    # corpus (no frequency signal) deliberately does *not* merge here.
    _UNDERSTAND_FILLER = {
        "i want to understand closures": 1,
        "i want to understand pointers": 1,
    }

    def test_merges_paraphrases_sharing_topic(self):
        weights = collections.Counter(
            {"what is recursion": 1, "i want to understand recursion": 1}
        )
        weights.update(self._UNDERSTAND_FILLER)
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
        weights.update(self._UNDERSTAND_FILLER)
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
        weights.update(self._UNDERSTAND_FILLER)
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
        # Two questions with partial content-word overlap: they merge under a
        # permissive threshold and stay apart under the strictest one. (The exact
        # crossover point depends on the corpus's document-frequency weighting, so
        # this pins the *contract* — threshold gates the merge — not a magic
        # number. The plain-Jaccard crossover is pinned in TestSimilarity.)
        weights = collections.Counter(
            {"tell my partner the truth": 1, "tell my partner something hard": 1}
        )
        self.assertEqual(cluster_questions(weights, threshold=0.1).merged_node_count, 1)
        self.assertEqual(cluster_questions(weights, threshold=1.0).merged_node_count, 0)

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
        # The founding merge — a singleton fingerprint {recursion} folding into a
        # doubleton {recursion, understand} at Jaccard 0.5 — must survive the
        # bridge-word fix. Session 007 proved no fingerprint-*size* guard can help
        # here, because this good merge is structurally identical to the bad one
        # ({not} ~ {not, right}); nothing about *size* separates them. Document-
        # frequency weighting is the tool that does: "recursion" is the rare,
        # informative word, so it holds the merge. (Its bad twin — a merge welded
        # by a corpus-wide word — is refused; see TestDocumentFrequencyWeighting.)
        weights = collections.Counter(
            {"what is recursion": 1, "i want to understand recursion": 1}
        )
        weights.update(
            {"i want to understand closures": 1, "i want to understand pointers": 1}
        )
        self.assertEqual(cluster_questions(weights).merged_node_count, 1)


class TestDocumentFrequencyWeighting(unittest.TestCase):
    """Down-weighting corpus-wide words dissolves the bridge-word hub (session 008).

    On the real Socratic corpus the vocative "socrates" (whom a question
    *addresses*, not what it's *about*) spanned ~18 questions, so a bare
    {socrat} question sat at Jaccard 0.5 with both {mean, socrat} and
    {say, socrat} and single-linkage welded a 15-member "what do you mean / say /
    answer" super-node. Weighting each word by inverse document frequency lets a
    frequent word count for little, so it can no longer act as a merge hub. See
    JOURNAL.md, session 008.
    """

    def test_rarer_word_weighs_more(self):
        # "socrates" in every question, "recursion" in one: recursion is the
        # stronger evidence of sameness and must weigh more.
        questions = [
            "what is recursion, socrates",
            "what is virtue, socrates",
            "what is justice, socrates",
        ]
        weights = importance_weights(questions)
        self.assertGreater(weights["recursion"], weights["socrat"])

    def test_ubiquitous_word_is_floored_not_zeroed(self):
        # A word in every question carries no discriminating signal, but the
        # weight is floored at 1.0 (never zero) so a shared word is always at
        # least weak evidence and the weighted Jaccard never divides by zero.
        questions = ["what is virtue, socrates", "what is justice, socrates"]
        weights = importance_weights(questions)
        self.assertEqual(weights["socrat"], 1.0)

    def test_document_frequency_counts_distinct_questions(self):
        df = document_frequencies(
            ["what is virtue, socrates", "what is justice, socrates", "why not"]
        )
        self.assertEqual(df["socrat"], 2)
        self.assertEqual(df["virtue"], 1)
        self.assertNotIn("not", df)  # negation is scaffolding, never a content word

    def test_corpus_wide_word_cannot_bridge_two_questions(self):
        # The failure in miniature. A bare vocative {socrat} would, under plain
        # Jaccard, sit at 0.5 with both {mean, socrat} and {say, socrat} and chain
        # the mean- and say-families into one blob. With the vocative made common
        # (four "socrates" questions) and the topic words kept rare, that bridge
        # is refused: the two families stay apart.
        weights = collections.Counter(
            {
                "why not, socrates": 1,  # -> {socrat}, the bare-vocative hub
                "what do you mean, socrates": 1,  # -> {mean, socrat}
                "what do you say, socrates": 1,  # -> {say, socrat}
                "farewell, socrates": 1,  # more "socrates" -> it's boilerplate
            }
        )
        clustering = cluster_questions(weights)
        mean_q = "what do you mean, socrates"
        say_q = "what do you say, socrates"
        self.assertNotEqual(clustering.label(mean_q), clustering.label(say_q))

    def test_informative_and_boilerplate_bridges_are_told_apart(self):
        # The whole point, in one corpus: two structurally identical singleton~
        # doubleton pairs. The one whose shared word is rare/topical (recursion)
        # merges; the one whose shared word is corpus-wide boilerplate (the
        # vocative) does not. Fingerprint *size* is identical for both — only
        # document frequency separates them, exactly as session 007 predicted.
        weights = collections.Counter(
            {
                # informative shared word "recursion" (rare) -> merges
                "what is recursion": 1,
                "i want to understand recursion": 1,
                "i want to understand closures": 1,  # makes "understand" common
                "i want to understand pointers": 1,
                # boilerplate shared word "socrates" (common) -> refused
                "why not, socrates": 1,
                "what do you mean, socrates": 1,
                "what do you say, socrates": 1,
                "farewell, socrates": 1,
            }
        )
        clustering = cluster_questions(weights)
        # good merge held
        self.assertEqual(
            clustering.label("what is recursion"),
            clustering.label("i want to understand recursion"),
        )
        # bad bridge refused
        self.assertEqual(clustering.label("why not, socrates"), "why not, socrates")

    def test_weighting_is_order_independent(self):
        forward = cluster_questions(
            collections.Counter(
                {"what is recursion, socrates": 1, "what is virtue, socrates": 1,
                 "what is justice, socrates": 1}
            )
        )
        reverse = cluster_questions(
            collections.Counter(
                {"what is justice, socrates": 1, "what is virtue, socrates": 1,
                 "what is recursion, socrates": 1}
            )
        )
        self.assertEqual(forward.members, reverse.members)


if __name__ == "__main__":
    unittest.main()
