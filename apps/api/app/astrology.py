from __future__ import annotations

from datetime import datetime

import swisseph as swe

SIGNS = [
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
]

PLANETS = [
    (swe.SUN, "Sun"),
    (swe.MOON, "Moon"),
    (swe.MERCURY, "Mercury"),
    (swe.VENUS, "Venus"),
    (swe.MARS, "Mars"),
    (swe.JUPITER, "Jupiter"),
    (swe.SATURN, "Saturn"),
    (swe.URANUS, "Uranus"),
    (swe.NEPTUNE, "Neptune"),
    (swe.PLUTO, "Pluto"),
    (swe.TRUE_NODE, "TrueNode"),
]

ASPECTS = [
    ("conjunction", 0, 8),
    ("opposition", 180, 8),
    ("trine", 120, 6),
    ("square", 90, 6),
    ("sextile", 60, 5),
]


def sign_of(longitude: float) -> dict:
    idx = int(longitude // 30) % 12
    return {"sign": SIGNS[idx], "degree": round(longitude % 30, 4)}


def _jd(dt_utc: datetime) -> float:
    return swe.julday(
        dt_utc.year,
        dt_utc.month,
        dt_utc.day,
        dt_utc.hour + dt_utc.minute / 60 + dt_utc.second / 3600,
    )


def planets_at(jd: float) -> list:
    planets = []
    for planet_id, name in PLANETS:
        pos, _ = swe.calc_ut(jd, planet_id, swe.FLG_SWIEPH | swe.FLG_SPEED)
        longitude_deg = pos[0]
        planets.append(
            {
                "name": name,
                "longitude": round(longitude_deg, 4),
                **sign_of(longitude_deg),
                "retrograde": pos[3] < 0,
            }
        )
    return planets


def _aspect(diff: float, orb: float):
    for name, angle, base_orb in ASPECTS:
        allow = max(orb, base_orb if orb >= 6 else orb)
        if abs(diff - angle) <= allow:
            return name, abs(diff - angle)
    return None, None


def cross_aspects(left: list, right: list, orb: float = 6.0) -> list:
    out = []
    for a in left:
        for b in right:
            if a is b:
                continue
            diff = abs(a["longitude"] - b["longitude"]) % 360
            diff = min(diff, 360 - diff)
            name, delta = _aspect(diff, orb)
            if name:
                out.append(
                    {
                        "a": a["name"],
                        "b": b["name"],
                        "type": name,
                        "orb": round(delta, 2),
                    }
                )
    return out


def compute_chart(dt_utc: datetime, latitude: float, longitude: float, house_system: str = "P") -> dict:
    jd = _jd(dt_utc)
    planets = planets_at(jd)

    cusps, ascmc = swe.houses(jd, latitude, longitude, house_system.encode())
    cusp_list = list(cusps)[-12:]
    houses = [{"house": i + 1, **sign_of(cusp_list[i])} for i in range(12)]

    aspects = cross_aspects(planets, planets, orb=6.0)
    return {
        "planets": planets,
        "houses": houses,
        "ascendant": sign_of(ascmc[0]),
        "midheaven": sign_of(ascmc[1]),
        "aspects": aspects,
    }


def compute_transits(natal: dict, when_utc: datetime) -> dict:
    jd = _jd(when_utc)
    transits = planets_at(jd)
    aspects = cross_aspects(transits, natal.get("planets", []), orb=3.0)
    harmonious = sum(1 for a in aspects if a["type"] in ("trine", "sextile"))
    challenging = sum(1 for a in aspects if a["type"] in ("square", "opposition"))
    return {
        "when": when_utc.isoformat(),
        "planets": transits,
        "aspects": aspects,
        "summary": f"{harmonious} 个和谐相位，{challenging} 个挑战相位",
    }


def compute_synastry(a: dict, b: dict) -> dict:
    aspects = cross_aspects(a.get("planets", []), b.get("planets", []), orb=6.0)
    harmonious = sum(1 for x in aspects if x["type"] in ("trine", "sextile"))
    challenging = sum(1 for x in aspects if x["type"] in ("square", "opposition"))
    score = max(0, min(100, 50 + 5 * (harmonious - challenging)))
    return {
        "aspects": aspects,
        "score": score,
        "counts": {"harmonious": harmonious, "challenging": challenging, "total": len(aspects)},
        "summary": f"和谐 {harmonious} 个，挑战 {challenging} 个",
    }
