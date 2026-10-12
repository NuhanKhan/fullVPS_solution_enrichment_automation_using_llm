import unittest

from cache_maintenance import select_older_than, summarize_cache

DAY = 86400
NOW = 1_800_000_000.0


def fake_file(name: str, age_days: float, size: int = 1000, entry: dict | None = None) -> dict:
    return {"path": f".cache/{name}", "bytes": size, "modified": NOW - age_days * DAY, "entry": entry}


def fake_entry(expert: str = "ariel", source: str = "native", fit: str = "not_fit", cost: float | None = 0.01,
               version: str = "v1") -> dict:
    entry = {"url": "https://x.com/a.pdf", "expert": expert, "prompt_version": version, "source": source,
             "extract": {"expert_fit": fit}}
    if cost is not None:
        entry["cost"] = cost
    return entry


class TestSelectOlderThan(unittest.TestCase):

    def test_only_files_older_than_the_limit_are_selected(self):
        files = [fake_file("old.json", 91, entry=fake_entry()), fake_file("new.json", 89, entry=fake_entry())]
        selected = select_older_than(files, NOW, 90)
        self.assertEqual([f["path"] for f in selected], [".cache/old.json"])

    def test_a_file_exactly_at_the_limit_is_kept(self):
        self.assertEqual(select_older_than([fake_file("edge.json", 90, entry=fake_entry())], NOW, 90), [])

    def test_unreadable_entries_and_stray_tmp_files_are_selected_by_age_too(self):
        files = [fake_file("broken.json", 100), fake_file("x.json.tmp", 100)]
        self.assertEqual(len(select_older_than(files, NOW, 90)), 2)


class TestSummarizeCache(unittest.TestCase):

    def test_empty_cache_gives_zero_counts_and_no_dates(self):
        summary = summarize_cache([], NOW, 90, {})
        self.assertEqual(summary["entries"], 0)
        self.assertEqual(summary["cost_usd"], 0.0)
        self.assertIsNone(summary["oldest"])
        self.assertIsNone(summary["newest"])

    def test_counts_entries_by_expert_source_and_fit(self):
        files = [
            fake_file("a.json", 1, entry=fake_entry("ariel", "native", "not_fit")),
            fake_file("b.json", 2, entry=fake_entry("ariel", "ocr", "strong_fit")),
            fake_file("c.json", 3, entry=fake_entry("other", "native", "not_fit")),
        ]
        summary = summarize_cache(files, NOW, 90, {})
        self.assertEqual(summary["entries"], 3)
        self.assertEqual(summary["by_expert"], {"ariel": 2, "other": 1})
        self.assertEqual(summary["by_source"], {"native": 2, "ocr": 1})
        self.assertEqual(summary["by_fit"], {"not_fit": 2, "strong_fit": 1})

    def test_cost_adds_up_and_entries_without_cost_are_counted_separately(self):
        files = [
            fake_file("a.json", 1, entry=fake_entry(cost=0.01)),
            fake_file("b.json", 1, entry=fake_entry(cost=0.02)),
            fake_file("c.json", 1, entry=fake_entry(cost=None)),
        ]
        summary = summarize_cache(files, NOW, 90, {})
        self.assertAlmostEqual(summary["cost_usd"], 0.03)
        self.assertEqual(summary["entries_without_cost"], 1)

    def test_unreadable_and_tmp_files_are_not_counted_as_entries(self):
        files = [fake_file("a.json", 1, entry=fake_entry()), fake_file("broken.json", 1), fake_file("x.json.tmp", 1)]
        summary = summarize_cache(files, NOW, 90, {})
        self.assertEqual(summary["entries"], 1)
        self.assertEqual(summary["unreadable"], 1)
        self.assertEqual(summary["stray_tmp"], 1)

    def test_size_counts_every_file(self):
        files = [fake_file("a.json", 1, size=1500, entry=fake_entry()), fake_file("x.json.tmp", 1, size=500)]
        self.assertEqual(summarize_cache(files, NOW, 90, {})["bytes"], 2000)

    def test_reports_what_a_prune_would_remove(self):
        files = [
            fake_file("old.json", 120, size=700, entry=fake_entry(cost=0.05)),
            fake_file("new.json", 10, size=300, entry=fake_entry(cost=0.01)),
        ]
        summary = summarize_cache(files, NOW, 90, {})
        self.assertEqual(summary["older_than_days"], 90)
        self.assertEqual(summary["prunable_files"], 1)
        self.assertEqual(summary["prunable_bytes"], 700)
        self.assertAlmostEqual(summary["prunable_cost_usd"], 0.05)

    def test_oldest_and_newest_are_iso_dates(self):
        files = [fake_file("a.json", 0, entry=fake_entry()), fake_file("b.json", 30, entry=fake_entry())]
        summary = summarize_cache(files, NOW, 90, {})
        self.assertEqual(summary["newest"], "2027-01-15")
        self.assertEqual(summary["oldest"], "2026-12-16")


    def test_ocr_texts_are_counted_apart_from_extract_entries(self):
        files = [
            fake_file("a.json", 1, entry=fake_entry()),
            fake_file("ocr/t.json", 1, size=60000, entry={"url": "https://x.com/a.pdf", "cost": 0.1, "text": "..."}),
        ]
        summary = summarize_cache(files, NOW, 90, {})
        self.assertEqual(summary["entries"], 1)
        self.assertEqual(summary["ocr_texts"], 1)
        self.assertEqual(summary["ocr_bytes"], 60000)
        self.assertAlmostEqual(summary["cost_usd"], 0.01)

    def test_counts_entries_on_the_current_and_older_prompts_per_expert(self):
        files = [
            fake_file("a.json", 1, entry=fake_entry("ariel", version="v2")),
            fake_file("b.json", 1, entry=fake_entry("ariel", version="v1")),
            fake_file("c.json", 1, entry=fake_entry("ariel", version="v1")),
            fake_file("d.json", 1, entry=fake_entry("gone", version="v9")),
        ]
        summary = summarize_cache(files, NOW, 90, {"ariel": "v2"})
        self.assertEqual(summary["by_prompt"], {"ariel": {"current": 1, "older": 2}, "gone": {"current": 0, "older": 1}})

    def test_entry_without_a_version_counts_as_older(self):
        entry = fake_entry()
        del entry["prompt_version"]
        summary = summarize_cache([fake_file("a.json", 1, entry=entry)], NOW, 90, {"ariel": "v1"})
        self.assertEqual(summary["by_prompt"], {"ariel": {"current": 0, "older": 1}})


if __name__ == "__main__":
    unittest.main()
