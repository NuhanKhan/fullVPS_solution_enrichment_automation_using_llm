import base64
import html
import io
import logging

import requests
from mistralai.client import Mistral
from pypdf import PdfReader

from config import (
    DOWNLOAD_TIMEOUT,
    MAX_TEXT_CHARS,
    MIN_CHARS_PER_PAGE,
    MISTRAL_API_KEY,
    MISTRAL_OCR_COST_PER_PAGE,
    MISTRAL_OCR_MODEL,
)


def download_pdf(url: str) -> tuple[bytes | None, str | None]:
    """Download a file. Returns (bytes, None) on success, (None, error message) on failure."""
    
    try:
        response = requests.get(url, timeout=DOWNLOAD_TIMEOUT)
        response.raise_for_status()  # Raise an error for bad responses

        return (response.content, None)
    except requests.RequestException as e:
        logging.error(f"Error downloading PDF from {url}: {e}")
        return (None, str(e))

def strip_wrapper(pdf_bytes: bytes) -> tuple[bytes | None, str | None]:
    """Strip the wrapper from a PDF file. Returns (stripped bytes, None)"""
    
    # Placeholder for actual stripping logic
    position = pdf_bytes.find(b"%PDF-")
    if position == -1:
        return (None, "no %PDF marker found")
    cleaned_pdf = pdf_bytes[position:]

    return (cleaned_pdf, None)

def needs_ocr(text: str, page_count: int) -> bool:
    """Determine if OCR is needed based on the extracted text and page count."""
    
    # If no text was extracted or the page count is low, assume OCR is needed
    if not text.strip() or page_count < 1:
        return True
    
    # Count only visible characters. Scans can carry a filing stamp padded with hundreds of spaces per page.
    visible_chars = len("".join(text.split()))
    chars_per_page = visible_chars / page_count
    if chars_per_page < MIN_CHARS_PER_PAGE:
        return True
    
    return False

def extract_native_text(pdf_bytes: bytes) -> tuple[str | None, int, str | None]:
    """Extract text from a PDF file. Returns (text, page_count, None) on success, (None, 0, error message) on failure."""

    try:  
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            text += (page.extract_text() or "") + "\n"
        
        page_count = len(reader.pages)

        return (text, page_count, None)
        
    except Exception as e:
        logging.error(f"Error extracting text from PDF: {e}")
        return (None, 0, str(e))

def cap_text(text: str, max_chars: int) -> str:
    """Cap the text to a maximum number of characters."""
    
    if len(text) > max_chars:
        head = int(max_chars * 0.7)
        tail = max_chars - head
        return text[:head] + text[-tail:]
    return text

def ocr_pdf(client: Mistral, pdf_bytes: bytes) -> tuple[str | None, int, str | None]:
    """Perform OCR on a PDF file using Mistral. Returns (text, pages billed, None) or (None, 0, error message)."""
    
    encoded = base64.b64encode(pdf_bytes).decode("ascii")
    document_url = f"data:application/pdf;base64,{encoded}"

    try:
        response = client.ocr.process(
            model=MISTRAL_OCR_MODEL,
            document={"type": "document_url", "document_url": document_url},
        )

        text = ""
        for page in response.pages:
            text += (page.markdown or "") + "\n"

        # Mistral bills per processed page and reports the count, it does not report a price
        pages = len(response.pages)
        if response.usage_info and response.usage_info.pages_processed:
            pages = response.usage_info.pages_processed

        return (html.unescape(text), pages, None)

    except Exception as e:
        logging.error(f"Error during OCR request: {e}")
        return (None, 0, str(e))

def get_mistral_client() -> Mistral:
    return Mistral(api_key=MISTRAL_API_KEY)

def get_pdf_text(client: Mistral, url: str) -> dict:
    """Get text from a PDF URL. Always returns {"text", "source", "error", "cost"}."""

    pdf_bytes, error = download_pdf(url)
    if error:
        return {"text": "", "source": "", "error": f"download: {error}", "cost": 0.0}

    clean_bytes, error = strip_wrapper(pdf_bytes)
    if error:
        return {"text": "", "source": "", "error": f"strip: {error}", "cost": 0.0}

    text, page_count, error = extract_native_text(clean_bytes)
    if error:
        return {"text": "", "source": "", "error": f"native: {error}", "cost": 0.0}

    source = "native"
    cost = 0.0
    if needs_ocr(text, page_count):
        ocr_text, pages, error = ocr_pdf(client, clean_bytes)
        if error:
            return {"text": "", "source": "", "error": f"ocr: {error}", "cost": 0.0}
        text = ocr_text
        source = "ocr"
        cost = pages * MISTRAL_OCR_COST_PER_PAGE

    return {"text": cap_text(text, MAX_TEXT_CHARS), "source": source, "error": None, "cost": cost}