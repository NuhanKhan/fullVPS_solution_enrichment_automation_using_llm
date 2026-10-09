import unittest

from cache import cache_key


class TestCacheKey(unittest.TestCase):

    def test_same_expert_and_url_give_the_same_key(self):
        self.assertEqual(cache_key("ariel", "https://x.com/a.pdf"), cache_key("ariel", "https://x.com/a.pdf"))

    def test_different_expert_gives_a_different_key(self):
        self.assertNotEqual(cache_key("ariel", "https://x.com/a.pdf"), cache_key("other", "https://x.com/a.pdf"))

    def test_different_url_gives_a_different_key(self):
        self.assertNotEqual(cache_key("ariel", "https://x.com/a.pdf"), cache_key("ariel", "https://x.com/b.pdf"))

    def test_surrounding_spaces_in_url_are_ignored(self):
        self.assertEqual(cache_key("ariel", " https://x.com/a.pdf "), cache_key("ariel", "https://x.com/a.pdf"))

    def test_key_is_safe_as_a_file_name(self):
        key = cache_key("ariel", "https://x.com/a.pdf?id=1&x=/../")
        self.assertTrue(key.isalnum())
