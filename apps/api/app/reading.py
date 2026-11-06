from __future__ import annotations

import json
from typing import Any, Dict

import httpx

from .config import settings

SYSTEM_PROMPT = (
    "你是一位温柔、专业、不说教的占星解读师。请基于给定的星盘数据写一段中文解读，"
    "给读者情绪价值和具体感，而不是宿命论。结构：1) 一句话点出这张盘的气质；"
    "2) 性格与情绪模式；3) 关系与沟通；4) 成长与事业方向；5) 一句温柔的提醒。"
    "总字数 260~360 字，不要提“星盘数据”或“根据数据”，不要编造具体事件。"
)

SIGN_CN = {
    "Aries": "白羊",
    "Taurus": "金牛",
    "Gemini": "双子",
    "Cancer": "巨蟹",
    "Leo": "狮子",
    "Virgo": "处女",
    "Libra": "天秤",
    "Scorpio": "天蝎",
    "Sagittarius": "射手",
    "Capricorn": "摩羯",
    "Aquarius": "水瓶",
    "Pisces": "双鱼",
}
PLANET_CN = {
    "Sun": "太阳",
    "Moon": "月亮",
    "Mercury": "水星",
    "Venus": "金星",
    "Mars": "火星",
    "Jupiter": "木星",
    "Saturn": "土星",
    "Uranus": "天王星",
    "Neptune": "海王星",
    "Pluto": "冥王星",
    "TrueNode": "北交点",
}


def summarize(chart: Dict[str, Any]) -> str:
    planets = []
    for p in chart.get("planets", []):
        name = PLANET_CN.get(p["name"], p["name"])
        planets.append(f"{name}在{SIGN_CN.get(p['sign'], p['sign'])}{round(p['degree'])}度")
    houses = chart.get("houses", [])
    asc = houses[0] if houses else chart.get("ascendant", {})
    mc = chart.get("midheaven", {})
    aspects = []
    for a in chart.get("aspects", [])[:8]:
        aspects.append(f"{a['a']}与{a['b']}{a['type']}（容许度{a['orb']}°）")
    return (
        "星盘信息："
        + "；".join(planets)
        + f"。上升{SIGN_CN.get(asc.get('sign'), asc.get('sign'))}{round(asc.get('degree', 0))}度"
        + f"，天顶{SIGN_CN.get(mc.get('sign'), mc.get('sign'))}。"
        + "主要相位："
        + "、".join(aspects)
    )


async def generate_reading(chart: Dict[str, Any]) -> str:
    if not settings.deepseek_api_key:
        raise RuntimeError("DeepSeek key 未配置")
    url = settings.deepseek_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": summarize(chart)},
        ],
        "temperature": 0.8,
        "max_tokens": 700,
    }
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def chart_to_prompt(chart: Dict[str, Any]) -> str:
    return json.dumps(summarize(chart), ensure_ascii=False)
