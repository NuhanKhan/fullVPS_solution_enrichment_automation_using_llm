import unittest
from types import SimpleNamespace

from llm import parse_json_response, reply_cost


class TestParseJsonResponse(unittest.TestCase):

    def test_plain_json_is_parsed(self):
        result = parse_json_response('{"a": 1}')
        self.assertEqual(result, ({"a": 1}, None))

    def test_markdown_fence_is_ignored(self):
        result = parse_json_response('```json\n{"a": 1}\n```')
        self.assertEqual(result, ({"a": 1}, None))

    def test_text_around_the_object_is_ignored(self):
        result = parse_json_response('Here you go: {"a": {"b": 2}} done')
        self.assertEqual(result, ({"a": {"b": 2}}, None))

    def test_no_object_returns_error(self):
        result, error = parse_json_response("sorry, I cannot help")
        self.assertIsNone(result)
        self.assertIsNotNone(error)

    def test_broken_json_returns_error(self):
        result, error = parse_json_response('{"a": 1,')
        self.assertIsNone(result)
        self.assertIsNotNone(error)

    def test_json_list_returns_error(self):
        result, error = parse_json_response('[{"a": 1}]')
        self.assertIsNone(result)
        self.assertIsNotNone(error)

    def test_empty_response_returns_error(self):
        result, error = parse_json_response("")
        self.assertIsNone(result)
        self.assertIsNotNone(error)



class TestReplyCost(unittest.TestCase):

    def test_cost_reported_by_openrouter_is_used(self):
        self.assertEqual(reply_cost(SimpleNamespace(cost=0.0123)), 0.0123)

    def test_missing_usage_counts_as_zero(self):
        self.assertEqual(reply_cost(None), 0.0)

    def test_usage_without_cost_counts_as_zero(self):
        self.assertEqual(reply_cost(SimpleNamespace(prompt_tokens=5)), 0.0)

    def test_null_cost_counts_as_zero(self):
        self.assertEqual(reply_cost(SimpleNamespace(cost=None)), 0.0)
