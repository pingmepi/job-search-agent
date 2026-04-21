"""Tests for drive.py naming + folder structure (no network calls)."""

from __future__ import annotations

from pathlib import Path

from integrations.drive import (
    DEFAULT_CANDIDATE_NAME,
    ROOT_FOLDER_NAME,
    _build_filename,
    _clean_company_for_filename,
    _slug,
)


class TestFolderStructure:
    def test_root_folder_name(self):
        assert ROOT_FOLDER_NAME == "Job search agent"

    def test_slug_cleans_value(self):
        assert _slug("Share Your Resume At", "fallback") == "share_your_resume_at"
        assert _slug("  Product/Manager  ", "fallback") == "product_manager"
        assert _slug("", "fallback") == "fallback"


class TestFilename:
    def test_pdf_resume(self):
        name = _build_filename(
            DEFAULT_CANDIDATE_NAME, "Stripe", "resume_pdf", Path("master_product.pdf")
        )
        assert name == "Mandalam_Karan_Stripe_resume.pdf"

    def test_txt_email(self):
        name = _build_filename(
            DEFAULT_CANDIDATE_NAME, "Acme Corp", "email", Path("email_draft.txt")
        )
        assert name == "Mandalam_Karan_Acme_Corp_email.txt"

    def test_linkedin(self):
        name = _build_filename(
            DEFAULT_CANDIDATE_NAME, "FooBar, Inc.", "linkedin", Path("linkedin_dm.txt")
        )
        assert name == "Mandalam_Karan_FooBar_Inc_linkedin.txt"

    def test_referral(self):
        name = _build_filename("Doe_Jane", "Zeta & Co", "referral", Path("referral.txt"))
        assert name == "Doe_Jane_Zeta_Co_referral.txt"

    def test_unknown_logical_name_passes_through(self):
        name = _build_filename(DEFAULT_CANDIDATE_NAME, "Acme", "custom", Path("anything.pdf"))
        assert name == "Mandalam_Karan_Acme_custom.pdf"


class TestCleanCompanyForFilename:
    def test_preserves_case(self):
        assert _clean_company_for_filename("Stripe") == "Stripe"

    def test_strips_punctuation(self):
        assert _clean_company_for_filename("Foo, Bar & Baz") == "Foo_Bar_Baz"

    def test_empty_fallback(self):
        assert _clean_company_for_filename("") == "Company"
