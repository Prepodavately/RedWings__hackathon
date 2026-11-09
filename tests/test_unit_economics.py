"""Контрольные расчеты и стресс-тесты модели участника №3."""

from dataclasses import asdict, replace
from itertools import product
from math import isfinite

import pytest

from src.models.sj100_fleet import calculate_required_sj100_fleet
from src.models.unit_economics import evaluate_hypotheses, simulate_fare_elasticity_curve
from src.schemas.contracts import CityScoreDTO, ComparisonBundleDTO, FinModelInput


@pytest.fixture
def cities():
    return [
        CityScoreDTO("KUF", "Самара", "ПФО", 2.74, 3.58, 89.26, 1, True),
        CityScoreDTO("GOJ", "Нижний Новгород", "ПФО", 2.08, 1.48, 73.91, 2, True),
        CityScoreDTO("SVX", "Екатеринбург", "УФО", 2.24, 7.95, 71.4, 3, True),
    ]


@pytest.mark.parametrize("scenario, expected", [
    ("base", (
        (443040, 3818.93616, 154.93616, 81.4063387593),
        (449280, 4471.61936, 1054.61936, 63.5144870927),
    )),
    ("conservative", (
        (385445, 3249.58503, -737.73497, 92.1877142465),
        (390874, 3785.025388, 103.865388, 72.9141711369),
    )),
])
def test_reference_scenarios(cities, scenario, expected):
    # 5200 односторонних рейсов, 520000 кресел. Например, P2P base:
    # 449280 * 8862 + 5200 * .65 * 145000 = 4 471 619 360 руб.
    result = evaluate_hypotheses(FinModelInput(scenario=scenario), cities)
    assert isinstance(result, ComparisonBundleDTO)
    assert result.winner == "p2p"
    for metrics, (pax, revenue, profit, belf) in zip((result.hub, result.p2p), expected):
        assert metrics.annual_passengers == pax
        assert metrics.annual_revenue_mln_rub == pytest.approx(revenue)
        assert metrics.ebitdar_mln_rub == pytest.approx(profit)
        assert metrics.breakeven_load_factor_pct == pytest.approx(belf)
        assert metrics.ebitdar_margin_pct == pytest.approx(profit / revenue * 100)
        assert metrics.market_share_delta_pct == pytest.approx(pax / 108_900_000 * 100)
    assert result.hub.required_aircraft_sj100 == 15
    assert result.p2p.required_aircraft_sj100 == 13


@pytest.mark.parametrize("frequency, hub_load, p2p_load", [
    (2, 81.5, 86.4), (3, 81.5, 86.4), (4, 85.2, 86.4),
    (5, 85.2, 86.4), (6, 87.2, 83.2), (10, 87.2, 83.2),
])
def test_frequency_thresholds(cities, frequency, hub_load, p2p_load):
    result = evaluate_hypotheses(FinModelInput(weekly_freq_per_route=frequency), cities)
    capacity = 10 * frequency * 2 * 52 * 100
    assert result.hub.annual_passengers == round(capacity * hub_load / 100)
    assert result.p2p.annual_passengers == round(capacity * p2p_load / 100)


@pytest.mark.parametrize("scenario", ["base", "conservative"])
@pytest.mark.parametrize("frequency", [2, 5, 6])
def test_zero_demand_has_no_passengers_and_does_not_recommend_launch(cities, scenario, frequency):
    result = evaluate_hypotheses(FinModelInput(
        load_factor_pct=0, scenario=scenario, weekly_freq_per_route=frequency,
    ), cities)
    for metrics in (result.hub, result.p2p):
        assert metrics.annual_passengers == 0
        assert metrics.market_share_delta_pct == 0
        assert metrics.ebitdar_mln_rub < 0
    assert "запуск не рекомендуется" in result.rationale


def test_winner_uses_market_growth_subject_to_profitability(cities):
    high_frequency = FinModelInput(weekly_freq_per_route=6, load_factor_pct=85)
    result = evaluate_hypotheses(high_frequency, cities)
    assert result.hub.annual_passengers > result.p2p.annual_passengers
    assert result.hub.ebitdar_mln_rub > 0
    assert result.winner == "hub"
    conservative = evaluate_hypotheses(replace(high_frequency, scenario="conservative"), cities)
    assert conservative.hub.ebitdar_mln_rub < 0 < conservative.p2p.ebitdar_mln_rub
    assert conservative.winner == "p2p"


@pytest.mark.parametrize("code, adjustment", [("hub", 1.2), ("p2p", 2.4)])
def test_breakeven_load_is_the_profit_sign_boundary(cities, code, adjustment):
    params = FinModelInput()
    belf = getattr(evaluate_hypotheses(params, cities), code).breakeven_load_factor_pct
    below = evaluate_hypotheses(replace(params, load_factor_pct=belf - adjustment - .1), cities)
    above = evaluate_hypotheses(replace(params, load_factor_pct=belf - adjustment + .1), cities)
    assert getattr(below, code).ebitdar_mln_rub < 0 < getattr(above, code).ebitdar_mln_rub


def test_unreachable_breakeven_is_not_hidden_by_clipping(cities):
    result = evaluate_hypotheses(FinModelInput(avg_fare_rub=1000), cities)
    assert result.hub.breakeven_load_factor_pct > 100
    assert result.p2p.breakeven_load_factor_pct > 100
    assert "запуск не рекомендуется" in result.rationale


@pytest.mark.parametrize("code", ["hub", "p2p"])
def test_seat_capacity_changes_revenue_but_not_fixed_flight_cost(cities, code):
    small = getattr(evaluate_hypotheses(FinModelInput(aircraft_seats=93), cities), code)
    large = getattr(evaluate_hypotheses(FinModelInput(aircraft_seats=103), cities), code)
    assert large.annual_passengers > small.annual_passengers
    assert large.annual_revenue_mln_rub > small.annual_revenue_mln_rub
    assert large.annual_revenue_mln_rub - large.ebitdar_mln_rub == pytest.approx(
        small.annual_revenue_mln_rub - small.ebitdar_mln_rub
    )


@pytest.mark.parametrize("field, value", [
    ("load_factor_pct", -1), ("load_factor_pct", 101),
    ("load_factor_pct", float("nan")), ("load_factor_pct", float("inf")),
    ("avg_fare_rub", 0), ("avg_fare_rub", -100), ("avg_fare_rub", float("inf")),
    ("avg_fare_rub", "8400"), ("avg_fare_rub", True),
    ("weekly_freq_per_route", 0), ("weekly_freq_per_route", 11),
    ("weekly_freq_per_route", 5.5), ("weekly_freq_per_route", True),
    ("active_routes_count", 7), ("active_routes_count", 13),
    ("aircraft_seats", 0), ("aircraft_seats", 104),
    ("scenario", "optimistic"), ("hub_iata", "XXX"), ("hub_iata", ""),
])
def test_invalid_inputs_fail_explicitly(cities, field, value):
    with pytest.raises(ValueError):
        evaluate_hypotheses(replace(FinModelInput(), **{field: value}), cities)


def test_selected_hub_must_be_in_top3_and_inputs_are_not_mutated(cities):
    params = FinModelInput(hub_iata="GOJ")
    before = (asdict(params), [asdict(city) for city in cities])
    assert "GOJ" in evaluate_hypotheses(params, cities).hub.title
    assert before == (asdict(params), [asdict(city) for city in cities])
    with pytest.raises(ValueError, match="Топ-3"):
        evaluate_hypotheses(params, [])
    with pytest.raises(ValueError, match="Топ-3"):
        evaluate_hypotheses(params, [replace(city, is_top3=False) for city in cities])


def test_dashboard_grid_preserves_capacity_and_accounting(cities):
    for scenario, freq, seats, routes, load, fare in product(
        ("base", "conservative"), (2, 5, 6, 10), (93, 100, 103),
        (8, 10, 12), (65, 84, 95, 100), (5500, 8400, 13500),
    ):
        params = FinModelInput(load, fare, freq, seats, routes, scenario)
        result = evaluate_hypotheses(params, cities)
        capacity = routes * freq * 2 * 52 * seats
        for metric in (result.hub, result.p2p):
            assert 0 <= metric.annual_passengers <= round(capacity * .95)
            assert metric.ebitdar_mln_rub < metric.annual_revenue_mln_rub
            assert all(isfinite(value) for value in asdict(metric).values()
                       if isinstance(value, (int, float)))


@pytest.mark.parametrize("code", ["hub", "p2p"])
@pytest.mark.parametrize("scenario", ["base", "conservative"])
def test_elasticity_curve_has_anchor_and_decreasing_load(cities, code, scenario):
    params = FinModelInput(scenario=scenario)
    reference = getattr(evaluate_hypotheses(params, cities), code)
    low, anchor, high = simulate_fare_elasticity_curve(params, code, [7000, 8400, 10000])
    assert low[1] > anchor[1] > high[1]
    assert high[1] == pytest.approx(anchor[1] * (10000 / 8400) ** -.65)
    assert anchor[2] == pytest.approx(reference.annual_revenue_mln_rub)
    assert anchor[3] == pytest.approx(reference.ebitdar_mln_rub)
    assert all(0 <= point[1] <= 95 for point in (low, anchor, high))
    assert params.avg_fare_rub == 8400


def test_elasticity_default_grid_and_bad_arguments():
    points = simulate_fare_elasticity_curve(FinModelInput())
    assert len(points) == 18
    assert [point[0] for point in points] == sorted({point[0] for point in points})
    assert points[0][0] == 5500 and points[-1][0] == 13500
    for fare in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            simulate_fare_elasticity_curve(FinModelInput(), fares=[fare])
    with pytest.raises(ValueError):
        simulate_fare_elasticity_curve(FinModelInput(), hypothesis="invalid")


@pytest.mark.parametrize("routes, frequency, is_hub, expected", [
    (10, 5, True, 15), (10, 5, False, 13),
    (0, 5, True, 0), (10, 0, False, 0),
    (1, 1, True, 3), (1, 1, False, 2), (12, 10, True, 35),
])
def test_fleet_rounds_up_and_handles_empty_network(routes, frequency, is_hub, expected):
    assert calculate_required_sj100_fleet(routes, frequency, is_hub) == expected


@pytest.mark.parametrize("routes, frequency, is_hub", [
    (-1, 5, True), (10, -1, False), (10.5, 5, True),
    (True, 5, True), (10, float("nan"), True), (10, 5, "hub"),
])
def test_fleet_rejects_invalid_inputs(routes, frequency, is_hub):
    with pytest.raises(ValueError):
        calculate_required_sj100_fleet(routes, frequency, is_hub)
