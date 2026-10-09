import unittest

from pdf_text import cap_text, needs_ocr, strip_wrapper


class TestStripWrapper(unittest.TestCase):

    def test_clean_pdf_is_unchanged(self):
        result = strip_wrapper(b"%PDF-1.7 hello")
        self.assertEqual(result, (b"%PDF-1.7 hello", None))

    def test_pdf_with_wrapper_is_stripped(self):
        result = strip_wrapper(b"some wrapper %PDF-1.7 hello")
        self.assertEqual(result, (b"%PDF-1.7 hello", None))

    def test_pdf_without_header_raises_error(self):
        result = strip_wrapper(b"no pdf header here")
        self.assertIsNone(result[0])
        self.assertIsNotNone(result[1])  # Ensure an error message is returned

class TestNeedsOcr(unittest.TestCase):

    def test_normal_text_does_not_need_ocr(self):
        text = "a" * 500
        self.assertFalse(needs_ocr(text, 1))

    def test_almost_empty_text_needs_ocr(self):
        text = "a" * 20
        self.assertTrue(needs_ocr(text, 1))

    def test_whitespace_only_needs_ocr(self):
        text = " \n" * 1000
        self.assertTrue(needs_ocr(text, 5))

    def test_scanned_pdf_with_stamps_needs_ocr(self):
        # 40 pages, only 8 real chars per page
        text = "a" * 320
        self.assertTrue(needs_ocr(text, 40))

    def test_scan_with_only_filing_stamps_padded_by_spaces_needs_ocr(self):
        # Real case: NJ e-filed scan, 54 pages, each page is 190 spaces plus the court stamp
        page = " " * 190 + "\n OCN-L-002715-26   09/10/2026 9:46:06 AM   Pg 1 of 54   Trans ID: LCV20262401754 \n"
        self.assertTrue(needs_ocr(page * 54, 54))

    def test_short_real_letter_does_not_need_ocr(self):
        # 1 page, 250 chars, real text
        text = "a" * 250
        self.assertFalse(needs_ocr(text, 1))



class TestCapText(unittest.TestCase):

    def test_long_text_keeps_head_and_tail(self):
        result = cap_text("abcdefghijklmnop", 10)
        self.assertEqual(result, "abcdefgnop")

    def test_short_text_is_unchanged(self):
        result = cap_text("abcdef", 10)
        self.assertEqual(result, "abcdef")

    def test_text_at_exact_limit_is_unchanged(self):
        result = cap_text("abcdefghij", 10)
        self.assertEqual(result, "abcdefghij")
