import datetime
import json
import logging
import os

from prompt_template import load_prompt, prompt_version

SECONDS_PER_DAY = 86400


def scan_cache(cache_dir: str) -> tuple[list[dict] | None, str | None]:
    """Every file in the cache folder and its subfolders (the OCR texts) as {path, bytes, modified, entry}.

    entry is the parsed JSON for a readable .json file, None for anything else (unreadable or .tmp).
    A missing folder is an empty cache, not an error.
    """

    if not os.path.isdir(cache_dir):
        return ([], None)

    paths = []
    for folder, _, names in os.walk(cache_dir):
        for name in names:
            paths.append(os.path.join(folder, name))

    files = []
    try:
        for path in sorted(paths):
            name = os.path.basename(path)
            stat = os.stat(path)
            entry = None
            if name.endswith(".json"):
                try:
                    with open(path, encoding="utf-8") as f:
                        entry = json.load(f)
                except (OSError, json.JSONDecodeError) as e:
                    logging.warning(f"unreadable cache file {path}: {e}")
            files.append({"path": path, "bytes": stat.st_size, "modified": stat.st_mtime, "entry": entry})
    except OSError as e:
        return (None, f"scan: {e}")

    return (files, None)


def select_older_than(files: list[dict], now: float, max_age_days: int) -> list[dict]:
    """Files last written or used more than max_age_days ago, of any kind."""

    cutoff = now - max_age_days * SECONDS_PER_DAY
    selected = []
    for file in files:
        if file["modified"] < cutoff:
            selected.append(file)
    return selected


def iso_date(timestamp: float) -> str:
    return datetime.datetime.fromtimestamp(timestamp, datetime.UTC).strftime("%Y-%m-%d")


def count_into(counts: dict, value: str) -> None:
    counts[value] = counts.get(value, 0) + 1


def current_prompt_versions(experts_dir: str) -> tuple[dict | None, str | None]:
    """{expert: prompt_version} for every prompt file in experts_dir."""

    versions = {}
    try:
        names = sorted(os.listdir(experts_dir))
    except OSError as e:
        return (None, f"prompts: {e}")
    for name in names:
        if not name.endswith(".txt"):
            continue
        text, error = load_prompt(os.path.join(experts_dir, name))
        if error:
            return (None, f"prompts: {error}")
        versions[name.removesuffix(".txt")] = prompt_version(text)
    return (versions, None)


def summarize_cache(files: list[dict], now: float, max_age_days: int, current_versions: dict) -> dict:
    """Counts, size, stored cost, prompt versions and what a prune at max_age_days would remove.

    current_versions is {expert: prompt_version}. An entry without a version counts as older, like in a run.
    """

    entries = 0
    ocr_texts = 0
    ocr_bytes = 0
    unreadable = 0
    stray_tmp = 0
    total_bytes = 0
    cost = 0.0
    without_cost = 0
    by_expert = {}
    by_source = {}
    by_fit = {}
    by_prompt = {}

    for file in files:
        total_bytes += file["bytes"]
        entry = file["entry"]
        if file["path"].endswith(".tmp"):
            stray_tmp += 1
            continue
        if entry is None or ("extract" not in entry and "text" not in entry):
            unreadable += 1
            continue
        if "extract" not in entry:
            ocr_texts += 1
            ocr_bytes += file["bytes"]
            continue

        entries += 1
        expert = entry.get("expert") or "unknown"
        count_into(by_expert, expert)
        if expert not in by_prompt:
            by_prompt[expert] = {"current": 0, "older": 0}
        if entry.get("prompt_version") is not None and entry.get("prompt_version") == current_versions.get(expert):
            by_prompt[expert]["current"] += 1
        else:
            by_prompt[expert]["older"] += 1
        count_into(by_source, entry.get("source") or "unknown")
        count_into(by_fit, entry.get("extract", {}).get("expert_fit") or "unknown")
        if "cost" in entry:
            cost += entry["cost"]
        else:
            without_cost += 1

    prunable = select_older_than(files, now, max_age_days)
    prunable_bytes = 0
    prunable_cost = 0.0
    for file in prunable:
        prunable_bytes += file["bytes"]
        # OCR texts carry their OCR cost, which is already inside their extract entry's cost
        if file["entry"] is not None and "extract" in file["entry"]:
            prunable_cost += file["entry"].get("cost", 0.0)

    oldest = None
    newest = None
    if files:
        modified = [file["modified"] for file in files]
        oldest = iso_date(min(modified))
        newest = iso_date(max(modified))

    return {
        "entries": entries,
        "ocr_texts": ocr_texts,
        "ocr_bytes": ocr_bytes,
        "unreadable": unreadable,
        "stray_tmp": stray_tmp,
        "bytes": total_bytes,
        "oldest": oldest,
        "newest": newest,
        "by_expert": by_expert,
        "by_source": by_source,
        "by_fit": by_fit,
        "by_prompt": by_prompt,
        "cost_usd": cost,
        "entries_without_cost": without_cost,
        "older_than_days": max_age_days,
        "prunable_files": len(prunable),
        "prunable_bytes": prunable_bytes,
        "prunable_cost_usd": prunable_cost,
    }


def delete_files(files: list[dict]) -> tuple[int | None, str | None]:
    """Delete each file. Returns (deleted, None), or (None, error) naming how many went before it failed."""

    deleted = 0
    for file in files:
        try:
            os.remove(file["path"])
        except FileNotFoundError:
            continue
        except OSError as e:
            return (None, f"prune: deleted {deleted} of {len(files)}, then {file['path']}: {e}")
        deleted += 1
    return (deleted, None)
