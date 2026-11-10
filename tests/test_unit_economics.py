"""Контрольные расчеты и стресс-тесты модели участника №3."""

from dataclasses import asdict, replace
from itertools import product
from math import isfinite

import pytest

from src.models.sj100_fleet import calculate_required_sj100_fleet, build_sj100_delivery_roadmap
from src.models.unit_economics import (evaluate_hypotheses, simulate_fare_elasticity_curve,
    evaluate_digital_one_click_impact, project_path_to_top2_airline)
from src.schemas.contracts import CityScoreDTO, ComparisonBundleDTO, FinModelInput, HypothesisResultDTO


@pytest.fixture
def cities():
    return [
        CityScoreDTO("KUF", "Самара", "ПФО", 2.74, 3.58, 89.26, 1, True),
        CityScoreDTO("GOJ", "Нижний Новгород", "ПФО", 2.08, 1.48, 73.91, 2, True),
        CityScoreDTO("SVX", "Екатеринбург", "УФО", 2.24, 7.95, 71.4, 3, True),
    ]


@pytest.mark.parametrize("scenario, expected", [
    ("base", (
        (443040, 3818.9, 154.9, 81.4),
        (449280, 4471.6, 1054.6, 63.5),
    )),
    ("conservative", (
        (385320, 3248.6, -738.7, 92.2),
        (391040, 3786.5, 105.3, 72.9),
    )),
])
def test_reference_scenarios(cities, scenario, expected):
    # 5200 односторонних рейсов, 520000 кресел. Например, P2P base:
    # 449280 * 8862 + 5200 * .65 * 145000 = 4 471 619 360 руб.
    result = evaluate_hypotheses(FinModelInput(scenario=scenario), cities)
    assert isinstance(result, ComparisonBundleDTO)
    assert result.winner == "p2p"
    for metrics, (pax, revenue, profit, belf) in zip((result.hub, result.p2p), expected):
        assert isinstance(metrics, HypothesisResultDTO)
        assert metrics.annual_passengers == pax
        assert metrics.annual_revenue_mln_rub == pytest.approx(revenue)
        assert metrics.ebitdar_mln_rub == pytest.approx(profit)
        assert metrics.breakeven_load_factor_pct == pytest.approx(belf)
        assert metrics.ebitdar_margin_pct == pytest.approx(round(profit / revenue * 100, 1))
        assert metrics.market_share_delta_pct == pytest.approx(round(pax / 108_900_000 * 100, 3))
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


def test_zero_load_is_rejected(cities):
    with pytest.raises(ValueError, match="load_factor_pct"):
        evaluate_hypotheses(FinModelInput(load_factor_pct=0), cities)


def test_winner_uses_weighted_revenue_and_profit(cities):
    high_frequency = FinModelInput(weekly_freq_per_route=6, load_factor_pct=85)
    result = evaluate_hypotheses(high_frequency, cities)
    assert result.hub.annual_passengers > result.p2p.annual_passengers
    assert result.hub.ebitdar_mln_rub > 0
    assert result.winner == "p2p"
    assert result.p2p.annual_revenue_mln_rub * .45 + result.p2p.ebitdar_mln_rub * .55 > result.hub.annual_revenue_mln_rub * .45 + result.hub.ebitdar_mln_rub * .55
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


def test_clipped_breakeven_keeps_loss_warning(cities):
    result = evaluate_hypotheses(FinModelInput(avg_fare_rub=3500), cities)
    assert result.hub.breakeven_load_factor_pct == 96.0
    assert result.p2p.breakeven_load_factor_pct == 96.0
    assert "запуск не рекомендуется" in result.rationale


@pytest.mark.parametrize("code", ["hub", "p2p"])
def test_seat_capacity_changes_revenue_and_hub_cost(cities, code):
    small = getattr(evaluate_hypotheses(FinModelInput(aircraft_seats=93), cities), code)
    large = getattr(evaluate_hypotheses(FinModelInput(aircraft_seats=103), cities), code)
    assert large.annual_passengers > small.annual_passengers
    assert large.annual_revenue_mln_rub > small.annual_revenue_mln_rub
    if code == "hub":
        assert large.annual_revenue_mln_rub - large.ebitdar_mln_rub == pytest.approx(3764.6)
        assert small.annual_revenue_mln_rub - small.ebitdar_mln_rub == pytest.approx(3429.2)
        return
    assert large.annual_revenue_mln_rub - large.ebitdar_mln_rub == pytest.approx(3516.1)
    assert small.annual_revenue_mln_rub - small.ebitdar_mln_rub == pytest.approx(3185.9)


@pytest.mark.parametrize("field, value", [
    ("load_factor_pct", -1), ("load_factor_pct", 101),
    ("load_factor_pct", float("nan")), ("load_factor_pct", float("inf")),
    ("avg_fare_rub", 0), ("avg_fare_rub", -100), ("avg_fare_rub", float("inf")),
    ("avg_fare_rub", "8400"), ("avg_fare_rub", True),
    ("weekly_freq_per_route", 0), ("weekly_freq_per_route", 22),
    ("weekly_freq_per_route", 5.5), ("weekly_freq_per_route", True),
    ("active_routes_count", 0), ("active_routes_count", 51),
    ("aircraft_seats", 0), ("aircraft_seats", 221),
    ("scenario", "optimistic"), ("hub_iata", "XXX"), ("hub_iata", ""),
])
def test_invalid_inputs_fail_explicitly(cities, field, value):
    with pytest.raises(ValueError):
        evaluate_hypotheses(replace(FinModelInput(), **{field: value}), cities)


def test_selected_hub_must_be_in_list_and_inputs_are_not_mutated(cities):
    params = FinModelInput(hub_iata="GOJ")
    before = (asdict(params), [asdict(city) for city in cities])
    assert "GOJ" in evaluate_hypotheses(params, cities).hub.title
    assert before == (asdict(params), [asdict(city) for city in cities])
    with pytest.raises(ValueError, match="пустым"):
        evaluate_hypotheses(params, [])
    outside_top3 = [replace(city, is_top3=False, rank=7) for city in cities]
    result = evaluate_hypotheses(params, outside_top3)
    assert "ранг 7" in result.rationale
    with pytest.raises(ValueError, match="не найден"):
        evaluate_hypotheses(params, [cities[0]])


def test_dashboard_grid_preserves_capacity_and_accounting(cities):
    for scenario, freq, seats, routes, load, fare in product(
        ("base", "conservative"), (2, 5, 6, 10), (93, 100, 103),
        (8, 10, 12), (50, 84, 95, 98), (5500, 8400, 13500),
    ):
        params = FinModelInput(load, fare, freq, seats, routes, scenario)
        result = evaluate_hypotheses(params, cities)
        capacity = routes * freq * 2 * 52 * seats
        for metric in (result.hub, result.p2p):
            assert 0 <= metric.annual_passengers <= round(capacity * .95)
            assert metric.ebitdar_mln_rub < metric.annual_revenue_mln_rub
            assert all(isfinite(value) for value in asdict(metric).values()
                       if isinstance(value, (int, float)))


@pytest.mark.parametrize("routes, frequency, is_hub, expected", [
    (10, 5, True, 15), (10, 5, False, 13),
    (1, 1, True, 3), (1, 1, False, 2), (12, 10, True, 35),
])
def test_fleet_rounds_up(routes, frequency, is_hub, expected):
    assert calculate_required_sj100_fleet(routes, frequency, is_hub) == expected


@pytest.mark.parametrize("routes, frequency, is_hub", [
    (0, 5, True), (10, 0, False), (-1, 5, True), (10, -1, False), (10.5, 5, True),
    (True, 5, True), (10, float("nan"), True), (10, 5, "hub"),
])
def test_fleet_rejects_invalid_inputs(routes, frequency, is_hub):
    with pytest.raises(ValueError):
        calculate_required_sj100_fleet(routes, frequency, is_hub)


@pytest.mark.parametrize("iata", ["KUF", "GOJ", "SVX", "KZN", "UFA", "CEK"])
def test_real_scoring_accepts_all_sidebar_and_candidate_hubs(iata):
    from src.scoring.city_scorer import get_scored_cities
    from src.schemas.contracts import ScoringWeights

    cities = get_scored_cities(ScoringWeights())
    assert len(cities) == 12
    if iata == "GOJ":
        assert not next(city for city in cities if city.iata == iata).is_top3
    result = evaluate_hypotheses(FinModelInput(hub_iata=iata), cities)
    assert iata in result.hub.title
    assert result.hub.annual_revenue_mln_rub == 3818.9


@pytest.mark.parametrize("load,fare,freq,seats,routes", [
    (50, 3500, 1, 75, 1), (98, 25000, 21, 220, 50),
])
def test_expanded_input_boundaries(cities, load, fare, freq, seats, routes):
    result = evaluate_hypotheses(FinModelInput(load, fare, freq, seats, routes), cities)
    assert result.hub.required_aircraft_sj100 >= 3
    assert result.p2p.required_aircraft_sj100 >= 2


def test_hub_lower_load_floor_and_upper_cap(cities):
    low = evaluate_hypotheses(FinModelInput(load_factor_pct=50, scenario="conservative"), cities)
    high = evaluate_hypotheses(FinModelInput(load_factor_pct=98), cities)
    assert low.hub.annual_passengers == 270400  # 520000 * 52%
    assert high.hub.annual_passengers == 494000  # 520000 * 95%


@pytest.mark.parametrize("scenario", ["base", "conservative"])
def test_elasticity_anchor_and_load_response(cities, scenario):
    params = FinModelInput(scenario=scenario)
    original = asdict(params)
    low, anchor, high = simulate_fare_elasticity_curve(params, cities, [7000, 8400, 11000])
    assert low["effective_load_factor_pct"] > anchor["effective_load_factor_pct"] > high["effective_load_factor_pct"]
    assert high["effective_load_factor_pct"] == pytest.approx(67.1)
    base = evaluate_hypotheses(params, cities)
    for code in ("hub", "p2p"):
        assert anchor[f"{code}_revenue_mln_rub"] == getattr(base, code).annual_revenue_mln_rub
        assert anchor[f"{code}_ebitdar_mln_rub"] == getattr(base, code).ebitdar_mln_rub
    assert asdict(params) == original


def test_elasticity_defaults_and_actual_optimum(cities):
    points = simulate_fare_elasticity_curve(FinModelInput(), cities)
    assert len(points) == 9
    assert max(points, key=lambda p: p["p2p_ebitdar_mln_rub"])["fare_rub"] == 10500
    flat = simulate_fare_elasticity_curve(FinModelInput(), cities, elasticity=0)
    assert all(p["effective_load_factor_pct"] == 84 for p in flat)
    extremes = simulate_fare_elasticity_curve(FinModelInput(), cities, [3500, 25000])
    assert [p["effective_load_factor_pct"] for p in extremes] == [98, 50]
    assert simulate_fare_elasticity_curve(FinModelInput(), cities, []) == []


@pytest.mark.parametrize("kwargs", [
    {"fares_rub": [0]}, {"fares_rub": [25001]}, {"fares_rub": [float("nan")]},
    {"elasticity": .1}, {"elasticity": float("inf")}, {"elasticity": True},
])
def test_elasticity_invalid_arguments(cities, kwargs):
    with pytest.raises(ValueError):
        simulate_fare_elasticity_curve(FinModelInput(), cities, **kwargs)


@pytest.mark.parametrize("scenario", ["base", "conservative"])
@pytest.mark.parametrize("interline,ancillary,recovery", list(product((False, True), repeat=3)))
def test_digital_switches_and_accounting(cities, scenario, interline, ancillary, recovery):
    params = FinModelInput(scenario=scenario)
    impact = evaluate_digital_one_click_impact(params, cities,
        enable_virtual_interline=interline, enable_one_click_ancillary=ancillary,
        enable_auto_disruption_recovery=recovery)
    base, digital = impact["p2p_base"], impact["p2p_digital"]
    contributions = impact["ebitdar_uplift_mln_rub"]
    assert digital["ebitdar_mln_rub"] - base["ebitdar_mln_rub"] == pytest.approx(sum(contributions.values()))
    assert impact["total_ebitdar_uplift_mln_rub"] == pytest.approx(sum(contributions.values()))
    assert contributions["virtual_interline"] == pytest.approx(120.2472 if interline else 0)
    assert contributions["one_click_ancillary"] == pytest.approx(digital["annual_passengers"] * 830 / 1e6 if ancillary else 0)
    assert contributions["auto_disruption_recovery"] == (22.5 if recovery else 0)
    if not any((interline, ancillary, recovery)):
        assert digital == base
    if all((interline, ancillary, recovery)):
        assert digital["ebitdar_mln_rub"] > base["ebitdar_mln_rub"]
        assert digital["breakeven_load_factor_pct"] < base["breakeven_load_factor_pct"]


def test_digital_reference_effect_and_breakeven(cities):
    r = evaluate_digital_one_click_impact(FinModelInput(), cities)
    d = r["p2p_digital"]
    assert d["annual_passengers"] == 464880
    assert d["annual_revenue_mln_rub"] == 4912.0192
    assert d["ebitdar_mln_rub"] == 1583.1976
    assert d["breakeven_load_factor_pct"] == 58.0
    # At unrounded BELF, tickets + ancillary + distribution savings + subsidies
    # cover base costs + interline IT - recovery savings.
    belf = r["digital_belf_unclipped_pct"] / 100
    assert 520000 * belf * (8862 + 650 + 180) + 490100000 == pytest.approx(3417000000 + 18000000 - 22500000)


def test_digital_cap_can_make_interline_unprofitable(cities):
    r = evaluate_digital_one_click_impact(FinModelInput(load_factor_pct=98), cities,
        enable_one_click_ancillary=False, enable_auto_disruption_recovery=False)
    assert r["p2p_base"]["annual_passengers"] == r["p2p_digital"]["annual_passengers"]
    assert r["ebitdar_uplift_mln_rub"]["virtual_interline"] == -18
    with pytest.raises(ValueError):
        evaluate_digital_one_click_impact(FinModelInput(), cities, enable_virtual_interline="yes")


def test_recovery_scales_with_routes(cities):
    r = evaluate_digital_one_click_impact(FinModelInput(active_routes_count=20), cities,
        enable_virtual_interline=False, enable_one_click_ancillary=False)
    assert r["total_ebitdar_uplift_mln_rub"] == 45


@pytest.mark.parametrize("scenario", ["base", "conservative"])
def test_growth_roadmap_targets_are_conditional_and_not_fleet_feasible(cities, scenario):
    params = FinModelInput(scenario=scenario)
    rows = project_path_to_top2_airline(params, cities)
    assert [r["wave_id"] for r in rows] == [0, 1, 2, 3]
    assert [r["routes_count"] for r in rows] == [0, 10, 65, 120]
    assert rows[0]["total_pax_mln"] == 4.465
    assert rows[0]["projected_revenue_bln_rub"] is None
    assert rows[1]["incremental_pax_mln"] == evaluate_hypotheses(params, cities).p2p.annual_passengers / 1e6
    assert rows[3]["market_share_pct"] >= 12.5
    assert rows[3]["market_rank_rf"] == 2
    assert rows[3]["fleet_total"] == 82
    assert rows[3]["fleet_gap"] > 0
    assert rows[3]["rank_is_conditional"]
    assert not rows[3]["fleet_capacity_feasible"]
    assert rows[3]["fleet_supported_routes_count"] < 120
    assert rows[3]["fleet_constrained_market_share_pct"] < 11.8
    for row in rows[1:]:
        assert row["fleet_total"] == sum(row["fleet_breakdown"].values())
        assert row["total_pax_mln"] == pytest.approx(4.465 + row["incremental_pax_mln"])
        assert row["market_share_pct"] == pytest.approx(row["total_pax_mln"] / 108.9 * 100, abs=.001)
        assert row["market_rank_rf"] != 3 or row["market_share_pct"] > 8.5
        supported = row["fleet_supported_routes_count"]
        assert calculate_required_sj100_fleet(supported, row["weekly_freq_per_route"], False) <= row["fleet_total"]
        assert row["fleet_constrained_total_pax_mln"] <= row["total_pax_mln"]
        assert row["fleet_required_model"] == calculate_required_sj100_fleet(row["routes_count"], row["weekly_freq_per_route"], False)


def test_growth_projection_depends_on_inputs_and_reports_fleet_gap(cities):
    base = project_path_to_top2_airline(FinModelInput(), cities)
    cheaper = project_path_to_top2_airline(FinModelInput(avg_fare_rub=5500), cities)
    assert cheaper[3]["projected_revenue_bln_rub"] < base[3]["projected_revenue_bln_rub"]
    expensive = project_path_to_top2_airline(FinModelInput(weekly_freq_per_route=21, load_factor_pct=50), cities)
    assert expensive[3]["weekly_freq_per_route"] == 21
    assert expensive[3]["fleet_gap"] > base[3]["fleet_gap"]


@pytest.mark.parametrize("required", [1, 2, 13, 35, 200])
@pytest.mark.parametrize("scenario", ["base", "conservative"])
def test_delivery_timing_capacity_and_no_double_counting(required, scenario):
    rows = build_sj100_delivery_roadmap(required, scenario)
    assert len(rows) == 10
    assert rows[0]["quarter"] == "2026 Q3" and rows[-1]["quarter"] == "2028 Q4"
    assert all(r["new_sj100_delivered_cumulative"] == 0 for r in rows[:4])
    assert rows[-1]["new_sj100_delivered_cumulative"] == required
    assert rows[-1]["existing_ssj_reserve_allocated"] == 0
    assert rows[-1]["total_available_fleet"] == required
    previous = 0
    for r in rows:
        fleet = r["total_available_fleet"]
        routes = r["supported_routes_count"]
        assert fleet == r["new_sj100_delivered_cumulative"] + r["existing_ssj_reserve_allocated"]
        assert previous <= fleet <= required
        assert r["existing_ssj_reserve_allocated"] <= (6 if scenario == "base" else 4)
        if routes:
            assert calculate_required_sj100_fleet(routes, 5, False) <= fleet
        assert calculate_required_sj100_fleet(routes + 1, 5, False) > fleet
        previous = fleet


def test_conservative_deliveries_never_lead_base():
    for base, conservative in zip(build_sj100_delivery_roadmap(13), build_sj100_delivery_roadmap(13, "conservative")):
        assert conservative["new_sj100_delivered_cumulative"] <= base["new_sj100_delivered_cumulative"]
        assert conservative["total_available_fleet"] <= base["total_available_fleet"]


@pytest.mark.parametrize("required,scenario", [(0,"base"), (-1,"base"), (True,"base"), (1.5,"base"), (float("nan"),"base"), (13,"other")])
def test_invalid_delivery_inputs(required, scenario):
    with pytest.raises(ValueError):
        build_sj100_delivery_roadmap(required, scenario)
