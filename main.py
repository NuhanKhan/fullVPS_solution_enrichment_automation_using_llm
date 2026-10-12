import argparse
import logging
import sys

from config import OUTPUT_TAB
from llm import get_openrouter_client
from pdf_text import get_mistral_client
from pipeline import run_pipeline
from sheets import get_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract attorney and case data from complaint PDFs.")
    parser.add_argument("--link", required=True, help="Google Sheets link, copied while the input tab is open (or a bare sheet id)")
    parser.add_argument("--expert", required=True, help="prompt file name in prompts/experts, without .txt")
    parser.add_argument("--input-tab", default=None, help="overrides the tab in the link")
    parser.add_argument("--output-tab", default=OUTPUT_TAB)
    parser.add_argument("--start-row", type=int, default=2, help="first sheet row to process")
    parser.add_argument("--limit", type=int, default=None, help="max rows to process")
    parser.add_argument("--no-email-lookup", action="store_true", help="skip the paid Perplexity email lookup")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what the run would do and roughly cost, then stop. Nothing is paid or written")
    parser.add_argument("--max-cost", type=float, default=None, help="stop once this many dollars are spent")
    prompt_change = parser.add_mutually_exclusive_group()
    prompt_change.add_argument("--redo-changed", action="store_true",
                               help="extract again the rows made with an older version of the prompt (paid)")
    prompt_change.add_argument("--keep-old", action="store_true",
                               help="use the cached answers from an older version of the prompt (free)")
    return parser.parse_args()


def prompt_change_mode(args: argparse.Namespace) -> str:
    if args.redo_changed:
        return "redo"
    if args.keep_old:
        return "keep"
    return "stop"


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Library noise: pypdf font warnings, one line per HTTP request, Google discovery cache notice
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)
    args = parse_args()

    service = get_service()
    mistral_client = get_mistral_client()
    openrouter_client = get_openrouter_client()

    summary, error = run_pipeline(
        service, mistral_client, openrouter_client, args.link, args.expert,
        args.input_tab, args.output_tab, args.start_row, args.limit, not args.no_email_lookup,
        prompt_change_mode(args), args.dry_run, args.max_cost,
    )
    if error:
        logging.error(error)
        sys.exit(1)

    logging.info(f"done: {summary}")


if __name__ == "__main__":
    main()
