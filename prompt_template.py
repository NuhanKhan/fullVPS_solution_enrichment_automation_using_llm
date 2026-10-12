import hashlib
import logging
import re

PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
PROMPT_VERSION_LENGTH = 12


def load_prompt(path: str) -> tuple[str | None, str | None]:
    """Read a prompt file. Returns (text, None) on success, (None, error message) on failure."""

    try:
        with open(path, encoding="utf-8") as f:
            return (f.read(), None)
    except OSError as e:
        logging.error(f"Error reading prompt {path}: {e}")
        return (None, str(e))


def fill_template(template: str, values: dict) -> tuple[str | None, str | None]:
    """Replace every {{name}} with values[name] in one pass. Missing or unused values are an error."""

    placeholders = set(PLACEHOLDER.findall(template))

    missing = sorted(placeholders - set(values))
    if missing:
        return (None, f"no value for placeholders: {', '.join(missing)}")

    unused = sorted(set(values) - placeholders)
    if unused:
        return (None, f"values not used by the template: {', '.join(unused)}")

    # One pass, so placeholder text inside a value (like the PDF text) is never replaced again
    filled = PLACEHOLDER.sub(lambda match: str(values[match.group(1)]), template)

    return (filled, None)


def prompt_version(template: str) -> str:
    """Short fingerprint of a prompt. Spacing and line breaks are ignored, any changed word gives a new one."""

    words = " ".join(template.split())
    return hashlib.sha256(words.encode()).hexdigest()[:PROMPT_VERSION_LENGTH]
