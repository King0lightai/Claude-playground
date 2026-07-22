import unittest

from cartographer.extract import extract_questions, normalize


class TestNormalize(unittest.TestCase):
    def test_lowercases_and_strips_question_mark(self):
        self.assertEqual(normalize("How Do I Do This?"), "how do i do this")

    def test_drops_leading_filler(self):
        self.assertEqual(normalize("So, how do I do this?"), "how do i do this")
        self.assertEqual(normalize("Well okay what now?"), "what now")

    def test_collapses_whitespace(self):
        self.assertEqual(normalize("  what   is    this  "), "what is this")


class TestExtractQuestions(unittest.TestCase):
    def test_extracts_explicit_question(self):
        self.assertEqual(
            extract_questions("How do I tell my partner the truth?"),
            ["how do i tell my partner the truth"],
        )

    def test_extracts_wh_question_without_mark(self):
        self.assertEqual(extract_questions("What is recursion"), ["what is recursion"])

    def test_extracts_intent_statement(self):
        self.assertEqual(
            extract_questions("I want to understand recursion."),
            ["i want to understand recursion"],
        )

    def test_ignores_plain_statements(self):
        self.assertEqual(extract_questions("The cat sat on the mat."), [])

    def test_preserves_order_across_a_conversation(self):
        text = "How do I start? The middle is hard. Why does it loop back?"
        self.assertEqual(
            extract_questions(text),
            ["how do i start", "why does it loop back"],
        )

    def test_short_wh_fragment_needs_a_question_mark(self):
        # "Why." alone is too short to count as an intent without a "?".
        self.assertEqual(extract_questions("Why."), [])
        self.assertEqual(extract_questions("Why?"), ["why"])


if __name__ == "__main__":
    unittest.main()
