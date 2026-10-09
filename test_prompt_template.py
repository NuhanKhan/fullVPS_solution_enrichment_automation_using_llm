import unittest

from prompt_template import fill_template


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


if __name__ == "__main__":
    unittest.main()
