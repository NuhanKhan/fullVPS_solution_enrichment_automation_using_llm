STATUSES = ("new", "cached", "prompt changed", "lookup owed")


def lookup_still_owed(cached: dict, lookup_enabled: bool) -> bool:
    """A row cached during a --no-email-lookup run gets its lookup the next time lookup is on.

    Entries from before the switch existed have no email_lookup key; they were made with lookup on.
    """

    return lookup_enabled and not cached.get("email_lookup", True)


def row_status(cached: dict | None, current_version: str, lookup_enabled: bool) -> str:
    """What a run would do with one row: one of STATUSES.

    An entry without a prompt_version cannot be trusted to match the prompt, so it counts as changed.
    """

    if cached is None:
        return "new"
    if cached.get("prompt_version") != current_version:
        return "prompt changed"
    if lookup_still_owed(cached, lookup_enabled):
        return "lookup owed"
    return "cached"


def count_statuses(statuses: list[str]) -> dict:
    counts = {}
    for status in STATUSES:
        counts[status] = 0
    for status in statuses:
        counts[status] += 1
    return counts


def estimate_cost(counts: dict, prompt_change: str, cost_per_row: float) -> float:
    """Rough cost of the rows that need the LLM. Cached rows are free, owed lookups are left out (small).

    Prompt changed rows are priced unless they are kept, so a stopped or dry run shows what a redo costs.
    """

    rows = counts["new"]
    if prompt_change != "keep":
        rows += counts["prompt changed"]
    return rows * cost_per_row


def plan_message(counts: dict, current_version: str, prompt_change: str, estimate: float) -> str:
    total = 0
    for status in STATUSES:
        total += counts[status]

    message = (f"plan for prompt {current_version}: {total} rows, {counts['cached']} cached (free), "
               f"{counts['prompt changed']} prompt changed, {counts['new']} new, "
               f"{counts['lookup owed']} lookup owed")
    if prompt_change == "keep" and counts["prompt changed"]:
        message += ". Prompt changed rows are kept as they are (--keep-old)"
    message += f". Estimated cost about ${estimate:.2f}"
    return message


def prompt_change_error(counts: dict, prompt_change: str) -> str | None:
    """The run stops when some rows were made with another prompt and nobody said what to do with them."""

    changed = counts["prompt changed"]
    if changed == 0 or prompt_change != "stop":
        return None
    return (f"prompt: {changed} rows were made with a different version of the prompt. "
            "Rerun with --redo-changed to pay for them again, or --keep-old to use the old answers")
