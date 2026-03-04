"""
OCR pipeline — extract text from job description screenshots.

Pipeline:
1. Tesseract raw OCR
2. LLM cleanup (fix formatting, remove noise)
3. Return clean text for JD extraction
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

try:
    import pytesseract
    from PIL import Image
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

from core.llm import chat_text
from core.config import get_settings


# ── OCR ───────────────────────────────────────────────────────────

def extract_text_from_image(image_path: Path) -> str:
    """
    Run Tesseract OCR on an image and return raw text.

    Raises RuntimeError if Tesseract is not installed.
    """
    if not HAS_TESSERACT:
        raise RuntimeError(
            "pytesseract or Pillow not available. "
            "Install with: pip install pytesseract Pillow "
            "and ensure Tesseract is installed: brew install tesseract"
        )

    image = Image.open(image_path)
    raw_text = pytesseract.image_to_string(image)
    return raw_text


# ── LLM cleanup ──────────────────────────────────────────────────

OCR_CLEANUP_PROMPT = """\
You are an OCR post-processor. You receive raw OCR output from a job description \
screenshot. Your job is to clean it up:

1. Fix obvious OCR errors (misread characters, merged words)
2. Restore proper formatting (paragraphs, bullet points, headers)
3. Remove any UI artifacts (buttons, navigation elements, timestamps)
4. Preserve ALL factual content — do not add or remove information

Return only the cleaned job description text.
"""


def clean_ocr_text(raw_text: str) -> str:
    """
    Use LLM to clean up raw OCR output.

    Returns cleaned, well-formatted text ready for JD extraction.
    """
    if not raw_text.strip():
        return ""

    response = chat_text(OCR_CLEANUP_PROMPT, raw_text)
    return response.text.strip()


def clean_ocr_text_with_usage(raw_text: str) -> tuple[str, dict[str, float | int]]:
    """
    Clean OCR text and return usage for the cleanup call.
    """
    if not raw_text.strip():
        return "", {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_estimate": 0.0,
            "generation_id": None,
        }

    response = chat_text(OCR_CLEANUP_PROMPT, raw_text)
    return response.text.strip(), {
        "prompt_tokens": response.prompt_tokens,
        "completion_tokens": response.completion_tokens,
        "total_tokens": response.total_tokens,
        "cost_estimate": response.cost_estimate,
        "generation_id": response.generation_id,
    }


def assess_ocr_quality(
    cleaned_text: str,
    *,
    min_text_chars: int = 120,
    min_alpha_chars: int = 60,
    require_jd_indicator: bool = True,
) -> tuple[bool, str]:
    """
    Heuristic OCR quality gate for JD extraction readiness.

    Returns (is_valid, reason).
    """
    text = (cleaned_text or "").strip()
    if len(text) < min_text_chars:
        return False, "Extracted text is too short"

    alpha_chars = sum(1 for ch in text if ch.isalpha())
    if alpha_chars < min_alpha_chars:
        return False, "Extracted text has insufficient readable content"

    jd_indicators = [
        "responsibilities",
        "requirements",
        "qualifications",
        "about the role",
        "what you'll do",
        "what we are looking for",
        "experience",
        "skills",
    ]
    indicator_hits = sum(1 for marker in jd_indicators if marker in text.lower())
    if require_jd_indicator and indicator_hits == 0:
        return False, "Extracted text does not look like a job description"

    return True, "ok"


class OCRQualityError(RuntimeError):
    """Raised when OCR output is too weak for reliable JD extraction."""


# ── Full pipeline ─────────────────────────────────────────────────

def ocr_pipeline(image_path: Path) -> str:
    """
    Full OCR pipeline: image → raw text → cleaned text.

    Parameters
    ----------
    image_path : Path to the screenshot image.

    Returns
    -------
    Cleaned text ready for JD extraction.
    """
    raw = extract_text_from_image(image_path)
    cleaned = clean_ocr_text(raw)
    settings = get_settings()
    valid, reason = assess_ocr_quality(
        cleaned,
        min_text_chars=settings.ocr_min_text_chars,
        min_alpha_chars=settings.ocr_min_alpha_chars,
        require_jd_indicator=settings.ocr_require_jd_indicator,
    )
    if not valid:
        raise OCRQualityError(reason)
    return cleaned


def ocr_pipeline_with_usage(image_path: Path) -> tuple[str, dict[str, float | int]]:
    """
    Full OCR pipeline with LLM usage metadata.
    """
    raw = extract_text_from_image(image_path)
    cleaned, usage = clean_ocr_text_with_usage(raw)
    settings = get_settings()
    valid, reason = assess_ocr_quality(
        cleaned,
        min_text_chars=settings.ocr_min_text_chars,
        min_alpha_chars=settings.ocr_min_alpha_chars,
        require_jd_indicator=settings.ocr_require_jd_indicator,
    )
    if not valid:
        raise OCRQualityError(reason)
    return cleaned, usage
