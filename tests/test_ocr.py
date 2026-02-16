"""Tests for OCR quality hardening helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.inbox.ocr import (
    OCRQualityError,
    assess_ocr_quality,
    clean_ocr_text_with_usage,
    ocr_pipeline_with_usage,
)


def test_clean_ocr_text_with_usage_empty_input() -> None:
    text, usage = clean_ocr_text_with_usage("")
    assert text == ""
    assert usage["total_tokens"] == 0
    assert usage["cost_estimate"] == 0.0


def test_assess_ocr_quality_rejects_short_text() -> None:
    ok, reason = assess_ocr_quality("too short")
    assert ok is False
    assert "too short" in reason.lower()


def test_assess_ocr_quality_accepts_jd_like_text() -> None:
    jd_like = (
        "About the role: We are looking for a product manager to lead roadmap and delivery. "
        "Responsibilities include defining requirements, working with engineering, and shipping features. "
        "Requirements: 5+ years experience in product management and strong communication skills."
    )
    ok, reason = assess_ocr_quality(jd_like)
    assert ok is True
    assert reason == "ok"


def test_ocr_pipeline_with_usage_raises_on_low_quality(monkeypatch, tmp_path: Path) -> None:
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"fake")

    monkeypatch.setattr("agents.inbox.ocr.extract_text_from_image", lambda _p: "raw")
    monkeypatch.setattr(
        "agents.inbox.ocr.clean_ocr_text_with_usage",
        lambda _raw: ("bad text", {"total_tokens": 10, "cost_estimate": 0.001}),
    )

    with pytest.raises(OCRQualityError):
        ocr_pipeline_with_usage(image_path)
