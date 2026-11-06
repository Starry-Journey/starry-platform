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


def compute_chart(dt_utc: datetime, latitude: float, longitude: float, house_system: str = "P") -> dict:
    jd = swe.julday(
        dt_utc.year,
        dt_utc.month,
        dt_utc.day,
        dt_utc.hour + dt_utc.minute / 60 + dt_utc.second / 3600,
    )

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

    cusps, ascmc = swe.houses(jd, latitude, longitude, house_system.encode())
    # pyswisseph 不同版本 cusps 可能是 12 或 13 个元素，统一取最后 12 个
    cusp_list = list(cusps)[-12:]
    houses = [{"house": i + 1, **sign_of(cusp_list[i])} for i in range(12)]

    aspects = []
    for i in range(len(planets)):
        for j in range(i + 1, len(planets)):
            a, b = planets[i], planets[j]
            diff = abs(a["longitude"] - b["longitude"]) % 360
            diff = min(diff, 360 - diff)
            for name, angle, orb in ASPECTS:
                if abs(diff - angle) <= orb:
                    aspects.append(
                        {
                            "a": a["name"],
                            "b": b["name"],
                            "type": name,
                            "orb": round(abs(diff - angle), 2),
                        }
                    )
                    break

    return {
        "planets": planets,
        "houses": houses,
        "ascendant": sign_of(ascmc[0]),
        "midheaven": sign_of(ascmc[1]),
        "aspects": aspects,
    }
