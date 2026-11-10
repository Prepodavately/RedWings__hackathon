"""Юнит-экономика новой сети SJ-100 — участник №3.

Источник коэффициентов: TZ_KOMANDY_RED_WINGS.md, разделы 5.3–5.4.
Это сценарные допущения команды, а не подтвержденные тарифы/затраты/субсидии.
Промежуточные поправки загрузки (+1.2 п.п. хабу при частоте 4–5,
-0.8 п.п. P2P при частоте >5) взяты из существующего aviationModel.ts.

Единицы: частота — пары рейсов/неделю; F = маршруты * частота * 2 * 52.
Стоимость 645/635 тыс. руб. применяется к ОДНОМУ плечу, согласно формулам
ТЗ (слова «парного плеча» в его тексте неоднозначны). При изменении числа
кресел стоимость рейса хаба масштабируется пропорционально seats/100
по уточненному ТЗ от 10.11.2026. Формулы P2P пока из предыдущего ТЗ.
Выручка включает билетную выручку и сценарные субсидии. EBITDAR = выручка
минус модельные операционные расходы, до аренды/амортизации/процентов/налогов.
BELF — фактическая загрузка, не значение входного ползунка до синергии;
для хаба показатель ограничен 55..96% по уточненному ТЗ. Это ограниченный
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

from dataclasses import dataclass, replace
from math import isfinite
from typing import Iterable, List, Optional, Tuple

from src.models.sj100_fleet import calculate_required_sj100_fleet
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
    if code == "hub":
        return round(min(MAX_LOAD_FACTOR_PCT, max(52.0, load)), 1)
    return max(0.0, min(MAX_LOAD_FACTOR_PCT, load))



def _calculate(
    params: FinModelInput, code: HypothesisCode, effective_load: Optional[float] = None
) -> HypothesisResultDTO:
    scenario = _SCENARIOS[params.scenario]
    is_hub = code == "hub"
    flights = params.active_routes_count * params.weekly_freq_per_route * 2 * WEEKS_PER_YEAR
    seats = flights * params.aircraft_seats
    load = _effective_load(params, code) if effective_load is None else effective_load
    passengers = round(seats * load / 100)
    fare = params.avg_fare_rub * (0.935 if is_hub else 1.055)
    if is_hub:
        fare = round(fare)
    subsidy = flights * (0.45 if is_hub else 0.65) * scenario.subsidy_per_flight_rub
    fixed_cost = scenario.hub_fixed_cost_rub if is_hub else 115_000_000.0
    seat_factor = params.aircraft_seats / 100 if is_hub else 1.0
    cost = flights * (645_000 if is_hub else 635_000) * scenario.cost_factor * seat_factor + fixed_cost
    revenue = passengers * fare + subsidy
    if is_hub:
        cost = round(cost / 1_000_000, 1) * 1_000_000
        revenue = round(revenue / 1_000_000, 1) * 1_000_000
    ebitdar_mln = (revenue - cost) / 1_000_000
    margin = ebitdar_mln / max(1.0, revenue / 1_000_000) * 100
    share = passengers / TOTAL_RF_MARKET_PAX_2025 * 100
    belf = max(0.0, (cost - subsidy) / max(1.0, seats * fare) * 100)
    if is_hub:
        ebitdar_mln = round(ebitdar_mln, 1)
        margin = round(ebitdar_mln / max(1.0, revenue / 1_000_000) * 100, 1)
        share = round(share, 3)
        belf = round(min(96.0, max(55.0, belf)), 1)
    return HypothesisResultDTO(
        code=code,
        title=(f"Гипотеза А: Региональный хаб ({params.hub_iata})" if is_hub
               else "Гипотеза Б: Прямые межрегиональные рейсы (P2P)"),
        annual_passengers=passengers,
        annual_revenue_mln_rub=revenue / 1_000_000,
        ebitdar_mln_rub=ebitdar_mln,
        ebitdar_margin_pct=margin,
        market_share_delta_pct=share,
        required_aircraft_sj100=calculate_required_sj100_fleet(
            params.active_routes_count, params.weekly_freq_per_route, is_hub
        ),
        breakeven_load_factor_pct=belf,
    )


def evaluate_hypotheses(
    params: FinModelInput, top_cities: List[CityScoreDTO]
) -> ComparisonBundleDTO:
    """Сравнить обе стратегии в выбранном сценарии, не меняя входные DTO.

    Победитель: максимальная доля рынка среди вариантов с EBITDAR >= 0;
    затем EBITDAR, меньший флот и P2P при полном равенстве. Если оба убыточны,
    обязательное поле winner обозначает вариант с меньшим убытком, а rationale
    явно запрещает трактовать это как рекомендацию запуска.
    Некорректные входы/выбор хаба вне переданного списка вызывают ValueError.
    """
    _validate_params(params)
    if not top_cities:
        raise ValueError("Список городов top_cities не может быть пустым")
    hub_city = next((city for city in top_cities if city.iata == params.hub_iata), None)
    if hub_city is None:
        raise ValueError(f"Город hub_iata={params.hub_iata!r} не найден в переданном списке городов")
    hub, p2p = _calculate(params, "hub"), _calculate(params, "p2p")
    viable = [result for result in (hub, p2p) if result.ebitdar_mln_rub >= 0]
    if viable:
        winner = max(viable, key=lambda result: (
            result.market_share_delta_pct, result.ebitdar_mln_rub,
            -result.required_aircraft_sj100, result.code == "p2p",
        ))
        decision = "Максимальный прирост доли рынка среди вариантов с неотрицательным EBITDAR."
    else:
        winner = max((hub, p2p), key=lambda result: (
            result.ebitdar_mln_rub, result.market_share_delta_pct,
            -result.required_aircraft_sj100, result.code == "p2p",
        ))
        decision = ("Обе стратегии убыточны: запуск не рекомендуется. "
                    "winner обозначает только вариант с меньшим убытком.")
    rationale = (
        f"{decision} {winner.title}: {winner.annual_passengers:,} пасс./год, "
        f"+{winner.market_share_delta_pct:.3f} п.п. рынка, "
        f"EBITDAR {winner.ebitdar_mln_rub:.2f} млн ₽, "
        f"потребность {winner.required_aircraft_sj100} SJ-100. "
        f"Сценарий: {params.scenario}; частота: {params.weekly_freq_per_route} "
        "пар рейсов/неделю. Расчет на полный год после поставок не ранее 2027-H2; "
        "субсидии и спрос — допущения, требующие проверки по маршрутам."
    )
    if not hub_city.is_top3:
        rationale += f" Хаб {hub_city.iata}: ранг {hub_city.rank} в переданном рейтинге; выбор вне Топ-3 допустим."
    return ComparisonBundleDTO(hub=hub, p2p=p2p, winner=winner.code, rationale=rationale)


def simulate_fare_elasticity_curve(
    params: FinModelInput,
    hypothesis: HypothesisCode = "p2p",
    fares: Optional[Iterable[float]] = None,
) -> List[Tuple[float, float, float, float]]:
    """Точки (базовый тариф ₽, фактическая загрузка %, выручка млн ₽, EBITDAR млн ₽).

    L(p) = L(p0) * (p/p0)**(-0.65), ограниченная 0..95%. L(p0) уже включает
    синергию и сценарий, повторно они не применяются. Сетка по умолчанию:
    5500..13500 с шагом 500 плюс текущий тариф. Гипотеза по умолчанию — P2P.
    Эластичность постоянная; это не парабола и не гарантия внутреннего оптимума.
    """
    _validate_params(params)
    if hypothesis not in ("hub", "p2p"):
        raise ValueError("hypothesis должен быть 'hub' или 'p2p'")
    if fares is None:
        fares = sorted(set(range(5500, 13501, 500)) | {params.avg_fare_rub})
    reference_load = _effective_load(params, hypothesis)
    points = []
    for fare in fares:
        _finite_number("fare", fare)
        if fare <= 0:
            raise ValueError("fare должен быть положительным")
        load = min(MAX_LOAD_FACTOR_PCT,
                   reference_load * (fare / params.avg_fare_rub) ** FARE_ELASTICITY)
        result = _calculate(replace(params, avg_fare_rub=fare), hypothesis, load)
        points.append((fare, load, result.annual_revenue_mln_rub, result.ebitdar_mln_rub))
    return points
