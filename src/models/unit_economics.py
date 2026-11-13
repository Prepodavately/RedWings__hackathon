"""Юнит-экономика новой сети SJ-100 — участник №3.

Источник коэффициентов: TZ_KOMANDY_RED_WINGS.md, разделы 5.3–5.4.
Это сценарные допущения команды, а не подтвержденные тарифы/затраты/субсидии.
Промежуточные поправки загрузки (+1.2 п.п. хабу при частоте 4–5,
-0.8 п.п. P2P при частоте >5) взяты из существующего aviationModel.ts.

Единицы: частота — пары рейсов/неделю; F = маршруты * частота * 2 * 52.
Стоимость 645/635 тыс. руб. применяется к ОДНОМУ плечу, согласно формулам
ТЗ (слова «парного плеча» в его тексте неоднозначны). При изменении числа
кресел стоимость рейса обеих стратегий масштабируется как seats/100.
Формулы, ограничения и округления — по полному ТЗ от 10.11.2026.
Выручка включает билетную выручку и сценарные субсидии. EBITDAR = выручка
минус модельные операционные расходы, до аренды/амортизации/процентов/налогов.
BELF — фактическая загрузка, не значение входного ползунка до синергии;
показатель ограничен 55..96% для хаба и 52..96% для P2P по ТЗ. Это ограниченный
индикатор для UI, а не точный порог вне этих границ; убыточность видна в EBITDAR.
Иллюстративные 81.4%/63.5% из ТЗ не используются как заданные ответы.

Пассажиры считаются по плечам, не как уникальные люди или O&D-поездки.
Прирост доли — процентные пункты от фиксированных 108.9 млн пассажиров,
при допущении, что весь поток новой сети дополнительный (без каннибализации).
Базовая доля RW не нужна: в материалах расходятся 2.7 и 4.465 млн пассажиров.
Все показатели годовые для полного года эксплуатации после поставок 2027-H2.
top_cities проверяет выбор хаба; DTO не содержит маршрутного спроса/времени,
поэтому рейтинг города не превращается в выдуманный коэффициент доходности.
Доказательства спроса и частот на каждом маршруте поставляет участник №1.
"""

from dataclasses import asdict, dataclass, replace
from math import isfinite
from random import Random
from typing import List, Sequence

import pandas as pd

from src.models.sj100_fleet import (
    AIRCRAFT_CATALOG, get_aircraft_spec,
    P2P_FLEET_FACTOR, ROUND_TRIPS_PER_AIRCRAFT_WEEK, calculate_required_sj100_fleet,
)
from src.schemas.contracts import (
    AircraftModelId,
    CityScoreDTO,
    ComparisonBundleDTO,
    FinModelInput,
    FleetGapSummaryDTO,
    HypothesisCode,
    HypothesisResultDTO,
)

WEEKS_PER_YEAR = 52
TOTAL_RF_MARKET_PAX_2025 = 108_900_000
RED_WINGS_BASE_PAX_2025 = 4_465_000  # База командного сценария, не новая статистика.
MAX_LOAD_FACTOR_PCT = 95.0
FARE_ELASTICITY = -0.65


@dataclass(frozen=True)
class _Scenario:
    demand_factor: float
    cost_factor: float
    subsidy_per_flight_rub: float
    hub_fixed_cost_rub: float


_SCENARIOS = {
    "base": _Scenario(1.0, 1.0, 145_000.0, 310_000_000.0),
    "conservative": _Scenario(0.87, 1.08, 95_000.0, 365_000_000.0),
}


def _finite_number(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} должен быть конечным числом")


def _validate_params(params: FinModelInput) -> None:
    _finite_number("load_factor_pct", params.load_factor_pct)
    if not 50 <= params.load_factor_pct <= 98:
        raise ValueError("load_factor_pct должен быть в диапазоне 50..98")
    _finite_number("avg_fare_rub", params.avg_fare_rub)
    if not 3500 <= params.avg_fare_rub <= 25000:
        raise ValueError("avg_fare_rub должен быть в диапазоне 3500..25000")
    # Загрузка и тариф допускают стресс-тесты за пределами ползунков UI.
    for name, low, high in (
        ("weekly_freq_per_route", 1, 21),
        ("aircraft_seats", 75, 220),
        ("active_routes_count", 1, 50),
    ):
        value = getattr(params, name)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"{name} должен быть целым числом в диапазоне {low}..{high}")
    if not isinstance(params.scenario, str) or params.scenario not in _SCENARIOS:
        raise ValueError("scenario должен быть 'base' или 'conservative'")
    if not isinstance(params.hub_iata, str) or len(params.hub_iata) != 3:
        raise ValueError("hub_iata должен содержать трехбуквенный код аэропорта")


def _effective_load(params: FinModelInput, code: HypothesisCode) -> float:
    freq = params.weekly_freq_per_route
    if code == "hub":
        adjustment = 3.2 if freq >= 6 else 1.2 if freq >= 4 else -2.5
    else:
        adjustment = 2.4 if freq <= 5 else -0.8
    load = (params.load_factor_pct + adjustment) * _SCENARIOS[params.scenario].demand_factor
    return round(min(95.0, max(52.0 if code == "hub" else 54.0, load)), 1)


def _calculate(
    params: FinModelInput, code: HypothesisCode, *,
    variable_cost_multiplier: float = 1.0, subsidy_retention: float = 1.0,
) -> HypothesisResultDTO:
    """Общий расчет; стресс-множители не меняют глобальные сценарии/DTO."""
    scenario = _SCENARIOS[params.scenario]
    is_hub = code == "hub"
    flights = params.active_routes_count * params.weekly_freq_per_route * 2 * WEEKS_PER_YEAR
    seats = flights * params.aircraft_seats
    passengers = int(round(seats * (_effective_load(params, code) / 100.0)))
    fare = round(params.avg_fare_rub * (0.935 if is_hub else 1.055))
    subsidy_mln = flights * (0.45 if is_hub else 0.65) * scenario.subsidy_per_flight_rub * subsidy_retention / 1e6
    fixed_cost_mln = scenario.hub_fixed_cost_rub / 1e6 if is_hub else 115.0
    cost_per_flight = (645_000 if is_hub else 635_000) * scenario.cost_factor * (params.aircraft_seats / 100.0) * variable_cost_multiplier
    cost_mln = round(flights * cost_per_flight / 1e6 + fixed_cost_mln, 1)
    revenue_mln = round(passengers * fare / 1e6 + subsidy_mln, 1)
    ebitdar_mln = round(revenue_mln - cost_mln, 1)
    belf = (cost_mln - subsidy_mln) * 1e6 / max(1.0, seats * fare) * 100.0
    return HypothesisResultDTO(
        code=code,
        title=(f"Гипотеза А: Региональный хаб ({params.hub_iata})" if is_hub
               else "Гипотеза Б: Прямые межрегиональные рейсы (P2P)"),
        annual_passengers=passengers,
        annual_revenue_mln_rub=revenue_mln,
        ebitdar_mln_rub=ebitdar_mln,
        ebitdar_margin_pct=round(ebitdar_mln / max(1.0, revenue_mln) * 100.0, 1),
        market_share_delta_pct=round(passengers / TOTAL_RF_MARKET_PAX_2025 * 100.0, 3),
        required_aircraft_sj100=calculate_required_sj100_fleet(
            params.active_routes_count, params.weekly_freq_per_route, is_hub
        ),
        breakeven_load_factor_pct=round(min(96.0, max(55.0 if is_hub else 52.0, belf)), 1),
    )


def evaluate_hypotheses(
    params: FinModelInput, top_cities: List[CityScoreDTO]
) -> ComparisonBundleDTO:
    """Контрактная экономика: score = 0.45 * revenue + 0.55 * EBITDAR.

    При равенстве побеждает P2P. Этот критерий сам по себе не гарантирует
    прибыльности. Выбор хаба разрешен из всего переданного списка городов,
    независимо от линейного is_top3; чужой рейтинг/DTO не изменяется.
    """
    _validate_params(params)
    if not top_cities:
        raise ValueError("Список городов top_cities не может быть пустым")
    hub_city = next((city for city in top_cities if city.iata == params.hub_iata), None)
    if hub_city is None:
        raise ValueError(f"Город hub_iata={params.hub_iata!r} не найден в переданном списке городов")
    hub, p2p = _calculate(params, "hub"), _calculate(params, "p2p")
    hub_score = hub.annual_revenue_mln_rub * .45 + hub.ebitdar_mln_rub * .55
    p2p_score = p2p.annual_revenue_mln_rub * .45 + p2p.ebitdar_mln_rub * .55
    winner = p2p if p2p_score >= hub_score else hub
    hub_fixed = _SCENARIOS[params.scenario].hub_fixed_cost_rub / 1e6
    rationale = (
        f"По критерию 0.45 × выручка + 0.55 × EBITDAR выбран {winner.code.upper()}. "
        f"Хаб: {hub_city.city_name} ({hub_city.iata}, ранг {hub_city.rank}, "
        f"балл {hub_city.total_score:.2f}). "
        f"EBITDAR: хаб {hub.ebitdar_mln_rub:.1f}, P2P {p2p.ebitdar_mln_rub:.1f} млн ₽; "
        f"BELF: {hub.breakeven_load_factor_pct:.1f}% против {p2p.breakeven_load_factor_pct:.1f}%. "
        f"Постоянные расходы: хаб {hub_fixed:.0f} против P2P 115 млн ₽/год "
        f"(экономия {hub_fixed - 115:.0f} млн ₽); флот P2P {p2p.required_aircraft_sj100} "
        f"против хаба {hub.required_aircraft_sj100} SJ-100. "
        f"Сценарий {params.scenario}; полный год эксплуатации после поставок не ранее 2027-H2. "
        "Спрос, субсидии и утилизация — допущения для проверки по маршрутам."
    )
    if not hub_city.is_top3:
        rationale += " Выбор вне линейного Топ-3 допустим."
    if winner.ebitdar_mln_rub < 0:
        rationale += " Выбранный вариант убыточен: запуск не рекомендуется без пересмотра экономики."
    return ComparisonBundleDTO(hub, p2p, winner.code, rationale)


def simulate_fare_elasticity_curve(
    params: FinModelInput,
    top_cities: List[CityScoreDTO],
    fares_rub: Sequence[float] = (5500, 6500, 7500, 8400, 9500, 10500, 11500, 12500, 13500),
    elasticity: float = -0.65,
) -> List[dict]:
    """Линейная эластичность L(p)=L0*(1+elasticity*(p/p0-1)).

    Пересчитанная входная загрузка ограничена 50..98% контрактом; синергия,
    сценарий и пределы 52/54..95% применяются evaluate_hypotheses один раз.
    effective_load_factor_pct — пересчитанный вход, загрузки отдельных
    стратегий возвращаются отдельно. Плато на границах допустимо.
    Максимум EBITDAR определяется по точкам, а не подгоняется под 8400..9500.
    """
    evaluate_hypotheses(params, top_cities)
    _finite_number("elasticity", elasticity)
    if elasticity > 0:
        raise ValueError("elasticity должна быть неположительной")
    points = []
    for fare in fares_rub:
        _finite_number("fare_rub", fare)
        if not 3500 <= fare <= 25000:
            raise ValueError("fare_rub должен быть в диапазоне 3500..25000")
        load = min(98.0, max(50.0, params.load_factor_pct *
                            (1 + elasticity * (fare / params.avg_fare_rub - 1))))
        adjusted = replace(params, avg_fare_rub=fare, load_factor_pct=load)
        result = evaluate_hypotheses(adjusted, top_cities)
        points.append({
            "fare_rub": fare, "effective_load_factor_pct": load,
            "hub_effective_load_factor_pct": _effective_load(adjusted, "hub"),
            "p2p_effective_load_factor_pct": _effective_load(adjusted, "p2p"),
            "hub_revenue_mln_rub": result.hub.annual_revenue_mln_rub,
            "hub_ebitdar_mln_rub": result.hub.ebitdar_mln_rub,
            "p2p_revenue_mln_rub": result.p2p.annual_revenue_mln_rub,
            "p2p_ebitdar_mln_rub": result.p2p.ebitdar_mln_rub,
            "winner": result.winner,
        })
    return points


def evaluate_digital_one_click_impact(
    params: FinModelInput, top_cities: List[CityScoreDTO], *,
    enable_virtual_interline: bool = True,
    enable_one_click_ancillary: bool = True,
    enable_auto_disruption_recovery: bool = True,
) -> dict:
    """Сценарный эффект цифровизации поверх округленной базовой P2P-модели.

    Interline: +3 п.п. к фактической загрузке (потолок 95%), 18 млн затрат.
    Ancillary: +650 ₽ выручки и -180 ₽ затрат на каждого итогового пассажира.
    Recovery: -22.5 млн затрат * routes/10. Дополнительных субсидий нет.
    Порядок атрибуции interline -> ancillary -> recovery: перекрестный эффект
    ancillary на новых пассажиров входит только в ancillary, без двойного счета.
    Все коэффициенты — гипотезы ТЗ; подтвержденные эффекты продукта отсутствуют.
    """
    flags = (enable_virtual_interline, enable_one_click_ancillary, enable_auto_disruption_recovery)
    if any(not isinstance(flag, bool) for flag in flags):
        raise ValueError("Переключатели цифровых сервисов должны быть bool")
    base = evaluate_hypotheses(params, top_cities).p2p
    flights = params.active_routes_count * params.weekly_freq_per_route * 2 * WEEKS_PER_YEAR
    capacity = flights * params.aircraft_seats
    load = min(95.0, _effective_load(params, "p2p") + (3.0 if enable_virtual_interline else 0))
    pax = round(capacity * (load / 100.0))
    fare = round(params.avg_fare_rub * 1.055)
    interline_cost = 18.0 if enable_virtual_interline else 0.0
    extra_tickets = (pax - base.annual_passengers) * fare / 1e6
    ancillary = pax * 650 / 1e6 if enable_one_click_ancillary else 0.0
    distribution_saving = pax * 180 / 1e6 if enable_one_click_ancillary else 0.0
    recovery = 22.5 * params.active_routes_count / 10 if enable_auto_disruption_recovery else 0.0
    uplift = {
        "virtual_interline": extra_tickets - interline_cost,
        "one_click_ancillary": ancillary + distribution_saving,
        "auto_disruption_recovery": recovery,
    }
    revenue = base.annual_revenue_mln_rub + extra_tickets + ancillary
    cost = (base.annual_revenue_mln_rub - base.ebitdar_mln_rub
            + interline_cost - distribution_saving - recovery)
    profit = revenue - cost
    subsidy = flights * .65 * _SCENARIOS[params.scenario].subsidy_per_flight_rub / 1e6
    # Savings 180 ₽/пасс. зависят от загрузки: учитываются в знаменателе BELF.
    fixed_cost = base.annual_revenue_mln_rub - base.ebitdar_mln_rub + interline_cost - recovery
    unit_contribution = fare + (830 if enable_one_click_ancillary else 0)
    raw_belf = max(0.0, (fixed_cost - subsidy) * 1e6 / (capacity * unit_contribution) * 100)
    digital = asdict(base)
    if any(flags):
        digital.update(
            annual_passengers=pax,
            annual_revenue_mln_rub=round(revenue, 6),
            ebitdar_mln_rub=round(profit, 6),
            ebitdar_margin_pct=round(profit / max(1.0, revenue) * 100, 1),
            breakeven_load_factor_pct=round(min(96.0, max(52.0, raw_belf)), 1),
            market_share_delta_pct=round(pax / TOTAL_RF_MARKET_PAX_2025 * 100, 3),
        )
    return {
        "p2p_base": asdict(base), "p2p_digital": digital,
        "ebitdar_uplift_mln_rub": {key: round(value, 6) for key, value in uplift.items()},
        "total_ebitdar_uplift_mln_rub": round(sum(uplift.values()), 6),
        "digital_effective_load_factor_pct": load,
        "digital_belf_unclipped_pct": raw_belf,
        "assumptions": "Эффекты ТЗ, годовые; interline +3 п.п./18 млн; ancillary 650+180 ₽/пасс.; recovery 22.5 млн на 10 маршрутов.",
    }


# Целевые пороги и планы — допущения команды, не гарантии места/поставок.
S7_REFERENCE_MARKET_SHARE_PCT = 11.8
URAL_REFERENCE_MARKET_SHARE_PCT = 8.5


def project_path_to_top2_airline(params: FinModelInput, top_cities: List[CityScoreDTO]) -> List[dict]:
    """Обратный расчет масштаба: цель пассажиров -> частота -> проверка флота.

    Волна 1 — исходный пилот без цифровых надбавок. Для волн 2/3 минимальная
    частота >= входной, достигающая цели 9.15/14.15 млн, ищется в 1..21.
    Смешанный флот — допущение: SJ-100=params.aircraft_seats, Ту-214=210,
    МС-21=211 кресел. Средняя вместимость округляется; модель SJ-100 линейно
    переносится на нее как приближение, не как доказанная экономика Ту/МС.
    Масштабирование финансов и пассажиров идет из шаблона входной сети
    пропорционально числу маршрутов (включая фиксированные расходы).
    Результат — годовой темп после полного развертывания, не факт за период.
    fleet_total — план выделенного флота, fleet_required_model — расчетная
    потребность по принятой утилизации. fleet_gap>0 запрещает трактовать
    расчетную долю/ранг как обеспеченный прогноз. Цели не подменяют результаты.
    База 28 бортов не суммируется с выделенным флотом волн 1–3; это отдельная
    существующая сеть, ее выручка не известна и в projected_* не включена.
    """
    pilot = evaluate_hypotheses(params, top_cities).p2p
    rows = [{
        "wave_id": 0, "period": "2025", "title": "База командного сценария",
        "routes_count": 0, "fleet_total": 28, "fleet_breakdown": {"existing": 28},
        "incremental_pax_mln": 0.0, "total_pax_mln": RED_WINGS_BASE_PAX_2025 / 1e6,
        "market_share_pct": round(RED_WINGS_BASE_PAX_2025 / TOTAL_RF_MARKET_PAX_2025 * 100, 2),
        "projected_revenue_bln_rub": None, "projected_ebitdar_bln_rub": None,
        "market_rank_rf": None, "rank_note": "Топ-5/6 — оценка ТЗ; полного рейтинга нет",
    }]
    plans = [
        (1, "2026–2027", "Ядро Поволжье — Урал", params.active_routes_count,
         {"SJ-100": pilot.required_aircraft_sj100}, None),
        (2, "2028–2029", "Федеральная P2P-сеть + Virtual Interline", 65,
         {"SJ-100": 36, "Ту-214": 12}, 9.15),
        (3, "2030", "Цель: авиаперевозчик №2", 120,
         {"SJ-100": 55, "Ту-214": 15, "МС-21": 12}, 14.15),
    ]
    for wave, period, title, routes, fleet, target in plans:
        fleet_total = sum(fleet.values())
        seat_map = {"SJ-100": params.aircraft_seats, "Ту-214": 210, "МС-21": 211}
        average_seats = round(sum(seat_map[k] * count for k, count in fleet.items()) / fleet_total)
        scale = routes / params.active_routes_count
        frequency = params.weekly_freq_per_route
        metrics = asdict(pilot)
        if wave > 1:
            for frequency in range(params.weekly_freq_per_route, 22):
                template = replace(params, aircraft_seats=average_seats, weekly_freq_per_route=frequency)
                metrics = evaluate_digital_one_click_impact(template, top_cities)["p2p_digital"]
                if (RED_WINGS_BASE_PAX_2025 + metrics["annual_passengers"] * scale) / 1e6 >= target:
                    break
        increment = metrics["annual_passengers"] * scale
        total = RED_WINGS_BASE_PAX_2025 + increment
        share = total / TOTAL_RF_MARKET_PAX_2025 * 100
        needed = calculate_required_sj100_fleet(routes, frequency, False)
        gap = max(0, needed - fleet_total)
        supported_routes = min(routes, int(fleet_total * ROUND_TRIPS_PER_AIRCRAFT_WEEK
                                           / (frequency * P2P_FLEET_FACTOR)))
        constrained_total = RED_WINGS_BASE_PAX_2025 + increment * supported_routes / routes
        # Полный рейтинг не известен: 2/3 — условно при неизменных конкурентах.
        rank = 2 if share > S7_REFERENCE_MARKET_SHARE_PCT else 3 if share > URAL_REFERENCE_MARKET_SHARE_PCT else None
        rows.append({
            "wave_id": wave, "period": period, "title": title,
            "routes_count": routes, "fleet_total": fleet_total, "fleet_breakdown": fleet,
            "incremental_pax_mln": round(increment / 1e6, 6), "total_pax_mln": round(total / 1e6, 6),
            "market_share_pct": round(share, 3),
            "projected_revenue_bln_rub": round(metrics["annual_revenue_mln_rub"] * scale / 1000, 6),
            "projected_ebitdar_bln_rub": round(metrics["ebitdar_mln_rub"] * scale / 1000, 6),
            "market_rank_rf": rank, "rank_is_conditional": True,
            "weekly_freq_per_route": frequency, "average_aircraft_seats": average_seats,
            "fleet_required_model": needed, "fleet_gap": gap,
            "fleet_capacity_feasible": gap == 0,
            "fleet_supported_routes_count": supported_routes,
            "fleet_constrained_total_pax_mln": round(constrained_total / 1e6, 6),
            "fleet_constrained_market_share_pct": round(constrained_total / TOTAL_RF_MARKET_PAX_2025 * 100, 3),
            "target_total_pax_mln": target,
            "target_reached": target is None or total / 1e6 >= target,
            "digital_enabled": wave > 1,
            "financial_scope": "Только новая сеть, годовой темп; база 2025 не включена",
            "assumptions": "Постоянный рынок 108.9 млн, S7 11.8%, Уральские 8.5%; нет каннибализации; поставки и спрос не подтверждены; до 2027-H2 только перераспределение существующего флота.",
        })
    return rows


def _deduplicate_aircraft_market_routes(routes_df: pd.DataFrame) -> pd.DataFrame:
    """Одна строка на неориентированную пару; входная витрина не изменяется.

    Частоты — максимум по направлениям, субсидия — any. Прочие поля Dev 1
    сохраняются из первого направления в порядке IATA (включая координаты).
    Это справочные поля этого направления, не суммы/средние по паре.
    Пропуск частоты не считается нулем: иначе появятся ложные белые пятна.
    """
    required = {"origin_iata", "dest_iata", "distance_km", "subsidy_eligible",
                "own_flights_weekly", "competitor_flights_weekly"}
    if not isinstance(routes_df, pd.DataFrame):
        raise ValueError("routes_df должен быть DataFrame")
    missing = required - set(routes_df.columns)
    if missing:
        raise ValueError(f"В routes_df отсутствуют колонки: {sorted(missing)}")
    if not routes_df.columns.is_unique:
        raise ValueError("Названия колонок routes_df не должны повторяться")
    records = routes_df.to_dict("records")
    pairs = {}
    for row in sorted(records, key=lambda r: (str(r["origin_iata"]), str(r["dest_iata"]))):
        for name in ("origin_iata", "dest_iata"):
            code = row[name]
            if not isinstance(code, str) or len(code) != 3 or not code.isascii() or not code.isalpha() or not code.isupper():
                raise ValueError(f"{name} должен быть трехбуквенным IATA-кодом")
        if row["origin_iata"] == row["dest_iata"]:
            raise ValueError("Маршрут не может вести в тот же аэропорт")
        for name in ("distance_km", "own_flights_weekly", "competitor_flights_weekly"):
            value = row[name]
            _finite_number(name, value)
            if value < 0 or (name == "distance_km" and value == 0):
                raise ValueError(f"Некорректное значение {name}")
        if not isinstance(row["subsidy_eligible"], bool):
            raise ValueError("subsidy_eligible должен быть bool")
        key = tuple(sorted((row["origin_iata"], row["dest_iata"])))
        if key not in pairs:
            pairs[key] = {**row, "pair_key": key}
        else:
            pair = pairs[key]
            for name in ("distance_km", "own_flights_weekly", "competitor_flights_weekly"):
                pair[name] = max(pair[name], row[name])
            pair["subsidy_eligible"] |= row["subsidy_eligible"]
    columns = list(routes_df.columns)
    if "pair_key" not in columns:
        columns.append("pair_key")
    return pd.DataFrame([pairs[key] for key in sorted(pairs)], columns=columns)


def evaluate_routes_by_aircraft_and_rw_gap(
    routes_df: pd.DataFrame,
    aircraft_id: AircraftModelId = "sj100_basic",
    load_factor_pct: float = 84.0,
    avg_fare_rub: float = 8400.0,
    weekly_freq: int = 5,
    subsidy_cut_pct: float = 0.0,
    min_belf_buffer_pct: float = 5.0,
) -> tuple[pd.DataFrame, FleetGapSummaryDTO]:
    """Каталог ВС × реальные пары Dev 1: текущая сеть и кандидаты расширения.

    Число пар вычисляется из входа (66 на полной витрине), а не задано константой.
    Тариф и затраты относятся к одному плечу; частота — к паре рейсов.
    Это маршрутный вклад до общесетевых постоянных расходов, без подстройки
    загрузки под спрос/конкуренцию. Статус keep_or_boost означает присутствие
    RW в пределах дальности, а не гарантию прибыльности существующего рейса.

    По уточнению пользователя BELF согласован с EBITDAR: знаменатель
    seats * fare без множителя 2 (затраты и тариф — на одно плечо).
    belf_pct ограничен 0..150% по ТЗ; belf_economic_pct — порог без обрезки.
    Отбор propose_new использует belf_pct и заданный запас загрузки.
    Флаг субсидии хотя бы одного направления применяется к обоим плечам
    пары: это сценарий, не подтвержденное право RW на субсидию/квоту.
    Потребность всех ВС оценивается эвристикой SJ-100 по требованию ТЗ;
    при нуле предложений max(1, count) оставляет минимальный резерв 2 борта.
    """
    from src.parsers.build_dataset import FLIGHT_FIXED_COST_RUB, FUEL_COST_RUB_PER_KM

    spec = get_aircraft_spec(aircraft_id)
    for name, value in (("load_factor_pct", load_factor_pct),
                        ("subsidy_cut_pct", subsidy_cut_pct),
                        ("min_belf_buffer_pct", min_belf_buffer_pct)):
        _finite_number(name, value)
        if not 0 <= value <= 100:
            raise ValueError(f"{name} должен быть в диапазоне 0..100")
    _finite_number("avg_fare_rub", avg_fare_rub)
    if avg_fare_rub <= 0:
        raise ValueError("avg_fare_rub должен быть положительным")
    if isinstance(weekly_freq, bool) or not isinstance(weekly_freq, int) or weekly_freq <= 0:
        raise ValueError("weekly_freq должен быть положительным целым числом")
    routes = _deduplicate_aircraft_market_routes(routes_df)
    routes["aircraft_id"] = aircraft_id
    routes["aircraft_range_status"] = [
        "out_of_range" if d > spec.max_km else
        "too_short" if d < spec.min_km else
        "optimal" if spec.opt_low_km <= d <= spec.opt_high_km else "acceptable"
        for d in routes["distance_km"]
    ]
    penalty = routes["aircraft_range_status"].eq("too_short").map(
        {True: spec.short_haul_penalty, False: 1.0}
    )
    routes["flight_cost_ac"] = (
        (FLIGHT_FIXED_COST_RUB + FUEL_COST_RUB_PER_KM * routes["distance_km"].astype(float))
        * (spec.seats / 100.0) * spec.cask_multiplier * penalty
    )
    routes["subsidy_per_flight_rub"] = (
        routes["subsidy_eligible"].astype(bool).astype(float)
        * _SCENARIOS["base"].subsidy_per_flight_rub * (1 - subsidy_cut_pct / 100)
    )
    routes["belf_economic_pct"] = (
        (routes["flight_cost_ac"] - routes["subsidy_per_flight_rub"])
        / (spec.seats * avg_fare_rub) * 100
    )
    routes["belf_pct"] = routes["belf_economic_pct"].clip(0.0, 150.0)
    flights = weekly_freq * 2 * WEEKS_PER_YEAR
    routes["annual_flights"] = flights
    routes["annual_pax"] = int(flights * spec.seats * (load_factor_pct / 100.0))
    routes["annual_subsidy_rub"] = flights * routes["subsidy_per_flight_rub"]
    routes["annual_ebitdar_mln"] = (
        routes["annual_pax"] * avg_fare_rub + routes["annual_subsidy_rub"]
        - flights * routes["flight_cost_ac"]
    ) / 1e6
    existing = routes["own_flights_weekly"].gt(0)
    feasible = routes["aircraft_range_status"].ne("out_of_range")
    proposed = (
        ~existing & routes["aircraft_range_status"].isin(["optimal", "acceptable"])
        & routes["belf_pct"].le(load_factor_pct - min_belf_buffer_pct)
    )
    routes["proposal_bucket"] = "not_fit"
    routes.loc[existing & feasible, "proposal_bucket"] = "keep_or_boost"
    routes.loc[proposed, "proposal_bucket"] = "propose_new"
    count = int(proposed.sum())
    summary = FleetGapSummaryDTO(
        aircraft_id=aircraft_id,
        total_market_pairs=len(routes),
        feasible_for_aircraft_count=int(feasible.sum()),
        optimal_range_count=int(routes["aircraft_range_status"].eq("optimal").sum()),
        existing_rw_count=int(existing.sum()),
        existing_rw_fit_count=int((existing & feasible).sum()),
        proposed_new_count=count,
        proposed_blue_ocean_count=int((proposed & routes["competitor_flights_weekly"].eq(0)).sum()),
        proposed_annual_pax=int(routes.loc[proposed, "annual_pax"].sum()),
        proposed_ebitdar_mln_rub=float(routes.loc[proposed, "annual_ebitdar_mln"].sum()),
        required_aircraft_count=calculate_required_sj100_fleet(max(1, count), weekly_freq, is_hub=False),
    )
    routes.attrs["assumptions"] = {
        "pair_aggregation": "max distance/frequency; any subsidy; remaining fields from one source direction",
        "subsidy_scope": "145000 RUB per flight on both legs if either direction eligible; RW eligibility unverified",
        "financial_scope": "route contribution before network overhead, rent, depreciation, interest and tax",
        "belf_selection_formula": "(flight_cost_ac - subsidy) / (seats * fare) * 100, clipped to 0..150; corrected per user clarification",
        "belf_economic_formula": "(flight_cost_ac - subsidy) / (seats * fare) * 100, unclipped",
        "fleet_method": "SJ-100 P2P heuristic for all models, max(1, proposed routes); not a timetable",
        "demand": "input load for all pairs; not validated against route demand",
    }
    return routes, summary


def compare_all_aircraft_models(
    routes_df: pd.DataFrame,
    load_factor_pct: float = 84.0,
    avg_fare_rub: float = 8400.0,
    weekly_freq: int = 5,
    subsidy_cut_pct: float = 0.0,
) -> list[FleetGapSummaryDTO]:
    """Пять сводок в порядке AIRCRAFT_CATALOG для таблицы Dev 4."""
    return [
        evaluate_routes_by_aircraft_and_rw_gap(
            routes_df, aircraft_id, load_factor_pct, avg_fare_rub,
            weekly_freq, subsidy_cut_pct,
        )[1]
        for aircraft_id in AIRCRAFT_CATALOG
    ]


def _route_level_pnl(
    params: FinModelInput, routes_df: "pd.DataFrame", *, subsidy_retention_pct: float = 100.0,
) -> dict:
    """P&L направленной P2P-сети по витрине Dev 1, без записи в витрины.

    По уточнению пользователя каждая строка задает парный маршрут:
    annual_flights=params.weekly_freq_per_route*2*52. freq из Dev 1 сохраняется
    как справка о направленном спросе, но не заменяет управляющую частоту.
    Обратные дубли A->B/B->A отклоняются: иначе оборот считался бы дважды.
    Размер сети равен числу строк, а не params.active_routes_count.
    Стоимость рейса=(385000+310*distance_km)*cost_factor*(seats/100).
    Постоянные 115 млн ₽/год распределяются ОДИН раз пропорционально вылетам.
    Тариф=params.avg_fare_rub*1.055; конкурентный тариф — только ориентир.
    Загрузка P2P учитывает частоту из params. Это сценарий заполнения
    емкости, не подтвержденный спрос; pax Dev 1 возвращается отдельно.
    Флаг субсидии означает присутствие направления в перечне, а не право RW
    на выплату: оператор, сезон и квоты требуют отдельной проверки. Для
    стресс-теста ставка из ТЗ применяется к ОБОИМ плечам eligible-маршрута согласно ТЗ (права на обратное плечо не подтверждены).
    BELF не обрезается: >100% показывает недостижимую безубыточность.
    """
    from src.parsers.build_dataset import FLIGHT_FIXED_COST_RUB, FUEL_COST_RUB_PER_KM

    _validate_params(params)
    _finite_number("subsidy_retention_pct", subsidy_retention_pct)
    if not 0 <= subsidy_retention_pct <= 100:
        raise ValueError("subsidy_retention_pct должен быть в диапазоне 0..100")
    required = {"origin_iata", "dest_iata", "distance_km", "subsidy_eligible"}
    if not isinstance(routes_df, pd.DataFrame) or routes_df.empty:
        raise ValueError("routes_df должен быть непустым DataFrame")
    if not required <= set(routes_df.columns):
        raise ValueError(f"В routes_df отсутствуют колонки: {sorted(required - set(routes_df.columns))}")
    if routes_df.duplicated(["origin_iata", "dest_iata"]).any():
        raise ValueError("Направления origin_iata/dest_iata не должны повторяться")
    records = routes_df.to_dict("records")
    for row in records:
        for name in ("origin_iata", "dest_iata"):
            value = row[name]
            if not isinstance(value, str) or len(value) != 3 or not value.isascii() or not value.isalpha() or not value.isupper():
                raise ValueError(f"{name} должен быть трехбуквенным IATA-кодом")
        if row["origin_iata"] == row["dest_iata"]:
            raise ValueError("Маршрут не может вести в тот же аэропорт")
        _finite_number("distance_km", row["distance_km"])
        if row["distance_km"] <= 0:
            raise ValueError("distance_km должен быть положительным")
        if not isinstance(row["subsidy_eligible"], bool):
            raise ValueError("subsidy_eligible должен быть bool, не строкой или пропуском")
        for name in ("competitor_fare_rub", "crj200_cask_advantage_pct", "pax", "freq"):
            value = row.get(name)
            if value is not None and not pd.isna(value):
                _finite_number(name, value)
                if name != "crj200_cask_advantage_pct" and value < 0:
                    raise ValueError(f"{name} не может быть отрицательным")
    pairs = [tuple(sorted((row["origin_iata"], row["dest_iata"]))) for row in records]
    if len(pairs) != len(set(pairs)):
        raise ValueError("Обратные направления одной пары нельзя считать дважды")
    route_flights = params.weekly_freq_per_route * 2 * WEEKS_PER_YEAR
    total_flights = route_flights * len(records)
    scenario = _SCENARIOS[params.scenario]
    fare = round(params.avg_fare_rub * 1.055)
    pnl = []
    for row in records:
        flights = route_flights
        seats = flights * params.aircraft_seats
        load = _effective_load(params, "p2p")
        passengers = round(seats * load / 100)
        flight_cost = (FLIGHT_FIXED_COST_RUB + FUEL_COST_RUB_PER_KM * row["distance_km"]) * scenario.cost_factor * params.aircraft_seats / 100
        overhead = 115e6 * flights / total_flights
        cost = flights * flight_cost + overhead
        subsidy_rate = scenario.subsidy_per_flight_rub * subsidy_retention_pct / 100 if row["subsidy_eligible"] else 0.0
        subsidy = flights * subsidy_rate
        tickets = passengers * fare
        competitor = row.get("competitor_fare_rub")
        competitor = None if competitor is None or pd.isna(competitor) else float(competitor)
        advantage = row.get("crj200_cask_advantage_pct")
        advantage = None if advantage is None or pd.isna(advantage) else float(advantage)
        demand = row.get("pax")
        demand = None if demand is None or pd.isna(demand) else float(demand)
        pnl.append({
            "route_code": row.get("route_code", f"{row['origin_iata']}-{row['dest_iata']}"),
            "origin_iata": row["origin_iata"], "dest_iata": row["dest_iata"],
            "distance_km": float(row["distance_km"]), "weekly_round_trips": params.weekly_freq_per_route,
            "dev1_weekly_departures": None if pd.isna(row.get("freq")) or row.get("freq") is None else float(row["freq"]),
            "annual_flights": flights, "annual_passengers": passengers,
            "effective_load_factor_pct": load, "effective_fare_rub": fare,
            "competitor_fare_rub": competitor,
            "fare_vs_competitor_rub": None if competitor is None else fare - competitor,
            "annual_revenue_mln_rub": (tickets + subsidy) / 1e6,
            "annual_cost_mln_rub": cost / 1e6,
            "allocated_fixed_cost_mln_rub": overhead / 1e6,
            "contribution_mln_rub": (tickets + subsidy - flights * flight_cost) / 1e6,
            "contribution_margin_pct": (tickets + subsidy - flights * flight_cost) / (tickets + subsidy) * 100,
            "annual_subsidy_mln_rub": subsidy / 1e6,
            "subsidy_eligible": row["subsidy_eligible"],
            "ebitdar_mln_rub": (tickets + subsidy - cost) / 1e6,
            "ebitdar_no_subsidy_mln_rub": (tickets - cost) / 1e6,
            "belf_with_subsidy_pct": max(0.0, (cost - subsidy) / (seats * fare) * 100),
            "belf_no_subsidy_pct": cost / (seats * fare) * 100,
            "viable_without_subsidy": tickets >= cost,
            "crj200_cask_advantage_pct": advantage,
            "dev1_estimated_passengers": demand,
            "scenario_exceeds_dev1_demand": None if demand is None else passengers > demand,
            "proof_source": row.get("proof_source", "не предоставлен"),
            "subsidy_check": row.get("subsidy_check", "не предоставлен"),
        })
    pnl.sort(key=lambda row: (-row["ebitdar_mln_rub"], row["origin_iata"], row["dest_iata"]))
    advantages = [row["crj200_cask_advantage_pct"] for row in pnl if row["crj200_cask_advantage_pct"] is not None]
    return {
        "routes_pnl": pnl,
        "total_revenue_mln_rub": sum(row["annual_revenue_mln_rub"] for row in pnl),
        "total_cost_mln_rub": sum(row["annual_cost_mln_rub"] for row in pnl),
        "total_ebitdar_mln_rub": sum(row["ebitdar_mln_rub"] for row in pnl),
        "total_ebitdar_no_subsidy_mln_rub": sum(row["ebitdar_no_subsidy_mln_rub"] for row in pnl),
        "profitable_routes_count": sum(row["ebitdar_mln_rub"] >= 0 for row in pnl),
        "profitable_without_subsidy_count": sum(row["viable_without_subsidy"] for row in pnl),
        "avg_crj200_cask_advantage_pct": sum(advantages) / len(advantages) if advantages else None,
        "cask_observed_routes_count": len(advantages),
        "subsidy_retention_pct": subsidy_retention_pct,
        "assumptions": "Парные рейсы params.weekly_freq_per_route*2*52; 115 млн ₽ постоянных затрат на переданную сеть; флаг субсидии применяется к обоим плечам по ТЗ, не подтвержденный договор RW; pax — емкость при заданной загрузке, CASK — оценка Dev 1.",
    }


def evaluate_route_level_economics(
    params: FinModelInput, routes_df: "pd.DataFrame", *,
    subsidy_retention_pct: float = 100.0, available_aircraft_limit: int | None = None,
) -> dict:
    """Помаршрутный P&L; при лимите — выбор маршрутов по маржинальности.

    Все параметры учета и направленных субсидий описаны в _route_level_pnl.
    При одинаковой частоте ресурс маршрута одинаков; сортируем по марже до
    общесетевых постоянных затрат (contribution/revenue), затем по вкладу в ₽.
    Маршруты с неположительным вкладом не отбираем. Это отбор по указанному
    критерию, не оптимизация расписания и не максимизация суммарной прибыли.
    После отбора 115 млн ₽ распределяются заново целиком, без пропорционального
    уменьшения. При 0/1 борте программа P2P не открывается: затраты запуска 0.
    classic_hub_reference — отдельный СРЕДНИЙ хабовый расчет по контрактной
    модели для числа маршрутов, поддерживаемого тем же лимитом, а не P&L
    реальной веерной сети. Возможность стыковок не выводится из числа бортов.
    """
    if available_aircraft_limit is not None and (
        isinstance(available_aircraft_limit, bool)
        or not isinstance(available_aircraft_limit, int) or available_aircraft_limit < 0
    ):
        raise ValueError("available_aircraft_limit должен быть неотрицательным целым числом или None")
    full = _route_level_pnl(params, routes_df, subsidy_retention_pct=subsidy_retention_pct)
    candidates = full["routes_pnl"]
    requested = calculate_required_sj100_fleet(len(candidates), params.weekly_freq_per_route, False)
    if available_aircraft_limit is None:
        return {**full, "available_aircraft_limit": None,
                "required_aircraft_sj100": requested,
                "selected_routes_count": len(candidates), "excluded_routes": []}
    capacity = max((n for n in range(1, len(candidates) + 1)
                    if calculate_required_sj100_fleet(n, params.weekly_freq_per_route, False)
                    <= available_aircraft_limit), default=0)
    ordered = sorted(candidates, key=lambda r: (
        -r["contribution_margin_pct"], -r["contribution_mln_rub"], r["origin_iata"], r["dest_iata"]
    ))
    selected = [row for row in ordered if row["contribution_mln_rub"] > 0][:capacity]
    keys = {(row["origin_iata"], row["dest_iata"]) for row in selected}
    if selected:
        mask = [(o, d) in keys for o, d in zip(routes_df["origin_iata"], routes_df["dest_iata"])]
        result = _route_level_pnl(params, routes_df.loc[mask], subsidy_retention_pct=subsidy_retention_pct)
    else:
        result = {**full, "routes_pnl": [], "avg_crj200_cask_advantage_pct": None}
        for name in ("total_revenue_mln_rub", "total_cost_mln_rub", "total_ebitdar_mln_rub",
                     "total_ebitdar_no_subsidy_mln_rub", "profitable_routes_count",
                     "profitable_without_subsidy_count", "cask_observed_routes_count"):
            result[name] = 0
    supported_hub_routes = max((n for n in range(1, len(candidates) + 1)
        if calculate_required_sj100_fleet(n, params.weekly_freq_per_route, True)
        <= available_aircraft_limit), default=0)
    hub = _calculate(replace(params, active_routes_count=supported_hub_routes), "hub",
                     subsidy_retention=subsidy_retention_pct / 100) if supported_hub_routes else None
    result.update(
        available_aircraft_limit=available_aircraft_limit,
        requested_aircraft_sj100=requested,
        required_aircraft_sj100=calculate_required_sj100_fleet(len(selected), params.weekly_freq_per_route, False) if selected else 0,
        selected_routes_count=len(selected),
        excluded_routes=[row for row in ordered if (row["origin_iata"], row["dest_iata"]) not in keys],
        selection_criterion="Положительная маржа до постоянных затрат / выручка, по убыванию",
        operations_started=bool(selected),
        profitable_selected_network=bool(selected) and result["total_ebitdar_mln_rub"] > 0,
        classic_hub_reference={
            "supported_routes_count": supported_hub_routes,
            "full_requested_network_supported": supported_hub_routes == len(candidates),
            "metrics": asdict(hub) if hub else None,
            "scope": "Средний хабовый сценарий; не помаршрутная оптимизация, реализуемость волн не подтверждена",
        },
    )
    return result


def build_strategy_switching_matrix(
    params: FinModelInput, top_cities: List[CityScoreDTO],
    frequencies: Sequence[int] = (2, 3, 4, 5, 6, 7, 8, 9, 10),
    fares_rub: Sequence[float] = (6000, 7000, 8000, 8400, 9000, 10000, 11000, 12000),
) -> dict:
    """Строки=частоты, столбцы=тарифы; разность EBITDAR=P2P-хаб (млн ₽).

    winner берется из контрактного взвешенного критерия, не из знака разности.
    Наличие областей победы каждой стратегии не гарантируется коэффициентами.
    """
    evaluate_hypotheses(params, top_cities)
    frequencies, fares_rub = list(frequencies), list(fares_rub)
    if not frequencies or not fares_rub:
        raise ValueError("Оси матрицы не могут быть пустыми")
    differences, winners = [], []
    for freq in frequencies:
        diff_row, winner_row = [], []
        for fare in fares_rub:
            result = evaluate_hypotheses(replace(params, weekly_freq_per_route=freq, avg_fare_rub=fare), top_cities)
            diff_row.append(round(result.p2p.ebitdar_mln_rub - result.hub.ebitdar_mln_rub, 1))
            winner_row.append(result.winner)
        differences.append(diff_row)
        winners.append(winner_row)
    return {
        "frequencies": frequencies, "fares_rub": fares_rub,
        "ebitdar_diff_matrix": differences, "winner_matrix": winners,
        "p2p_win_share_pct": sum(value == "p2p" for row in winners for value in row) / (len(frequencies) * len(fares_rub)) * 100,
        "axis_order": "rows=frequencies, columns=fares_rub",
        "difference_definition": "p2p.ebitdar_mln_rub - hub.ebitdar_mln_rub",
    }


# Сценарные коэффициенты согласованы пользователем 11.11.2026; не данные Dev 2.
SCISSOR_COORDINATION_COST_PER_WAVE_MLN = 24.0
SCISSOR_LOAD_BOOST_PER_WAVE_PP = 1.8
SCISSOR_TRANSIT_SHARE = 0.25
SCISSOR_TRANSIT_FARE_DISCOUNT = 0.06  # средний дисконт сети = 0.25 * 6% = 1.5%


def evaluate_scissor_hub_economics(
    params: FinModelInput, top_cities: List[CityScoreDTO], *,
    scissor_hub_iata: str = "KUF", scissor_waves_per_day: int = 2,
) -> dict:
    """Сценарий P2P + обмен пассажирами, со справкой геометрии Dev 2.

    Сравнение использует один выбранный аэропорт для классического и гибридного
    хаба. +1.8 п.п./волна, 24 млн ₽/волна координации, 25% транзита с дисконтом
    6% (1.5% на всю сеть) — согласованные пользователем сценарные допущения.
    Индекс Dev 2 вычисляется из текущих parquet, но НЕ конвертируется в спрос:
    геометрия не доказывает загрузку, 75-минутную пересадку или отсутствие ТО.
    Флот P2P сохранен как допущение о реализуемости сквозного расписания.
    Координационные затраты пропорциональны числу волн; субсидии как у P2P.
    Гибрид не обязан выигрывать, например при уже достигнутом потолке загрузки.
    """
    from pathlib import Path
    from src.scoring.city_scorer import load_features, calculate_gravity_matrix, calculate_scissor_hub_index

    if isinstance(scissor_waves_per_day, bool) or not isinstance(scissor_waves_per_day, int) or not 1 <= scissor_waves_per_day <= 3:
        raise ValueError("scissor_waves_per_day должен быть целым числом 1..3")
    selected = replace(params, hub_iata=scissor_hub_iata)
    comparison = evaluate_hypotheses(selected, top_cities)
    root = Path(__file__).resolve().parents[2]
    features = load_features()
    routes = pd.read_parquet(root / "data/processed/routes_proof.parquet")
    gravity = calculate_gravity_matrix(features, routes)
    indices = calculate_scissor_hub_index(features, gravity)
    matched = indices[indices["iata"] == scissor_hub_iata]
    if matched.empty:
        raise ValueError("scissor_hub_iata отсутствует в витрине Dev 2")
    evidence = matched.iloc[0]
    base = comparison.p2p
    flights = params.active_routes_count * params.weekly_freq_per_route * 2 * WEEKS_PER_YEAR
    capacity = flights * params.aircraft_seats
    load = min(95.0, _effective_load(selected, "p2p") + SCISSOR_LOAD_BOOST_PER_WAVE_PP * scissor_waves_per_day)
    pax = round(capacity * (load / 100))
    fare = round(round(params.avg_fare_rub * 1.055) * (1 - SCISSOR_TRANSIT_SHARE * SCISSOR_TRANSIT_FARE_DISCOUNT))
    subsidy = flights * .65 * _SCENARIOS[params.scenario].subsidy_per_flight_rub / 1e6
    revenue = round(pax * fare / 1e6 + subsidy, 1)
    coordination_cost = SCISSOR_COORDINATION_COST_PER_WAVE_MLN * scissor_waves_per_day
    cost = base.annual_revenue_mln_rub - base.ebitdar_mln_rub + coordination_cost
    profit = round(revenue - cost, 1)
    belf = (cost - subsidy) * 1e6 / (capacity * fare) * 100
    hybrid = {
        **asdict(base), "code": "scissor_hybrid",
        "title": f"P2P + Узел-ножницы ({scissor_hub_iata})",
        "annual_passengers": pax, "annual_revenue_mln_rub": revenue,
        "annual_cost_mln_rub": round(cost, 1), "ebitdar_mln_rub": profit,
        "ebitdar_margin_pct": round(profit / max(1.0, revenue) * 100, 1),
        "breakeven_load_factor_pct": belf,
        "market_share_delta_pct": round(pax / TOTAL_RF_MARKET_PAX_2025 * 100, 3),
        "effective_load_factor_pct": load, "effective_fare_rub": fare,
        "fixed_cost_mln_rub": 115.0 + coordination_cost,
    }
    return {
        "classic_hub": asdict(comparison.hub), "pure_p2p": asdict(base),
        "scissor_hybrid": hybrid,
        "ebitdar_uplift_vs_p2p_mln_rub": round(profit - base.ebitdar_mln_rub, 1),
        "ebitdar_uplift_vs_classic_hub_mln_rub": round(profit - comparison.hub.ebitdar_mln_rub, 1),
        "fixed_cost_saving_vs_classic_hub_mln_rub": _SCENARIOS[params.scenario].hub_fixed_cost_rub / 1e6 - hybrid["fixed_cost_mln_rub"],
        "scissor_evidence": {
            "iata": scissor_hub_iata, "scissor_rank": int(evidence["scissor_rank"]),
            "scissor_hub_index": float(evidence["scissor_hub_index"]),
            "eligible_directed_pairs": int(evidence["eligible_directed_pairs"]),
            "source": "Dev 2 calculate_scissor_hub_index; current cities_features/routes_proof.parquet",
            "max_detour_pct": 15.0,
        },
        "assumptions": {
            "coordination_cost_mln_rub": coordination_cost,
            "coordination_cost_per_wave_mln_rub": SCISSOR_COORDINATION_COST_PER_WAVE_MLN,
            "load_boost_per_wave_pp": SCISSOR_LOAD_BOOST_PER_WAVE_PP,
            "waves_per_day": scissor_waves_per_day, "transfer_window_minutes": 75,
            "transit_share": SCISSOR_TRANSIT_SHARE,
            "transit_discount_pct": SCISSOR_TRANSIT_FARE_DISCOUNT * 100,
            "blended_discount_pct": SCISSOR_TRANSIT_SHARE * SCISSOR_TRANSIT_FARE_DISCOUNT * 100,
            "status": "Сценарные допущения; не доказаны геометрией и требуют проверки расписания/спроса/ТО",
        },
    }


def _linear_quantiles(values: Sequence[float]) -> list[float]:
    """Квантили p5/p50/p95: линейная интерполяция позиции (n-1)*p."""
    ordered = sorted(values)
    result = []
    for p in (.05, .50, .95):
        position = (len(ordered) - 1) * p
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        result.append(round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 6))
    return result


def run_monte_carlo_stress_test(
    params: FinModelInput, top_cities: List[CityScoreDTO], *, n_simulations: int = 500, seed: int = 42,
) -> dict:
    """Согласованные шоки обеим стратегиям, локальный random.Random(seed).

    Распределения согласованы пользователем 11.11.2026: загрузка normal(0,6)
    п.п. с clipping 50..98, тариф uniform(.9,1.1) с clipping 3500..25000,
    переменные расходы uniform(1,1.2), сохранение субсидий uniform(.5,1).
    Это независимые гипотезы, не оцененная статистическая модель рисков.
    Коэффициенты накладываются на выбранный base/conservative; постоянные
    расходы не инфлируются повторно. win — контрактный score, не знак прибыли.
    Прибыльность: EBITDAR>=0. Интервалы вероятностей не подгоняются под ТЗ.
    """
    evaluate_hypotheses(params, top_cities)
    if isinstance(n_simulations, bool) or not isinstance(n_simulations, int) or n_simulations <= 0:
        raise ValueError("n_simulations должен быть положительным целым числом")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed должен быть целым числом")
    rng = Random(seed)
    hub_profits, p2p_profits = [], []
    wins = 0
    for _ in range(n_simulations):
        sampled = replace(params,
            load_factor_pct=min(98.0, max(50.0, params.load_factor_pct + rng.gauss(0, 6))),
            avg_fare_rub=min(25000.0, max(3500.0, params.avg_fare_rub * rng.uniform(.9, 1.1))))
        cost_multiplier, retention = rng.uniform(1, 1.2), rng.uniform(.5, 1)
        hub = _calculate(sampled, "hub", variable_cost_multiplier=cost_multiplier, subsidy_retention=retention)
        p2p = _calculate(sampled, "p2p", variable_cost_multiplier=cost_multiplier, subsidy_retention=retention)
        hub_profits.append(hub.ebitdar_mln_rub)
        p2p_profits.append(p2p.ebitdar_mln_rub)
        wins += p2p.annual_revenue_mln_rub * .45 + p2p.ebitdar_mln_rub * .55 >= hub.annual_revenue_mln_rub * .45 + hub.ebitdar_mln_rub * .55
    return {
        "p2p_prob_profitable_pct": round(sum(value >= 0 for value in p2p_profits) / n_simulations * 100, 6),
        "hub_prob_profitable_pct": round(sum(value >= 0 for value in hub_profits) / n_simulations * 100, 6),
        "p2p_win_probability_pct": round(wins / n_simulations * 100, 6),
        "p2p_ebitdar_p5_p50_p95": _linear_quantiles(p2p_profits),
        "hub_ebitdar_p5_p50_p95": _linear_quantiles(hub_profits),
        "n_simulations": n_simulations, "seed": seed,
        "assumptions": {
            "load_noise_std_pp": 6.0, "load_clip_pct": [50, 98],
            "fare_multiplier_uniform": [.9, 1.1], "fare_clip_rub": [3500, 25000],
            "variable_cost_multiplier_uniform": [1.0, 1.2],
            "subsidy_retention_uniform": [.5, 1.0], "scenario": params.scenario,
            "shared_shocks_between_strategies": True,
            "distribution_status": "Согласованные сценарные допущения, не эмпирическая калибровка",
        },
    }


def run_financial_monte_carlo(
    params: FinModelInput, top_cities: List[CityScoreDTO], n_samples: int = 1000, seed: int = 42,
) -> dict:
    """Асимметричный финансовый стресс, отдельный от прежнего stress_test.

    Независимые равномерные шоки: загрузка [-12,+4] п.п., сохранение субсидий
    [0,1], переменные расходы [1,1.2], тариф [.85,1.05]. Шоки общие для двух
    стратегий в каждой итерации. Применяются к выбранному сценарию; загрузка
    ограничена 50..98%, тариф 3500..25000 ₽. EBITDAR>0 строго, win по
    контрактному score=0.45*revenue+0.55*EBITDAR (равенство в пользу P2P).
    Это риск-сценарии ТЗ, не частотный прогноз по исторической статистике.
    """
    evaluate_hypotheses(params, top_cities)
    if isinstance(n_samples, bool) or not isinstance(n_samples, int) or n_samples <= 0:
        raise ValueError("n_samples должен быть положительным целым числом")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed должен быть целым числом")
    rng = Random(seed)
    profits = {"hub": [], "p2p": []}
    wins = 0
    for _ in range(n_samples):
        load_shift = rng.uniform(-12.0, 4.0)
        retention = rng.uniform(0.0, 1.0)
        cost_multiplier = rng.uniform(1.0, 1.2)
        fare_multiplier = rng.uniform(.85, 1.05)
        sampled = replace(params,
            load_factor_pct=min(98.0, max(50.0, params.load_factor_pct + load_shift)),
            avg_fare_rub=min(25000.0, max(3500.0, params.avg_fare_rub * fare_multiplier)))
        hub = _calculate(sampled, "hub", variable_cost_multiplier=cost_multiplier, subsidy_retention=retention)
        p2p = _calculate(sampled, "p2p", variable_cost_multiplier=cost_multiplier, subsidy_retention=retention)
        profits["hub"].append(hub.ebitdar_mln_rub)
        profits["p2p"].append(p2p.ebitdar_mln_rub)
        wins += p2p.annual_revenue_mln_rub * .45 + p2p.ebitdar_mln_rub * .55 >= hub.annual_revenue_mln_rub * .45 + hub.ebitdar_mln_rub * .55
    return {
        "p2p_prob_positive_ebitdar_pct": round(sum(p > 0 for p in profits["p2p"]) / n_samples * 100, 6),
        "hub_prob_positive_ebitdar_pct": round(sum(p > 0 for p in profits["hub"]) / n_samples * 100, 6),
        "p2p_win_prob_pct": round(wins / n_samples * 100, 6),
        "p2p_ebitdar_p5_p50_p95": _linear_quantiles(profits["p2p"]),
        "hub_ebitdar_p5_p50_p95": _linear_quantiles(profits["hub"]),
        "n_samples": n_samples, "seed": seed,
        "assumptions": {
            "load_shift_uniform_pp": [-12, 4], "load_clip_pct": [50, 98],
            "subsidy_retention_uniform": [0, 1], "variable_cost_multiplier_uniform": [1, 1.2],
            "fare_multiplier_uniform": [.85, 1.05], "fare_clip_rub": [3500, 25000],
            "scenario": params.scenario, "profitability_rule": "EBITDAR > 0",
            "winner_rule": "0.45 * revenue + 0.55 * EBITDAR; ties -> p2p",
            "shared_shocks_between_strategies": True,
            "quantiles": "linear interpolation at (n-1)*p; млн ₽",
            "distribution_status": "Сценарные распределения, не историческая калибровка",
        },
    }


SVX_TRANSIT_MARGIN_POOL_MLN = 1000.0  # Допущение: 15% потери = 150 млн ₽ из диапазона ТЗ.
CLASSIC_HUB_SVX_CANNIBALIZATION_SHARE = .15
SCISSOR_SVX_CANNIBALIZATION_SHARE = .025  # Сценарий <3%, не результат геометрической модели.


def evaluate_svx_kuf_cannibalization(params: FinModelInput, top_cities: List[CityScoreDTO]) -> dict:
    """Инкрементальная маржа НОВОЙ сети минус утрата маржи текущей базы SVX.

    15% и 2.5% — заданные доли отвлечения транзитного потока. Перенос этих
    долей на маржу предполагает одинаковую маржу пассажиров; маржинальный
    пул SVX=1000 млн ₽ — допущение, дающее потерю 150 млн ₽ в диапазоне ТЗ.
    Не смешиваем его с EBITDAR новой сети или всей авиакомпании. Финансовых
    данных базы SVX нет; сценарий не подтверждает фактическую каннибализацию.
    Геометрия отдельно проверяет все 8 пар GOJ/KZN/GSV/VOG -> MRV/PEE.
    Для возможности остановки в KUF принят критерий Dev 2: крюк <15%.
    Не подменяем им оценку спроса, расписания или подтверждение потери <3%.
    Фидер WZ-1033 показан как возможность; дополнительная маржа не начисляется
    без оценки пассажиров. Новый CAPEX базы ТОиР в KUF принят нулевым по
    архитектуре полухаба, но операционные расходы 115+48 млн ₽ сохранены.
    """
    from pathlib import Path
    from src.parsers.rosstat_loader import AIRPORT_COORDS, haversine_km

    comparison = evaluate_scissor_hub_economics(params, top_cities, scissor_hub_iata="KUF")
    evidence = []
    for origin in ("GOJ", "KZN", "GSV", "VOG"):
        for dest in ("MRV", "PEE"):
            direct = haversine_km(AIRPORT_COORDS[origin], AIRPORT_COORDS[dest])
            via = {hub: haversine_km(AIRPORT_COORDS[origin], AIRPORT_COORDS[hub])
                        + haversine_km(AIRPORT_COORDS[hub], AIRPORT_COORDS[dest])
                   for hub in ("SVX", "KUF")}
            kuf_detour = (via["KUF"] / direct - 1) * 100
            evidence.append({
                "origin_iata": origin, "dest_iata": dest,
                "direct_distance_km": round(direct, 3),
                "via_svx_distance_km": round(via["SVX"], 3),
                "via_kuf_distance_km": round(via["KUF"], 3),
                "svx_detour_pct": round((via["SVX"] / direct - 1) * 100, 3),
                "svx_extra_km": round(via["SVX"] - direct, 3),
                "kuf_detour_pct": round(kuf_detour, 3),
                "kuf_passes_15pct_detour": kuf_detour < 15.0,
                "saving_kuf_vs_svx_km": round(via["SVX"] - via["KUF"], 3),
            })
    adjusted = {}
    for key, share in (("classic_hub", CLASSIC_HUB_SVX_CANNIBALIZATION_SHARE),
                       ("scissor_hybrid", SCISSOR_SVX_CANNIBALIZATION_SHARE)):
        metrics = comparison[key]
        loss = SVX_TRANSIT_MARGIN_POOL_MLN * share
        adjusted[key] = {
            **metrics, "svx_cannibalization_pct": share * 100,
            "svx_margin_loss_mln_rub": loss,
            "net_ebitdar_after_svx_cannibalization_mln_rub": round(metrics["ebitdar_mln_rub"] - loss, 6),
        }
    root = Path(__file__).resolve().parents[2]
    routes = pd.read_parquet(root / "data/processed/routes_proof.parquet")
    feeder = routes[(routes["origin_iata"] == "SVX") & (routes["dest_iata"] == "KUF")]
    if feeder.empty:
        raise ValueError("В витрине Dev 1 отсутствует SVX->KUF")
    feeder_row = feeder.iloc[0]
    return {
        **adjusted, "pure_p2p_reference": comparison["pure_p2p"],
        "svx_transit_margin_pool_mln_rub": SVX_TRANSIT_MARGIN_POOL_MLN,
        "corridor_routes": evidence,
        "geometrically_supported_kuf_routes_count": sum(r["kuf_passes_15pct_detour"] for r in evidence),
        "svx_kuf_distance_km": round(haversine_km(AIRPORT_COORDS["SVX"], AIRPORT_COORDS["KUF"]), 3),
        "scissor_new_base_capex_mln_rub": 0.0,
        "scissor_new_base_fixed_cost_mln_rub": 0.0,
        "scissor_total_fixed_cost_mln_rub": comparison["scissor_hybrid"]["fixed_cost_mln_rub"],
        "feeder": {"flight_code": "WZ-1033", "origin_iata": "SVX", "dest_iata": "KUF",
                   "observed_weekly_flights": int(feeder_row["own_flights_weekly"]),
                   "source": str(feeder_row["proof_source"]),
                   "incremental_margin_included_mln_rub": 0.0,
                   "status": "Дополнительный подвоз возможен, прирост спроса не измерен"},
        "assumptions": {
            "cannibalization_status": "15%/2.5% и маржинальный пул 1000 млн ₽ — сценарий ТЗ, не измерение",
            "margin_allocation": "Пропорционально отвлеченному транзитному потоку",
            "geometry_status": "Гаверсинус по координатам Dev 1; не фактические воздушные трассы",
            "financial_scope": "Новая сеть минус потеря существующей маржи SVX; не весь EBITDAR компании",
            "capex_status": "Нет строительства новой базы ТОиР по проектной гипотезе; прочие инвестиции не оценены",
        },
    }


def get_assumptions_audit_table() -> dict:
    """Паспорт формул, сценарных коэффициентов и локальных первоисточников.

    8 пар RW и 21 запись перечня — проверка происхождения входных данных.
    Наличие расписания не калибрует себестоимость: фактических затрат, налета,
    расхода топлива и маржи рейсов в витринах нет. calibration_status поэтому
    явно not_empirically_calibrated; остатки к фактическим расходам не выдумываются.
    CASK-преимущество Dev 1 — снижение SJ относительно CRJ, а не обратная
    надбавка CRJ относительно SJ: 31% экономии соответствует ~45% надбавки.
    """
    import hashlib
    import json
    from pathlib import Path
    from src.parsers.build_dataset import (
        RW_FLIGHT_CODES, SUBSIDY_2026, SUBSIDY_SOURCE,
        FLIGHT_FIXED_COST_RUB, FUEL_COST_RUB_PER_KM,
        CRJ200_CASK_ADV_BASE_PCT, CRJ200_CASK_ADV_SLOPE, CRJ200_CASK_ADV_PEAK_KM,
    )
    from src.models.sj100_fleet import HUB_FLEET_FACTOR

    root = Path(__file__).resolve().parents[2]
    routes = pd.read_parquet(root / "data/processed/routes_proof.parquet")
    schedules = json.loads((root / "data/raw/schedules_raw.json").read_text(encoding="utf-8"))
    rows = []
    def entry(name, value, unit, source, limitation):
        rows.append({"assumption": name, "value": value, "unit": unit,
                     "source": source, "status": "model_assumption", "limitation": limitation})
    entry("sj100_distance_cost", {"fixed_rub": FLIGHT_FIXED_COST_RUB, "rub_per_km": FUEL_COST_RUB_PER_KM},
          "руб./односторонний рейс", "src/parsers/build_dataset.py", "385000+310*distance; фактических расходов для калибровки нет")
    entry("scenario_coefficients", {k: asdict(v) for k, v in _SCENARIOS.items()}, "множители и рубли",
          "ТЗ Dev 3; _SCENARIOS", "Спрос, стоимость, ставка субсидии и затраты базы — допущения")
    entry("average_flight_cost", {"hub": 645000, "p2p": 635000, "p2p_fixed_mln": 115}, "руб./рейс; млн ₽/год",
          "ТЗ; _calculate", "Средний рейс; переменная стоимость масштабируется seats/100")
    entry("loads", {"hub_adjustments_pp": [-2.5, 1.2, 3.2], "p2p_adjustments_pp": [2.4, -.8],
                    "hub_limits_pct": [52, 95], "p2p_limits_pct": [54, 95]}, "п.п. / %",
          "ТЗ; _effective_load", "Пороги частот: хаб <=3/4..5/>=6, P2P <=5/>=6; не оценка спроса по билетам")
    entry("fare_and_subsidy_mix", {"hub_fare_factor": .935, "p2p_fare_factor": 1.055,
                                   "hub_subsidized_share": .45, "p2p_subsidized_share": .65}, "доли",
          "ТЗ; _calculate", "Доли используются в средней модели; route_level использует флаги Dev 1")
    entry("accounting", {"weeks": 52, "legs_per_round_trip": 2, "belf_hub_clip_pct": [55, 96],
                          "belf_p2p_clip_pct": [52, 96], "winner_revenue_weight": .45, "winner_profit_weight": .55},
          "единицы модели", "ТЗ; _calculate/evaluate_hypotheses",
          "Полный год; пассажиры по плечам; выручка с субсидиями; EBITDAR до аренды/амортизации/процентов/налогов; clipped BELF не истинный порог вне границ")
    entry("route_network", {"fixed_cost_mln": 115, "subsidy_retention_pct": [0, 100]}, "млн ₽/год и %",
          "Уточнение пользователя; evaluate_route_level_economics", "2*52*частота из params; субсидия на оба плеча — допущение; распределение всей фиксированной суммы после отбора")
    entry("fleet", {"round_trips_per_week": ROUND_TRIPS_PER_AIRCRAFT_WEEK,
                    "hub_factor": HUB_FLEET_FACTOR, "p2p_factor": P2P_FLEET_FACTOR,
                    "minimum_hub": 3, "minimum_p2p": 2}, "безразмерные коэффициенты / борта",
          "ТЗ; src/models/sj100_fleet.py", "Укрупненная потребность; не подтверждает расписание и волны пересадок")
    entry("deliveries", {"base_pct": [0,0,0,0,15,30,45,65,85,100],
                         "conservative_pct": [0,0,0,0,0,10,25,45,70,100],
                         "reserve_base_limit": 6, "reserve_conservative_limit": 4}, "% потребности по кварталам",
          "ТЗ; build_sj100_delivery_roadmap", "2026 Q3..2028 Q4; не подтвержденный заказ/поставка; резерв требует проверки")
    entry("elasticity", FARE_ELASTICITY, "линейная эластичность", "ТЗ; simulate_fare_elasticity_curve", "Не регрессия по продажам; входная загрузка ограничена 50..98%")
    entry("digital", {"interline_load_pp": 3, "interline_cost_mln": 18, "ancillary_rub_per_pax": 650,
                      "distribution_saving_rub_per_pax": 180, "recovery_mln_per_10_routes": 22.5}, "п.п., руб., млн ₽/год",
          "ТЗ; evaluate_digital_one_click_impact", "Не результаты A/B-тестов; перекрестный эффект начисляется один раз")
    entry("scissor", {"coordination_mln_per_wave": SCISSOR_COORDINATION_COST_PER_WAVE_MLN,
                      "load_pp_per_wave": SCISSOR_LOAD_BOOST_PER_WAVE_PP,
                      "transit_share": SCISSOR_TRANSIT_SHARE, "transit_discount": SCISSOR_TRANSIT_FARE_DISCOUNT,
                      "connection_minutes": 75, "detour_limit_pct": 15}, "сценарные величины",
          "ТЗ и src/scoring/SCISSOR_HUB.md", "Геометрия не доказывает загрузку/экономию ТО/реализуемость пересадки")
    entry("svx_cannibalization", {"margin_pool_mln": SVX_TRANSIT_MARGIN_POOL_MLN,
                                 "classic_share": CLASSIC_HUB_SVX_CANNIBALIZATION_SHARE,
                                 "scissor_share": SCISSOR_SVX_CANNIBALIZATION_SHARE}, "млн ₽/год и доли",
          "Уточнение пользователя; evaluate_svx_kuf_cannibalization", "Пул 1000 млн ₽ выбран для потери 150 млн ₽ при 15%; не финансовая отчетность SVX")
    entry("financial_stress", {"load_shift_pp": [-12,4], "subsidy_retention": [0,1],
                               "variable_cost_factor": [1,1.2], "fare_factor": [.85,1.05]}, "равномерные интервалы",
          "Уточнение пользователя; run_financial_monte_carlo", "Независимые факторы, общие для стратегий; не эмпирические вероятности")
    entry("legacy_stress", {"load_sigma_pp": 6, "subsidy_retention": [.5,1],
                            "variable_cost_factor": [1,1.2], "fare_factor": [.9,1.1]}, "нормальная загрузка; равномерные множители",
          "ТЗ; run_monte_carlo_stress_test", "Отдельный прежний сценарий, отличается от нового финансового стресса")
    entry("market_and_scaling", {"rf_pax": TOTAL_RF_MARKET_PAX_2025, "rw_base_pax": RED_WINGS_BASE_PAX_2025,
                                "s7_share_pct": S7_REFERENCE_MARKET_SHARE_PCT, "ural_share_pct": URAL_REFERENCE_MARKET_SHARE_PCT,
                                "wave_routes": [65,120], "target_pax_mln": [9.15,14.15],
                                "tu214_seats": 210, "ms21_seats": 211}, "пассажиры, %, кресла",
          "ТЗ; project_path_to_top2_airline", "База RW 4.465 млн — командный сценарий, в кейсе также 2.7 млн; рынок/конкуренты постоянны, флот и цели условны")
    entry("crj200_cask_comparison", {"sj100_saving_at_peak_pct": CRJ200_CASK_ADV_BASE_PCT,
                                   "peak_distance_km": CRJ200_CASK_ADV_PEAK_KM,
                                   "slope_pp_per_km": CRJ200_CASK_ADV_SLOPE, "sj100_seats":100, "crj200_seats":50},
          "% снижения CASK SJ относительно CRJ", "src/parsers/build_dataset.py",
          "Формула Dev 1, не наблюденный расход CRJ; обратная надбавка CRJ считается saving/(100-saving)")
    flights, seen = [], set()
    for (origin, dest), code in RW_FLIGHT_CODES.items():
        key = tuple(sorted((origin, dest)))
        if key in seen:
            continue
        seen.add(key)
        match = routes[(routes.origin_iata == origin) & (routes.dest_iata == dest)]
        if len(match) != 1:
            raise ValueError(f"Нет однозначного направления {origin}->{dest} в витрине")
        row = match.iloc[0]
        cache = [r for r in schedules if r["origin_iata"] == origin and r["dest_iata"] == dest and r["own_operator"]]
        model_cost = FLIGHT_FIXED_COST_RUB + FUEL_COST_RUB_PER_KM * float(row["distance_km"])
        saving = float(row["crj200_cask_advantage_pct"])
        flights.append({
            "flight_code": code, "reverse_flight_code": RW_FLIGHT_CODES.get((dest, origin)),
            "origin_iata": origin, "dest_iata": dest,
            "weekly_flights_observed": int(row["own_flights_weekly"]),
            "source_urls": sorted({r["source"] for r in cache}),
            "observation_weeks": sorted({r["week"] for r in cache}),
            "distance_km": float(row["distance_km"]), "model_flight_cost_rub": model_cost,
            "actual_flight_cost_rub": None, "calibration_residual_rub": None,
            "sj100_cask_rub_per_seat_km": model_cost / (100 * float(row["distance_km"])),
            "sj100_saving_vs_crj_pct": saving,
            "implied_crj_premium_vs_sj_pct": saving / (100 - saving) * 100,
            "calibration_status": "not_empirically_calibrated",
            "schedule_status": "observed_in_dev1_cache" if cache else "not_found_in_cache",
        })
    subsidies = [{"origin_iata": o, "dest_iata": d, "operator": value[0],
                  "weekly_flights": value[1], "period": value[2],
                  "source": SUBSIDY_SOURCE, "source_url": "https://favt.gov.ru/",
                  "local_reference": "src/parsers/build_dataset.py:SUBSIDY_2026",
                  "status": "local_transcription_not_live_verified"}
                 for (o, d), value in SUBSIDY_2026.items()]
    files = ["data/processed/routes_proof.parquet", "data/raw/schedules_raw.json",
             "src/parsers/build_dataset.py", "src/scoring/SCISSOR_HUB.md"]
    return {
        "assumptions": rows, "rw_flight_validation": flights,
        "rw_route_pairs_count": len(flights), "rw_directed_flight_codes_count": len(RW_FLIGHT_CODES),
        "subsidy_register": subsidies, "subsidized_directed_routes_count": len(subsidies),
        "calibration": {"status": "not_empirically_calibrated",
                        "reason": "Есть расписания и модельные расходы; фактические затраты RW/CRJ и пассажирская маржа отсутствуют",
                        "needed": ["фактические расходы рейса", "налет/расход топлива", "загрузка и тариф продажи", "фактические выплаты субсидий"]},
        "source_sha256": {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in files},
    }
