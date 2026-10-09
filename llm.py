import json
import logging

from openai import APIError, OpenAI

from config import LLM_MAX_RETRIES, LLM_TIMEOUT, OPENROUTER_API_KEY, OPENROUTER_BASE_URL


def get_openrouter_client() -> OpenAI:
    return OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        timeout=LLM_TIMEOUT,
        max_retries=LLM_MAX_RETRIES,
    )


def reply_cost(usage: object) -> float:
    """Dollar cost OpenRouter reports in usage.cost, 0.0 when it is missing."""

    cost = getattr(usage, "cost", None)
    if cost is None:
        return 0.0
    return float(cost)


def chat(client: OpenAI, model: str, messages: list[dict], json_mode: bool) -> tuple[str | None, float, str | None]:
    """One chat completion. Returns (reply text, cost, None) or (None, cost, error message).

    Cost is always a number. A failed request counts as 0.0, since OpenRouter returns no usage for it.
    """

    kwargs = {"model": model, "messages": messages}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = client.chat.completions.create(**kwargs)
    except APIError as e:
        logging.error(f"Error calling {model}: {e}")
        return (None, 0.0, str(e))

    cost = reply_cost(response.usage)

    # OpenRouter can answer 200 with no choices when the upstream provider fails
    if not response.choices:
        return (None, cost, f"{model} returned no choices")

    content = response.choices[0].message.content
    if not content:
        return (None, cost, f"{model} returned an empty reply")

    return (content, cost, None)


def parse_json_response(content: str) -> tuple[dict | None, str | None]:
    """Pull the JSON object out of an LLM reply, ignoring code fences and text around it."""

    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        text = text.removeprefix("json")
        text = text.strip()

    if text.startswith("["):
        return (None, "expected a JSON object, got a list")

    start = text.find("{")
    if start == -1:
        return (None, "no JSON object in reply")

    # json has no non-raising parser, so this is the one try/except allowed in pure code
    try:
        data, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as e:
        return (None, f"invalid JSON: {e}")

    return (data, None)
