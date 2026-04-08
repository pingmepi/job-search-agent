"""Tests for core/json_utils.py — shared JSON extraction utility."""

from core.json_utils import extract_first_json_object


class TestExtractFirstJsonObject:
    def test_clean_json(self):
        assert extract_first_json_object('{"a": 1}') == '{"a": 1}'

    def test_json_with_surrounding_text(self):
        text = 'Here is the result: {"company": "Acme"} and more text'
        assert extract_first_json_object(text) == '{"company": "Acme"}'

    def test_nested_braces(self):
        text = '{"outer": {"inner": "value"}}'
        assert extract_first_json_object(text) == '{"outer": {"inner": "value"}}'

    def test_braces_inside_strings(self):
        text = '{"key": "value with {braces} inside"}'
        assert extract_first_json_object(text) == '{"key": "value with {braces} inside"}'

    def test_escaped_quotes(self):
        text = '{"key": "value with \\"escaped\\" quotes"}'
        result = extract_first_json_object(text)
        assert result is not None
        assert result.startswith("{")
        assert result.endswith("}")

    def test_no_json(self):
        assert extract_first_json_object("no json here") is None

    def test_empty_string(self):
        assert extract_first_json_object("") is None

    def test_unclosed_brace(self):
        assert extract_first_json_object('{"key": "value"') is None

    def test_markdown_fenced_json(self):
        text = '```json\n{"company": "Acme"}\n```'
        assert extract_first_json_object(text) == '{"company": "Acme"}'

    def test_deeply_nested(self):
        text = '{"a": {"b": {"c": {"d": 1}}}}'
        assert extract_first_json_object(text) == text
