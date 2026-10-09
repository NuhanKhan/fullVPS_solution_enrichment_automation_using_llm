import json

# Extract fields written in this order after the attorney columns. Anything else the LLM
# returns is appended after these, so a new expert field is never silently dropped.
CASE_FIELDS = [
    "plaintiff_firm",
    "case_name_short",
    "summary",
    "claim_amount",
    "nature_of_suit",
    "expert_fit",
    "fit_reason",
    "confidence_score",
    "primary_technical_issue",
    "outreach_one_liner",
]

# Attorney key in the extract -> output column
ATTORNEY_FIELDS = {
    "first_name": "attorney_first_name",
    "last_name": "attorney_last_name",
    "email": "attorney_email",
    "phone": "attorney_phone",
    "address": "attorney_address",
}

# Added by email_lookup.py, written after the case fields
LOOKUP_FIELDS = ["needs_email_search", "search_query", "email_source", "email_check"]


def format_value(value: object) -> object:
    """Make a value safe for a sheet cell. Numbers stay numbers."""

    if value is None:
        return ""
    if isinstance(value, bool):
        if value:
            return "TRUE"
        return "FALSE"
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return value


def pdf_was_downloaded(pdf_result: dict) -> bool:
    """True when a real PDF was fetched, even if a later step failed."""

    error = pdf_result["error"]
    if not error:
        return True
    return not error.startswith(("download:", "strip:"))


def build_output_rows(expert: str, input_row: dict, link_column: str, pdf_result: dict,
                      extract: dict | None, extract_error: str | None) -> list[dict]:
    """One flat row per attorney. A failed or empty case still gives exactly one row."""

    link = input_row.get(link_column, "")
    base = {
        "row_index": input_row["row_index"],
        "expert": expert,
        "complaint_cell_value": link,
        "pdf_url": link.strip(),
        "pdf_downloaded": format_value(pdf_was_downloaded(pdf_result)),
        "download_error": format_value(pdf_result["error"]),
        "extract_error": format_value(extract_error),
        "extract_warning": "",
        "ocr_used": format_value(pdf_result["source"] == "ocr"),
    }

    for column in ATTORNEY_FIELDS.values():
        base[column] = ""

    if extract is None:
        return [base]

    base["extract_warning"] = format_value(extract.get("extract_warning"))
    for field in CASE_FIELDS:
        base[field] = format_value(extract.get(field))
    for field in LOOKUP_FIELDS:
        base[field] = ""
    for field in extract:
        if field != "attorneys" and field not in base:
            base[field] = format_value(extract[field])

    attorneys = extract.get("attorneys") or []
    if not attorneys:
        return [base]

    rows = []
    for attorney in attorneys:
        row = dict(base)
        for key, column in ATTORNEY_FIELDS.items():
            row[column] = format_value(attorney.get(key))
        for field in LOOKUP_FIELDS:
            row[field] = format_value(attorney.get(field))
        rows.append(row)

    return rows
