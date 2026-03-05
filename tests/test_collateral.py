"""Tests for collateral selection parsing."""

from __future__ import annotations

from agents.inbox.collateral import normalize_collateral_selection


def test_normalize_collateral_space_separated_values() -> None:
    selection, valid = normalize_collateral_selection("email referral")
    assert valid is True
    assert selection == ["email", "referral"]


def test_normalize_collateral_mixed_delimiters_and_aliases() -> None:
    selection, valid = normalize_collateral_selection("mail/linkedin & ref")
    assert valid is True
    assert selection == ["email", "linkedin", "referral"]


def test_normalize_collateral_none() -> None:
    selection, valid = normalize_collateral_selection("none")
    assert valid is True
    assert selection == []


def test_normalize_collateral_invalid_input() -> None:
    selection, valid = normalize_collateral_selection("cover letter")
    assert valid is False
    assert selection is None
