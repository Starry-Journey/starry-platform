import datetime as dt

from generate import cover_svg, pick_theme, wrap_title


def test_cover_contains_title_and_tag():
    svg = cover_svg("城市里的慢半拍", "城市", dt.date(2026, 11, 15))
    assert "城市里的慢半拍" in svg
    assert "2026-11-15" in svg
    assert svg.startswith("<svg")


def test_wrap_title_limits_lines():
    lines = wrap_title("一二三四五六七八九十一二三四五", 6)
    assert len(lines) <= 2
    assert all(len(line) <= 6 for line in lines)


def test_pick_theme_is_stable_per_date():
    a = pick_theme(dt.date(2026, 11, 15))
    b = pick_theme(dt.date(2026, 11, 15))
    assert a == b
