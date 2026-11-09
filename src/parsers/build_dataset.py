"""
Пайплайн сборки витрин data/processed/*.parquet по ТЗ Dev 1.
ВЛАДЕЛЕЦ ФАЙЛА: Dev 1 (Data & Parsing)

Выход:
  data/processed/cities_features.parquet — 12 городов ТЗ (см. rosstat_loader.py)
  data/processed/routes_proof.parquet    — все пары А→Б с расчётами и proof_source (+ .csv)

get_network_routes(hypothesis, hub_iata) возвращает 10–12 маршрутов с колонками из ТЗ.

Запуск: make parse  (python -m src.parsers.build_dataset)

Допущения вынесены в блок ДОПУЩЕНИЯ и указаны в proof_source каждого маршрута.
"""

from __future__ import annotations

import math
import warnings
from pathlib import Path

import pandas as pd

from src.parsers.rosstat_loader import (
    MOSCOW_HUB,
    TZ_CITIES,
    AIRPORT_COORDS,
    haversine_km,
    load_rosstat_and_rosaviatsia,
)
from src.parsers.schedule_scraper import load_schedules

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
CITIES_PATH = PROCESSED_DIR / "cities_features.parquet"
ROUTES_PATH = PROCESSED_DIR / "routes_proof.parquet"

HYPOTHESES = ("hub", "p2p")
MAX_ROUTES = 12                # ТЗ: 10–12 маршрутов
MIN_ROUTES = 10                # ТЗ: минимум 10

# ---- ДОПУЩЕНИЯ (не из источников; менять здесь и пересчитывать) ----
SEATS_PER_AIRCRAFT = 100       # config/settings.yaml: fleet.default_seats (SJ-100)
LOAD_FACTOR = 0.84             # FinModelInput.load_factor_pct по умолчанию
DEPARTURE_SHARE = 0.50         # доля пассажиров аэропорта, вылетающих из него
CORE_SHARE = 0.10              # доля вылетающих, летящих в города набора
DISTANCE_EXPONENT = 1.0        # гравитация: спрос ∝ население_B / расстояние_AB^γ
RW_CAPTURE_BASE = 0.20         # доля рынка пары, которую забирает Red Wings (базовый сценарий)
BLOCK_SPEED_KMH = 650.0        # средняя блочная скорость SJ-100 (допущение)
TAXI_OVERHEAD_MIN = 20         # рулёжка, взлёт, заход на посадку (допущение)
WEEKS_PER_YEAR = 52
FARE_FALLBACK = "медиана тарифов конкурентов по всем парам (нет тарифа на этой паре)"

# Субсидируемые маршруты из Екатеринбурга на 2026 (Росавиация; 30 рейсов из Кольцово).
# Полный федеральный перечень (305 направлений) не получен: для остальных пар статус не проверен.
SUBSIDY_SOURCE = "Росавиация, перечень 2026 (Сигнал Урал, 26.11.2025): https://signalural.ru/news/10457"
SUBSIDY_2026_FROM_SVX = {"GOJ", "OMS", "VOG", "GSV"}  # из 12 городов ТЗ


def build_cities_features() -> pd.DataFrame:
    return load_rosstat_and_rosaviatsia()


def _pair_competitor_info() -> dict[tuple[str, str], dict]:
    """
    По каждой паре: рейсы конкурентов (без Red Wings), рейсы Red Wings, тарифы.
    Пары, которых нет в schedules_raw.json, в результат не попадают.
    """
    df = load_schedules()
    info: dict[tuple[str, str], dict] = {}
    for (origin, dest), g in df.groupby(["origin_iata", "dest_iata"]):
        comp = g[~g["own_operator"]]
        own = g[g["own_operator"]]
        carriers = []
        for r in comp.itertuples():
            if r.weekly_flights <= 0:
                continue
            text = f"{r.carrier} {r.weekly_flights}/нед"
            if pd.notna(r.min_fare_rub):
                text += f", от {int(r.min_fare_rub)} ₽"
            carriers.append(text)
        fares = [float(x) for x in comp["min_fare_rub"].dropna()]
        info[(origin, dest)] = {
            "competitor_weekly": int(comp["weekly_flights"].sum()),
            "own_weekly": int(own["weekly_flights"].sum()),
            "carriers": "; ".join(carriers) if carriers else "прямых рейсов не найдено",
            "fares": fares,
            "sources": ", ".join(sorted(set(g["source"]))),
        }
    return info


def _launch_quarter(own_weekly: int, competitor_weekly: int) -> str:
    """Предложение по срокам запуска (правило, не прогноз):
    уже летает Red Wings → Q3 2026; есть конкуренты → Q2 2027; конкурентов нет → Q1 2028."""
    if own_weekly > 0:
        return "Q3 2026"
    if competitor_weekly > 0:
        return "Q2 2027"
    return "Q1 2028"


def build_routes(cities: pd.DataFrame) -> pd.DataFrame:
    """
    Все пары А→Б между 12 городами ТЗ.

    Пассажиропоток (пар А→Б, в год, в одну сторону):
        рынок_AB = пасс_аэропорта_A × DEPARTURE_SHARE × CORE_SHARE × доля_B
        доля_B   = (население_B / расстояние_AB^γ) / Σ_j (население_j / расстояние_Aj^γ)
    Red Wings: pax = рынок_AB × RW_CAPTURE_BASE; freq = ceil(pax / 52 / (SEATS × LF)), минимум 1.
    """
    info = _pair_competitor_info()
    all_fares = [f for v in info.values() for f in v["fares"]]
    fare_fallback = float(pd.Series(all_fares).median()) if all_fares else float("nan")

    rows: list[dict] = []
    for a in cities.itertuples(index=False):
        others = [b for b in cities.itertuples(index=False) if b.iata != a.iata]
        dist = {b.iata: haversine_km((a.lat, a.lon), (b.lat, b.lon)) for b in others}
        gravity = {b.iata: b.population_mln / dist[b.iata] ** DISTANCE_EXPONENT for b in others}
        gravity_total = sum(gravity.values())
        pool = a.airport_pax_mln * 1e6 * DEPARTURE_SHARE * CORE_SHARE

        for b in others:
            share = gravity[b.iata] / gravity_total
            market = pool * share
            pax = market * RW_CAPTURE_BASE
            freq = max(1, math.ceil(pax / WEEKS_PER_YEAR / (SEATS_PER_AIRCRAFT * LOAD_FACTOR)))
            d_km = dist[b.iata]
            flight_min = round(d_km / BLOCK_SPEED_KMH * 60 + TAXI_OVERHEAD_MIN)
            detour = (
                haversine_km((a.lat, a.lon), MOSCOW_HUB) + haversine_km(MOSCOW_HUB, (b.lat, b.lon))
            ) / d_km

            pi = info.get((a.iata, b.iata))
            if pi is None:
                comp_weekly = None
                own_weekly = None
                carriers = "НЕ ИЗМЕРЕНО"
                fare = None
                fare_src = "нет данных"
                proof_comp = "Конкуренты на паре: НЕ ИЗМЕРЕНО (пары нет в schedules_raw.json)."
            else:
                comp_weekly = pi["competitor_weekly"]
                own_weekly = pi["own_weekly"]
                carriers = pi["carriers"]
                if pi["fares"]:
                    fare = sum(pi["fares"]) / len(pi["fares"])
                    fare_src = "среднее min-тарифов конкурентов на паре (" + pi["sources"] + ")"
                else:
                    fare = fare_fallback
                    fare_src = FARE_FALLBACK
                proof_comp = (
                    f"Конкуренты на паре: {comp_weekly} прямых рейс(ов)/нед ({carriers}) "
                    f"по {pi['sources']} (неделя 09–15.11.2026)."
                )
                if own_weekly:
                    proof_comp += f" Red Wings уже выполняет {own_weekly} рейс(ов)/нед на этой паре."

            proof = (
                f"Пассажиропоток: аэропорт {a.iata} = {a.airport_pax_mln:.3f} млн пасс. в 2025 г. "
                f"(data/raw/rosaviatsia_2025.csv) × {DEPARTURE_SHARE:.0%} вылетающих × "
                f"{CORE_SHARE:.0%} в города набора (допущение) × гравитация на {b.iata}: "
                f"население {b.population_mln:.3f} млн (data/raw/rosstat_cities.csv), "
                f"расстояние {d_km:.0f} км; доля {share:.1%} → рынок {market:,.0f} пасс./год. "
                f"Red Wings берёт {RW_CAPTURE_BASE:.0%} (допущение) = {pax:,.0f} пасс./год. "
                f"Частота: {pax / WEEKS_PER_YEAR:,.0f} пасс./нед ÷ ({SEATS_PER_AIRCRAFT} мест × "
                f"{LOAD_FACTOR:.0%}) → {freq} рейс(ов)/нед. "
                f"{proof_comp} "
                f"Доля конкурентов в аэропорту {a.iata}: "
                + (
                    f"{a.competitor_share_pct:.0f}% ({a.main_competitor}, data/raw/rosaviatsia_2025.csv)."
                    if pd.notna(a.competitor_share_pct)
                    else "не найдена в открытых источниках."
                )
            )

            if "SVX" in (a.iata, b.iata):
                other = b.iata if a.iata == "SVX" else a.iata
                if other in SUBSIDY_2026_FROM_SVX:
                    sub_flag = True
                    sub_check = (f"да: маршрут из Екатеринбурга в перечне 2026 ({SUBSIDY_SOURCE}); "
                                 f"обратное направление — допущение")
                else:
                    sub_flag = False
                    sub_check = f"нет в перечне 2026 для Екатеринбурга ({SUBSIDY_SOURCE})"
            else:
                sub_flag = False
                sub_check = ("не проверено: полный перечень 2026 (305 направлений) не получен; "
                             "известен только список маршрутов из Екатеринбурга")

            rows.append({
                "origin_iata": a.iata,
                "origin_city": a.city_name,
                "dest_iata": b.iata,
                "dest_city": b.city_name,
                "lat_o": a.lat,
                "lon_o": a.lon,
                "lat_d": b.lat,
                "lon_d": b.lon,
                "distance_km": int(round(d_km)),
                "flight_time_min": int(flight_min),
                "competitor_flights_weekly": comp_weekly,
                "own_flights_weekly": own_weekly,
                "competitor_carriers": carriers,
                "competitor_fare_rub": None if fare is None or pd.isna(fare) else int(round(fare)),
                "fare_source": fare_src,
                "subsidy_eligible": sub_flag,
                "subsidy_check": sub_check,
                "launch_quarter": _launch_quarter(own_weekly or 0, comp_weekly or 0),
                "moscow_detour_ratio": round(detour, 2),
                "market_pax_year": int(round(market)),
                "pax": int(round(pax)),
                "freq": int(freq),
                "competitor_share_origin_pct": a.competitor_share_pct,
                "proof_source": proof,
            })

    df = pd.DataFrame(rows)
    int_cols = ["competitor_flights_weekly", "own_flights_weekly", "competitor_fare_rub"]
    for c in int_cols:
        df[c] = df[c].astype("Int64")
    df["subsidy_eligible"] = df["subsidy_eligible"].astype(bool)
    return df


def build_processed_tables() -> None:
    """Собирает cities_features.parquet и routes_proof.parquet (+ routes_proof.csv)."""
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
    Маршруты гипотезы для Dev 2–4 (колонки по ТЗ, 10–12 строк, отсортированы по pax).

    hypothesis="p2p": направления между городами ТЗ (прямые региональные рейсы).
    hypothesis="hub": направления с хабом hub_iata в обе стороны.
    """
    if hypothesis not in HYPOTHESES:
        raise ValueError(f"hypothesis должен быть одним из {HYPOTHESES}, получено {hypothesis!r}")

    if not ROUTES_PATH.exists():
        build_processed_tables()
    routes = pd.read_parquet(ROUTES_PATH)

    if hypothesis == "hub":
        if hub_iata not in TZ_CITIES:
            raise ValueError(f"Хаб {hub_iata} не входит в 12 городов ТЗ: {TZ_CITIES}")
        routes = routes[(routes["origin_iata"] == hub_iata) | (routes["dest_iata"] == hub_iata)]

    routes = routes.sort_values("pax", ascending=False).head(MAX_ROUTES).reset_index(drop=True)

    tag = "HUB" if hypothesis == "hub" else "P2P"
    routes.insert(0, "route_code", [
        f"RW-{tag}-{o}-{d}" for o, d in zip(routes["origin_iata"], routes["dest_iata"])
    ])

    if len(routes) < MIN_ROUTES:
        warnings.warn(
            f"Гипотеза {hypothesis!r}: {len(routes)} маршрутов, минимум {MIN_ROUTES} по ТЗ.",
            stacklevel=2,
        )
    return routes


if __name__ == "__main__":
    build_processed_tables()
