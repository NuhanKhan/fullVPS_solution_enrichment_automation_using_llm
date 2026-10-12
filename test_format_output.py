import glob
import itertools
import json
import os
import re
import unittest

from config import PROMPTS_DIR
from extract import build_extract_prompt
from format_output import build_output_rows, format_value

INPUT_ROW = {"row_index": 7, "Complaint Link": "https://x.com/a.pdf", "Case Name": "Smith"}
PDF_OK = {"text": "body", "source": "native", "error": None}


def prompt_schema(path: str) -> dict:
    """The JSON object a prompt asks for, read from the prompt file itself."""

    with open(path, encoding="utf-8") as f:
        text = f.read()
    marker = text.index("Return EXACTLY this JSON structure:")
    start = text.index("{", marker)
    schema, _ = json.JSONDecoder().raw_decode(text[start:])
    return schema


def expert_prompt_paths() -> list[str]:
    return sorted(glob.glob(os.path.join(PROMPTS_DIR, "experts", "*.txt")))


class TestEveryExpertPromptFitsThePipeline(unittest.TestCase):

    def test_every_expert_prompt_fills_with_only_pdf_text_and_opener_number(self):
        for path in expert_prompt_paths():
            with open(path, encoding="utf-8") as f:
                template = f.read()
            filled, error = build_extract_prompt(template, "COMPLAINT TEXT", 2)
            self.assertIsNone(error, f"{path}: {error}")
            self.assertIn("COMPLAINT TEXT", filled, path)
            self.assertNotIn("{{", filled, f"{path}: a placeholder was left unfilled")
            self.assertNotIn("$json", template, f"{path}: n8n placeholder syntax left in the prompt")

    def test_every_expert_prompt_asks_for_a_list_of_attorneys(self):
        for path in expert_prompt_paths():
            attorneys = prompt_schema(path).get("attorneys")
            self.assertIsInstance(attorneys, list, f"{path}: attorneys is not a list")
            self.assertEqual(set(attorneys[0]), {"first_name", "last_name", "email", "phone", "address"}, path)

    def test_every_expert_prompt_uses_the_shared_column_names(self):
        for path in expert_prompt_paths():
            schema = prompt_schema(path)
            self.assertIn("case_name_short", schema, path)
            self.assertIn("outreach_one_liner", schema, path)
            self.assertNotIn("confidence", schema, f"{path}: use confidence_score")
            for key in schema:
                if key.startswith("case_name_short"):
                    self.assertEqual(key, "case_name_short", f"{path}: use case_name_short, not {key}")

    def test_every_expert_prompt_scores_fit_on_the_scale_that_triggers_email_lookup(self):
        for path in expert_prompt_paths():
            schema = prompt_schema(path)
            for key in ("expert_fit", "fit_reason", "confidence_score"):
                self.assertIn(key, schema, f"{path}: {key} missing")
            with open(path, encoding="utf-8") as f:
                text = f.read()
            for value in ("strong_fit", "possible_fit", "not_fit"):
                self.assertIn(value, text, f"{path}: expert_fit value {value} never mentioned")

    def test_no_expert_prompt_contains_drafting_leftovers(self):
        leftovers = [r"SAME AS (YOUR )?ORIGINAL", r"contentReference", r"oaicite", r"\]\(https?://",
                     r"^Yes\. I", r"^This version is tailored", r"^Paste this"]
        for path in expert_prompt_paths():
            with open(path, encoding="utf-8") as f:
                text = f.read()
            for pattern in leftovers:
                self.assertIsNone(re.search(pattern, text, re.MULTILINE), f"{path}: leftover {pattern}")

    def test_one_liner_templates_do_not_hard_code_the_first_opener(self):
        for path in expert_prompt_paths():
            with open(path, encoding="utf-8") as f:
                text = f.read()
            if "If template 1" in text or "is not used by this prompt" in text:
                continue
            hard_coded = text.count('"I came across [CASE_NAME]') - text.count('1. "I came across [CASE_NAME]"')
            self.assertEqual(hard_coded, 0, f"{path}: a template starts with opener 1 instead of [OPENER]")

    def test_every_expert_prompt_has_at_most_one_outreach_rules_section(self):
        for path in expert_prompt_paths():
            with open(path, encoding="utf-8") as f:
                text = f.read()
            headers = re.findall(r"^#* *OUTREACH ONE[- ]LINER RULES", text, re.MULTILINE | re.IGNORECASE)
            self.assertLessEqual(len(headers), 1, path)

    def test_every_expert_prompt_uses_the_shared_case_name_format(self):
        for path in expert_prompt_paths():
            with open(path, encoding="utf-8") as f:
                self.assertIn("Party A v Party B", f.read(), path)

    def test_no_two_expert_prompts_are_copies_of_each_other(self):
        lines = {}
        for path in expert_prompt_paths():
            with open(path, encoding="utf-8") as f:
                lines[path] = {line.strip() for line in f if len(line.strip()) > 20}
        for a, b in itertools.combinations(lines, 2):
            shared = len(lines[a] & lines[b]) / min(len(lines[a]), len(lines[b]))
            self.assertLess(shared, 0.9, f"{a} and {b} share {shared:.0%} of their lines")


class TestEveryPromptFieldIsWritten(unittest.TestCase):

    def test_every_field_of_every_expert_prompt_reaches_the_output_row(self):
        paths = glob.glob(os.path.join(PROMPTS_DIR, "experts", "*.txt"))
        self.assertTrue(paths)

        for path in paths:
            schema = prompt_schema(path)
            attorney_keys = list(schema["attorneys"][0])
            extract = {}
            for key in schema:
                extract[key] = f"value of {key}"
            attorney = {}
            for key in attorney_keys:
                attorney[key] = f"attorney {key}"
            extract["attorneys"] = [attorney]

            row = build_output_rows("expert", INPUT_ROW, "Complaint Link", PDF_OK, extract, None)[0]
            written = set(row.values())

            for key in schema:
                if key == "attorneys":
                    continue
                self.assertIn(f"value of {key}", written, f"{path}: {key} never reaches the output")
            for key in attorney_keys:
                self.assertIn(f"attorney {key}", written, f"{path}: attorney {key} never reaches the output")


class TestBuildOutputRows(unittest.TestCase):

    def extract(self):
        return {
            "attorneys": [
                {"first_name": "Ana", "last_name": "Ruiz", "email": "ana@firm.com", "phone": None, "address": None,
                 "needs_email_search": False, "search_query": ""},
                {"first_name": "Bo", "last_name": "Li", "email": None, "phone": "555", "address": "1 Main St",
                 "needs_email_search": True, "search_query": "Find Bo Li"},
            ],
            "case_name_short": "Smith v Jones",
            "expert_fit": "strong_fit",
            "confidence_score": 85,
            "outreach_one_liner": "I came across Smith v Jones.",
        }

    def test_one_row_per_attorney(self):
        rows = build_output_rows("ariel", INPUT_ROW, "Complaint Link", PDF_OK, self.extract(), None)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["attorney_first_name"], "Ana")
        self.assertEqual(rows[1]["attorney_first_name"], "Bo")
        self.assertEqual(rows[1]["attorney_address"], "1 Main St")

    def test_case_fields_repeat_on_every_attorney_row(self):
        rows = build_output_rows("ariel", INPUT_ROW, "Complaint Link", PDF_OK, self.extract(), None)
        for row in rows:
            self.assertEqual(row["case_name_short"], "Smith v Jones")
            self.assertEqual(row["row_index"], 7)
            self.assertEqual(row["expert"], "ariel")

    def test_null_becomes_empty_and_bool_becomes_text(self):
        rows = build_output_rows("ariel", INPUT_ROW, "Complaint Link", PDF_OK, self.extract(), None)
        self.assertEqual(rows[1]["attorney_email"], "")
        self.assertEqual(rows[0]["needs_email_search"], "FALSE")
        self.assertEqual(rows[1]["needs_email_search"], "TRUE")
        self.assertEqual(rows[1]["search_query"], "Find Bo Li")

    def test_numbers_are_kept_as_numbers(self):
        rows = build_output_rows("ariel", INPUT_ROW, "Complaint Link", PDF_OK, self.extract(), None)
        self.assertEqual(rows[0]["confidence_score"], 85)

    def test_unknown_extract_field_is_still_written(self):
        extract = {**self.extract(), "new_score": "high"}
        rows = build_output_rows("ariel", INPUT_ROW, "Complaint Link", PDF_OK, extract, None)
        self.assertEqual(rows[0]["new_score"], "high")

    def test_failed_download_gives_one_row_with_the_error(self):
        pdf = {"text": "", "source": "", "error": "download: 404"}
        rows = build_output_rows("ariel", INPUT_ROW, "Complaint Link", pdf, None, None)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["pdf_downloaded"], "FALSE")
        self.assertEqual(rows[0]["download_error"], "download: 404")
        self.assertEqual(rows[0]["complaint_cell_value"], "https://x.com/a.pdf")
        self.assertEqual(rows[0]["attorney_first_name"], "")

    def test_link_that_is_not_a_pdf_counts_as_not_downloaded(self):
        pdf = {"text": "", "source": "", "error": "strip: no %PDF marker found"}
        rows = build_output_rows("ariel", INPUT_ROW, "Complaint Link", pdf, None, None)
        self.assertEqual(rows[0]["pdf_downloaded"], "FALSE")

    def test_failed_extract_gives_one_row_with_the_error(self):
        rows = build_output_rows("ariel", INPUT_ROW, "Complaint Link", PDF_OK, None, "llm: timeout")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["pdf_downloaded"], "TRUE")
        self.assertEqual(rows[0]["extract_error"], "llm: timeout")

    def test_no_attorneys_still_gives_one_row(self):
        extract = {**self.extract(), "attorneys": []}
        rows = build_output_rows("ariel", INPUT_ROW, "Complaint Link", PDF_OK, extract, None)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["case_name_short"], "Smith v Jones")
        self.assertEqual(rows[0]["attorney_email"], "")

    def test_ocr_source_sets_ocr_used(self):
        pdf = {"text": "body", "source": "ocr", "error": None}
        rows = build_output_rows("ariel", INPUT_ROW, "Complaint Link", pdf, self.extract(), None)
        self.assertEqual(rows[0]["ocr_used"], "TRUE")

    def test_email_source_and_check_are_written(self):
        extract = self.extract()
        extract["attorneys"][0]["email_source"] = "document"
        extract["attorneys"][1]["email_source"] = "lookup"
        extract["attorneys"][1]["email_check"] = "generic inbox"
        rows = build_output_rows("ariel", INPUT_ROW, "Complaint Link", PDF_OK, extract, None)
        self.assertEqual(rows[0]["email_source"], "document")
        self.assertEqual(rows[1]["email_source"], "lookup")
        self.assertEqual(rows[1]["email_check"], "generic inbox")

    def test_extract_warning_is_written_next_to_extract_error(self):
        extract = {**self.extract(), "extract_warning": "outreach_one_liner is blank"}
        rows = build_output_rows("ariel", INPUT_ROW, "Complaint Link", PDF_OK, extract, None)
        self.assertEqual(rows[0]["extract_warning"], "outreach_one_liner is blank")
        columns = list(rows[0])
        self.assertEqual(columns.index("extract_warning"), columns.index("extract_error") + 1)

    def test_rows_start_with_the_default_column_order(self):
        rows = build_output_rows("ariel", INPUT_ROW, "Complaint Link", PDF_OK, self.extract(), None)
        self.assertEqual(list(rows[0])[:4], ["row_index", "expert", "complaint_cell_value", "pdf_url"])


class TestFormatValue(unittest.TestCase):

    def test_list_becomes_json_text(self):
        self.assertEqual(format_value(["a", "b"]), '["a", "b"]')

    def test_text_is_unchanged(self):
        self.assertEqual(format_value("abc"), "abc")
