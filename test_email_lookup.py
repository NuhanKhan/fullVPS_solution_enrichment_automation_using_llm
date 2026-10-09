import unittest

from email_lookup import (
    build_lookup_messages,
    email_check,
    fill_missing_emails,
    merge_email,
    needs_lookup,
    parse_lookup_email,
)


def attorney(first="Ana", last="Ruiz", email=None, phone=None, address=None):
    return {"first_name": first, "last_name": last, "email": email, "phone": phone, "address": address}


class TestNeedsLookup(unittest.TestCase):

    def test_fit_case_with_missing_email_needs_lookup(self):
        self.assertTrue(needs_lookup(attorney(), "strong_fit"))
        self.assertTrue(needs_lookup(attorney(), "possible_fit"))

    def test_not_fit_case_is_never_looked_up(self):
        self.assertFalse(needs_lookup(attorney(), "not_fit"))

    def test_attorney_with_email_is_not_looked_up(self):
        self.assertFalse(needs_lookup(attorney(email="ana@firm.com"), "strong_fit"))

    def test_attorney_without_any_name_is_not_looked_up(self):
        self.assertFalse(needs_lookup(attorney(first=None, last=None), "strong_fit"))

    def test_last_name_alone_is_enough_to_look_up(self):
        self.assertTrue(needs_lookup(attorney(first=None), "strong_fit"))


class TestBuildLookupMessages(unittest.TestCase):

    def test_system_and_user_messages_are_filled(self):
        user_template = "Find {{first_name}} {{last_name}}. Law firm: {{firm}}. Address: {{address}}. Phone: {{phone}}."
        messages, error = build_lookup_messages("SYSTEM", user_template, attorney(phone="909-555-1234"), "Ruiz LLP")
        self.assertIsNone(error)
        self.assertEqual(messages, [
            {"role": "system", "content": "SYSTEM"},
            {"role": "user", "content": "Find Ana Ruiz. Law firm: Ruiz LLP. Address: unknown. Phone: 909-555-1234."},
        ])

    def test_missing_firm_is_written_as_unknown(self):
        messages, error = build_lookup_messages("S", "Law firm: {{firm}} {{first_name}}{{last_name}}{{address}}{{phone}}", attorney(), None)
        self.assertIsNone(error)
        self.assertTrue(messages[1]["content"].startswith("Law firm: unknown"))


class TestParseLookupEmail(unittest.TestCase):

    def test_found_email_is_returned(self):
        self.assertEqual(parse_lookup_email('{"emails": ["ana@ruizlaw.com"]}'), ("ana@ruizlaw.com", None))

    def test_email_is_trimmed_and_lowercased(self):
        self.assertEqual(parse_lookup_email('{"emails": [" Ana@RuizLaw.com "]}'), ("ana@ruizlaw.com", None))

    def test_null_email_means_not_found(self):
        self.assertEqual(parse_lookup_email('{"emails": [null]}'), ("", None))

    def test_first_valid_email_wins(self):
        self.assertEqual(parse_lookup_email('{"emails": [null, "not an email", "ana@ruizlaw.com"]}'), ("ana@ruizlaw.com", None))

    def test_mailto_prefix_is_removed(self):
        self.assertEqual(parse_lookup_email('{"emails": ["mailto:ana@ruizlaw.com"]}'), ("ana@ruizlaw.com", None))

    def test_cloudflare_protected_placeholder_means_not_found(self):
        # Real reply for Jason Earley: the firm site hides emails behind Cloudflare
        self.assertEqual(parse_lookup_email('{"emails":["mailto:[email\u00a0protected]"]}'), ("", None))

    def test_reply_wrapped_in_fences_is_read(self):
        self.assertEqual(parse_lookup_email('```json\n{"emails": ["ana@ruizlaw.com"]}\n```'), ("ana@ruizlaw.com", None))

    def test_reply_without_emails_list_returns_error(self):
        result, error = parse_lookup_email('{"email": "ana@ruizlaw.com"}')
        self.assertIsNone(result)
        self.assertIsNotNone(error)

    def test_reply_that_is_not_json_returns_error(self):
        result, error = parse_lookup_email("I could not find it.")
        self.assertIsNone(result)
        self.assertIsNotNone(error)


class TestMergeEmail(unittest.TestCase):

    def test_only_email_is_overwritten(self):
        original = {**attorney(phone="555"), "search_query": "q", "needs_email_search": True}
        result = merge_email(original, "ana@ruizlaw.com")
        self.assertEqual(result, {**original, "email": "ana@ruizlaw.com"})

    def test_original_attorney_is_not_modified(self):
        original = attorney()
        merge_email(original, "ana@ruizlaw.com")
        self.assertIsNone(original["email"])


class TestEmailCheck(unittest.TestCase):

    def test_domain_containing_a_firm_name_word_matches(self):
        self.assertEqual(email_check("carter@zinn-law.com", "The Zinn Law Firm"), "domain matches firm")

    def test_domain_of_another_firm_does_not_match(self):
        # Real case: ER sheet row 184, firm Barnett Law, lookup found skofirm.com addresses
        self.assertEqual(email_check("allyson.breeden@skofirm.com", "Barnett Law, LLC"), "domain does not match firm")

    def test_generic_inbox_is_flagged_first(self):
        # Real case: ER sheet row 238, David Kreizer -> info@kreizerlaw.com
        self.assertEqual(email_check("info@kreizerlaw.com", "Kreizer Law"), "generic inbox")

    def test_no_firm_name_cannot_be_compared(self):
        # Real case: ER sheet row 160, no plaintiff_firm, lookup found a Canadian namesake
        self.assertEqual(email_check("kallen@wbmlawyers.nb.ca", None), "no firm to compare")

    def test_firm_made_only_of_common_words_cannot_be_compared(self):
        self.assertEqual(email_check("ana@ruizlaw.com", "The Law Firm, LLC"), "no firm to compare")

    def test_match_ignores_case(self):
        self.assertEqual(email_check("bialor@HKDLaw.com", "HKD LAW"), "domain matches firm")


class TestFillMissingEmailsWithLookupOff(unittest.TestCase):

    def test_no_lookup_runs_and_attorneys_are_still_marked(self):
        extract = {
            "expert_fit": "strong_fit",
            "plaintiff_firm": "Ruiz LLP",
            "attorneys": [attorney(email="ana@ruizlaw.com"), attorney(first="Bo", last="Li")],
        }
        # client=None: any call to Perplexity would crash, so this proves none is made
        result, cost, errors = fill_missing_emails(None, "S", "U {{first_name}}", extract, lookup_enabled=False)
        self.assertEqual(cost, 0.0)
        self.assertEqual(errors, [])
        first, second = result["attorneys"]
        self.assertEqual(first["email_source"], "document")
        self.assertFalse(first["needs_email_search"])
        self.assertTrue(second["needs_email_search"])
        self.assertEqual(second["search_query"], "")
        self.assertEqual(second["email_source"], "")
