#!/usr/bin/env python3
"""东京新闻雷达 —— 抓 RSS / 网页 → DeepSeek 打分与中文摘要 → 生成每日简报

运行方式:
    python3 radar.py --config config.yaml --out-dir ./out --dry-run   # 不调 API、不写库
    python3 radar.py --config config.yaml --out-dir ./out            # 完整一次

设计原则:
  * 幂等：同一链接只处理一次（SQLite 去重），重跑不会产生重复简报
  * 容错：单个源失败只记录、不中断
  * 省钱：只看最近 N 天新条目，按批调用 API
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import mktime_tz, parsedate_to_datetime, parsedate_tz
from pathlib import Path

import feedparser
import requests
import yaml

USER_AGENT = "TokyoNewsRadar/1.0 (+personal digest)"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TZ_CN = timezone(timedelta(hours=8))

DIGEST_HEADER = """---
layout: page
menu_id: news
title: {title}
date: {date} 08:00:00
description: {description}
---

"""


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------- 抓取层
def _parse_date(entry) -> str:
    """兼容 RFC 2822 与 ISO-8601 两种常见日期格式 → ISO 字符串（UTC）"""
    raw = (entry.get("published") or entry.get("updated") or "").strip()
    if not raw:
        return ""
    dt = None
    for parser in (
        lambda t: datetime.fromisoformat(t.replace("Z", "+00:00")),
        parsedate_to_datetime,
    ):
        try:
            dt = parser(raw)
            break
        except (TypeError, ValueError):
            continue
    if dt is None:
        try:
            t = parsedate_tz(raw)
            if t:
                dt = datetime.fromtimestamp(mktime_tz(t), tz=timezone.utc)
        except Exception:
            return ""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _clean_summary(html: str, limit: int) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def fetch_rss(src: dict, cfg: dict) -> list:
    timeout = cfg["fetch"].get("timeout", 15)
    cap = int(src.get("max_items_per_feed") or cfg["fetch"].get("max_items_per_feed") or 0)
    r = requests.get(src["url"], timeout=timeout, headers={"User-Agent": BROWSER_UA})
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    limit = int(cfg["llm"].get("max_summary_chars", 600))
    out = []
    for e in feed.entries:
        out.append(
            {
                "title": (e.get("title") or "").strip(),
                "link": (e.get("link") or "").strip(),
                "summary": _clean_summary(e.get("summary") or e.get("description") or "", limit),
                "published": _parse_date(e),
            }
        )
    return out[:cap] if cap else out


def fetch_html(src: dict, cfg: dict) -> list:
    """GitHub Trending 这类没有 RSS 的页面：用 selector + 正则粗提取"""
    timeout = cfg["fetch"].get("timeout", 15)
    r = requests.get(src["url"], timeout=timeout, headers={"User-Agent": BROWSER_UA})
    r.raise_for_status()
    blocks = re.findall(r'<article[^>]*class="[^"]*Box-row[^"]*"[^>]*>(.*?)</article>', r.text, re.S)
    if not blocks:
        # 兜底：整页按 <article> 切
        blocks = re.findall(r"<article[^>]*>(.*?)</article>", r.text, re.S)
    out = []
    for b in blocks:
        # 仓库名：<a href="/owner/repo" ...>owner / repo</a>
        m = re.search(r'<a\s+href="/([^"]+)"[^>]*>\s*(.*?)\s*</a>', b, re.S)
        if not m or m.group(1).startswith(("login", "signup", "topics")):
            continue
        href = m.group(1)
        if not re.search(r"^[\w.-]+/[\w.-]+$", href):
            continue
        desc = ""
        dm = re.search(r"<p[^>]*>(.*?)</p>", b, re.S)
        if dm:
            desc = re.sub(r"<[^>]+>", " ", dm.group(1))
            desc = re.sub(r"\s+", " ", desc).strip()
        out.append(
            {
                "title": f"{href.replace('/', ' / ')} — {desc[:60]}" if desc else href.replace("/", " / "),
                "link": f"https://github.com/{href}",
                "summary": desc[: int(cfg["llm"].get("max_summary_chars", 600))],
                "published": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
    return out


def fetch_one(src: dict, cfg: dict) -> dict:
    t0 = time.time()
    try:
        if src.get("type", "rss") == "html":
            items = fetch_html(src, cfg)
        else:
            items = fetch_rss(src, cfg)
        return {"src": src, "items": items, "error": None, "seconds": round(time.time() - t0, 2)}
    except Exception as exc:  # 单源失败不阻断整体
        return {
            "src": src,
            "items": [],
            "error": f"{type(exc).__name__}: {exc}",
            "seconds": round(time.time() - t0, 2),
        }


def fetch_all(cfg: dict) -> list:
    workers = int(cfg["fetch"].get("workers", 5))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda s: fetch_one(s, cfg), cfg["feeds"]))


# ---------------------------------------------------------------- 存储层
SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id          TEXT PRIMARY KEY,     -- sha256(link)[:16]
    link        TEXT NOT NULL,
    title       TEXT NOT NULL,
    feed        TEXT NOT NULL,
    category    TEXT NOT NULL,
    published   TEXT,
    summary     TEXT,
    score       INTEGER,
    reason      TEXT,
    cn_summary  TEXT,
    first_seen  TEXT NOT NULL,
    digest_date TEXT
);
CREATE INDEX IF NOT EXISTS idx_digest ON items(digest_date);
"""


def open_db(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def item_id(link: str) -> str:
    return hashlib.sha256(link.strip().encode("utf-8")).hexdigest()[:16]


def known_ids(conn: sqlite3.Connection) -> set:
    return {row[0] for row in conn.execute("SELECT id FROM items")}


def save_items(conn: sqlite3.Connection, items: list):
    conn.executemany(
        """INSERT OR IGNORE INTO items
           (id, link, title, feed, category, published, summary, score, reason, cn_summary, first_seen, digest_date)
           VALUES (:id, :link, :title, :feed, :category, :published, :summary, :score, :reason, :cn_summary, :first_seen, :digest_date)""",
        [
            {
                **it,
                "score": it.get("score"),
                "reason": it.get("reason"),
                "cn_summary": it.get("cn_summary"),
                "digest_date": it.get("digest_date"),
            }
            for it in items
        ],
    )
    conn.commit()


# ---------------------------------------------------------------- 评分层
PROMPT = """你是我的个人资讯助理，目标是帮我拓展视野、促进个人成长。请为下面每条资讯打 1-10 分，并写一句中文摘要。
我的关注（尽量均衡，不要偏向单一领域）：科技与 AI、开源工具与效率提升、创意与艺术（AI 视频/设计/动画/影像）、经济与商业趋势、科学、人文与日常生活。
评分标准：
- 9-10：能改变认知、技能或视角的深度内容，或真正重要的发布/趋势
- 7-8：值得一读的新工具、新作品、新观点
- 5-6：一般性新闻，可略过
- 1-4：营销稿、重复报道、纯娱乐八卦、与我无关的琐事

只输出 JSON 数组，不要任何解释，格式：
[{"idx": 1, "score": 8, "summary": "中文摘要一句", "reason": "为什么值得看，8个字以内"}]

待评分条目：
{items}
"""


def llm_score(items: list, cfg: dict) -> list:
    llm = cfg["llm"]
    api_key = os.environ.get(llm.get("api_key_env", "DEEPSEEK_API_KEY"), "")
    if not api_key:
        raise RuntimeError(f"缺少环境变量 {llm.get('api_key_env')}，无法调用 DeepSeek")
    batch = int(llm.get("batch_size", 8))
    url = llm["base_url"].rstrip("/") + "/chat/completions"
    results = []
    for start in range(0, len(items), batch):
        chunk = items[start : start + batch]
        listing = "\n".join(
            f"{i + 1}. [来源:{it['category']}] {it['title']}\n   {it['summary'][:300]}"
            for i, it in enumerate(chunk)
        )
        payload = {
            "model": llm.get("model", "deepseek-chat"),
            "messages": [{"role": "user", "content": PROMPT.replace("{items}", listing)}],
            "temperature": llm.get("temperature", 0.3),
            "response_format": {"type": "json_object"},
        }
        resp = requests.post(
            url,
            json=payload,
            timeout=90,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = _extract_json(content)
        if not parsed:
            raise RuntimeError(f"模型返回无法解析: {content[:200]}")
        for i, it in enumerate(chunk):
            hit = next((p for p in parsed if p.get("idx") == i + 1), None)
            if hit:
                it["score"] = int(hit.get("score", 0))
                it["cn_summary"] = str(hit.get("summary", "")).strip()
                it["reason"] = str(hit.get("reason", "")).strip()
            else:
                it["score"] = 0
        results.extend(chunk)
    return results


def _extract_json(text: str):
    """从模型输出里取出第一段完整的 JSON 数组；兼容 {items:[...]} 与 markdown 代码块"""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.S)
    start = text.find("[")
    if start < 0:
        start = text.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
                if isinstance(data, dict):
                    data = data.get("items") or data.get("results") or []
                return data if isinstance(data, list) else None
    return None


def _title_tokens(title: str) -> set:
    stop = {
        "the",
        "a",
        "an",
        "of",
        "and",
        "to",
        "in",
        "on",
        "for",
        "with",
        "is",
        "are",
        "at",
        "by",
        "as",
        "its",
        "it",
        "this",
        "that",
        "from",
        "how",
        "why",
        "what",
        "new",
        "could",
        "may",
        "will",
        "can",
        "has",
        "have",
        "be",
        "we",
        "our",
    }
    return {w for w in re.findall(r"[a-z0-9]{2,}", (title or "").lower()) if w not in stop}


def dedupe_titles(items: list) -> list:
    """同一事件常被多个源报到；按标题词集相似度去掉近重复，保留分高/先出现的"""
    kept = []
    for it in sorted(items, key=lambda x: (-(x.get("score") or 0), x.get("published") or "")):
        toks = _title_tokens(it["title"])
        if any(
            toks
            and _title_tokens(k["title"])
            and len(toks & _title_tokens(k["title"])) / len(toks | _title_tokens(k["title"])) > 0.72
            for k in kept
        ):
            continue
        kept.append(it)
    return kept


def pick_balanced(items: list, cfg: dict) -> list:
    """先保 9 分以上；其余按类别轮转填充，避免单一类别占满整期"""
    max_items = int(cfg["digest"].get("max_items", 20))
    min_score = int(cfg["digest"].get("min_score", 7))
    pool = sorted(
        [c for c in items if (c.get("score") or 0) >= min_score],
        key=lambda x: (-(x["score"] or 0), x.get("published") or ""),
    )
    if not pool:
        return []
    buckets = {}
    for it in pool:
        buckets.setdefault(it["category"], []).append(it)
    picked, order = [], sorted(buckets, key=lambda c: -max(i["score"] for i in buckets[c]))
    # 高分段优先：先给每个类别 Top1，再 Top2 …
    round_no = 0
    while len(picked) < max_items and any(len(buckets[c]) > round_no for c in order):
        for c in order:
            if len(picked) >= max_items:
                break
            if len(buckets[c]) > round_no:
                picked.append(buckets[c][round_no])
        round_no += 1
    return dedupe_titles(picked)


# ---------------------------------------------------------------- 输出层
def render_digest(items: list, cfg: dict, date_str: str) -> str:
    title = f"{cfg['digest'].get('title', '每日简报')} · {date_str}"
    cats = []
    for it in items:
        if it["category"] not in cats:
            cats.append(it["category"])
    desc = f"{date_str} 每日简报：{len(items)} 条精选，覆盖{'、'.join(cats)}；关注个人成长与视野拓展。"[:120]
    lines = [DIGEST_HEADER.format(title=title, date=date_str, description=desc)]

    by_cat = {}
    for it in items:
        by_cat.setdefault(it["category"], []).append(it)
    order = [c for c in ("科技", "开源工具", "创意艺术", "经济商业", "科学", "生活文化") if c in by_cat] + [
        c for c in by_cat if c not in ("科技", "开源工具", "创意艺术", "经济商业", "科学", "生活文化")
    ]

    for cat in order:
        lines.append(f"## {cat}")
        lines.append("")
        for it in by_cat[cat]:
            lines.append(f"- [{it['title']}]({it['link']})")
            if it.get("cn_summary"):
                lines.append(f"  {it['cn_summary']} `{it['feed']} · {it['score']}/10`")
            else:
                lines.append(f"  `{it['feed']} · {it['score']}/10`")
            if it.get("reason"):
                lines.append(f"  > {it['reason']}")
        lines.append("")

    lines.append("---")
    lines.append(f"*由东京新闻雷达自动生成，共 {len(items)} 条。*")
    return "\n".join(lines)


def _digest_dates(pages_dir: Path) -> list:
    return sorted(
        (
            f.stem
            for f in pages_dir.glob("*.md")
            if f.stem != "index" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", f.stem)
        ),
        reverse=True,
    )


def write_digest(content: str, cfg: dict, out_dir: Path, date_str: str) -> Path:
    posts_dir = out_dir / cfg["output"].get("posts_dir", "source/news")
    posts_dir.mkdir(parents=True, exist_ok=True)
    dates = _digest_dates(posts_dir)

    # 上一期（更早）/ 下一期（更新）
    older = [d for d in dates if d < date_str]
    newer = [d for d in dates if d > date_str]
    nav = []
    if older:
        nav.append(f"[← 上一期 {older[0]}](/news/{older[0]}/)")
    if newer:
        nav.append(f"[下一期 {newer[-1]} →](/news/{newer[-1]}/)")
    if nav:
        content = content.rstrip() + "\n\n---\n\n" + " · ".join(nav) + "\n"

    path = posts_dir / f"{date_str}.md"
    path.write_text(content, encoding="utf-8")
    write_index(posts_dir)
    return path


def write_index(pages_dir: Path):
    """生成 /news/ 目录页：按月分组、日期倒序"""
    dates = _digest_dates(pages_dir)
    months = {}
    for d in dates:
        months.setdefault(d[:7], []).append(d)
    lines = [
        "---",
        "layout: page",
        "menu_id: news",
        "title: 每日简报",
        "description: 每天从外网精选的资讯合集",
        "---",
        "",
        "每天自动抓取、打分、翻译成中文的资讯合集，按月份和日期倒序排列。",
        "",
    ]
    for month in sorted(months, reverse=True):
        lines.append(f"## {month}")
        lines.append("")
        for d in months[month]:
            lines.append(f"- [{d}](/news/{d}/)")
        lines.append("")
    (pages_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser(description="东京新闻雷达")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--out-dir", default="out")
    ap.add_argument("--db", default="data/radar.db")
    ap.add_argument("--dry-run", action="store_true", help="跳过 DeepSeek 和数据库写入，用假数据出样报")
    ap.add_argument("--date", default=None, help="简报日期 YYYY-MM-DD，默认今天")
    args = ap.parse_args()

    cfg = load_config(args.config)
    now = datetime.now(TZ_CN)
    date_str = args.date or now.strftime("%Y-%m-%d")
    out_dir = Path(args.out_dir)
    conn = open_db(args.db)
    seen = known_ids(conn)
    max_age = now - timedelta(days=int(cfg["fetch"].get("max_age_days", 3)))

    print(f"[radar] {now:%Y-%m-%d %H:%M} 开始抓取 {len(cfg['feeds'])} 个源")
    results = fetch_all(cfg)
    candidates = []
    for res in results:
        status = "OK" if res["error"] is None else f"FAIL {res['error']}"
        print(f"  - {res['src']['name']:<28} {status:<6} {len(res['items']):>3} 条 {res['seconds']:>5.1f}s")
        for it in res["items"]:
            if not it["link"] or item_id(it["link"]) in seen:
                continue
            if it["published"]:
                try:
                    pub = datetime.fromisoformat(it["published"])
                    if pub < max_age:
                        continue
                except ValueError:
                    pass
            it.update(
                id=item_id(it["link"]),
                feed=res["src"]["name"],
                category=res["src"].get("category", "未分类"),
                first_seen=now.isoformat(timespec="seconds"),
            )
            candidates.append(it)

    print(f"[radar] 新条目 {len(candidates)} 条（已去重 {len(seen)} 条历史）")
    if not candidates:
        print("[radar] 没有新条目，退出")
        return 0

    min_score = int(cfg["digest"].get("min_score", 7))
    if args.dry_run:
        import random

        for it in candidates:
            it["score"] = random.randint(4, 10)
            it["cn_summary"] = f"（样报占位）{it['title'][:40]}"
            it["reason"] = "dry-run 未调用 DeepSeek"
        pool = candidates
    else:
        print(f"[radar] 调用 DeepSeek 打分 {len(candidates)} 条 …")
        scored = llm_score(candidates, cfg)
        save_items(conn, scored)
        # 当天已入选的 + 本次新打分的，并集重算，重跑不会把当日简报越跑越短
        rows = conn.execute(
            "SELECT * FROM items WHERE score IS NOT NULL AND score >= ? "
            "AND (digest_date = ? OR digest_date IS NULL)",
            (min_score, date_str),
        ).fetchall()
        pool = [dict(r) for r in rows]

    picked = pick_balanced(pool, cfg)
    if not picked:
        print(f"[radar] 没有条目达到 {min_score} 分")
        return 0

    for it in pool:
        if not it.get("digest_date"):
            conn.execute("UPDATE items SET digest_date=? WHERE id=?", (date_str, it["id"]))
    conn.commit()
    content = render_digest(picked, cfg, date_str)
    path = write_digest(content, cfg, out_dir, date_str)
    print(f"[radar] 简报写入 {path}（{len(picked)} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
