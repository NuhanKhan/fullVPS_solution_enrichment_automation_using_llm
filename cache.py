import hashlib
import json
import logging
import os


def cache_key(expert: str, url: str) -> str:
    """Same document scored for two experts is two different results, so both go in the key."""

    return hashlib.sha256(f"{expert}\n{url.strip()}".encode()).hexdigest()


def load_cached(cache_dir: str, key: str) -> tuple[dict | None, str | None]:
    """Returns (entry, None) on a hit, (None, None) on a miss, (None, error) if the file is unreadable."""

    path = os.path.join(cache_dir, f"{key}.json")
    if not os.path.exists(path):
        return (None, None)

    try:
        with open(path, encoding="utf-8") as f:
            return (json.load(f), None)
    except (OSError, json.JSONDecodeError) as e:
        logging.error(f"Error reading cache file {path}: {e}")
        return (None, str(e))


def save_cached(cache_dir: str, key: str, entry: dict) -> tuple[str | None, str | None]:
    """Write the entry atomically. Returns (path, None) or (None, error)."""

    path = os.path.join(cache_dir, f"{key}.json")
    temp_path = f"{path}.tmp"

    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
        # A crash mid-write leaves only the .tmp file, never a half written cache entry
        os.replace(temp_path, path)
        return (path, None)
    except OSError as e:
        logging.error(f"Error writing cache file {path}: {e}")
        return (None, str(e))
