"""Контрольные расчеты и стресс-тесты модели участника №3."""

from dataclasses import asdict, replace
from itertools import product
from math import isfinite

import pytest
import pandas as pd

from src.models.unit_economics import (
    evaluate_route_level_economics, evaluate_scissor_hub_economics,
    build_strategy_switching_matrix, run_monte_carlo_stress_test,
    run_financial_monte_carlo, evaluate_svx_kuf_cannibalization, get_assumptions_audit_table,
)
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


# Уровень 2: помаршрутные данные, «ножницы», сетка стратегий и стресс-тесты.


@pytest.fixture
def financial_routes():
    return pd.DataFrame([
        {"origin_iata": "KUF", "dest_iata": "PEE", "distance_km": 1000,
         "freq": 1, "subsidy_eligible": True, "competitor_fare_rub": 9000,
         "crj200_cask_advantage_pct": 30.0},
        {"origin_iata": "UFA", "dest_iata": "OMS", "distance_km": 1000,
         "freq": 2, "subsidy_eligible": False, "competitor_fare_rub": float("nan"),
         "crj200_cask_advantage_pct": 32.0},
    ])


def test_route_level_economics_with_real_dev1_routes():
    from src.parsers.build_dataset import get_network_routes
    routes = get_network_routes("p2p")
    original = routes.copy(deep=True)
    assert len(routes) == 10
    params = FinModelInput()
    subsidized = evaluate_route_level_economics(params, routes)
    zero = evaluate_route_level_economics(params, routes, subsidy_retention_pct=0)
    pd.testing.assert_frame_equal(original, routes)
    assert len(subsidized["routes_pnl"]) == 10
    assert subsidized["total_cost_mln_rub"] == zero["total_cost_mln_rub"]
    assert subsidized["total_ebitdar_no_subsidy_mln_rub"] == zero["total_ebitdar_mln_rub"]
    subsidy = sum(row["annual_subsidy_mln_rub"] for row in subsidized["routes_pnl"])
    assert subsidy == 75.4  # Единственный флаг GOJ->UFA, 520 * 145000.
    assert subsidized["total_revenue_mln_rub"] - zero["total_revenue_mln_rub"] == pytest.approx(subsidy)
    assert subsidized["avg_crj200_cask_advantage_pct"] == pytest.approx(30.62)
    assert subsidized["profitable_without_subsidy_count"] == zero["profitable_routes_count"]
    assert subsidized["profitable_routes_count"] >= zero["profitable_routes_count"]
    assert sum(row["annual_passengers"] for row in subsidized["routes_pnl"]) == 449280
    assert all(row["proof_source"] for row in subsidized["routes_pnl"])


def test_route_accounting_and_subsidy_stress(financial_routes):
    full = evaluate_route_level_economics(FinModelInput(), financial_routes)
    half = evaluate_route_level_economics(FinModelInput(), financial_routes, subsidy_retention_pct=50)
    first, second = full["routes_pnl"]
    assert first["origin_iata"] == "KUF"  # прибыль выше благодаря субсидии
    assert first["annual_flights"] == second["annual_flights"] == 520
    assert first["annual_passengers"] == 44928
    assert first["annual_cost_mln_rub"] == pytest.approx(418.9)  # 520*695000 + 57.5 млн
    assert first["annual_revenue_mln_rub"] == pytest.approx(473.551936)
    assert second["annual_revenue_mln_rub"] == pytest.approx(398.151936)
    assert first["annual_subsidy_mln_rub"] == 75.4
    assert second["annual_subsidy_mln_rub"] == 0
    assert first["fare_vs_competitor_rub"] == -138
    assert second["competitor_fare_rub"] is None
    assert sum(row["allocated_fixed_cost_mln_rub"] for row in full["routes_pnl"]) == 115
    for key in ("revenue", "cost", "ebitdar"):
        field = f"annual_{key}_mln_rub" if key != "ebitdar" else "ebitdar_mln_rub"
        assert full[f"total_{key}_mln_rub"] == pytest.approx(sum(r[field] for r in full["routes_pnl"]))
    assert full["total_revenue_mln_rub"] - full["total_cost_mln_rub"] == pytest.approx(full["total_ebitdar_mln_rub"])
    assert full["total_ebitdar_mln_rub"] - half["total_ebitdar_mln_rub"] == pytest.approx(37.7)
    assert first["belf_with_subsidy_pct"] < first["belf_no_subsidy_pct"]
    assert first["viable_without_subsidy"] is False
    assert full["profitable_routes_count"] == 1
    assert full["profitable_without_subsidy_count"] == 0


def test_route_controls_and_data_missingness(financial_routes):
    baseline = evaluate_route_level_economics(FinModelInput(), financial_routes)
    cons = evaluate_route_level_economics(FinModelInput(scenario="conservative"), financial_routes)
    assert cons["total_ebitdar_mln_rub"] < baseline["total_ebitdar_mln_rub"]
    assert cons["total_cost_mln_rub"] > baseline["total_cost_mln_rub"]
    fares = evaluate_route_level_economics(FinModelInput(avg_fare_rub=3500), financial_routes)
    assert all(row["belf_no_subsidy_pct"] > 100 for row in fares["routes_pnl"])
    missing = financial_routes.drop(columns=["freq", "competitor_fare_rub", "crj200_cask_advantage_pct"])
    result = evaluate_route_level_economics(FinModelInput(active_routes_count=50), missing)
    assert result["total_ebitdar_mln_rub"] == baseline["total_ebitdar_mln_rub"]
    assert result["avg_crj200_cask_advantage_pct"] is None
    assert result["cask_observed_routes_count"] == 0
    assert all(row["dev1_weekly_departures"] is None for row in result["routes_pnl"])
    fast = evaluate_route_level_economics(FinModelInput(weekly_freq_per_route=10), financial_routes)
    assert sum(row["annual_flights"] for row in fast["routes_pnl"]) == 2080


@pytest.mark.parametrize("retention", [-1, 101, float("nan"), float("inf"), True, "50"])
def test_route_invalid_retention(financial_routes, retention):
    with pytest.raises(ValueError):
        evaluate_route_level_economics(FinModelInput(), financial_routes, subsidy_retention_pct=retention)


@pytest.mark.parametrize("field,value", [
    ("distance_km", 0), ("distance_km", float("nan")), ("distance_km", float("inf")),
    ("distance_km", "1000"), ("subsidy_eligible", "False"), ("subsidy_eligible", None),
    ("origin_iata", "XXX1"), ("competitor_fare_rub", -1),
    ("crj200_cask_advantage_pct", float("inf")),
])
def test_route_invalid_values(financial_routes, field, value):
    bad = financial_routes.astype(object)
    bad.at[0, field] = value
    with pytest.raises(ValueError):
        evaluate_route_level_economics(FinModelInput(), bad)


def test_route_invalid_schema_and_duplicate_roundtrips(financial_routes):
    for bad in ([], pd.DataFrame(), financial_routes.drop(columns="distance_km"),
                pd.concat([financial_routes, financial_routes.iloc[:1]])):
        with pytest.raises(ValueError):
            evaluate_route_level_economics(FinModelInput(), bad)
    reverse = financial_routes.copy()
    reverse.loc[1, ["origin_iata", "dest_iata"]] = ["PEE", "KUF"]
    with pytest.raises(ValueError, match="Обратные"):
        evaluate_route_level_economics(FinModelInput(), reverse)


@pytest.mark.parametrize("scenario", ["base", "conservative"])
def test_scissor_hub_outperforms_classic_hub(cities, scenario):
    original = [asdict(city) for city in cities]
    result = evaluate_scissor_hub_economics(FinModelInput(scenario=scenario), cities)
    hub, p2p, hybrid = (result[k] for k in ("classic_hub", "pure_p2p", "scissor_hybrid"))
    assert hybrid["ebitdar_mln_rub"] > hub["ebitdar_mln_rub"]
    assert hybrid["ebitdar_mln_rub"] > p2p["ebitdar_mln_rub"]
    assert hybrid["required_aircraft_sj100"] == p2p["required_aircraft_sj100"] == 13
    assert hub["required_aircraft_sj100"] == 15
    assert hybrid["annual_passengers"] > p2p["annual_passengers"]
    assert hybrid["fixed_cost_mln_rub"] == 163
    assert result["assumptions"]["coordination_cost_mln_rub"] == 48
    assert result["assumptions"]["blended_discount_pct"] == 1.5
    assert result["scissor_evidence"]["iata"] == "KUF"
    assert result["scissor_evidence"]["scissor_rank"] == 2
    assert result["scissor_evidence"]["eligible_directed_pairs"] == 46
    assert [asdict(city) for city in cities] == original


def test_scissor_wave_costs_and_load_cap(cities):
    for waves in (1, 2, 3):
        result = evaluate_scissor_hub_economics(FinModelInput(), cities, scissor_waves_per_day=waves)
        hybrid = result["scissor_hybrid"]
        assert hybrid["effective_load_factor_pct"] == pytest.approx(86.4 + 1.8 * waves)
        assert hybrid["fixed_cost_mln_rub"] == 115 + 24 * waves
        assert hybrid["annual_revenue_mln_rub"] - hybrid["annual_cost_mln_rub"] == pytest.approx(hybrid["ebitdar_mln_rub"])
    capped = evaluate_scissor_hub_economics(FinModelInput(load_factor_pct=98), cities)
    assert capped["scissor_hybrid"]["effective_load_factor_pct"] == 95
    assert capped["ebitdar_uplift_vs_p2p_mln_rub"] < 0  # не навязываем победителя


def test_scissor_selected_city_joins_real_geometry():
    from src.scoring.city_scorer import get_scored_cities
    from src.schemas.contracts import ScoringWeights
    cities = get_scored_cities(ScoringWeights())
    result = evaluate_scissor_hub_economics(FinModelInput(), cities, scissor_hub_iata="KZN")
    assert "KZN" in result["classic_hub"]["title"]
    assert "KZN" in result["scissor_hybrid"]["title"]
    assert result["scissor_evidence"]["scissor_rank"] == 5


@pytest.mark.parametrize("waves", [0, 4, True, 1.5, float("nan")])
def test_scissor_invalid_waves(cities, waves):
    with pytest.raises(ValueError):
        evaluate_scissor_hub_economics(FinModelInput(), cities, scissor_waves_per_day=waves)


def test_scissor_invalid_city(cities):
    with pytest.raises(ValueError):
        evaluate_scissor_hub_economics(FinModelInput(), cities, scissor_hub_iata="XXX")


def test_switching_matrix_and_monte_carlo_reproducibility(cities):
    params = FinModelInput()
    before = asdict(params)
    matrix = build_strategy_switching_matrix(params, cities, frequencies=[6, 2], fares_rub=[6000, 8400, 12000])
    assert matrix["frequencies"] == [6, 2]
    assert len(matrix["winner_matrix"]) == 2
    for i, freq in enumerate(matrix["frequencies"]):
        for j, fare in enumerate(matrix["fares_rub"]):
            result = evaluate_hypotheses(replace(params, weekly_freq_per_route=freq, avg_fare_rub=fare), cities)
            assert matrix["winner_matrix"][i][j] == result.winner
            assert matrix["ebitdar_diff_matrix"][i][j] == pytest.approx(result.p2p.ebitdar_mln_rub - result.hub.ebitdar_mln_rub)
    default = build_strategy_switching_matrix(params, cities)
    assert len(default["winner_matrix"]) == 9
    assert all(len(row) == 8 for row in default["winner_matrix"])
    assert default["p2p_win_share_pct"] == 100 * sum(v == "p2p" for row in default["winner_matrix"] for v in row) / 72
    first = run_monte_carlo_stress_test(params, cities, seed=42)
    assert first == run_monte_carlo_stress_test(params, cities, seed=42)
    assert first != run_monte_carlo_stress_test(params, cities, seed=43)
    assert first["p2p_prob_profitable_pct"] > first["hub_prob_profitable_pct"]
    for code in ("p2p", "hub"):
        assert 0 <= first[f"{code}_prob_profitable_pct"] <= 100
        assert first[f"{code}_ebitdar_p5_p50_p95"] == sorted(first[f"{code}_ebitdar_p5_p50_p95"])
    assert asdict(params) == before


@pytest.mark.parametrize("freqs,fares", [([], [8400]), ([5], []), ([0], [8400]), ([True], [8400]), ([5], [float("nan")])])
def test_invalid_matrix_axes(cities, freqs, fares):
    with pytest.raises(ValueError):
        build_strategy_switching_matrix(FinModelInput(), cities, freqs, fares)


@pytest.mark.parametrize("n,seed", [(0, 42), (-1, 42), (True, 42), (1.5, 42), (5, True), (5, "42")])
def test_invalid_monte_carlo_arguments(cities, n, seed):
    with pytest.raises(ValueError):
        run_monte_carlo_stress_test(FinModelInput(), cities, n_simulations=n, seed=seed)


def test_monte_carlo_does_not_mutate_global_rng_and_handles_one_sample(cities):
    import random
    before = random.getstate()
    r = run_monte_carlo_stress_test(FinModelInput(), cities, n_simulations=1)
    assert before == random.getstate()
    for code in ("p2p", "hub"):
        q = r[f"{code}_ebitdar_p5_p50_p95"]
        assert q[0] == q[1] == q[2]
        assert r[f"{code}_prob_profitable_pct"] in (0, 100)


def test_monte_carlo_zero_shocks_matches_contract(monkeypatch, cities):
    import src.models.unit_economics as model
    class NoShock:
        def __init__(self, seed):
            pass
        def gauss(self, mean, std):
            return 0
        def uniform(self, low, high):
            return 1.0
    monkeypatch.setattr(model, "Random", NoShock)
    r = model.run_monte_carlo_stress_test(FinModelInput(), cities, n_simulations=3)
    assert r["p2p_ebitdar_p5_p50_p95"] == [1054.6] * 3
    assert r["hub_ebitdar_p5_p50_p95"] == [154.9] * 3
    assert r["p2p_prob_profitable_pct"] == r["hub_prob_profitable_pct"] == 100


def test_stress_subsidies_and_variable_costs_are_applied_once():
    from src.models.unit_economics import _calculate, _linear_quantiles
    p = FinModelInput()
    base = _calculate(p, "p2p")
    cut = _calculate(p, "p2p", subsidy_retention=0)
    assert base.ebitdar_mln_rub - cut.ebitdar_mln_rub == pytest.approx(490.1)
    expensive = _calculate(p, "p2p", variable_cost_multiplier=1.2)
    assert base.ebitdar_mln_rub - expensive.ebitdar_mln_rub == pytest.approx(660.4)  # 3302 * .2
    assert _linear_quantiles([0, 100]) == [5, 50, 95]


@pytest.fixture
def real_financial_routes():
    from src.parsers.build_dataset import get_network_routes
    return get_network_routes("p2p")


@pytest.mark.parametrize("limit", [0, 1, 2, 4, 5, 7, 13, 50])
def test_available_fleet_limit_capacity_and_full_fixed_cost(real_financial_routes, limit):
    original = real_financial_routes.copy(deep=True)
    result = evaluate_route_level_economics(FinModelInput(), real_financial_routes, available_aircraft_limit=limit)
    assert result["required_aircraft_sj100"] <= limit
    assert result["selected_routes_count"] == len(result["routes_pnl"])
    assert len(result["routes_pnl"]) + len(result["excluded_routes"]) == 10
    pd.testing.assert_frame_equal(original, real_financial_routes)
    if result["selected_routes_count"]:
        assert result["required_aircraft_sj100"] == calculate_required_sj100_fleet(result["selected_routes_count"], 5, False)
        assert sum(row["allocated_fixed_cost_mln_rub"] for row in result["routes_pnl"]) == pytest.approx(115)
        assert all(row["contribution_mln_rub"] > 0 for row in result["routes_pnl"])
    else:
        assert result["total_revenue_mln_rub"] == result["total_cost_mln_rub"] == result["total_ebitdar_mln_rub"] == 0
        assert result["required_aircraft_sj100"] == 0
        assert not result["operations_started"]
    assert result["total_revenue_mln_rub"] - result["total_cost_mln_rub"] == pytest.approx(result["total_ebitdar_mln_rub"])


@pytest.mark.parametrize("limit", [4, 5])
def test_limited_p2p_profitable_and_average_hub_unprofitable(real_financial_routes, limit):
    result = evaluate_route_level_economics(FinModelInput(), real_financial_routes, available_aircraft_limit=limit)
    assert result["selected_routes_count"] == 3
    assert result["total_ebitdar_mln_rub"] == pytest.approx(247.169808)
    assert result["classic_hub_reference"]["metrics"]["ebitdar_mln_rub"] < 0
    assert not result["classic_hub_reference"]["full_requested_network_supported"]


def test_fleet_selection_is_by_contribution_margin_and_order_independent(real_financial_routes):
    full = evaluate_route_level_economics(FinModelInput(), real_financial_routes)
    top = sorted(full["routes_pnl"], key=lambda r: (-r["contribution_margin_pct"], -r["contribution_mln_rub"], r["origin_iata"], r["dest_iata"]))[:3]
    chosen = evaluate_route_level_economics(FinModelInput(), real_financial_routes, available_aircraft_limit=5)
    shuffled = evaluate_route_level_economics(FinModelInput(), real_financial_routes.iloc[::-1], available_aircraft_limit=5)
    assert {(r['origin_iata'], r['dest_iata']) for r in top} == {(r['origin_iata'], r['dest_iata']) for r in chosen['routes_pnl']}
    assert chosen == shuffled
    assert full["required_aircraft_sj100"] == 13
    assert full["selected_routes_count"] == 10


def test_fleet_limit_with_subsidy_loss_and_unprofitable_candidates(real_financial_routes):
    zero = evaluate_route_level_economics(FinModelInput(), real_financial_routes,
        available_aircraft_limit=5, subsidy_retention_pct=0)
    assert zero["total_ebitdar_mln_rub"] == zero["total_ebitdar_no_subsidy_mln_rub"]
    assert all(row["annual_subsidy_mln_rub"] == 0 for row in zero["routes_pnl"])
    assert zero["required_aircraft_sj100"] <= 5
    # Очень низкий тариф: отрицательный вклад нельзя маскировать сокращением сети.
    low = evaluate_route_level_economics(FinModelInput(avg_fare_rub=3500), real_financial_routes,
        available_aircraft_limit=5, subsidy_retention_pct=0)
    assert low["selected_routes_count"] == 0
    assert not low["profitable_selected_network"]


@pytest.mark.parametrize("limit", [-1, True, 2.5, float("nan"), float("inf"), "5"])
def test_invalid_aircraft_limit(real_financial_routes, limit):
    with pytest.raises(ValueError, match="available_aircraft_limit"):
        evaluate_route_level_economics(FinModelInput(), real_financial_routes, available_aircraft_limit=limit)


def test_financial_monte_carlo_reproducibility_and_stricter_risks(cities):
    import random
    before = random.getstate()
    params = FinModelInput()
    result = run_financial_monte_carlo(params, cities)
    assert result == run_financial_monte_carlo(params, cities)
    assert result != run_financial_monte_carlo(params, cities, seed=43)
    assert random.getstate() == before
    assert result["n_samples"] == 1000 and result["seed"] == 42
    assert result["p2p_prob_positive_ebitdar_pct"] > result["hub_prob_positive_ebitdar_pct"]
    assert 0 <= result["p2p_win_prob_pct"] <= 100
    assert result["p2p_prob_positive_ebitdar_pct"] < run_monte_carlo_stress_test(params, cities)["p2p_prob_profitable_pct"]
    for code in ("hub", "p2p"):
        assert result[f"{code}_ebitdar_p5_p50_p95"] == sorted(result[f"{code}_ebitdar_p5_p50_p95"])
        assert 0 <= result[f"{code}_prob_positive_ebitdar_pct"] <= 100
    pessimistic = run_financial_monte_carlo(replace(params, scenario="conservative"), cities)
    assert pessimistic["p2p_prob_positive_ebitdar_pct"] < result["p2p_prob_positive_ebitdar_pct"]


def test_financial_monte_carlo_one_sample_and_positive_means_strictly_positive(monkeypatch, cities):
    import src.models.unit_economics as model
    one = run_financial_monte_carlo(FinModelInput(), cities, n_samples=1)
    assert len(set(one["p2p_ebitdar_p5_p50_p95"])) == 1
    original = model._calculate
    def zero_profit(*args, **kwargs):
        return replace(original(*args, **kwargs), ebitdar_mln_rub=0)
    monkeypatch.setattr(model, "_calculate", zero_profit)
    result = run_financial_monte_carlo(FinModelInput(), cities, n_samples=4)
    assert result["p2p_prob_positive_ebitdar_pct"] == result["hub_prob_positive_ebitdar_pct"] == 0


@pytest.mark.parametrize("n,seed", [(0,42), (-1,42), (True,42), (2.5,42), (5,True), (5,"42")])
def test_financial_monte_carlo_invalid_inputs(cities, n, seed):
    with pytest.raises(ValueError):
        run_financial_monte_carlo(FinModelInput(), cities, n_samples=n, seed=seed)


def test_financial_monte_carlo_no_shocks_matches_reference(monkeypatch, cities):
    import src.models.unit_economics as model
    class NoShock:
        def __init__(self, seed):
            pass
        def uniform(self, low, high):
            return 0.0 if low == -12 else 1.0
    monkeypatch.setattr(model, "Random", NoShock)
    result = run_financial_monte_carlo(FinModelInput(), cities, n_samples=3)
    assert result["p2p_ebitdar_p5_p50_p95"] == [1054.6] * 3
    assert result["hub_ebitdar_p5_p50_p95"] == [154.9] * 3


@pytest.mark.parametrize("scenario", ["base", "conservative"])
def test_svx_cannibalization_accounting_and_geometry(cities, scenario):
    params = FinModelInput(scenario=scenario)
    before = asdict(params), [asdict(c) for c in cities]
    result = evaluate_svx_kuf_cannibalization(params, cities)
    assert result["classic_hub"]["svx_margin_loss_mln_rub"] == 150
    assert result["scissor_hybrid"]["svx_cannibalization_pct"] == 2.5
    for strategy in ("classic_hub", "scissor_hybrid"):
        row = result[strategy]
        assert row["net_ebitdar_after_svx_cannibalization_mln_rub"] == pytest.approx(row["ebitdar_mln_rub"] - row["svx_margin_loss_mln_rub"])
    assert result["scissor_total_fixed_cost_mln_rub"] == 163
    assert result["scissor_new_base_fixed_cost_mln_rub"] == 0
    assert result["feeder"]["incremental_margin_included_mln_rub"] == 0
    assert result["feeder"]["flight_code"] == "WZ-1033"
    assert result["feeder"]["observed_weekly_flights"] > 0
    assert len(result["corridor_routes"]) == 8
    assert result["geometrically_supported_kuf_routes_count"] == 3
    assert all(row["svx_detour_pct"] > 35 for row in result["corridor_routes"])
    assert any(row["svx_extra_km"] < 950 for row in result["corridor_routes"])
    assert any(row["svx_extra_km"] > 1300 for row in result["corridor_routes"])
    for row in result["corridor_routes"]:
        assert row["via_svx_distance_km"] - row["direct_distance_km"] == pytest.approx(row["svx_extra_km"], abs=.002)
        assert row["kuf_passes_15pct_detour"] == (row["kuf_detour_pct"] < 15)
    assert (asdict(params), [asdict(c) for c in cities]) == before


def test_svx_kuf_requires_kuf_in_candidate_pool(cities):
    with pytest.raises(ValueError, match="не найден"):
        evaluate_svx_kuf_cannibalization(FinModelInput(), [city for city in cities if city.iata != "KUF"])


def test_assumptions_audit_sources_and_calibration_limitations():
    import json
    result = get_assumptions_audit_table()
    assert result == get_assumptions_audit_table()
    json.dumps(result, allow_nan=False)
    assert result["calibration"]["status"] == "not_empirically_calibrated"
    assert result["rw_route_pairs_count"] == 8
    assert result["rw_directed_flight_codes_count"] == 16
    assert result["subsidized_directed_routes_count"] == 21
    codes = {row["flight_code"] for row in result["rw_flight_validation"]}
    assert {"WZ-1025", "WZ-1033", "WZ-5343", "WZ-5305"} <= codes
    for row in result["rw_flight_validation"]:
        assert row["actual_flight_cost_rub"] is None
        assert row["calibration_residual_rub"] is None
        assert row["source_urls"] and row["observation_weeks"]
        assert row["weekly_flights_observed"] > 0
        assert row["model_flight_cost_rub"] == 385000 + 310 * row["distance_km"]
        assert row["implied_crj_premium_vs_sj_pct"] > row["sj100_saving_vs_sj_pct" if "sj100_saving_vs_sj_pct" in row else "sj100_saving_vs_crj_pct"]
    assert all(len(value) == 64 for value in result["source_sha256"].values())
    assert len({row["assumption"] for row in result["assumptions"]}) == len(result["assumptions"])
    assert all(row["source"] and row["limitation"] for row in result["assumptions"])
    assert any(row["operator"] != "Ред Вингс" for row in result["subsidy_register"])
