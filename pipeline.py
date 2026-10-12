import logging
import os

from googleapiclient.discovery import Resource
from mistralai.client import Mistral
from openai import OpenAI

from cache import cache_key, load_cached, save_cached, text_key, touch_cached
from config import (
    CACHE_DIR,
    COMPLAINT_LINK_COLUMN,
    ESTIMATED_COST_PER_ROW,
    OCR_CACHE_DIR,
    PROMPTS_DIR,
    WRITE_EVERY_ROWS,
)
from email_lookup import fill_missing_emails
from extract import extract_case
from format_output import build_output_rows
from pdf_text import get_pdf_text
from prompt_template import load_prompt, prompt_version
from run_plan import (
    count_statuses,
    estimate_cost,
    lookup_still_owed,
    plan_message,
    prompt_change_error,
    row_status,
)
from sheet_link import parse_sheet_link, pick_input_tab
from sheets import (
    ensure_tab,
    get_service_account_email,
    get_sheet_values,
    get_tabs,
    quote_tab,
    rows_to_dicts,
    write_rows,
)


def should_process(row: dict, link_column: str) -> bool:
    link = row.get(link_column, "").strip()
    return link.startswith("http")


def select_rows(rows: list[dict], link_column: str, start_row: int, limit: int | None) -> list[dict]:
    """Rows to run, in sheet order. The limit counts only rows that will actually be processed."""

    selected = []
    for row in rows:
        if row["row_index"] < start_row:
            continue
        if not should_process(row, link_column):
            continue
        if limit is not None and len(selected) >= limit:
            break
        selected.append(row)
    return selected


def row_failed(output_rows: list[dict]) -> bool:
    first = output_rows[0]
    return bool(first["download_error"] or first["extract_error"])


def load_prompts(expert: str) -> tuple[dict | None, str | None]:
    paths = {
        "expert": os.path.join(PROMPTS_DIR, "experts", f"{expert}.txt"),
        "lookup_system": os.path.join(PROMPTS_DIR, "email_lookup_system.txt"),
        "lookup_user": os.path.join(PROMPTS_DIR, "email_lookup_user.txt"),
    }
    prompts = {}
    for name, path in paths.items():
        text, error = load_prompt(path)
        if error:
            return (None, f"prompt {path}: {error}")
        prompts[name] = text
    prompts["expert_version"] = prompt_version(prompts["expert"])
    return (prompts, None)


def row_warned(output_rows: list[dict]) -> bool:
    return bool(output_rows[0].get("extract_warning"))


def lookup_and_cache(openrouter_client: OpenAI, prompts: dict, row_index: int, key: str, entry: dict,
                     lookup_enabled: bool) -> tuple[dict, float]:
    """Run the email lookup on entry["extract"], then cache the entry. Returns (extract, lookup cost)."""

    extract, cost, lookup_errors = fill_missing_emails(
        openrouter_client, prompts["lookup_system"], prompts["lookup_user"], entry["extract"], lookup_enabled,
    )
    for lookup_error in lookup_errors:
        logging.error(f"row {row_index}: {lookup_error}")

    # A failed lookup is not cached, so the next run tries it again
    if not lookup_errors:
        new_entry = {**entry, "cost": entry["cost"] + cost, "email_lookup": lookup_enabled, "extract": extract}
        _, error = save_cached(CACHE_DIR, key, new_entry)
        if error:
            logging.warning(f"row {row_index}: not cached: {error}")

    return (extract, cost)


def get_text(mistral_client: Mistral, row_index: int, url: str) -> dict:
    """get_pdf_text, but OCR text is kept by URL, so a scanned document is never OCR'd twice."""

    key = text_key(url)
    stored, error = load_cached(OCR_CACHE_DIR, key)
    if error:
        logging.warning(f"row {row_index}: unreadable OCR text file, reading the PDF again: {error}")
    if stored:
        touch_cached(OCR_CACHE_DIR, key)
        logging.info(f"row {row_index}: OCR text reused, no OCR paid")
        return {"text": stored["text"], "source": "ocr", "error": None, "cost": 0.0}

    pdf_result = get_pdf_text(mistral_client, url)
    if pdf_result["source"] == "ocr" and not pdf_result["error"]:
        stored = {"url": url, "cost": pdf_result["cost"], "text": pdf_result["text"]}
        _, error = save_cached(OCR_CACHE_DIR, key, stored)
        if error:
            logging.warning(f"row {row_index}: OCR text not kept: {error}")
    return pdf_result


def use_cached(openrouter_client: OpenAI, prompts: dict, expert: str, row: dict, key: str, cached: dict,
               lookup_enabled: bool) -> tuple[list[dict], float]:
    """Build the row from its cache entry. Only an owed email lookup is paid for."""

    row_index = row["row_index"]
    pdf_result = {"text": "", "source": cached["source"], "error": None, "cost": 0.0}
    entry = {**cached, "cost": cached.get("cost", 0.0)}

    if lookup_still_owed(cached, lookup_enabled):
        logging.info(f"row {row_index}: cache hit, running the email lookup it skipped before")
        extract, cost = lookup_and_cache(openrouter_client, prompts, row_index, key, entry, lookup_enabled)
        logging.info(f"row {row_index}: cost ${cost:.4f}")
        return (build_output_rows(expert, row, COMPLAINT_LINK_COLUMN, pdf_result, extract, None), cost)

    _, error = touch_cached(CACHE_DIR, key)
    if error:
        logging.warning(f"row {row_index}: could not mark cache entry as used: {error}")
    if cached.get("prompt_version") == prompts["expert_version"]:
        logging.info(f"row {row_index}: cache hit, no paid calls")
    else:
        logging.info(f"row {row_index}: cache hit from prompt {cached.get('prompt_version')}, kept (--keep-old)")
    return (build_output_rows(expert, row, COMPLAINT_LINK_COLUMN, pdf_result, cached["extract"], None), 0.0)


def process_row(mistral_client: Mistral, openrouter_client: OpenAI, prompts: dict, expert: str,
                row: dict, lookup_enabled: bool, redo_changed: bool) -> tuple[list[dict], float]:
    """Run one input row end to end. Returns (output rows, dollars spent on this row).

    Never raises, a failure becomes an output row with the error. A cache hit costs 0.0, unless the
    row was cached with lookup off and lookup is now on, then only the lookup is paid for. A row made
    with another version of the prompt is extracted again only when redo_changed is set.
    """

    row_index = row["row_index"]
    url = row[COMPLAINT_LINK_COLUMN].strip()
    key = cache_key(expert, url)

    cached, error = load_cached(CACHE_DIR, key)
    if error:
        logging.warning(f"row {row_index}: unreadable cache entry, processing again: {error}")
    if cached:
        if row_status(cached, prompts["expert_version"], lookup_enabled) != "prompt changed" or not redo_changed:
            return use_cached(openrouter_client, prompts, expert, row, key, cached, lookup_enabled)
        logging.info(f"row {row_index}: prompt changed since {cached.get('prompt_version')}, extracting again")

    pdf_result = get_text(mistral_client, row_index, url)
    cost = pdf_result["cost"]
    if pdf_result["error"]:
        logging.error(f"row {row_index}: {pdf_result['error']}")
        return (build_output_rows(expert, row, COMPLAINT_LINK_COLUMN, pdf_result, None, None), cost)
    logging.info(f"row {row_index}: {pdf_result['source']} text, {len(pdf_result['text'])} chars")

    extract, extract_cost, error = extract_case(openrouter_client, prompts["expert"], pdf_result["text"], row_index)
    cost += extract_cost
    if error:
        logging.error(f"row {row_index}: extract: {error} (${cost:.4f} spent)")
        return (build_output_rows(expert, row, COMPLAINT_LINK_COLUMN, pdf_result, None, error), cost)
    logging.info(f"row {row_index}: {extract.get('expert_fit')}, {len(extract['attorneys'])} attorneys")
    if extract["extract_warning"]:
        logging.warning(f"row {row_index}: {extract['extract_warning']}, data kept")

    entry = {"url": url, "expert": expert, "prompt_version": prompts["expert_version"],
             "source": pdf_result["source"], "cost": cost, "extract": extract}
    extract, lookup_cost = lookup_and_cache(openrouter_client, prompts, row_index, key, entry, lookup_enabled)
    cost += lookup_cost

    logging.info(f"row {row_index}: cost ${cost:.4f}")
    return (build_output_rows(expert, row, COMPLAINT_LINK_COLUMN, pdf_result, extract, None), cost)


def plan_rows(selected: list[dict], expert: str, current_version: str, lookup_enabled: bool) -> list[str]:
    """What the run would do with each selected row, read from the cache only. Free."""

    statuses = []
    for row in selected:
        cached, _ = load_cached(CACHE_DIR, cache_key(expert, row[COMPLAINT_LINK_COLUMN].strip()))
        statuses.append(row_status(cached, current_version, lookup_enabled))
    return statuses


def open_sheet(service: Resource, link: str, input_tab: str | None) -> tuple[dict | None, str | None]:
    """Turn the --link (and optional --input-tab) into {"sheet_id", "input_tab"}."""

    parsed, error = parse_sheet_link(link)
    if error:
        return (None, error)

    tabs, error = get_tabs(service, parsed["sheet_id"])
    if error:
        email, _ = get_service_account_email()
        return (None, f"cannot open the sheet ({error}). Is it shared with {email}?")

    tab, error = pick_input_tab(tabs, parsed["gid"], input_tab)
    if error:
        return (None, error)

    return ({"sheet_id": parsed["sheet_id"], "input_tab": tab}, None)


def run_pipeline(service: Resource, mistral_client: Mistral, openrouter_client: OpenAI, link: str, expert: str,
                 input_tab: str | None, output_tab: str, start_row: int, limit: int | None,
                 lookup_enabled: bool, prompt_change: str, dry_run: bool,
                 max_cost: float | None) -> tuple[dict | None, str | None]:
    """Open the sheet from its link, process each row of the input tab, write results every WRITE_EVERY_ROWS rows.

    prompt_change is "stop" (refuse to start if any row was made with another prompt version), "redo" or
    "keep". A dry run logs the plan and stops before anything is created or paid for. max_cost stops the
    run once that many dollars are spent.

    Returns (summary counts, None), or (None, error) when the run cannot start or a write fails.
    """

    prompts, error = load_prompts(expert)
    if error:
        return (None, error)

    sheet, error = open_sheet(service, link, input_tab)
    if error:
        return (None, error)
    sheet_id = sheet["sheet_id"]
    input_tab = sheet["input_tab"]
    if input_tab == output_tab:
        return (None, f"input and output tab are both {input_tab!r}, the results would be appended to the input")
    logging.info(f"sheet {sheet_id}, input tab {input_tab!r}, output tab {output_tab!r}")

    values, error = get_sheet_values(service, sheet_id, quote_tab(input_tab))
    if error:
        return (None, f"read {input_tab}: {error}")

    rows, error = rows_to_dicts(values)
    if error:
        return (None, f"input tab {input_tab}: {error}")
    if COMPLAINT_LINK_COLUMN not in values[0]:
        return (None, f"input tab {input_tab} has no '{COMPLAINT_LINK_COLUMN}' column")

    selected = select_rows(rows, COMPLAINT_LINK_COLUMN, start_row, limit)
    lookup_state = "on"
    if not lookup_enabled:
        lookup_state = "off"
    logging.info(f"{len(selected)} rows to process from {input_tab}, expert {expert}, email lookup {lookup_state}")

    counts = count_statuses(plan_rows(selected, expert, prompts["expert_version"], lookup_enabled))
    estimate = estimate_cost(counts, prompt_change, ESTIMATED_COST_PER_ROW)
    logging.info(plan_message(counts, prompts["expert_version"], prompt_change, estimate))
    stop_error = prompt_change_error(counts, prompt_change)
    if dry_run:
        if stop_error:
            logging.warning(f"a real run would stop here: {stop_error}")
        return ({"dry_run": True, **counts, "estimated_cost_usd": round(estimate, 4)}, None)
    if stop_error:
        return (None, stop_error)

    # Before any paid call, so a bad output tab never wastes a run
    _, error = ensure_tab(service, sheet_id, output_tab)
    if error:
        return (None, f"output tab {output_tab}: {error}")

    summary = {"processed": 0, "failed": 0, "warnings": 0, "rows_written": 0, "cost_usd": 0.0, "stopped_early": False}
    pending = []

    for count, row in enumerate(selected, start=1):
        output_rows, cost = process_row(mistral_client, openrouter_client, prompts, expert, row, lookup_enabled,
                                        prompt_change == "redo")
        pending.extend(output_rows)
        summary["processed"] += 1
        summary["cost_usd"] += cost
        if row_failed(output_rows):
            summary["failed"] += 1
        if row_warned(output_rows):
            summary["warnings"] += 1

        over_budget = max_cost is not None and summary["cost_usd"] >= max_cost and count < len(selected)
        if count % WRITE_EVERY_ROWS == 0 or count == len(selected) or over_budget:
            written, error = write_rows(service, sheet_id, output_tab, pending)
            if error:
                return (None, f"write {output_tab} after {count} rows: {error}")
            summary["rows_written"] += written
            logging.info(f"wrote {written} rows to {output_tab} ({count} of {len(selected)} input rows done, "
                         f"${summary['cost_usd']:.4f} so far)")
            pending = []

        if over_budget:
            logging.warning(f"stopping: ${summary['cost_usd']:.4f} spent, --max-cost is ${max_cost:.2f}. "
                            f"Continue with --start-row {row['row_index'] + 1}")
            summary["stopped_early"] = True
            break

    summary["cost_usd"] = round(summary["cost_usd"], 4)
    return (summary, None)
