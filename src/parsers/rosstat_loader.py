"""
Загрузчик данных: города-кандидаты (Росстат, Росавиация, расписания конкурентов).
ВЛАДЕЛЕЦ ФАЙЛА: Dev 1 (Data & Parsing)

load_rosstat_and_rosaviatsia() возвращает ровно 12 городов из ТЗ с колонками ТЗ:
iata, city_name, region, lat, lon, population_mln, airport_pax_mln, dist_to_mow_km,
competitor_gap_score, tourism_demand_score, main_competitor (+ служебные колонки с источниками).
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

# Координаты аэропортов (IATA), градусы. Все 12 сверены по Википедии (ru).
AIRPORT_COORDS = {
    "KUF": (53.502, 50.155),   # Курумоч
    "GOJ": (56.230, 43.787),   # Стригино
    "UFA": (54.551, 55.868),   # Уфа
    "KZN": (55.608, 49.278),   # Казань
    "MRV": (44.225, 43.083),   # Минеральные Воды
    "PEE": (57.918, 56.022),   # Большое Савино
    "SVX": (56.741, 60.804),   # Кольцово
    "CEK": (55.305, 61.505),   # Челябинск (Баландино)
    "TJM": (57.183, 65.344),   # Рощино
    "VOG": (48.787, 44.350),   # Гумрак
    "GSV": (51.713, 46.169),   # Гагарин
    "OMS": (54.967, 73.317),   # Омск-Центральный
}

# Москва (центр города) — для dist_to_mow_km и индекса крюка через Москву
MOSCOW_HUB = (55.7558, 37.6173)
EARTH_RADIUS_KM = 6371.0

COMPETITOR_SOURCE = (
    "доля вылетов главного перевозчика среди всех вылетов аэропорта за 10–15.11.2026 "
    "(табло Яндекс.Расписаний, data/raw/rosaviatsia_2025.csv)"
)


def haversine_km(a: tuple, b: tuple) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def _min_max(series: pd.Series) -> pd.Series:
    """Шкала 0..100. Если все значения равны — 50."""
    lo, hi = series.min(), series.max()
    if hi <= lo:
        return pd.Series(50.0, index=series.index)
    return ((series - lo) / (hi - lo) * 100.0).round(2)


def load_rosstat_and_rosaviatsia(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """
    12 городов-кандидатов из ТЗ.

    competitor_gap_score = 100 − доля главного конкурента, % (формула ТЗ).
    tourism_demand_score = среднее двух шкал 0..100: средняя зарплата по субъекту (ПСП, Росстат)
        и авиаподвижность (пассажиропоток аэропорта / население агломерации).
    """
    cities = pd.read_csv(raw_dir / ROSSTAT_FILE, dtype={"iata": str})
    airports = pd.read_csv(raw_dir / ROSAVIATSIA_FILE, dtype={"iata": str})

    df = cities.merge(airports, on="iata", how="left", validate="one_to_one",
                      suffixes=("_rosstat", "_rosaviatsia"))

    if set(df["iata"]) != set(TZ_CITIES) or len(df) != len(TZ_CITIES):
        raise ValueError(
            f"Ожидались ровно 12 городов из ТЗ {TZ_CITIES}, получено {sorted(df['iata'])}"
        )
    if df["airport_pax_2025_mln"].isna().any():
        raise ValueError("Нет данных по пассажиропотоку аэропорта для части городов")

    df["lat"] = df["iata"].map(lambda c: AIRPORT_COORDS[str(c)][0])
    df["lon"] = df["iata"].map(lambda c: AIRPORT_COORDS[str(c)][1])
    df["dist_to_mow_km"] = [
        int(round(haversine_km(AIRPORT_COORDS[str(c)], MOSCOW_HUB))) for c in df["iata"]
    ]

    missing = df.loc[df["main_competitor"].isna() | df["competitor_share_pct"].isna(), "iata"].tolist()
    if missing:
        raise ValueError(f"Нет main_competitor/competitor_share_pct в {ROSAVIATSIA_FILE}: {missing}")
    df["competitor_share_pct"] = df["competitor_share_pct"].astype(float)
    df["main_competitor"] = [
        f"{name} ({share:.0f}%)" for name, share in zip(df["main_competitor"], df["competitor_share_pct"])
    ]
    df["competitor_gap_score"] = (100.0 - df["competitor_share_pct"]).round(2)
    df["competitor_share_source"] = COMPETITOR_SOURCE

    mobility = df["airport_pax_2025_mln"] / df["population_mln"]
    df["tourism_demand_score"] = ((_min_max(df["avg_wage_rub_region"]) + _min_max(mobility)) / 2).round(2)

    df["src_population"] = f"data/raw/{ROSSTAT_FILE} (agglomeration_members, source_rosstat)"
    df["src_airport_pax"] = f"data/raw/{ROSAVIATSIA_FILE} (source_rosaviatsia)"

    df = df.rename(columns={"airport_pax_2025_mln": "airport_pax_mln"})
    return df.sort_values("iata").reset_index(drop=True)
