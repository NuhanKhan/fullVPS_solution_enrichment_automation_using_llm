import unittest

from prompt_template import fill_template, prompt_version


class TestFillTemplate(unittest.TestCase):

    def test_placeholders_are_replaced(self):
        result = fill_template("Hi {{name}}, row {{row}}", {"name": "Ali", "row": 2})
        self.assertEqual(result, ("Hi Ali, row 2", None))

    def test_json_braces_are_left_alone(self):
        result = fill_template('Return {"email": null} for {{name}}', {"name": "Ali"})
        self.assertEqual(result, ('Return {"email": null} for Ali', None))

    def test_missing_value_returns_error(self):
        result, error = fill_template("Hi {{name}} {{last}}", {"name": "Ali"})
        self.assertIsNone(result)
        self.assertIn("last", error)

    def test_unused_value_returns_error(self):
        result, error = fill_template("Hi {{name}}", {"name": "Ali", "typo": "x"})
        self.assertIsNone(result)
        self.assertIn("typo", error)

    def test_placeholder_text_inside_a_value_is_not_replaced(self):
        result = fill_template("{{text}} / {{n}}", {"text": "doc says {{n}}", "n": 1})
        self.assertEqual(result, ("doc says {{n}} / 1", None))


class TestPromptVersion(unittest.TestCase):

    def test_same_text_gives_the_same_version(self):
        self.assertEqual(prompt_version("Score the case."), prompt_version("Score the case."))

    def test_a_changed_word_gives_a_new_version(self):
        self.assertNotEqual(prompt_version("Score the case."), prompt_version("Score the claim."))

    def test_spacing_and_line_breaks_do_not_count_as_a_change(self):
        self.assertEqual(prompt_version("Score the case.\n"), prompt_version("Score   the\r\ncase."))

    def test_version_is_twelve_hex_characters(self):
        version = prompt_version("Score the case.")
        self.assertEqual(len(version), 12)
        int(version, 16)


if __name__ == "__main__":
    unittest.main()
