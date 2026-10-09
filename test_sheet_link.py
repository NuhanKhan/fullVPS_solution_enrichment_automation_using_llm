import unittest

from sheet_link import parse_sheet_link, pick_input_tab

SHEET_ID = "1NGQlX4TBc9C3Z0N2UpIPmXqU33PAn5cea9VZBFGWF5A"

TABS = [
    {"title": "Final", "sheetId": 2010309802},
    {"title": "Sheet1", "sheetId": 1310297553},
    {"title": "Output", "sheetId": 9315286},
]


class TestParseSheetLink(unittest.TestCase):

    def test_browser_link_gives_id_and_tab(self):
        link = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid=1310297553#gid=1310297553"
        self.assertEqual(parse_sheet_link(link), ({"sheet_id": SHEET_ID, "gid": 1310297553}, None))

    def test_old_style_link_with_gid_only_after_hash(self):
        link = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=0"
        self.assertEqual(parse_sheet_link(link), ({"sheet_id": SHEET_ID, "gid": 0}, None))

    def test_link_without_tab_gives_no_gid(self):
        link = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
        self.assertEqual(parse_sheet_link(link), ({"sheet_id": SHEET_ID, "gid": None}, None))

    def test_link_with_account_prefix_is_read(self):
        link = f"https://docs.google.com/spreadsheets/u/1/d/{SHEET_ID}/edit?usp=sharing"
        self.assertEqual(parse_sheet_link(link), ({"sheet_id": SHEET_ID, "gid": None}, None))

    def test_bare_sheet_id_is_accepted(self):
        self.assertEqual(parse_sheet_link(f"  {SHEET_ID} "), ({"sheet_id": SHEET_ID, "gid": None}, None))

    def test_link_that_is_not_a_sheet_returns_error(self):
        result, error = parse_sheet_link("https://docs.google.com/document/d/abc/edit")
        self.assertIsNone(result)
        self.assertIsNotNone(error)

    def test_empty_link_returns_error(self):
        result, error = parse_sheet_link("")
        self.assertIsNone(result)
        self.assertIsNotNone(error)


class TestPickInputTab(unittest.TestCase):

    def test_tab_named_on_the_command_line_wins(self):
        self.assertEqual(pick_input_tab(TABS, 1310297553, "Final"), ("Final", None))

    def test_tab_from_the_link_is_used(self):
        self.assertEqual(pick_input_tab(TABS, 1310297553, None), ("Sheet1", None))

    def test_first_tab_is_used_when_link_has_no_tab(self):
        self.assertEqual(pick_input_tab(TABS, None, None), ("Final", None))

    def test_unknown_tab_name_returns_error(self):
        result, error = pick_input_tab(TABS, None, "Nope")
        self.assertIsNone(result)
        self.assertIn("Nope", error)

    def test_unknown_gid_returns_error(self):
        result, error = pick_input_tab(TABS, 123, None)
        self.assertIsNone(result)
        self.assertIn("123", error)

    def test_sheet_without_tabs_returns_error(self):
        result, error = pick_input_tab([], None, None)
        self.assertIsNone(result)
        self.assertIsNotNone(error)
