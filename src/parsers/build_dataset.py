"""
Пайплайн сборки финальных витрин data/processed/*.parquet.
ВЛАДЕЛЕЦ ФАЙЛА: Dev 1 (Data & Parsing)

Выход:
  data/processed/cities_features.parquet — города-кандидаты (Росстат + Росавиация)
  data/processed/routes_proof.parquet    — направления А → Б с пассажиропотоком, частотой
                                           и колонкой proof_source (+ копия routes_proof.csv)

Запуск: make parse  (python -m src.parsers.build_dataset)

Все числа, которых нет в data/raw/, вынесены в блок ДОПУЩЕНИЯ и попадают в proof_source
каждого маршрута. Это оценка по модели, а не измеренный пассажиропоток.
"""

from __future__ import annotations

import json
import math
import warnings
from pathlib import Path

import pandas as pd

from src.parsers.rosstat_loader import RAW_DIR, load_rosstat_and_rosaviatsia

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
CITIES_PATH = PROCESSED_DIR / "cities_features.parquet"
ROUTES_PATH = PROCESSED_DIR / "routes_proof.parquet"
SCHEDULES_CACHE = RAW_DIR / "schedules_raw.json"

HYPOTHESES = ("hub", "p2p")

# Координаты аэропортов (IATA). KUF, GOJ, UFA — из repoArchitecture.ts, PEE — из старого стаба;
# остальные — справочные значения, проверить по OurAirports/Википедии.
AIRPORT_COORDS = {
    "KUF": (53.50, 50.15),
    "GOJ": (56.23, 43.78),
    "UFA": (54.55, 55.87),
    "KZN": (55.61, 49.28),
    "SVX": (56.74, 60.80),
    "KRR": (45.03, 39.17),
    "KJA": (56.17, 92.49),
    "OVB": (55.01, 82.65),
    "OMS": (54.97, 73.31),
    "PEE": (57.91, 56.02),
    "CEK": (55.31, 61.51),
    "VOG": (48.78, 44.35),
}
MAX_ROUTES = 12                # config/settings.yaml: network.max_routes

# ---- ДОПУЩЕНИЯ МОДЕЛИ (не из источников; менять здесь и пересчитывать) ----
SEATS_PER_AIRCRAFT = 100       # config/settings.yaml: fleet.default_seats
LOAD_FACTOR = 0.84             # FinModelInput.load_factor_pct по умолчанию
DEPARTURE_SHARE = 0.50         # доля пассажиров аэропорта, вылетающих из него
CORE_SHARE = 0.10              # доля вылетающих, летящих в города этого набора
DISTANCE_EXPONENT = 1.0        # гравитация: спрос ∝ население_B / расстояние_AB^γ
RW_CAPTURE_BASE = 0.20         # доля рынка пары, которую забирает Red Wings (базовый сценарий)
MIN_ROUTES = 8                 # config/settings.yaml: network.min_routes
WEEKS_PER_YEAR = 52
EARTH_RADIUS_KM = 6371.0


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def build_cities_features() -> pd.DataFrame:
    """Таблица городов-кандидатов с источниками по каждой группе данных."""
    df = load_rosstat_and_rosaviatsia()

    no_coords = sorted(set(df["iata"]) - set(AIRPORT_COORDS))
    if no_coords:
        raise ValueError(f"Нет координат аэропортов в AIRPORT_COORDS: {no_coords}")

    return pd.DataFrame(
        {
            "iata": df["iata"],
            "city_name": df["city_name"],
            "region": df["region"],
            "population_mln": df["agglomeration_pop_mln"],
            "airport_pax_mln": df["airport_pax_2025_mln"],
            "main_competitor": df["main_competitor"],
            "competitor_share_pct": df["competitor_share_pct"],
            "lat": df["iata"].map(lambda c: AIRPORT_COORDS[c][0]),
            "lon": df["iata"].map(lambda c: AIRPORT_COORDS[c][1]),
            "src_population": df["src_population"],
            "src_airport_pax": df["src_airport_pax"],
        }
    )


def _load_competitor_flights() -> dict[tuple[str, str], int]:
    """
    Частоты прямых рейсов конкурентов из кэша парсера (data/raw/schedules_raw.json).
    Если кэша нет или он пуст — возвращает пустой словарь, значения не подставляются.
    """
    if not SCHEDULES_CACHE.exists():
        return {}
    try:
        records = json.loads(SCHEDULES_CACHE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {
        (r["origin_iata"], r["dest_iata"]): int(r["direct_competitor_flights_weekly"])
        for r in records
        if "direct_competitor_flights_weekly" in r
    }


def build_routes(cities: pd.DataFrame) -> pd.DataFrame:
    """
    Все направления А → Б между городами набора.

    Пассажиропоток (пар А→Б, в год, в одну сторону):
        рынок_AB = пасс_аэропорта_A × DEPARTURE_SHARE × CORE_SHARE × доля_B
        доля_B   = (население_B / расстояние_AB^γ) / Σ_j (население_j / расстояние_Aj^γ)
    Red Wings: pax = рынок_AB × RW_CAPTURE_BASE.
    Частота: freq = ceil(pax / 52 / (SEATS × LOAD_FACTOR)), минимум 1 рейс в неделю.
    """
    competitor_flights = _load_competitor_flights()
    rows: list[dict] = []

    for a in cities.itertuples(index=False):
        others = [b for b in cities.itertuples(index=False) if b.iata != a.iata]
        distance = {
            b.iata: _haversine_km((a.lat, a.lon), (b.lat, b.lon)) for b in others
        }
        gravity = {
            b.iata: b.population_mln / distance[b.iata] ** DISTANCE_EXPONENT for b in others
        }
        gravity_total = sum(gravity.values())
        departing_core_pool = a.airport_pax_mln * 1e6 * DEPARTURE_SHARE * CORE_SHARE

        for b in others:
            dest_share = gravity[b.iata] / gravity_total
            market_pax = departing_core_pool * dest_share
            pax = market_pax * RW_CAPTURE_BASE
            freq = max(1, math.ceil(pax / WEEKS_PER_YEAR / (SEATS_PER_AIRCRAFT * LOAD_FACTOR)))

            comp_key = (a.iata, b.iata)
            if comp_key in competitor_flights:
                comp_flights = competitor_flights[comp_key]
                comp_text = (
                    f"Конкуренты: {comp_flights} рейс(ов)/нед на паре по "
                    f"data/raw/schedules_raw.json."
                )
            else:
                comp_flights = None
                if pd.notna(a.competitor_share_pct):
                    airport_comp = (
                        f"В аэропорту {a.iata} доля конкурентов {a.competitor_share_pct:.0f}% "
                        f"({a.main_competitor}, data/raw/rosaviatsia_2025.csv)."
                    )
                else:
                    airport_comp = (
                        f"Доля конкурентов в аэропорту {a.iata} не найдена в открытых источниках."
                    )
                comp_text = (
                    f"Конкуренты на паре: НЕ ИЗМЕРЕНО (data/raw/schedules_raw.json пуст). "
                    f"{airport_comp}"
                )

            proof = (
                f"Пассажиропоток: аэропорт {a.iata} = {a.airport_pax_mln:.2f} млн пасс. в 2025 г. "
                f"(data/raw/rosaviatsia_2025.csv) × {DEPARTURE_SHARE:.0%} вылетающих × "
                f"{CORE_SHARE:.0%} в города набора (допущение) × гравитация на {b.iata}: "
                f"население {b.population_mln:.2f} млн (data/raw/rosstat_cities.csv), "
                f"расстояние {distance[b.iata]:.0f} км; доля {dest_share:.1%} → рынок "
                f"{market_pax:,.0f} пасс./год. Red Wings берёт {RW_CAPTURE_BASE:.0%} (допущение) "
                f"= {pax:,.0f} пасс./год. Частота: {pax / WEEKS_PER_YEAR:,.0f} пасс./нед ÷ "
                f"({SEATS_PER_AIRCRAFT} мест × {LOAD_FACTOR:.0%}) → {freq} рейс(ов)/нед. "
                f"{comp_text}"
            )

            rows.append(
                {
                    "origin": a.iata,
                    "dest": b.iata,
                    "origin_city": a.city_name,
                    "dest_city": b.city_name,
                    "lat_o": a.lat,
                    "lon_o": a.lon,
                    "lat_d": b.lat,
                    "lon_d": b.lon,
                    "distance_km": round(distance[b.iata], 1),
                    "market_pax_year": round(market_pax),
                    "pax": round(pax),
                    "freq": freq,
                    "competitor_share_origin_pct": a.competitor_share_pct,
                    "competitor_flights_weekly": comp_flights,
                    "proof_source": proof,
                }
            )

    return pd.DataFrame(rows)


def build_processed_tables() -> None:
    """Собирает cities_features.parquet и routes_proof.parquet (+ routes_proof.csv) в data/processed/."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    cities = build_cities_features()
    cities.to_parquet(CITIES_PATH, index=False)

    routes = build_routes(cities)
    routes.to_parquet(ROUTES_PATH, index=False)
    routes.to_csv(ROUTES_PATH.with_suffix(".csv"), index=False, encoding="utf-8-sig")

    print(f"Городов: {len(cities)} → {CITIES_PATH}")
    print(f"Направлений А→Б: {len(routes)} → {ROUTES_PATH}")


def get_network_routes(hypothesis: str, hub_iata: str = "KUF") -> pd.DataFrame:
    """
    Маршруты из data/processed/routes_proof.parquet для гипотезы.

    hypothesis="p2p": направления между городами набора (прямые региональные рейсы).
    hypothesis="hub": направления с хабом hub_iata (в обе стороны).
    Оба варианта обрезаются до MAX_ROUTES лучших по пассажиропотоку.
    В каждой строке есть proof_source: откуда взят пассажиропоток и частота конкурентов.
    """
    if hypothesis not in HYPOTHESES:
        raise ValueError(f"hypothesis должен быть одним из {HYPOTHESES}, получено {hypothesis!r}")

    if not ROUTES_PATH.exists():
        build_processed_tables()
    routes = pd.read_parquet(ROUTES_PATH)

    if hypothesis == "hub":
        if hub_iata not in set(routes["origin"]):
            raise ValueError(f"Хаб {hub_iata} отсутствует в данных: {sorted(set(routes['origin']))}")
        routes = routes[(routes["origin"] == hub_iata) | (routes["dest"] == hub_iata)]

    routes = routes.sort_values("pax", ascending=False).head(MAX_ROUTES).reset_index(drop=True)

    if len(routes) < MIN_ROUTES:
        warnings.warn(
            f"Гипотеза {hypothesis!r}: {len(routes)} маршрутов, минимум {MIN_ROUTES}. "
            f"Нужно больше городов в data/raw/rosstat_cities.csv и rosaviatsia_2025.csv.",
            stacklevel=2,
        )

    return routes


if __name__ == "__main__":
    build_processed_tables()
