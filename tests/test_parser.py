"""parser.py 테스트."""

from consumer_dispute_mcp.parser import _clean_text, _parse_remedies


def test_clean_text():
    assert _clean_text("  hello   world\n ") == "hello world"


def test_parse_remedies_comma():
    assert _parse_remedies("제품교환, 구입가환급") == ["제품교환", "구입가환급"]


def test_parse_remedies_or():
    assert _parse_remedies("제품교환 또는 구입가환급") == ["제품교환", "구입가환급"]


def test_parse_remedies_single():
    assert _parse_remedies("무상수리") == ["무상수리"]
