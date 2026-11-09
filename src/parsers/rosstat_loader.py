"""
Загрузчик данных: города-кандидаты (Росстат, Росавиация, расписания конкурентов).
ВЛАДЕЛЕЦ ФАЙЛА: Dev 1 (Data & Parsing)

load_rosstat_and_rosaviatsia() возвращает ровно 12 региональных городов из ТЗ.
Колонка population_mln — население агломерации (городской округ + пригородные
муниципалитеты из agglomeration_members), как требует ТЗ. population_city_mln — только город.
"""

import math
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

ROSSTAT_FILE = "rosstat_cities.csv"
ROSAVIATSIA_FILE = "rosaviatsia_2025.csv"

# Состав кандидатов по ТЗ (порядок и коды не менять)
TZ_CITIES = ["KUF", "GOJ", "UFA", "KZN", "MRV", "PEE", "SVX", "CEK", "TJM", "VOG", "GSV", "OMS"]

# Координаты аэропортов (IATA), градусы. Все 12 сверены по Википедии (ru),
# градусы-минуты-секунды переведены в десятичные.
AIRPORT_COORDS = {
    "KUF": (53.502, 50.155),   # Курумоч
    "GOJ": (56.230, 43.787),   # Стригино
    "UFA": (54.551, 55.868),   # Уфа
    "KZN": (55.608, 49.278),   # Казань
    "MRV": (44.225, 43.083),   # Минеральные Воды
    "PEE": (57.918, 56.022),   # Большое Савино
    "SVX": (56.741, 60.804),   # Кольцово
    "CEK": (55.305, 61.505),   # Челябинск (Баландино/Курчатов)
    "TJM": (57.183, 65.344),   # Рощино
    "VOG": (48.787, 44.350),   # Гумрак
    "GSV": (51.713, 46.169),   # Гагарин
    "OMS": (54.967, 73.317),   # Омск-Центральный
}

# Шереметьево (SVO) — ориентир для индекса крюка через Москву и расстояния до МАУ
MOSCOW_HUB = (55.9726, 37.4146)
EARTH_RADIUS_KM = 6371.0


def haversine_km(a: tuple, b: tuple) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def _min_max(series: pd.Series, invert: bool = False) -> pd.Series:
    """Шкала 0..100. Если все значения равны — 50."""
    lo, hi = series.min(), series.max()
    if hi <= lo:
        return pd.Series(50.0, index=series.index)
    scaled = (series - lo) / (hi - lo) * 100.0
    return (100.0 - scaled if invert else scaled).round(2)


def load_rosstat_and_rosaviatsia(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """
    12 городов-кандидатов из ТЗ.

    competitor_gap_score: чем меньше прямых рейсов конкурентов выходит из города, тем выше балл
        (0..100), по данным data/raw/schedules_raw.json.
    tourism_demand_score: ПРОКСИ — нормированный пассажиропоток аэропорта 2025. Данных о
        турпотоке по городам в открытых источниках не нашлось.
    """
    from src.parsers.schedule_scraper import load_schedules

    cities = pd.read_csv(raw_dir / ROSSTAT_FILE, dtype={"iata": str})
    airports = pd.read_csv(raw_dir / ROSAVIATSIA_FILE, dtype={"iata": str})

    df = cities.merge(airports, on="iata", how="left", validate="one_to_one")

    if set(df["iata"]) != set(TZ_CITIES) or len(df) != len(TZ_CITIES):
        raise ValueError(
            f"Ожидались ровно 12 городов из ТЗ {TZ_CITIES}, получено {sorted(df['iata'])}"
        )
    if df["airport_pax_2025_mln"].isna().any():
        raise ValueError("Нет данных Росавиации по пассажиропотоку для части городов")

    df["lat"] = df["iata"].map(lambda c: AIRPORT_COORDS[c][0])
    df["lon"] = df["iata"].map(lambda c: AIRPORT_COORDS[c][1])
    df["dist_to_mow_km"] = [
        round(haversine_km(AIRPORT_COORDS[c], MOSCOW_HUB)) for c in df["iata"]
    ]

    # Исходящие прямые рейсы конкурентов из каждого города (сумма по всем парам из города)
    sched = load_schedules()
    comp_out = sched[~sched["own_operator"]].groupby("origin_iata")["weekly_flights"].sum()
    outbound = df["iata"].map(comp_out).fillna(0).astype(float)
    df["competitor_flights_out_weekly"] = outbound.astype(int)
    df["competitor_gap_score"] = _min_max(outbound, invert=True)

    df["tourism_demand_score"] = _min_max(df["airport_pax_2025_mln"])

    df["src_population"] = f"data/raw/{ROSSTAT_FILE} (agglomeration_members, см. source)"
    df["src_airport_pax"] = f"data/raw/{ROSAVIATSIA_FILE} (пассажиропоток аэропорта 2025, см. source)"
    df["src_competitors"] = "data/raw/schedules_raw.json (рейсы конкурентов, неделя 09–15.11.2026)"

    # Доля конкурентов: если нет данных Росавиации по пассажирам — оценка по расписаниям
    flight_share = _origin_flight_share(sched)
    has_rosaviatsia = df["competitor_share_pct"].notna()
    df["competitor_share_source"] = [
        "Росавиация 2025 (доля пассажиров)" if h
        else "оценка: доля рейсов конкурентов в расписании 09–15.11.2026 (не доля пассажиров)"
        for h in has_rosaviatsia
    ]
    df["competitor_share_pct"] = [
        s if h else flight_share[i]
        for s, h, i in zip(df["competitor_share_pct"], has_rosaviatsia, df["iata"])
    ]
    df["main_competitor"] = df["main_competitor"].fillna("нет данных Росавиации (оценка по расписаниям)")

    df = df.rename(columns={"airport_pax_2025_mln": "airport_pax_mln"})
    return df.sort_values("iata").reset_index(drop=True)


def _origin_flight_share(sched: pd.DataFrame) -> dict:
    """Доля рейсов конкурентов от всех прямых рейсов (конкуренты + Red Wings) из аэропорта, %."""
    comp = sched[~sched["own_operator"]].groupby("origin_iata")["weekly_flights"].sum()
    own = sched[sched["own_operator"]].groupby("origin_iata")["weekly_flights"].sum()
    total = comp.add(own, fill_value=0)
    return {
        o: round(100.0 * comp.get(o, 0) / total[o], 1) for o in total.index if total[o] > 0
    }
