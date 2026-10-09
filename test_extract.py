import unittest

from extract import build_extract_prompt, clean_attorneys, pick_opener, validate_extract


def attorney(first=None, last=None, email=None, phone=None, address=None):
    return {"first_name": first, "last_name": last, "email": email, "phone": phone, "address": address}


class TestPickOpener(unittest.TestCase):

    def test_even_rows_use_opener_two(self):
        self.assertEqual(pick_opener(2), 2)

    def test_odd_rows_use_opener_one(self):
        self.assertEqual(pick_opener(3), 1)


class TestBuildExtractPrompt(unittest.TestCase):

    def test_text_and_opener_are_filled_in(self):
        template = "Use opener number {{opener_number}}:\n{{pdf_text}}"
        result = build_extract_prompt(template, "COMPLAINT TEXT", 3)
        self.assertEqual(result, ("Use opener number 1:\nCOMPLAINT TEXT", None))

    def test_template_without_pdf_text_returns_error(self):
        result, error = build_extract_prompt("{{opener_number}}", "COMPLAINT TEXT", 2)
        self.assertIsNone(result)
        self.assertIsNotNone(error)


class TestCleanAttorneys(unittest.TestCase):

    def test_attorney_with_no_name_and_no_email_is_dropped(self):
        result = clean_attorneys([attorney(phone="555"), attorney(first="Ana", last="Ruiz")])
        self.assertEqual(result, [attorney(first="Ana", last="Ruiz")])

    def test_same_email_is_kept_once(self):
        result = clean_attorneys([
            attorney(first="Ana", email="ana@firm.com"),
            attorney(first="Ana", email=" ANA@firm.com "),
        ])
        self.assertEqual(result, [attorney(first="Ana", email="ana@firm.com")])

    def test_attorneys_without_email_are_all_kept(self):
        result = clean_attorneys([attorney(first="Ana"), attorney(first="Bo")])
        self.assertEqual(result, [attorney(first="Ana"), attorney(first="Bo")])

    def test_email_only_attorney_is_kept_without_a_name(self):
        result = clean_attorneys([attorney(email="info@firm.com")])
        self.assertEqual(result, [attorney(email="info@firm.com")])


class TestValidateExtract(unittest.TestCase):

    def good(self):
        return {
            "attorneys": [attorney(first="Ana", last="Ruiz", email="ana@firm.com")],
            "case_name_short": "Smith v Jones",
            "outreach_one_liner": "I came across Smith v Jones involving a fall.",
        }

    def test_good_reply_passes_with_clean_attorneys(self):
        data = self.good()
        data["attorneys"].append(attorney())
        result, error = validate_extract(data)
        self.assertIsNone(error)
        self.assertEqual(result["attorneys"], [attorney(first="Ana", last="Ruiz", email="ana@firm.com")])

    def test_input_dict_is_not_modified(self):
        data = self.good()
        data["attorneys"].append(attorney())
        validate_extract(data)
        self.assertEqual(len(data["attorneys"]), 2)

    def test_missing_attorneys_returns_error(self):
        data = self.good()
        del data["attorneys"]
        self.assertIsNotNone(validate_extract(data)[1])

    def test_attorneys_not_a_list_returns_error(self):
        data = self.good()
        data["attorneys"] = "Ana Ruiz"
        self.assertIsNotNone(validate_extract(data)[1])

    def test_attorney_not_an_object_returns_error(self):
        data = self.good()
        data["attorneys"] = ["Ana Ruiz"]
        self.assertIsNotNone(validate_extract(data)[1])

    def test_good_reply_has_no_warning(self):
        result, error = validate_extract(self.good())
        self.assertIsNone(error)
        self.assertIsNone(result["extract_warning"])

    def test_blank_outreach_one_liner_keeps_the_data_with_a_warning(self):
        # Real case: ER sheet row 4 came back with an empty one-liner, a paid extraction was thrown away
        data = self.good()
        data["outreach_one_liner"] = "  "
        result, error = validate_extract(data)
        self.assertIsNone(error)
        self.assertEqual(result["case_name_short"], "Smith v Jones")
        self.assertIn("outreach_one_liner", result["extract_warning"])

    def test_null_outreach_one_liner_keeps_the_data_with_a_warning(self):
        data = self.good()
        data["outreach_one_liner"] = None
        result, error = validate_extract(data)
        self.assertIsNone(error)
        self.assertIsNotNone(result["extract_warning"])

    def test_unfilled_case_name_placeholder_keeps_the_data_with_a_warning(self):
        data = self.good()
        data["outreach_one_liner"] = "I came across [CASE_NAME] involving a fall."
        result, error = validate_extract(data)
        self.assertIsNone(error)
        self.assertIn("[CASE_NAME]", result["extract_warning"])
