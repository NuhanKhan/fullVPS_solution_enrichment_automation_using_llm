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
    return parser.parse_args()


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
    )
    if error:
        logging.error(error)
        sys.exit(1)

    logging.info(f"done: {summary}")


if __name__ == "__main__":
    main()
