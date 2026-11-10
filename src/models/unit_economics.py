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
from typing import List, Sequence

from src.models.sj100_fleet import (
    P2P_FLEET_FACTOR, ROUND_TRIPS_PER_AIRCRAFT_WEEK, calculate_required_sj100_fleet,
)
from src.schemas.contracts import (
    CityScoreDTO,
    ComparisonBundleDTO,
    FinModelInput,
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


def _calculate(params: FinModelInput, code: HypothesisCode) -> HypothesisResultDTO:
    scenario = _SCENARIOS[params.scenario]
    is_hub = code == "hub"
    flights = params.active_routes_count * params.weekly_freq_per_route * 2 * WEEKS_PER_YEAR
    seats = flights * params.aircraft_seats
    passengers = int(round(seats * (_effective_load(params, code) / 100.0)))
    fare = round(params.avg_fare_rub * (0.935 if is_hub else 1.055))
    subsidy_mln = flights * (0.45 if is_hub else 0.65) * scenario.subsidy_per_flight_rub / 1e6
    fixed_cost_mln = scenario.hub_fixed_cost_rub / 1e6 if is_hub else 115.0
    cost_per_flight = (645_000 if is_hub else 635_000) * scenario.cost_factor * (params.aircraft_seats / 100.0)
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
