import unittest

from run_plan import (
    count_statuses,
    estimate_cost,
    lookup_still_owed,
    plan_message,
    prompt_change_error,
    row_status,
)

CURRENT = "a3f9c1d2e4b5"


class TestLookupStillOwed(unittest.TestCase):

    def test_entry_cached_with_lookup_off_is_owed_a_lookup_when_on(self):
        self.assertTrue(lookup_still_owed({"email_lookup": False}, True))

    def test_entry_cached_with_lookup_on_is_not_owed(self):
        self.assertFalse(lookup_still_owed({"email_lookup": True}, True))

    def test_nothing_is_owed_while_lookup_is_off(self):
        self.assertFalse(lookup_still_owed({"email_lookup": False}, False))

    def test_entry_from_before_the_switch_counts_as_looked_up(self):
        self.assertFalse(lookup_still_owed({"source": "native"}, True))


class TestRowStatus(unittest.TestCase):

    def test_no_cache_entry_is_new(self):
        self.assertEqual(row_status(None, CURRENT, True), "new")

    def test_entry_from_the_current_prompt_is_cached(self):
        self.assertEqual(row_status({"prompt_version": CURRENT}, CURRENT, True), "cached")

    def test_entry_from_another_prompt_is_prompt_changed(self):
        self.assertEqual(row_status({"prompt_version": "000000000000"}, CURRENT, True), "prompt changed")

    def test_entry_without_a_version_cannot_be_trusted_and_is_prompt_changed(self):
        self.assertEqual(row_status({"source": "native"}, CURRENT, True), "prompt changed")

    def test_current_entry_that_skipped_its_lookup_is_lookup_owed(self):
        cached = {"prompt_version": CURRENT, "email_lookup": False}
        self.assertEqual(row_status(cached, CURRENT, True), "lookup owed")

    def test_prompt_change_wins_over_an_owed_lookup(self):
        cached = {"prompt_version": "000000000000", "email_lookup": False}
        self.assertEqual(row_status(cached, CURRENT, True), "prompt changed")


class TestCountStatuses(unittest.TestCase):

    def test_every_status_is_present_even_at_zero(self):
        self.assertEqual(count_statuses(["new", "cached", "new"]),
                         {"new": 2, "cached": 1, "prompt changed": 0, "lookup owed": 0})


class TestEstimateCost(unittest.TestCase):

    def test_new_and_prompt_changed_rows_are_priced_cached_rows_are_free(self):
        counts = {"new": 2, "cached": 50, "prompt changed": 3, "lookup owed": 4}
        self.assertAlmostEqual(estimate_cost(counts, "redo", 0.012), 0.06)

    def test_keep_old_leaves_prompt_changed_rows_out_of_the_estimate(self):
        counts = {"new": 2, "cached": 50, "prompt changed": 3, "lookup owed": 4}
        self.assertAlmostEqual(estimate_cost(counts, "keep", 0.012), 0.024)


class TestPromptChangeError(unittest.TestCase):

    def test_changed_rows_stop_the_run_by_default(self):
        counts = {"new": 0, "cached": 0, "prompt changed": 5, "lookup owed": 0}
        error = prompt_change_error(counts, "stop")
        self.assertIn("--redo-changed", error)
        self.assertIn("--keep-old", error)

    def test_redo_or_keep_lets_the_run_go_on(self):
        counts = {"new": 0, "cached": 0, "prompt changed": 5, "lookup owed": 0}
        self.assertIsNone(prompt_change_error(counts, "redo"))
        self.assertIsNone(prompt_change_error(counts, "keep"))

    def test_no_changed_rows_never_stops(self):
        counts = {"new": 3, "cached": 1, "prompt changed": 0, "lookup owed": 0}
        self.assertIsNone(prompt_change_error(counts, "stop"))


class TestPlanMessage(unittest.TestCase):

    def test_names_every_count_the_version_and_the_estimate(self):
        counts = {"new": 8, "cached": 60, "prompt changed": 180, "lookup owed": 2}
        message = plan_message(counts, CURRENT, "redo", 2.256)
        for text in ("250 rows", "60 cached", "180 prompt changed", "8 new", "2 lookup owed", CURRENT, "$2.26"):
            self.assertIn(text, message)

    def test_keep_old_rows_are_not_priced(self):
        counts = {"new": 1, "cached": 0, "prompt changed": 180, "lookup owed": 0}
        message = plan_message(counts, CURRENT, "keep", 0.012)
        self.assertIn("kept as they are", message)
