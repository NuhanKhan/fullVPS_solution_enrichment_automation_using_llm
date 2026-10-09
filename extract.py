from openai import OpenAI

from config import EXTRACT_MODEL
from llm import chat, parse_json_response
from prompt_template import fill_template


def pick_opener(row_index: int) -> int:
    """Alternate the two outreach openers by row, so reruns give the same sentence."""

    if row_index % 2 == 0:
        return 2
    return 1


def build_extract_prompt(template: str, text: str, row_index: int) -> tuple[str | None, str | None]:
    return fill_template(template, {"pdf_text": text, "opener_number": pick_opener(row_index)})


def clean_attorneys(attorneys: list[dict]) -> list[dict]:
    """Drop entries with no name and no email, keep one attorney per email address."""

    cleaned = []
    seen_emails = set()

    for attorney in attorneys:
        email = (attorney.get("email") or "").strip().lower()
        has_name = bool(attorney.get("first_name") or attorney.get("last_name"))

        if not email and not has_name:
            continue
        if email and email in seen_emails:
            continue
        if email:
            seen_emails.add(email)

        cleaned.append({**attorney, "email": email or None})

    return cleaned


def one_liner_warning(one_liner: object) -> str | None:
    """A problem with the one-liner is a warning, not an error: the rest of the paid extraction is still good."""

    if not isinstance(one_liner, str) or not one_liner.strip():
        return "outreach_one_liner is blank"
    if "[CASE_NAME]" in one_liner:
        return "outreach_one_liner still contains [CASE_NAME]"
    return None


def validate_extract(data: dict) -> tuple[dict | None, str | None]:
    """Check the reply shape and clean the attorney list. Never modifies the input.

    Only an unusable shape is an error. A bad one-liner is written to extract_warning and the data is kept.
    """

    attorneys = data.get("attorneys")
    if not isinstance(attorneys, list):
        return (None, "attorneys is missing or not a list")

    for attorney in attorneys:
        if not isinstance(attorney, dict):
            return (None, "an attorney entry is not an object")

    warning = one_liner_warning(data.get("outreach_one_liner"))

    return ({**data, "attorneys": clean_attorneys(attorneys), "extract_warning": warning}, None)


def extract_case(client: OpenAI, template: str, text: str, row_index: int) -> tuple[dict | None, float, str | None]:
    """Send the complaint text with the expert prompt. Returns (extract, cost, None) or (None, cost, error).

    Cost is filled even on a parse or validate error, because the call was already paid for.
    """

    prompt, error = build_extract_prompt(template, text, row_index)
    if error:
        return (None, 0.0, f"prompt: {error}")

    content, cost, error = chat(client, EXTRACT_MODEL, [{"role": "user", "content": prompt}], json_mode=True)
    if error:
        return (None, cost, f"llm: {error}")

    data, error = parse_json_response(content)
    if error:
        return (None, cost, f"parse: {error}")

    extract, error = validate_extract(data)
    if error:
        return (None, cost, f"validate: {error}")

    return (extract, cost, None)
