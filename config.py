import os

from dotenv import load_dotenv

load_dotenv()

# ---------- Secrets (from .env, fail loudly if missing) ----------

GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
if not GOOGLE_SERVICE_ACCOUNT_JSON:
    raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON environment variable is not set.")

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
if not MISTRAL_API_KEY:
    raise ValueError("MISTRAL_API_KEY environment variable is not set.")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY environment variable is not set.")

# ---------- Settings ----------

DOWNLOAD_TIMEOUT = 30
MIN_CHARS_PER_PAGE = 100
MAX_TEXT_CHARS = 250000
MISTRAL_OCR_MODEL = "mistral-ocr-2512"
MISTRAL_OCR_COST_PER_PAGE = 0.002  # $2 per 1,000 pages, standard API price (not batch)
SHEETS_BATCH_SIZE = 500
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
EXTRACT_MODEL = "deepseek/deepseek-v4.1-flash"
EMAIL_LOOKUP_MODEL = "perplexity/sonar"
LLM_TIMEOUT = 180
LLM_MAX_RETRIES = 0  # one attempt per paid call, a retry can double the bill

# Email lookup only runs for cases the expert would actually be pitched on
EMAIL_LOOKUP_FITS = ("strong_fit", "possible_fit")

# email_check on looked up emails. A flag for review, nothing is rejected.
GENERIC_EMAIL_PREFIXES = (
    "info", "contact", "office", "admin", "intake", "hello", "mail", "reception",
    "staff", "frontdesk", "help", "inquiries", "enquiries", "law", "attorneys",
)
# Words ignored when comparing a firm name to an email domain
FIRM_NAME_STOPWORDS = (
    "the", "and", "law", "laws", "lawyer", "lawyers", "firm", "group", "office", "offices",
    "llc", "llp", "pllc", "lpa", "associates", "attorney", "attorneys", "legal", "partners", "inc",
)

# Sheet defaults. The sheet itself comes from --link, the input tab from the link's gid or --input-tab.
OUTPUT_TAB = "Output"
COMPLAINT_LINK_COLUMN = "Complaint Link"
WRITE_EVERY_ROWS = 10

# Local paths
PROMPTS_DIR = "prompts"
CACHE_DIR = ".cache"
