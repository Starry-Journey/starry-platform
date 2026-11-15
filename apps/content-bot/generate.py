#!/usr/bin/env python3
"""每日文章生成器：主题轮换 + DeepSeek 起草 + 星空封面 SVG。

默认只写到 --out 目录，不碰博客仓库；确认后再复制/发布。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import random
import re
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

THEMES = [
    ("宇宙", "从一次抬头看星星、某个天文现象或宇宙尺度出发，写一点对日常的联想。"),
    ("技术", "从一个小的技术变化/工具/开源项目出发，写它如何影响普通人的生活。"),
    ("阅读", "从最近读到的一段文字、一本书或一个观点出发，写自己的理解。"),
    ("城市", "从通勤、街角、天气或城市里的一件小事出发，写观察。"),
    ("日常", "从做饭、整理房间、散步、睡眠等日常细节出发，写感受。"),
    ("艺术", "从一张图、一段音乐、一部动画或一个设计出发，写审美体验。"),
]

SYSTEM = (
    "你是一位克制、真诚的中文随笔作者。写 600~900 字，不要鸡汤，不要标题党，"
    "不要分点，不要小标题，不要出现“在这个快节奏的时代”这类套话。"
    "从具体细节切入，允许留白。只输出 JSON："
    '{"title": "不超过 20 字", "description": "60~90 字摘要", "body": "正文，段落用 \\n\\n 分隔"}'
)


def pick_theme(date: dt.date):
    idx = date.toordinal() % len(THEMES)
    return THEMES[idx]


def deepseek(theme_name: str, theme_prompt: str, date: dt.date) -> dict:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise SystemExit("缺少 DEEPSEEK_API_KEY")
    base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    user = f"今天是 {date.isoformat()}，主题是「{theme_name}」。{theme_prompt}请写一篇适合个人博客的随笔。"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
        "temperature": 0.9,
        "max_tokens": 1800,
    }
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.load(resp)
    text = data["choices"][0]["message"]["content"].strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 兜底：把整段当正文
        data = {"title": f"{theme_name}·{date.month}月{date.day}日", "description": "", "body": text}
    data["title"] = str(data.get("title", "")).strip()[:30] or f"{theme_name}·{date}"
    data["description"] = str(data.get("description", "")).strip()[:120]
    data["body"] = str(data.get("body", "")).strip()
    return data


def wrap_title(title: str, width: int = 12):
    lines = []
    while title:
        lines.append(title[:width])
        title = title[width:]
    return lines[:2]


def cover_svg(title: str, tag: str, date: dt.date) -> str:
    seed = int(hashlib.sha256(date.isoformat().encode()).hexdigest()[:8], 16)
    rnd = random.Random(seed)
    stars = []
    for _ in range(90):
        x, y = rnd.randint(40, 1160), rnd.randint(30, 420)
        r = rnd.choice([0.8, 1, 1.2, 1.6])
        o = rnd.choice([0.4, 0.6, 0.8])
        stars.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#dfe6ff" opacity="{o}"/>')
    points = [(rnd.randint(80, 1120), rnd.randint(60, 380)) for _ in range(6)]
    lines = "".join(
        f'<line x1="{points[i][0]}" y1="{points[i][1]}" x2="{points[i + 1][0]}" y2="{points[i + 1][1]}" '
        'stroke="#8f7cff" stroke-width="1" opacity="0.35"/>'
        for i in range(len(points) - 1)
    )
    title_lines = wrap_title(title)
    title_tspans = "".join(
        f'<tspan x="80" dy="{0 if i == 0 else 64}">{escape(line)}</tspan>'
        for i, line in enumerate(title_lines)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0b1024"/>
      <stop offset="0.55" stop-color="#070b18"/>
      <stop offset="1" stop-color="#1a0f2e"/>
    </linearGradient>
    <radialGradient id="glow" cx="50%" cy="35%" r="60%">
      <stop offset="0" stop-color="#8f7cff" stop-opacity="0.18"/>
      <stop offset="1" stop-color="#8f7cff" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="1200" height="630" fill="url(#bg)"/>
  <rect width="1200" height="630" fill="url(#glow)"/>
  <g>{"".join(stars)}</g>
  <g>{lines}</g>
  <text x="80" y="470" fill="#eef2ff" font-family="'Noto Sans SC','PingFang SC',sans-serif"
        font-size="56" font-weight="600">{title_tspans}</text>
  <text x="80" y="560" fill="#9aa6cc" font-family="ui-monospace,monospace" font-size="22">
    {escape(tag)} · {date.isoformat()} · Starry Journey
  </text>
</svg>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--out", default="/tmp/content-bot")
    ap.add_argument("--dry-run", action="store_true", help="只生成到 out 目录")
    args = ap.parse_args()
    date = dt.date.fromisoformat(args.date)
    tag, prompt = pick_theme(date)
    data = deepseek(tag, prompt, date)

    out = Path(args.out)
    posts = out / "source/_posts"
    covers = out / "source/images/covers"
    posts.mkdir(parents=True, exist_ok=True)
    covers.mkdir(parents=True, exist_ok=True)

    slug = f"{date.isoformat()}-daily"
    post_path = posts / f"{slug}.md"
    cover_name = f"{slug}.svg"
    cover_path = covers / cover_name
    cover_path.write_text(cover_svg(data["title"], tag, date), encoding="utf-8")

    front = (
        "---\n"
        f"title: {data['title']}\n"
        f"date: {date.isoformat()} 07:30:00\n"
        f"tags: [{tag}, 每日随笔]\n"
        "categories: [日常]\n"
        f"description: {data['description']}\n"
        f"cover: /images/covers/{cover_name}\n"
        "---\n\n"
    )
    post_path.write_text(front + data["body"] + "\n", encoding="utf-8")
    print(post_path)
    print(cover_path)


if __name__ == "__main__":
    main()
