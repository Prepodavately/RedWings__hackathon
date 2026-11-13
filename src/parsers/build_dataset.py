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

import numpy as np
import pandas as pd

from src.parsers.rosstat_loader import (
    MOSCOW_HUB,
    TZ_CITIES,
    AIRPORT_COORDS,
    haversine_km,
    load_rosstat_and_rosaviatsia,
)
from src.parsers.schedule_scraper import fetch_competitor_routes

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
CITIES_PATH = PROCESSED_DIR / "cities_features.parquet"
ROUTES_PATH = PROCESSED_DIR / "routes_proof.parquet"

HYPOTHESES = ("hub", "p2p")

# ТЗ, «Важная деталь для get_network_routes»: прямые межрегиональные пары для hypothesis="p2p"
P2P_PAIRS = [
    ("KUF", "GOJ"), ("KUF", "PEE"), ("GOJ", "UFA"), ("GOJ", "MRV"), ("UFA", "VOG"),
    ("KUF", "CEK"), ("UFA", "OMS"), ("GOJ", "SVX"), ("KZN", "CEK"), ("GSV", "SVX"),
]
HUB_RAYS = 10  # ТЗ: веер из хаба, «все 10 лучей вылетают из hub_iata»
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

# ---- ДОПУЩЕНИЯ ЮНИТ-ЭКОНОМИКИ РЕЙСА SJ-100 (модель, не данные) ----
FLIGHT_FIXED_COST_RUB = 385_000   # ТО, аэропортовые сборы, экипаж — на один рейс
FUEL_COST_RUB_PER_KM = 310        # керосин ПД-8, ₽/км
DEFAULT_FARE_RUB = 8_400.0        # FinModelInput.avg_fare_rub по умолчанию
MIN_FARE_FLOOR_RUB = 4_500.0      # нижняя граница тарифа для точки безубыточности
TARGET_LOAD_FACTOR_PCT = 84.0     # целевая загрузка для оценки коммерческой жизнеспособности
CRJ200_CASK_ADV_BASE_PCT = 31.5   # преимущество SJ-100 (100 кресел) над CRJ-200 (50) по CASK на плече ~950 км
CRJ200_CASK_ADV_SLOPE = 0.004     # снижение преимущества за каждый км отклонения от 950 км
CRJ200_CASK_ADV_PEAK_KM = 950.0

# Субсидируемые маршруты 2026 (Росавиация, «Перечень субсидируемых в 2026 году маршрутов»,
# страница favt.gov.ru). Отобраны направления между 12 городами ТЗ; список направленный:
# субсидируется только указанное направление А→Б.
SUBSIDY_SOURCE = "Росавиация, перечень субсидируемых маршрутов 2026 (favt.gov.ru)"
SUBSIDY_2026 = {
    ("KUF", "TJM"): ("Ред Вингс", 2, "01.01–30.04 и 01.10–31.12.2026"),
    ("GOJ", "KUF"): ("Ред Вингс", 4, "01.01–30.04 и 01.10–31.12.2026"),
    ("GOJ", "UFA"): ("Икар", 2, "01.01–31.05 и 01.09–31.12.2026"),
    ("GOJ", "CEK"): ("ЮВТ Аэро", 2, "01.01–30.04 и 01.10–31.12.2026"),
    ("KZN", "GOJ"): ("ЮВТ Аэро", 2, "02.01–30.04 и 01.10–31.12.2026"),
    ("KZN", "KUF"): ("ЮВТ Аэро", 2, "02.01–30.04 и 01.10–31.12.2026"),
    ("KZN", "OMS"): ("Икар", 2, "01.01–30.04 и 01.10–31.12.2026"),
    ("KZN", "PEE"): ("ЮВТ Аэро", 2, "02.01–30.04 и 01.10–31.12.2026"),
    ("PEE", "KUF"): ("ЮВТ Аэро", 2, "02.01–30.04 и 01.10–31.12.2026"),
    ("SVX", "GOJ"): ("Ред Вингс", 4, "01.01–30.04 и 01.10–31.12.2026"),
    ("SVX", "OMS"): ("Ред Вингс", 2, "01.01–30.04 и 01.10–31.12.2026"),
    ("SVX", "GSV"): ("Ред Вингс", 3, "01.01–30.04 и 01.10–31.12.2026"),
    ("VOG", "SVX"): ("НордСтар", 2, "15.01–31.05 и 01.10–31.12.2026"),
    ("VOG", "KZN"): ("Икар", 2, "01.01–30.04 и 01.10–31.12.2026"),
    ("MRV", "OMS"): ("Азимут", 2, "01.10–31.12.2026"),
    ("MRV", "PEE"): ("Азимут", 2, "01.01–30.04 и 01.10–31.12.2026"),
    ("MRV", "KUF"): ("Азимут", 3, "01.01–30.04 и 01.10–31.12.2026"),
    ("MRV", "GSV"): ("Азимут", 2, "01.06–31.12.2026"),
    ("MRV", "TJM"): ("Азимут", 2, "01.01–30.04 и 01.11–31.12.2026"),
    ("MRV", "CEK"): ("Азимут", 3, "01.01–30.04 и 01.10–31.12.2026"),
    ("OMS", "UFA"): ("Азимут", 2, "01.01–30.04 и 01.10–31.12.2026"),
}

# Реальные номера рейсов Red Wings на парах, где компания уже летает (страницы расписания
# biletdv.ru, неделя 09–15.11.2026). Для остальных пар код — заглушка.
RW_FLIGHT_CODES = {
    ("SVX", "UFA"): "WZ-1025", ("UFA", "SVX"): "WZ-1026",
    ("SVX", "KUF"): "WZ-1033", ("KUF", "SVX"): "WZ-1034",
    ("SVX", "KZN"): "WZ-1067", ("KZN", "SVX"): "WZ-1068",
    ("SVX", "GOJ"): "WZ-5029", ("GOJ", "SVX"): "WZ-5030",
    ("KUF", "GOJ"): "WZ-5343", ("GOJ", "KUF"): "WZ-5344",
    ("SVX", "OMS"): "WZ-5071", ("OMS", "SVX"): "WZ-5072",
    ("SVX", "GSV"): "WZ-5047", ("GSV", "SVX"): "WZ-5048",
    ("KUF", "TJM"): "WZ-5305", ("TJM", "KUF"): "WZ-5306",
}

# Ж/д: минимальное время в пути (минуты), «Время в пути на поезде от …» на rasp.yandex.ru,
# снято 09.11.2026. Для остальных пар — оценка по расстоянию (помечается в rail_source):
# Минеральных Вод нет на Яндекс.Расписаниях, часть пар не измерялась.
RAIL_MIN_MINUTES = {
    ("CEK", "SVX"): 240, ("GOJ", "KUF"): 668, ("GOJ", "KZN"): 492, ("GSV", "KUF"): 495,
    ("KUF", "KZN"): 923, ("KUF", "SVX"): 1395, ("KUF", "UFA"): 457, ("KUF", "VOG"): 983,
    ("PEE", "SVX"): 334, ("SVX", "TJM"): 267, ("SVX", "UFA"): 822,
    ("KUF", "PEE"): 1800, ("GOJ", "UFA"): 1560, ("UFA", "VOG"): 1560, ("CEK", "KUF"): 1012,
    ("OMS", "UFA"): 1327, ("GOJ", "SVX"): 1174, ("CEK", "KZN"): 1300, ("GSV", "SVX"): 1800,
    ("KUF", "TJM"): 1560,
}
RAIL_WEAK_THRESHOLD_H = 12  # ТЗ: rail_travel_hours >= 12 → rail_weak_competitor = True

# ---- ДОПУЩЕНИЯ ДОСТУПНОСТИ (ТЗ Dev 1, шаг 2; модель, не измерения) ----
TERMINAL_OVERHEAD_H = 1.5      # регистрация, досмотр, выдача багажа на прямом рейсе
MOSCOW_VIA_SPEED_KMH = 800.0   # средняя скорость двух перелётов через Москву
MOSCOW_VIA_OVERHEAD_H = 3.5    # 2 ч стыковка в Москве + 1,5 ч терминалы
CORE_ACCESS_H = 0.45           # доезд до аэропорта из основного города
# Время доезда из спутников — те же сценарные значения, что у Dev 2
# (src/scoring/city_scorer.py: AIRPORT_ACCESS_HOURS, DEFAULT_ACCESS_HOURS), не изохроны.
SATELLITE_ACCESS_H = {
    "KUF": {"тольятти": 0.75},
    "GOJ": {"дзержинск": 0.55},
    "GSV": {"энгельс": 0.70},
    "VOG": {"волжский": 0.60},
    "MRV": {"пятигорск": 0.35, "ессентуки": 0.55, "кисловодск": 0.75},
}
SATELLITE_DEFAULT_ACCESS_H = 0.65
# ТЗ: own_flights_weekly >= 4 → existing_core, 1..3 → existing_thin
RW_CORE_MIN_WEEKLY = 4


def build_cities_features() -> pd.DataFrame:
    return load_rosstat_and_rosaviatsia()


def _pair_competitor_info() -> dict[tuple[str, str], dict]:
    """
    По каждой паре: рейсы конкурентов (без Red Wings), рейсы Red Wings, тарифы.
    Данные идут через fetch_competitor_routes (use_cache=True → schedules_raw.json);
    пары, которых нет в кэше, в результат не попадают.
    """
    all_pairs = [(a, b) for a in TZ_CITIES for b in TZ_CITIES if a != b]
    df = fetch_competitor_routes(all_pairs, use_cache=True)
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


def _access_time_h(iata: str, population_city_mln: float, members: str) -> float:
    """
    Среднее время доезда до аэропорта, ч, взвешенное по населению:
    (P_город × CORE_ACCESS_H + Σ P_спутник × t_спутник) / (P_город + Σ P_спутник).
    agglomeration_members: «Название (123,456); …» — численность спутника в людях.
    """
    total_pop = population_city_mln * 1e6
    weighted = total_pop * CORE_ACCESS_H
    overrides = SATELLITE_ACCESS_H.get(iata, {})
    for member in (members or "").split(";"):
        member = member.strip()
        if not member:
            continue
        name, _, pop_txt = member.rpartition("(")
        pop = int("".join(ch for ch in pop_txt if ch.isdigit()))
        key = " ".join(name.casefold().replace("ё", "е").split())
        hits = [h for token, h in overrides.items() if token in key]
        t = hits[0] if hits else SATELLITE_DEFAULT_ACCESS_H
        total_pop += pop
        weighted += pop * t
    return round(weighted / total_pop, 2)


def _rw_network_status(own_weekly: int, competitor_weekly: int) -> str:
    """ТЗ Dev 1, шаг 2: статус пары в сети Red Wings."""
    if own_weekly >= RW_CORE_MIN_WEEKLY:
        return "existing_core"
    if own_weekly >= 1:
        return "existing_thin"
    return "new_blue_ocean" if competitor_weekly == 0 else "new_head_to_head"


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
    # Регрессия время в пути (ч) от расстояния (км) по измеренным парам Яндекс.Расписаний
    fit_pts = [
        (haversine_km(AIRPORT_COORDS[x], AIRPORT_COORDS[y]), RAIL_MIN_MINUTES[(x, y)] / 60)
        for (x, y) in RAIL_MIN_MINUTES
    ]
    rail_fit = np.polyfit([p[0] for p in fit_pts], [p[1] for p in fit_pts], 1)
    all_fares = [f for v in info.values() for f in v["fares"]]
    fare_fallback = float(pd.Series(all_fares).median()) if all_fares else float("nan")

    access_h = {
        c.iata: _access_time_h(c.iata, c.population_city_mln, c.agglomeration_members)
        for c in cities.itertuples(index=False)
    }

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

            key = tuple(sorted((a.iata, b.iata)))
            if key in RAIL_MIN_MINUTES:
                rail_h = round(RAIL_MIN_MINUTES[key] / 60, 2)
                rail_src = "Яндекс Расписания (мин. время в пути)"
                rail_txt = (f"Ж/д: от {RAIL_MIN_MINUTES[key] // 60} ч {RAIL_MIN_MINUTES[key] % 60} мин "
                            f"(Яндекс Расписания, мин. время в пути).")
            else:
                rail_h = round(rail_fit[0] * d_km + rail_fit[1], 2)
                rail_src = "оценка: линейная регрессия время/расстояние по измеренным парам"
                rail_txt = (f"Ж/д: около {rail_h:.1f} ч — оценка по расстоянию "
                            f"(на Яндекс.Расписаниях пары нет).")
            rail_weak = bool(rail_h >= RAIL_WEAK_THRESHOLD_H)

            proof = (
                f"Росстат: {a.population_mln + b.population_mln:.2f} млн чел. в 2 агломерациях "
                f"({a.city_name} {a.population_mln:.2f} + {b.city_name} {b.population_mln:.2f}); "
                + (f"прямых авиарейсов конкурентов {comp_weekly}/нед. " if comp_weekly is not None
                   else "прямых авиарейсов конкурентов: не измерено. ")
                + f"Пассажиропоток: аэропорт {a.iata} = {a.airport_pax_mln:.3f} млн пасс. в 2025 г. "
                f"(data/raw/rosaviatsia_2025.csv) × {DEPARTURE_SHARE:.0%} вылетающих × "
                f"{CORE_SHARE:.0%} в города набора (допущение) × гравитация на {b.iata}: "
                f"население {b.population_mln:.3f} млн (data/raw/rosstat_cities.csv), "
                f"расстояние {d_km:.0f} км; доля {share:.1%} → рынок {market:,.0f} пасс./год. "
                f"Red Wings берёт {RW_CAPTURE_BASE:.0%} (допущение) = {pax:,.0f} пасс./год. "
                f"Частота: {pax / WEEKS_PER_YEAR:,.0f} пасс./нед ÷ ({SEATS_PER_AIRCRAFT} мест × "
                f"{LOAD_FACTOR:.0%}) → {freq} рейс(ов)/нед. "
                f"{proof_comp} {rail_txt} "
                f"Доля конкурентов в аэропорту {a.iata}: {a.competitor_share_pct:.0f}% "
                f"({a.competitor_share_source})."
            )

            sub = SUBSIDY_2026.get((a.iata, b.iata))
            if sub:
                sub_flag = True
                sub_check = (f"да: {sub[0]}, {sub[1]} рейс(ов)/нед, периоды {sub[2]} "
                             f"({SUBSIDY_SOURCE})")
            else:
                sub_flag = False
                sub_check = f"нет в перечне субсидируемых маршрутов 2026 ({SUBSIDY_SOURCE})"

            # Юнит-экономика рейса без госсубсидии (допущения выше)
            flight_cost_rub = round(FLIGHT_FIXED_COST_RUB + FUEL_COST_RUB_PER_KM * d_km)
            eff_fare = fare if (fare is not None and not pd.isna(fare)) else DEFAULT_FARE_RUB
            belf_no_subsidy_pct = round(
                min(100.0, flight_cost_rub / (SEATS_PER_AIRCRAFT * max(eff_fare, MIN_FARE_FLOOR_RUB)) * 100.0), 1
            )
            commercial_viable_no_subsidy = bool(belf_no_subsidy_pct <= TARGET_LOAD_FACTOR_PCT)
            crj200_cask_advantage_pct = round(
                CRJ200_CASK_ADV_BASE_PCT - CRJ200_CASK_ADV_SLOPE * abs(d_km - CRJ200_CASK_ADV_PEAK_KM), 1
            )

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
                "rail_travel_hours": rail_h,
                "rail_weak_competitor": rail_weak,
                "rail_source": rail_src,
                "rail_text": rail_txt,
                "launch_quarter": _launch_quarter(own_weekly or 0, comp_weekly or 0),
                "air_door_to_door_h": round((flight_min + TERMINAL_OVERHEAD_H * 60) / 60.0, 2),
                "moscow_via_time_h": round(
                    (a.dist_to_mow_km + b.dist_to_mow_km) / MOSCOW_VIA_SPEED_KMH + MOSCOW_VIA_OVERHEAD_H, 2
                ),
                "access_time_origin_h": access_h[a.iata],
                "access_time_dest_h": access_h[b.iata],
                "moscow_detour_ratio": round(detour, 2),
                "flight_cost_rub": int(flight_cost_rub),
                "belf_no_subsidy_pct": belf_no_subsidy_pct,
                "commercial_viable_no_subsidy": commercial_viable_no_subsidy,
                "crj200_cask_advantage_pct": crj200_cask_advantage_pct,
                "market_pax_year": int(round(market)),
                "pax": int(round(pax)),
                "freq": int(freq),
                "competitor_share_origin_pct": a.competitor_share_pct,
                "competitor_share_source": a.competitor_share_source,
                "proof_source": proof,
            })

    df = pd.DataFrame(rows)
    # int64, если все пары измерены; иначе nullable Int64, чтобы не падать и не подставлять нули
    for c in ["competitor_flights_weekly", "own_flights_weekly", "competitor_fare_rub"]:
        df[c] = df[c].astype("Int64")
        if df[c].notna().all():
            df[c] = df[c].astype("int64")
        else:
            warnings.warn(f"{c}: есть неизмеренные пары, оставлены пустыми (Int64)", stacklevel=2)
    df["subsidy_eligible"] = df["subsidy_eligible"].astype(bool)

    # Статус — по паре O-D (обе стороны одинаково): берётся максимум рейсов из двух направлений.
    # Пример: Саратов→Казань 1 рейс/нед, обратно 0 — пара не «белое пятно», а head-to-head.
    pair_key = pd.Series(
        ["-".join(sorted(k)) for k in zip(df["origin_iata"], df["dest_iata"])], index=df.index
    )
    own_max = df.groupby(pair_key)["own_flights_weekly"].transform("max")
    comp_max = df.groupby(pair_key)["competitor_flights_weekly"].transform("max")
    status_at = df.columns.get_loc("launch_quarter") + 1
    df.insert(status_at, "rw_network_status", [
        None if pd.isna(o) or pd.isna(c) else _rw_network_status(int(o), int(c))
        for o, c in zip(own_max, comp_max)
    ])
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

    if hypothesis == "p2p":
        order = {pair: i for i, pair in enumerate(P2P_PAIRS)}
        keys = list(zip(routes["origin_iata"], routes["dest_iata"]))
        routes = routes[[k in order for k in keys]].copy()
        routes["_order"] = [order[k] for k in zip(routes["origin_iata"], routes["dest_iata"])]
        routes = routes.sort_values("_order").drop(columns="_order").reset_index(drop=True)
    else:
        if hub_iata not in TZ_CITIES:
            raise ValueError(f"Хаб {hub_iata} не входит в 12 городов ТЗ: {TZ_CITIES}")
        routes = routes[routes["origin_iata"] == hub_iata]
        routes = routes.sort_values("pax", ascending=False).head(HUB_RAYS).reset_index(drop=True)

    tag = "HUB" if hypothesis == "hub" else "P2P"
    codes, code_src = [], []
    for o, d in zip(routes["origin_iata"], routes["dest_iata"]):
        if (o, d) in RW_FLIGHT_CODES:
            codes.append(RW_FLIGHT_CODES[(o, d)])
            code_src.append("реальный номер Red Wings (biletdv.ru, 09–15.11.2026)")
        else:
            codes.append(f"RW-{tag}-{o}-{d}")
            code_src.append("заглушка: Red Wings на этой паре не летает, номер назначит авиакомпания")
    routes.insert(0, "route_code", codes)
    routes.insert(1, "route_code_source", code_src)

    if len(routes) < MIN_ROUTES:
        warnings.warn(
            f"Гипотеза {hypothesis!r}: {len(routes)} маршрутов, минимум {MIN_ROUTES} по ТЗ.",
            stacklevel=2,
        )
    return routes


if __name__ == "__main__":
    build_processed_tables()
