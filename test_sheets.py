import unittest

from sheets import chunk_rows, dicts_to_rows, merge_header, quote_tab, rows_to_dicts


class TestRowsToDicts(unittest.TestCase):

    def test_short_row_is_padded(self):
        values = [
            ["name", "email", "firm"],
            ["Ali", "ali@x.com"],
        ]
        result, error = rows_to_dicts(values)
        self.assertIsNone(error)
        expected = [
            {"row_index": 2, "name": "Ali", "email": "ali@x.com", "firm": ""},
        ]
        self.assertEqual(result, expected)
    
    def test_long_row_is_truncated(self):
        values = [
            ["name", "email", "firm"],
            ["Ali", "ali@x.com", "X Corp", "Engineer"],
        ]
        result, error = rows_to_dicts(values)
        self.assertIsNone(error)
        expected = [
            {"row_index": 2, "name": "Ali", "email": "ali@x.com", "firm": "X Corp"},
        ]
        self.assertEqual(result, expected)
    
    def test_empty_tab_returns_no_header_error(self):
        result, error = rows_to_dicts([])
        self.assertIsNone(result)
        self.assertIsNotNone(error)

    def test_blank_first_row_returns_no_header_error(self):
        result, error = rows_to_dicts([[], ["Ali", "ali@x.com"]])
        self.assertIsNone(result)
        self.assertIsNotNone(error)

    def test_header_row_only(self):
        values = [
            ["name", "email", "firm"],
        ]
        result, error = rows_to_dicts(values)
        self.assertIsNone(error)
        expected = []
        self.assertEqual(result, expected)

    def test_multiple_rows(self):
        values = [
            ["name", "email", "firm"],
            ["Ali", "ali@x.com", "X Corp"],
            ["Sara", "sara@y.com", "Y Inc"],
        ]
        result, error = rows_to_dicts(values)
        self.assertIsNone(error)
        expected = [
            {"row_index": 2, "name": "Ali", "email": "ali@x.com", "firm": "X Corp"},
            {"row_index": 3, "name": "Sara", "email": "sara@y.com", "firm": "Y Inc"},
        ]
        self.assertEqual(result, expected)
    def test_row_with_empty_cells(self):
        values = [
            ["name", "email", "firm"],
            ["Ali", "", "X Corp"],
            ["", "sara@y.com", ""],
        ]
        result, error = rows_to_dicts(values)
        self.assertIsNone(error)
        expected = [
            {"row_index": 2, "name": "Ali", "email": "", "firm": "X Corp"},
            {"row_index": 3, "name": "", "email": "sara@y.com", "firm": ""},
        ]
        self.assertEqual(result, expected)
    def test_row_with_empty_cells_and_missing_columns(self):
        values = [
            ["name", "email", "firm"],
            ["Ali", "", "X Corp"],
            ["Sara", "sara@y.com", ""],
            ["John", "john@z.com", "Z Ltd"],
            ["", "", ""],
            []
        ]
        result, error = rows_to_dicts(values)
        self.assertIsNone(error)
        expected = [
            {"row_index": 2, "name": "Ali", "email": "", "firm": "X Corp"},
            {"row_index": 3, "name": "Sara", "email": "sara@y.com", "firm": ""},
            {"row_index": 4, "name": "John", "email": "john@z.com", "firm": "Z Ltd"},
            {"row_index": 5, "name": "", "email": "", "firm": ""},
            {"row_index": 6, "name": "", "email": "", "firm": ""},
        ]
        self.assertEqual(result, expected)


class TestDictsToRows(unittest.TestCase):
    
    def test_dicts_to_rows(self):
        dicts = [
            {"row_index": 2, "name": "Ali", "email": "ali@x.com", "firm": "X Corp"},
            {"row_index": 3, "name": "Sara", "email": "sara@y.com", "firm": "Y Inc"},
        ]
        header_row = ["name", "email", "firm"]
        result = dicts_to_rows(dicts, header_row)
        expected = [
            ["Ali", "ali@x.com", "X Corp"],
            ["Sara", "sara@y.com", "Y Inc"],
        ]
        self.assertEqual(result, expected)

    def test_dicts_to_rows_with_missing_keys(self):
        dicts = [
            {"row_index": 2, "name": "Ali", "email": "ali@x.com"},
            {"row_index": 3, "name": "Sara", "firm": "Y Inc"},
        ]
        header_row = ["name", "email", "firm"]
        result = dicts_to_rows(dicts, header_row)
        expected = [
            ["Ali", "ali@x.com", ""],
            ["Sara", "", "Y Inc"],
        ]
        self.assertEqual(result, expected)

    def test_dicts_to_rows_empty_dicts(self):
        dicts = []
        header_row = ["name", "email", "firm"]
        result = dicts_to_rows(dicts, header_row)
        expected = []
        self.assertEqual(result, expected)

class TestMergeHeader(unittest.TestCase):

    def test_empty_sheet_takes_all_new_keys(self):
        result = merge_header([], ["name", "email"])
        self.assertEqual(result, ["name", "email"])

    def test_no_new_keys_changes_nothing(self):
        result = merge_header(["name", "email"], ["email", "name"])
        self.assertEqual(result, ["name", "email"])

    def test_new_key_goes_to_the_end(self):
        result = merge_header(["name", "email"], ["name", "phone"])
        self.assertEqual(result, ["name", "email", "phone"])

    def test_duplicate_new_keys_added_once(self):
        result = merge_header(["name"], ["phone", "email", "phone"])
        self.assertEqual(result, ["name", "phone", "email"])

    def test_existing_list_is_not_modified(self):
        existing = ["name"]
        merge_header(existing, ["phone"])
        self.assertEqual(existing, ["name"])


class TestChunkRows(unittest.TestCase):

    def test_rows_split_into_batches_of_size(self):
        result = chunk_rows([[1], [2], [3], [4], [5]], 2)
        self.assertEqual(result, [[[1], [2]], [[3], [4]], [[5]]])

    def test_rows_under_size_stay_in_one_batch(self):
        result = chunk_rows([[1], [2]], 500)
        self.assertEqual(result, [[[1], [2]]])

    def test_no_rows_gives_no_batches(self):
        self.assertEqual(chunk_rows([], 500), [])


class TestQuoteTab(unittest.TestCase):

    def test_plain_name_is_quoted(self):
        self.assertEqual(quote_tab("Final"), "'Final'")

    def test_name_with_spaces_is_quoted(self):
        self.assertEqual(quote_tab("Jason Leads"), "'Jason Leads'")

    def test_single_quote_in_name_is_doubled(self):
        self.assertEqual(quote_tab("Jason's Leads"), "'Jason''s Leads'")
