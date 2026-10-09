import re

from openai import OpenAI

from config import (
    EMAIL_LOOKUP_FITS,
    EMAIL_LOOKUP_MODEL,
    FIRM_NAME_STOPWORDS,
    GENERIC_EMAIL_PREFIXES,
)
from llm import chat, parse_json_response
from prompt_template import fill_template

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
WORD = re.compile(r"[a-z0-9]+")


def needs_lookup(attorney: dict, expert_fit: str | None) -> bool:
    """Look up only named attorneys with no email, on cases the expert would be pitched on."""

    if attorney.get("email"):
        return False
    if not attorney.get("first_name") and not attorney.get("last_name"):
        return False
    return expert_fit in EMAIL_LOOKUP_FITS


def build_lookup_messages(system: str, user_template: str, attorney: dict, firm: str | None) -> tuple[list[dict] | None, str | None]:
    values = {
        "first_name": attorney.get("first_name") or "",
        "last_name": attorney.get("last_name") or "",
        "firm": firm or "unknown",
        "address": attorney.get("address") or "unknown",
        "phone": attorney.get("phone") or "unknown",
    }
    user, error = fill_template(user_template, values)
    if error:
        return (None, error)

    return ([{"role": "system", "content": system}, {"role": "user", "content": user}], None)


def parse_lookup_email(content: str) -> tuple[str | None, str | None]:
    """Read {"emails": [...]} from the reply. Returns ("", None) when nothing valid was found."""

    data, error = parse_json_response(content)
    if error:
        return (None, error)

    emails = data.get("emails")
    if not isinstance(emails, list):
        return (None, "reply has no emails list")

    for email in emails:
        if not isinstance(email, str):
            continue
        cleaned = email.strip().lower().removeprefix("mailto:")
        if EMAIL_PATTERN.match(cleaned):
            return (cleaned, None)

    return ("", None)


def merge_email(attorney: dict, email: str) -> dict:
    """Copy every field and overwrite only the email, so nothing else is dropped."""

    return {**attorney, "email": email}


def email_check(email: str, firm: str | None) -> str:
    """Flag a looked up email for review. Nothing is rejected, Perplexity answers are guesses.

    A domain that shares no word with the firm name can still be right (some firms use short or
    unrelated domains), so "domain does not match firm" means check by hand, not wrong.
    """

    local, _, domain = email.lower().partition("@")
    if local in GENERIC_EMAIL_PREFIXES:
        return "generic inbox"

    firm_words = []
    for word in WORD.findall((firm or "").lower()):
        if len(word) >= 3 and word not in FIRM_NAME_STOPWORDS:
            firm_words.append(word)
    if not firm_words:
        return "no firm to compare"

    for word in firm_words:
        if word in domain:
            return "domain matches firm"
    return "domain does not match firm"


def lookup_email(client: OpenAI, messages: list[dict]) -> tuple[str | None, float, str | None]:
    """One Perplexity call. Returns (email or "", cost, None) or (None, cost, error)."""

    content, cost, error = chat(client, EMAIL_LOOKUP_MODEL, messages, json_mode=False)
    if error:
        return (None, cost, f"llm: {error}")

    email, error = parse_lookup_email(content)
    if error:
        return (None, cost, f"parse: {error}")

    return (email, cost, None)


def fill_missing_emails(client: OpenAI, system: str, user_template: str, extract: dict,
                        lookup_enabled: bool) -> tuple[dict, float, list[str]]:
    """Look up missing emails. Adds needs_email_search, search_query, email_source and email_check to every attorney.

    With lookup_enabled False no call is made, but every attorney is still marked, so the columns stay the same.

    Returns (new extract, total lookup cost, list of lookup errors for the caller to log). A failed
    lookup leaves that attorney's email empty, it never drops the row.
    """

    expert_fit = extract.get("expert_fit")
    firm = extract.get("plaintiff_firm")
    attorneys = []
    errors = []
    total_cost = 0.0

    for attorney in extract["attorneys"]:
        source = ""
        if attorney.get("email"):
            source = "document"
        result = {
            **attorney,
            "needs_email_search": not attorney.get("email"),
            "search_query": "",
            "email_source": source,
            "email_check": "",
        }

        if not lookup_enabled or not needs_lookup(attorney, expert_fit):
            attorneys.append(result)
            continue

        messages, error = build_lookup_messages(system, user_template, attorney, firm)
        if error:
            errors.append(f"email prompt: {error}")
            attorneys.append(result)
            continue

        result["search_query"] = messages[1]["content"]
        email, cost, error = lookup_email(client, messages)
        total_cost += cost
        if error:
            errors.append(f"email lookup for {attorney.get('first_name')} {attorney.get('last_name')}: {error}")
        elif email:
            result = merge_email(result, email)
            result["email_source"] = "lookup"
            result["email_check"] = email_check(email, firm)

        attorneys.append(result)

    return ({**extract, "attorneys": attorneys}, total_cost, errors)
