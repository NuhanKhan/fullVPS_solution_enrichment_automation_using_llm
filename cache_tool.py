import argparse
import logging
import os
import sys
import time

from cache_maintenance import (
    current_prompt_versions,
    delete_files,
    scan_cache,
    select_older_than,
    summarize_cache,
)
from config import CACHE_DIR, CACHE_MAX_AGE_DAYS, PROMPTS_DIR


def positive_days(value: str) -> int:
    days = int(value)
    if days < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return days


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Inspect or prune the {CACHE_DIR}/ cache of finished extracts.")
    commands = parser.add_subparsers(dest="command", required=True)

    stats = commands.add_parser("stats", help="show what is in the cache")
    stats.add_argument("--older-than-days", type=positive_days, default=CACHE_MAX_AGE_DAYS,
                       help="also report what a prune at this age would remove")

    prune = commands.add_parser("prune", help="delete entries not written or used for N days")
    prune.add_argument("--older-than-days", type=positive_days, default=CACHE_MAX_AGE_DAYS)
    prune.add_argument("--yes", action="store_true", help="really delete; without it nothing is deleted")
    return parser.parse_args()


def log_stats(summary: dict) -> None:
    logging.info(f"cache {CACHE_DIR}/: {summary['entries']} entries, {summary['bytes'] / 1_000_000:.1f} MB")
    logging.info(f"OCR texts kept: {summary['ocr_texts']}, {summary['ocr_bytes'] / 1_000_000:.1f} MB")
    logging.info(f"oldest {summary['oldest']}, newest {summary['newest']} (UTC, last written or used)")
    logging.info(f"by expert: {summary['by_expert']}")
    logging.info(f"by source: {summary['by_source']}")
    logging.info(f"by fit: {summary['by_fit']}")
    for expert, counts in summary["by_prompt"].items():
        logging.info(f"prompt for {expert}: {counts['current']} entries on the current version, {counts['older']} on "
                     "an older one (redone only with --redo-changed)")
    logging.info(f"cost stored: ${summary['cost_usd']:.4f}, plus {summary['entries_without_cost']} entries from "
                 "before cost logging")
    if summary["unreadable"] or summary["stray_tmp"]:
        logging.warning(f"{summary['unreadable']} unreadable files, {summary['stray_tmp']} leftover .tmp files")
    logging.info(f"older than {summary['older_than_days']} days: {summary['prunable_files']} files, "
                 f"{summary['prunable_bytes'] / 1_000_000:.1f} MB, ${summary['prunable_cost_usd']:.4f} to pay "
                 "again if they come back")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()

    files, error = scan_cache(CACHE_DIR)
    if error:
        logging.error(error)
        sys.exit(1)

    versions, error = current_prompt_versions(os.path.join(PROMPTS_DIR, "experts"))
    if error:
        logging.error(error)
        sys.exit(1)

    now = time.time()
    summary = summarize_cache(files, now, args.older_than_days, versions)
    log_stats(summary)
    if args.command == "stats":
        return

    old_files = select_older_than(files, now, args.older_than_days)
    if not args.yes:
        logging.info(f"dry run: would delete {len(old_files)} files. Add --yes to delete them.")
        return

    deleted, error = delete_files(old_files)
    if error:
        logging.error(error)
        sys.exit(1)
    logging.info(f"deleted {deleted} files older than {args.older_than_days} days")


if __name__ == "__main__":
    main()
