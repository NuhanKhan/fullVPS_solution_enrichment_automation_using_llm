import json
import logging

from google.auth.exceptions import TransportError
from google.oauth2 import service_account
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

from config import GOOGLE_SERVICE_ACCOUNT_JSON, SHEETS_BATCH_SIZE

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Google API errors plus network failures. Code bugs (KeyError, TypeError) still crash on purpose.
GOOGLE_ERRORS = (HttpError, TransportError, OSError)

def get_service() -> Resource:
    credentials = service_account.Credentials.from_service_account_file(
    GOOGLE_SERVICE_ACCOUNT_JSON,
    scopes=SCOPES,
    )
    service = build("sheets", "v4", credentials=credentials)

    return service

def get_service_account_email() -> tuple[str | None, str | None]:
    """The address a sheet must be shared with so this app can open it."""

    try:
        with open(GOOGLE_SERVICE_ACCOUNT_JSON, encoding="utf-8") as f:
            return (json.load(f)["client_email"], None)
    except (OSError, ValueError, KeyError) as e:
        logging.error(f"Error reading client_email from {GOOGLE_SERVICE_ACCOUNT_JSON}: {e}")
        return (None, str(e))

def quote_tab(tab: str) -> str:
    """A1 notation for a whole tab. Quotes always, so names with spaces or digits work."""

    return "'" + tab.replace("'", "''") + "'"

def get_tabs(service: Resource, sheet_id: str) -> tuple[list[dict] | None, str | None]:
    """List tabs in sheet order. Returns ([{"title", "sheetId"}, ...], None) or (None, error)."""

    try:
        meta = service.spreadsheets().get(spreadsheetId=sheet_id, fields="sheets.properties(title,sheetId)").execute()
        tabs = []
        for sheet in meta.get("sheets", []):
            tabs.append({"title": sheet["properties"]["title"], "sheetId": sheet["properties"]["sheetId"]})
        return (tabs, None)
    except GOOGLE_ERRORS as e:
        logging.error(f"Error opening sheet {sheet_id}: {e}")
        return (None, str(e))

def get_sheet_values(service: Resource, sheet_id: str, range_name: str) -> tuple[list[list] | None, str | None]:
    """Read a range. Returns (values, None) on success, (None, error message) on failure."""

    try:
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=sheet_id, range=range_name).execute()
        values = result.get("values", [])

        return (values, None)
    except GOOGLE_ERRORS as e:
        logging.error(f"Error reading {range_name}: {e}")
        return (None, str(e))

def ensure_tab(service: Resource, sheet_id: str, tab: str) -> tuple[bool | None, str | None]:
    """Create the tab if it does not exist. Returns (True if created, None) or (None, error)."""

    tabs, error = get_tabs(service, sheet_id)
    if error:
        return (None, error)
    for existing in tabs:
        if existing["title"] == tab:
            return (False, None)

    try:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab}}}]},
        ).execute()
        logging.info(f"Created tab {tab}")
        return (True, None)
    except GOOGLE_ERRORS as e:
        logging.error(f"Error creating tab {tab}: {e}")
        return (None, str(e))

def rows_to_dicts(values: list[list]) -> tuple[list[dict] | None, str | None]:
    """Turn sheet values into row dicts. Returns (None, error) if the tab has no header row."""

    if not values or not values[0]:
        return (None, "no header row")

    column_headers = values[0]
    formatted_values = []

    for row_index, row in enumerate(values[1:]):
        temp_dict = {}
        temp_dict["row_index"] = row_index + 2  # +2 to account for the header row and 0-based indexing
        for i in range(len(column_headers)):
            if i < len(row):
                temp_dict[column_headers[i]] = row[i]
            else:
                temp_dict[column_headers[i]] = ""
        formatted_values.append(temp_dict)

    return (formatted_values, None)


def dicts_to_rows(dicts: list[dict], header_row: list[str]) -> list[list]:
    if not dicts:
        return []
    rows = []
    #no need of header row as we will be using a different function to get the header row

    for d in dicts:
        row = [d.get(key, "") for key in header_row]
        rows.append(row)

    return rows


def merge_header(existing_header: list[str], new_header: list[str]) -> list[str]:
    merged_header = existing_header.copy()
    for column in new_header:
        if column not in merged_header:
            merged_header.append(column)
    return merged_header

def chunk_rows(rows: list[list], size: int) -> list[list[list]]:
    """Split rows into batches of at most size rows."""

    batches = []
    for start in range(0, len(rows), size):
        batches.append(rows[start:start + size])
    return batches

def write_rows(service: Resource, sheet_id: str, tab: str, dicts: list[dict]) -> tuple[int | None, str | None]:
    """Append dicts to a tab, adding new headers at the end. Returns (rows written, None) or (None, error)."""

    if not dicts:
        return (0, None)

    # Only row 1 is needed for the header
    existing_values, error = get_sheet_values(service, sheet_id, f"{quote_tab(tab)}!1:1")
    if error:
        return (None, f"read header: {error}")
    existing_header = existing_values[0] if existing_values else []

    # Merge the existing header with the new header from the dicts
    new_header = []
    for d in dicts:
        for key in d:
            new_header.append(key)
    merged_header = merge_header(existing_header, new_header)

    # New columns on an existing header usually mean LLM key drift, so make them visible
    if existing_header:
        for column in merged_header[len(existing_header):]:
            logging.warning(f"New column added to {tab}: {column}")

    # Convert dicts to rows based on the merged header
    rows = dicts_to_rows(dicts, merged_header)

    try:
        # 1. Header goes to row 1
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{quote_tab(tab)}!1:1",
            valueInputOption="RAW",
            body={"values": [merged_header]},
        ).execute()
    except GOOGLE_ERRORS as e:
        logging.error(f"Error writing header to {tab}: {e}")
        return (None, f"write header: {e}")

    # 2. Data rows go below, in batches
    written = 0
    for batch in chunk_rows(rows, SHEETS_BATCH_SIZE):
        try:
            service.spreadsheets().values().append(
                spreadsheetId=sheet_id,
                range=f"{quote_tab(tab)}!A1",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": batch},
            ).execute()
        except GOOGLE_ERRORS as e:
            logging.error(f"Error appending rows to {tab} after {written} rows: {e}")
            return (None, f"append: {written} of {len(rows)} rows written: {e}")
        written += len(batch)

    return (written, None)
