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

Examples:

```
# Try the first 10 rows
uv run python main.py --link "<sheet link>" --expert ariel_cohen_emergency_medicine --limit 10

# Continue from row 12 after that
uv run python main.py --link "<sheet link>" --expert ariel_cohen_emergency_medicine --start-row 12

# Cheapest run: no email lookup
uv run python main.py --link "<sheet link>" --expert ariel_cohen_emergency_medicine --no-email-lookup
```

Results are **appended**, never overwritten. Running the same rows twice writes them twice, so use `--start-row` to continue a run.

To check a link without processing anything, set `--start-row` past the last row. The log shows which sheet and tabs it resolved to.

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

To force a row to be processed again, delete its file from `.cache/`. The cache holds client case data and is not committed.

## Prompts

- `prompts/experts/<expert>.txt`: one prompt per expert. The file name is the `--expert` value. It must contain `{{pdf_text}}` and `{{opener_number}}`, and keep the line `Return EXACTLY this JSON structure:` followed by the JSON shape (a test checks that every field in it reaches an output column).
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
llm.py              OpenRouter client and JSON reply parsing
prompt_template.py  load prompts and fill {{placeholders}}
config.py           keys from .env, models, prices, defaults
prompts/            expert and lookup prompts
test_*.py           one test file per module
```
