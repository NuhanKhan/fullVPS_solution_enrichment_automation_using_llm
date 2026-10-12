import unittest

from pipeline import (
    row_failed,
    row_warned,
    select_rows,
    should_process,
)

LINK = "Complaint Link"


def row(index, link):
    return {"row_index": index, LINK: link}


class TestShouldProcess(unittest.TestCase):

    def test_row_with_a_link_is_processed(self):
        self.assertTrue(should_process(row(2, "https://pdfserver.amlaw.com/a.pdf"), LINK))

    def test_blank_link_is_skipped(self):
        self.assertFalse(should_process(row(2, "  "), LINK))

    def test_text_that_is_not_a_link_is_skipped(self):
        self.assertFalse(should_process(row(2, "Read Complaint"), LINK))

    def test_row_without_the_link_column_is_skipped(self):
        self.assertFalse(should_process({"row_index": 2}, LINK))


class TestSelectRows(unittest.TestCase):

    def rows(self):
        return [row(2, "https://a"), row(3, ""), row(4, "https://b"), row(5, "https://c")]

    def test_all_linked_rows_are_selected_by_default(self):
        selected = select_rows(self.rows(), LINK, 2, None)
        self.assertEqual([r["row_index"] for r in selected], [2, 4, 5])

    def test_rows_before_start_row_are_left_out(self):
        selected = select_rows(self.rows(), LINK, 4, None)
        self.assertEqual([r["row_index"] for r in selected], [4, 5])

    def test_limit_counts_only_rows_that_will_be_processed(self):
        selected = select_rows(self.rows(), LINK, 2, 2)
        self.assertEqual([r["row_index"] for r in selected], [2, 4])


class TestRowFailed(unittest.TestCase):

    def test_row_with_download_error_failed(self):
        self.assertTrue(row_failed([{"download_error": "download: 404", "extract_error": ""}]))

    def test_row_with_extract_error_failed(self):
        self.assertTrue(row_failed([{"download_error": "", "extract_error": "llm: timeout"}]))

    def test_row_without_errors_did_not_fail(self):
        self.assertFalse(row_failed([{"download_error": "", "extract_error": ""}]))


class TestRowWarned(unittest.TestCase):

    def test_row_with_extract_warning_is_counted(self):
        self.assertTrue(row_warned([{"extract_warning": "outreach_one_liner is blank"}]))

    def test_row_without_warning_is_not_counted(self):
        self.assertFalse(row_warned([{"extract_warning": ""}]))

    def test_failed_row_without_the_column_is_not_counted(self):
        self.assertFalse(row_warned([{"download_error": "download: 404"}]))
