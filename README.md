# Complaint enrichment pipeline

Reads court complaint PDF links from a Google Sheet, extracts attorney and case data with an LLM, scores each case against an expert witness's specialty, and writes the results back to the same sheet.

For each row:

1. Download the complaint PDF (amlaw HTML wrappers are stripped).
2. Read its text layer, or OCR it with Mistral when the PDF is a scan.
3. Send the text to an LLM with the expert's prompt. It returns the attorneys, a short case name, a summary, the expert fit (`strong_fit`, `possible_fit`, `not_fit`) and an outreach one-liner.
4. For fit cases, look up attorneys whose email is not in the complaint (Perplexity, optional).
5. Write one row per attorney to the `Output` tab.

Runs locally, one row at a time.

## Setup

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```
uv sync
cp .env.example .env
```

Fill in `.env`:

| Key | What it is |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter key. Used for both the extraction model and the Perplexity email lookup. |
| `MISTRAL_API_KEY` | Mistral key, for OCR of scanned PDFs. |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Path to a Google service account key file with the Sheets API enabled. |

The program stops at startup if any key is missing.

**Share every sheet with the service account.** Open the sheet, click Share, and add the `client_email` address from the service account JSON file as an **Editor** (it creates and writes the output tab). Without this, the run stops with a 403 error that names the address.

## Running

Open the input tab of the sheet in your browser, copy the address bar, and run:

```
uv run python main.py --link "<sheet link>" --expert ariel_cohen_emergency_medicine
```

Keep the link in quotes, it contains `&` and `#`.

| Option | Default | Meaning |
|---|---|---|
| `--link` | required | Google Sheets link (or a bare sheet id). The tab open when the link was copied is the input tab. |
| `--expert` | required | Prompt file name in `prompts/experts/`, without `.txt`. |
| `--input-tab` | from the link | Input tab by name. Overrides the link. Without either, the first tab is used. |
| `--output-tab` | `Output` | Tab to append results to, in the same sheet. Created if missing. Must differ from the input tab. |
| `--start-row` | `2` | First sheet row to process. |
| `--limit` | all | Maximum number of rows to process. |
| `--no-email-lookup` | lookup on | Skip the paid Perplexity email lookup. |
| `--dry-run` | off | Show what the run would do and roughly what it costs, then stop. Nothing is paid for or written. |
| `--max-cost` | no cap | Stop once this many dollars are spent. Finished rows are saved; the log says which `--start-row` continues. |
| `--redo-changed` | | After a prompt change: extract the affected rows again (paid). See "Changing a prompt". |
| `--keep-old` | | After a prompt change: keep the old answers for the affected rows (free). |

Examples:

```
# Try the first 10 rows
uv run python main.py --link "<sheet link>" --expert ariel_cohen_emergency_medicine --limit 10

# Continue from row 12 after that
uv run python main.py --link "<sheet link>" --expert ariel_cohen_emergency_medicine --start-row 12

# Cheapest run: no email lookup
uv run python main.py --link "<sheet link>" --expert ariel_cohen_emergency_medicine --no-email-lookup

# See what a run would cost before paying, then run it with a $5 ceiling
uv run python main.py --link "<sheet link>" --expert ariel_cohen_emergency_medicine --dry-run
uv run python main.py --link "<sheet link>" --expert ariel_cohen_emergency_medicine --max-cost 5
```

Results are **appended**, never overwritten. Running the same rows twice writes them twice, so use `--start-row` to continue a run.

To check a link without processing anything, use `--dry-run`. The log shows which sheet and tabs it resolved to, and the plan:

```
plan for prompt 9f3bd9581a55: 248 rows, 60 cached (free), 180 prompt changed, 8 new, 0 lookup owed. Estimated cost about $2.26
```

The estimate is rough: $0.012 per row that needs the LLM (`ESTIMATED_COST_PER_ROW` in `config.py`, the average of past runs). Use `--max-cost` when it matters.

## The input sheet

The input tab needs a header row with a `Complaint Link` column. Every other column is ignored. Rows whose link is empty or not a URL are skipped.

## The output

One row per attorney. A case with no attorneys, or a row that failed, still gets exactly one row, so every input row is accounted for.

| Column | Meaning |
|---|---|
| `row_index` | Row number in the input tab. |
| `expert` | Which expert prompt scored the row. |
| `complaint_cell_value`, `pdf_url` | The input link. |
| `pdf_downloaded` | `FALSE` when the link gave no PDF (for example formsite links). |
| `download_error` | Why getting the PDF text failed (`download:`, `strip:`, `native:`, `ocr:`). |
| `extract_error` | Why the LLM step failed. |
| `extract_warning` | The data was kept but something is off, such as a blank one-liner. |
| `ocr_used` | `TRUE` when the PDF was a scan. |
| `attorney_first_name` ... `attorney_address` | One attorney. |
| `plaintiff_firm` ... `outreach_one_liner` | Case fields from the expert prompt. Any new field a prompt adds becomes a new column. |
| `needs_email_search` | `TRUE` when the complaint had no email for this attorney. |
| `search_query` | The question sent to Perplexity, empty if no lookup ran. |
| `email_source` | `document` (from the complaint) or `lookup` (found by Perplexity). |
| `email_check` | For looked up emails only: `domain matches firm`, `domain does not match firm`, `generic inbox` or `no firm to compare`. A flag for review; nothing is rejected. |

New columns are added at the end of the header automatically. Existing columns never move.

## Cost

Every row logs its cost (`row 12: cost $0.0081`) and the run ends with a summary that includes `cost_usd`. Cost is never written to the sheet.

Measured on real runs: about $0.008 to $0.012 per complaint. Scanned PDFs cost more ($2 per 1,000 OCR pages), and long complaints cost more in the LLM step.

Paid calls are never retried, so a failure is not billed twice.

## Cache

Finished rows are cached in `.cache/`, keyed by expert and PDF link, so no document is paid for twice. Rerunning a cached row costs nothing. Rows that failed are not cached and are retried on the next run.

A row cached during a `--no-email-lookup` run gets its email lookup on the next run with lookup on, paying only for the lookup.

Text from scanned (OCR) documents is kept too, in `.cache/ocr/`, keyed by PDF link only. Any expert and any prompt version reuses it, so a document is never OCR'd twice. Text-layer documents are simply downloaded again, which is free.

To force a row to be processed again, delete its file from `.cache/`. The cache holds client case data and is not committed.

Check and clean the cache with `cache_tool.py`. It needs no sheet link and makes no paid calls:

```
uv run python cache_tool.py stats                          entries, OCR texts, size, experts, fits, prompt versions, cost stored, what a prune would remove
uv run python cache_tool.py prune                          dry run: shows what would be deleted, deletes nothing
uv run python cache_tool.py prune --yes                    delete entries not written or used for 90 days
uv run python cache_tool.py prune --older-than-days 30 --yes
```

Age counts from when an entry was last written or used by a run, so a complaint that keeps coming up is never pruned. The default of 90 days is `CACHE_MAX_AGE_DAYS` in `config.py`. A pruned document is simply paid for again if it shows up later. Unreadable entries, leftover `.tmp` files and kept OCR texts are pruned by the same age rule. Copying `.cache/` without keeping file times (plain `cp` instead of `cp -p`) resets every entry's age.

## Changing a prompt

Every cached answer remembers which version of the prompt wrote it (a short fingerprint like `9f3bd9581a55`, shown in the log and in `cache_tool.py stats`). Changing any word of the prompt gives a new fingerprint. Spacing and line breaks do not count.

After a prompt change, a run refuses to start if any of its rows were answered by the old version, and says how many:

```
prompt: 180 rows were made with a different version of the prompt. Rerun with --redo-changed to pay for them again, or --keep-old to use the old answers
```

So an edit, accidental or not, never costs money until someone chooses `--redo-changed`. A redo pays for the LLM step only (about $0.005 to $0.01 per complaint); OCR text is reused.

A client asking for a new column is a prompt change too: add the field to the JSON in the prompt, and the output gets a new column for it automatically. A good routine:

```
# 1. edit prompts/experts/<expert>.txt
# 2. see what it will cost
uv run python main.py --link "<sheet link>" --expert <expert> --dry-run
# 3. try it on 20 rows, in a new tab so old and new answers do not mix
uv run python main.py --link "<sheet link>" --expert <expert> --redo-changed --limit 20 --output-tab "Output v2"
# 4. check the new column in the sheet, then do the rest
uv run python main.py --link "<sheet link>" --expert <expert> --redo-changed --start-row <next row> --output-tab "Output v2"
```

Prompts are committed to git, so `git log -p prompts/` shows what changed and when.

## Prompts

- `prompts/experts/<expert>.txt`: one prompt per expert. The file name is the `--expert` value. It must contain `{{pdf_text}}` and `{{opener_number}}`, and keep the line `Return EXACTLY this JSON structure:` followed by the JSON shape (a test checks that every field in it reaches an output column). The JSON shape must have an `attorneys` list (`first_name`, `last_name`, `email`, `phone`, `address`), `case_name_short` and `outreach_one_liner`. Columns shared by all experts keep one name and one scale: `case_name_short` (format "Party A v Party B"), `expert_fit` (`strong_fit`, `possible_fit`, `not_fit`), `fit_reason`, `confidence_score` (0 to 100), and a one-liner on every row. Templates start with `[OPENER]`, not a hard-coded "I came across". Tests check all of this, and also that no prompt is a copy of another or contains leftover drafting text.
- Email lookup only runs for `expert_fit` values `strong_fit` and `possible_fit`. A prompt may keep its own scale in another field (for example `fit_level`), as long as it maps it onto `expert_fit`.
- `prompts/experts/` holds 31 expert prompts. 28 were converted from the n8n workflows on 2026-10-11 and have not been run yet; do a `--dry-run` and a small `--limit` run before a full sheet.
- `prompts/email_lookup_system.txt`, `prompts/email_lookup_user.txt`: the Perplexity lookup. Placeholders: `{{first_name}}`, `{{last_name}}`, `{{firm}}`, `{{address}}`, `{{phone}}`.

A missing or extra placeholder stops the row with a `prompt:` error instead of sending a broken prompt.

## Models

Set in `config.py`:

- Extraction: `deepseek/deepseek-v4.1-flash` via OpenRouter.
- Email lookup: `perplexity/sonar` via OpenRouter.
- OCR: `mistral-ocr-2512`, pinned on purpose (the `latest` alias moved to a version at double the price).

## Tests

```
uv run python -m unittest discover
uv run ruff check .
```

The unit tests make no network calls and cost nothing.

## Layout

```
main.py             command line options, logging, builds the API clients
pipeline.py         the loop: open the sheet, process each row, write results
sheet_link.py       read the sheet id and tab from --link
sheets.py           Google Sheets: list tabs, read rows, create a tab, append rows
pdf_text.py         download, strip the amlaw wrapper, text layer, OCR fallback
extract.py          the expert prompt LLM call and checks on its reply
email_lookup.py     Perplexity lookup and the email_source / email_check flags
format_output.py    one flat output row per attorney
cache.py            the .cache/ files
cache_maintenance.py  cache stats and age based pruning
cache_tool.py       command line for cache stats and prune
run_plan.py         what a run will do per row (new, cached, prompt changed) and its rough cost
llm.py              OpenRouter client and JSON reply parsing
prompt_template.py  load prompts and fill {{placeholders}}
config.py           keys from .env, models, prices, defaults
prompts/            expert and lookup prompts
test_*.py           one test file per module
```
