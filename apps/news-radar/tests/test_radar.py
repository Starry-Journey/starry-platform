import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import radar  # noqa: E402


def test_extract_json_handles_fences_and_trailing_text():
    raw = '```json\n[{"idx": 1, "score": 8, "summary": "ok"}]\n```\n后面还有文字 [干扰]'
    data = radar._extract_json(raw)
    assert data == [{"idx": 1, "score": 8, "summary": "ok"}]


def test_extract_json_returns_none_for_garbage():
    assert radar._extract_json("not json at all") is None


def test_dedupe_titles_drops_near_duplicates():
    items = [
        {"title": "NASA finds new dwarf planet beyond Neptune", "score": 9, "published": "2026-10-31"},
        {"title": "NASA finds a new dwarf planet beyond Neptune", "score": 8, "published": "2026-10-31"},
        {"title": "Black holes can split in two", "score": 8, "published": "2026-10-31"},
    ]
    kept = radar.dedupe_titles(items)
    assert len(kept) == 2


def test_pick_balanced_covers_categories_and_respects_limit():
    items = []
    for cat in ["科技", "开源工具", "创意艺术", "经济商业", "科学", "生活文化"]:
        for i in range(5):
            items.append(
                {"title": f"{cat}第{i}条独立新闻", "category": cat, "score": 8, "published": "2026-10-31"}
            )
    cfg = {"digest": {"min_score": 7, "max_items": 12}}
    picked = radar.pick_balanced(items, cfg)
    assert len(picked) == 12
    assert len({i["category"] for i in picked}) == 6


def test_render_digest_description_is_rich():
    items = [
        {
            "title": "A",
            "link": "https://a",
            "category": "科技",
            "score": 9,
            "feed": "HN",
            "cn_summary": "摘要",
            "reason": "",
        },
        {
            "title": "B",
            "link": "https://b",
            "category": "科学",
            "score": 8,
            "feed": "Q",
            "cn_summary": "摘要",
            "reason": "",
        },
    ]
    cfg = {"digest": {"title": "每日简报"}, "output": {"tags": ["每日简报"]}}
    text = radar.render_digest(items, cfg, "2026-10-31")
    assert "description:" in text
    assert "科技" in text and "科学" in text
    assert "2026-10-31" in text
