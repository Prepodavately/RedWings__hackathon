"""Проверки свойств скоринга; синтетические значения не являются данными городов."""
import json
from dataclasses import asdict, replace
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

from src.schemas.contracts import ScoringWeights, CityScoreDTO
from src.scoring.city_scorer import (
    METRICS, effective_weights, get_scored_cities, prepare_features,
    score_cities, weight_sensitivity,
)
from src.scoring.normalizer import distance_sweet_spot_score, min_max_normalize
from src.scoring.city_scorer import (
    calculate_effective_population, calculate_gravity_matrix,
    compute_gravity_anomaly_field, calculate_network_graph_metrics,
)


@pytest.fixture
def live_network():
    root = Path(__file__).resolve().parents[3]
    cities = pd.read_parquet(root / "data/processed/cities_features.parquet")
    routes = pd.read_parquet(root / "data/processed/routes_proof.parquet")
    with pytest.warns(UserWarning, match="exploratory"):
        scores = get_scored_cities(ScoringWeights(), data=cities)
    return cities, routes, scores


@pytest.fixture
def small_network():
    """Три синтетических города: цепь AAA—KUF—BBB, у AAA—BBB нет рейса."""
    cities = pd.DataFrame({
        "iata": ["AAA", "KUF", "BBB"], "city_name": ["А", "Хаб", "Б"],
        "population_city_mln": [1., 2., 3.], "agglomeration_members": "",
        "avg_wage_rub_region": 50000., "airport_pax_mln": 1.,
        "lat": [50., 53., 56.], "lon": [40., 45., 50.], "dist_to_mow_km": 1000.,
    })
    rows = []
    for a, b, time, distance, own in [("AAA", "KUF", 2., 100., 2.),
                                     ("KUF", "BBB", 3., 150., 2.),
                                     ("AAA", "BBB", 4., 220., 0.)]:
        for origin, dest in ((a, b), (b, a)):
            rows.append(dict(origin_iata=origin, dest_iata=dest, air_door_to_door_h=time,
                             distance_km=distance, own_flights_weekly=own,
                             competitor_flights_weekly=0., moscow_via_time_h=10.,
                             rail_travel_hours=8., access_time_origin_h=.25, access_time_dest_h=.5))
    scores = [CityScoreDTO(code, code, "Тест", 1., 1., 50., i + 1, True)
              for i, code in enumerate(cities.iata)]
    return cities, pd.DataFrame(rows), scores


@pytest.mark.parametrize("mode", ["potential", "anomaly"])
def test_gravity_field_grid_bounds(live_network, mode):
    cities, routes, scores = live_network
    before_c, before_r = cities.copy(deep=True), routes.copy(deep=True)
    field = compute_gravity_anomaly_field(cities, routes, scores, mode=mode)
    z = np.asarray(field.z_values)
    assert z.shape == (110, 160)
    assert (field.lons[0], field.lons[-1], field.lats[0], field.lats[-1]) == (26., 82., 40., 64.)
    assert isinstance(field.z_values, tuple) and isinstance(field.z_values[0], tuple)
    assert np.isfinite(z).all() and z.min() >= -100 and z.max() <= 100
    assert np.max(np.abs(z)) == pytest.approx(100)
    if mode == "potential":
        assert z.min() == pytest.approx(-100)
    else:
        assert z.mean() == pytest.approx(0, abs=1e-10)
        assert z.min() < 0 < z.max()
    assert cities.lat.min() <= field.barycenter_lat <= cities.lat.max()
    assert cities.lon.min() <= field.barycenter_lon <= cities.lon.max()
    json.dumps(asdict(field), allow_nan=False)
    pd.testing.assert_frame_equal(cities, before_c)
    pd.testing.assert_frame_equal(routes, before_r)


def test_gravity_matrix_changes_with_params(live_network):
    cities, routes, _ = live_network
    # Сохранённая колонка не должна блокировать изменение lam из UI.
    cities = cities.assign(effective_population_mln=999.)
    base = calculate_gravity_matrix(cities, routes)
    for kwargs in ({"gamma": 1.6}, {"lam": 1.2}, {"distance_knots_km": (100., 400., 700., 1800.)}):
        assert not np.allclose(base, calculate_gravity_matrix(cities, routes, **kwargs))
    expected = calculate_effective_population(cities)
    np.testing.assert_allclose(list(base.attrs["effective_population_mln"].values()), expected)
    excluded = calculate_gravity_matrix(cities, routes, exclude_existing_rw=True)
    existing = routes.loc[routes.own_flights_weekly > 0]
    assert len(existing) == 16 and excluded.attrs["excluded_existing_rw_pairs"] == 16
    for row in routes.itertuples():
        assert excluded.loc[row.origin_iata, row.dest_iata] == pytest.approx(
            0 if row.own_flights_weekly > 0 else base.loc[row.origin_iata, row.dest_iata])
    assert not np.allclose(base, excluded)


@pytest.mark.parametrize("knots", [(300, 800, 800, 3000), (300, 900, 800, 3000),
                                  (-1, 800, 1500, 3000), (0, 1, 2), (0, 1, 2, np.inf),
                                  (True, 800, 1500, 3000), None])
def test_gravity_rejects_invalid_range_knots(small_network, knots):
    with pytest.raises(ValueError, match="distance_knots_km"):
        calculate_gravity_matrix(small_network[0], distance_knots_km=knots)


def test_gravity_custom_range_and_directional_rw_mask(small_network):
    from src.scoring.city_scorer import _gravity_range_weight
    np.testing.assert_allclose(_gravity_range_weight(np.array([0, 100, 200, 300, 500, 750, 1000]),
                                                     (100, 300, 500, 1000)), [0, 0, .5, 1, 1, .5, 0])
    cities, routes, _ = small_network
    routes.loc[routes.origin_iata == "KUF", "own_flights_weekly"] = 0
    masked = calculate_gravity_matrix(cities, routes, exclude_existing_rw=True)
    assert masked.loc["AAA", "KUF"] == 0 < masked.loc["KUF", "AAA"]
    routes.loc[0, "own_flights_weekly"] = np.nan
    assert calculate_gravity_matrix(cities, routes, exclude_existing_rw=True).loc["AAA", "KUF"] > 0
    no_own = routes.drop(columns="own_flights_weekly")
    np.testing.assert_allclose(calculate_gravity_matrix(cities, no_own, exclude_existing_rw=True),
                               calculate_gravity_matrix(cities, no_own))


@pytest.mark.parametrize("own", [-1, np.inf, "invalid"])
def test_invalid_rw_frequency(small_network, own):
    cities, routes, _ = small_network
    routes["own_flights_weekly"] = own
    with pytest.raises(ValueError, match="own_flights_weekly"):
        calculate_gravity_matrix(cities, routes, exclude_existing_rw=True)


def test_field_barycenter_counts_unique_outgoing_white_spots(small_network):
    cities, routes, scores = small_network
    cities["airport_pax_mln"] = 0.
    scores = [replace(s, total_score=100.) for s in scores]
    field = compute_gravity_anomaly_field(cities, routes, scores, exclude_existing_rw=True, grid_w=5, grid_h=4)
    # Белые пятна только AAA→BBB и BBB→AAA; масса .6*(1+.1*число направлений).
    weights = np.array([.66, .6, .66])
    assert field.barycenter_lon == pytest.approx(np.average(cities.lon, weights=weights))
    # Пропуск частоты НЕ является нулём и не получает бонус белого пятна.
    routes.loc[(routes.origin_iata == "AAA") & (routes.dest_iata == "BBB"), "own_flights_weekly"] = np.nan
    field = compute_gravity_anomaly_field(cities, routes, scores, exclude_existing_rw=True, grid_w=5, grid_h=4)
    assert field.barycenter_lon == pytest.approx(np.average(cities.lon, weights=[.6, .6, .66]))


def test_field_live_scores_lambda_supply_and_order(live_network):
    cities, routes, scores = live_network
    kwargs = dict(grid_w=13, grid_h=9, mode="anomaly")
    base = compute_gravity_anomaly_field(cities, routes, scores, **kwargs)
    shuffled = compute_gravity_anomaly_field(cities.iloc[::-1], routes.iloc[::-1], scores[::-1], **kwargs)
    np.testing.assert_allclose(base.z_values, shuffled.z_values, atol=1e-10)
    changed_scores = [replace(s, total_score=100 if s.iata == "KUF" else 0) for s in scores]
    for changes in ({"scored_cities": changed_scores}, {"lam": 1.5}, {"gamma": 2.5},
                    {"radius_km": 500.}, {"exclude_existing_rw": True},
                    {"routes_df": routes.assign(competitor_flights_weekly=np.where(routes.origin_iata == "KUF", 100., 0.))}):
        inputs = dict(cities_df=cities, routes_df=routes, scored_cities=scores, **kwargs)
        inputs.update(changes)
        assert not np.allclose(base.z_values, compute_gravity_anomaly_field(**inputs).z_values)


@pytest.mark.parametrize("kwargs", [{"mode": "bad"}, {"grid_w": 1}, {"grid_h": 3.5},
                                    {"grid_h": True}, {"gamma": 0}, {"lam": -1},
                                    {"radius_km": np.inf}, {"exclude_existing_rw": "yes"}])
def test_field_rejects_invalid_parameters(small_network, kwargs):
    with pytest.raises(ValueError):
        compute_gravity_anomaly_field(*small_network, **kwargs)


@pytest.mark.parametrize("problem", ["missing", "duplicate", "invalid_score"])
def test_field_requires_complete_unique_scores(small_network, problem):
    cities, routes, scores = small_network
    if problem == "missing":
        scores = scores[:-1]
    elif problem == "duplicate":
        scores = scores + scores[:1]
    else:
        scores[0] = replace(scores[0], total_score=np.nan)
    with pytest.raises(ValueError):
        compute_gravity_anomaly_field(cities, routes, scores)


def test_network_graph_metrics_improvement(live_network):
    cities, routes, _ = live_network
    # Десять НОВЫХ пар, а не подбор индексов под город-победитель.
    proposed = [("KUF", "PEE"), ("GOJ", "UFA"), ("GOJ", "MRV"), ("UFA", "VOG"),
                ("KUF", "CEK"), ("UFA", "OMS"), ("KZN", "CEK"), ("KUF", "MRV"),
                ("KUF", "VOG"), ("CEK", "GSV")]
    before_c, before_r = cities.copy(deep=True), routes.copy(deep=True)
    baseline, expanded, nodes_b, nodes_p = calculate_network_graph_metrics(cities, routes, proposed)
    assert baseline.active_routes_count == 8 and expanded.active_routes_count == 18
    assert expanded.weighted_travel_time_h < baseline.weighted_travel_time_h
    assert expanded.tarkhov_connectivity_idx > baseline.tarkhov_connectivity_idx
    assert expanded.multimodal_access_idx > baseline.multimodal_access_idx
    assert baseline.mode == "baseline_rw" and expanded.mode == "proposed_network"
    for nodes in (nodes_b, nodes_p):
        assert len(nodes) == 12 and {node.iata for node in nodes} == set(cities.iata)
        assert all(0 <= node.weighted_degree_centrality <= 1 for node in nodes)
    json.dumps([asdict(x) for x in (baseline, expanded, *nodes_b, *nodes_p)], allow_nan=False)
    pd.testing.assert_frame_equal(cities, before_c)
    pd.testing.assert_frame_equal(routes, before_r)
    # Порядок городов и дубль A→B / B→A не меняют сетевые показатели.
    other = calculate_network_graph_metrics(cities.iloc[::-1], routes.sample(frac=1, random_state=42),
                                            proposed + [(b, a) for a, b in proposed])
    for a, b in zip((baseline, expanded), other[:2]):
        for name in asdict(a):
            if name != "mode":
                assert getattr(a, name) == pytest.approx(getattr(b, name))


def test_network_shortest_paths_and_indices_by_hand(small_network):
    cities, routes, _ = small_network
    baseline, expanded, nodes_b, nodes_p = calculate_network_graph_metrics(cities, routes, [], beta=1.)
    # AAA→BBB: baseline Москва 10ч, proposed через KUF 2+1.25+3=6.25ч.
    assert nodes_b[0].city_weighted_time_h == pytest.approx((2*2 + 3*10) / 5)
    assert nodes_p[0].city_weighted_time_h == pytest.approx((2*2 + 3*6.25) / 5)
    assert expanded.weighted_travel_time_h == pytest.approx((1*4.55 + 2*2.75 + 3*(12.25/3)) / 6)
    assert baseline.tarkhov_connectivity_idx == round((2/3) * (470/2250), 4)
    assert expanded.tarkhov_connectivity_idx == round((2/3) * (470/500), 4)
    # baseline AAA→BBB: поезд 8ч лучше Москвы; доезд .25+.5 добавляется после min.
    assert nodes_b[0].city_multimodal_index == pytest.approx((2/2.75 + 3/8.75) / 2)
    assert nodes_p[0].city_multimodal_index == pytest.approx((2/2.75 + 3/7.) / 2)
    assert nodes_b[1].weighted_degree_centrality == pytest.approx(1.)
    assert baseline.avg_degree_centrality == pytest.approx(2/3)
    # При слишком долгой стыковке выбирается Москва, а не бесконечность/худший путь.
    capped = calculate_network_graph_metrics(cities, routes, [], hub_transfer_h=20.)
    assert capped[1].weighted_travel_time_h == pytest.approx(baseline.weighted_travel_time_h)


def test_graph_no_edges_and_no_gravity_are_finite(small_network):
    cities, routes, _ = small_network
    routes["own_flights_weekly"] = 0.
    cities["lat"], cities["lon"] = 50., 40.  # G == 0, деление на max(G) запрещено
    baseline, expanded, nodes_b, _ = calculate_network_graph_metrics(cities, routes, [("AAA", "BBB")])
    assert baseline.active_routes_count == baseline.tarkhov_connectivity_idx == 0
    assert baseline.avg_degree_centrality == 0
    assert all(n.weighted_degree_centrality == 0 for n in nodes_b)
    assert expanded.active_routes_count == 1
    assert expanded.weighted_travel_time_h < baseline.weighted_travel_time_h


@pytest.mark.parametrize("pairs", [[("AAA", "AAA")], [("AAA", "XXX")], ["AAA-BBB"]])
def test_graph_rejects_invalid_proposals(small_network, pairs):
    with pytest.raises(ValueError, match="proposed_pair_codes"):
        calculate_network_graph_metrics(*small_network[:2], pairs)


def test_graph_rejects_incomplete_pair_evidence(small_network):
    cities, routes, _ = small_network
    routes = routes.loc[~((routes.origin_iata.isin(["AAA", "BBB"])) & (routes.dest_iata.isin(["AAA", "BBB"])))]
    with pytest.raises(ValueError, match="всех уникальных пар"):
        calculate_network_graph_metrics(cities, routes, [])


def test_graph_averages_directional_frequencies_and_keeps_existing_weight(small_network):
    cities, routes, _ = small_network
    cities["lat"], cities["lon"] = 50., 40.  # G == 0, можно проверить веса вручную
    routes.loc[(routes.origin_iata == "KUF") & (routes.dest_iata == "AAA"), "own_flights_weekly"] = 4.
    baseline, expanded, nodes_b, nodes_p = calculate_network_graph_metrics(
        cities, routes, [("AAA", "KUF"), ("KUF", "AAA")])
    # Средняя частота AAA—KUF = (2+4)/2 = 3, KUF—BBB = 2.
    assert baseline.active_routes_count == expanded.active_routes_count == 2
    for nodes in (nodes_b, nodes_p):
        np.testing.assert_allclose([n.weighted_degree_centrality for n in nodes], [.6, 1., .4])


@pytest.mark.parametrize("column,value", [("rail_travel_hours", np.nan), ("air_door_to_door_h", 0.),
                                         ("access_time_origin_h", -1.), ("own_flights_weekly", np.inf)])
def test_graph_rejects_invalid_route_evidence(small_network, column, value):
    cities, routes, _ = small_network
    routes.loc[0, column] = value
    with pytest.raises(ValueError, match=column):
        calculate_network_graph_metrics(cities, routes, [])


def test_complete_aviation_graph_does_not_clip_planar_normalization(live_network):
    cities, routes, _ = live_network
    all_pairs = [(a, b) for i, a in enumerate(cities.iata) for b in cities.iata.iloc[i+1:]]
    expanded = calculate_network_graph_metrics(cities, routes, all_pairs)[1]
    assert expanded.active_routes_count == 66
    assert expanded.tarkhov_connectivity_idx == pytest.approx(66 / 30)


@pytest.mark.parametrize("aircraft_id", ["crj200", "sj100_basic", "sj100_lr", "tu214", "mc21_310"])
def test_dev3_aircraft_catalog_to_gravity_and_graph(live_network, aircraft_id):
    """Реальная цепочка контрактов Dev 1 → Dev 3 → Dev 2 для Dev 4."""
    from src.models.sj100_fleet import get_aircraft_gravity_knots, get_aircraft_spec
    from src.models.unit_economics import evaluate_routes_by_aircraft_and_rw_gap

    cities, routes, _ = live_network
    before = routes.copy(deep=True)
    knots = get_aircraft_gravity_knots(aircraft_id)
    spec = get_aircraft_spec(aircraft_id)
    gravity = calculate_gravity_matrix(cities, routes, distance_knots_km=knots, exclude_existing_rw=True)
    assert gravity.attrs["range_knots_km"] == list(knots)
    assert gravity.attrs["excluded_existing_rw_pairs"] == 16
    distances = np.asarray(gravity.attrs["distance_km"])
    values = gravity.to_numpy()
    assert (values[(distances <= spec.min_km) | (distances >= spec.max_km)] == 0).all()
    range_weights = np.asarray(gravity.attrs["range_weight"])
    assert (range_weights[(distances >= spec.opt_low_km) & (distances <= spec.opt_high_km)] == 1).all()

    market, summary = evaluate_routes_by_aircraft_and_rw_gap(routes, aircraft_id)
    proposals = market.loc[market.proposal_bucket.eq("propose_new"), "pair_key"].tolist()
    assert len(proposals) == summary.proposed_new_count
    baseline, expanded, nodes_b, nodes_p = calculate_network_graph_metrics(cities, routes, proposals)
    assert baseline.active_routes_count == summary.existing_rw_count == 8
    assert expanded.active_routes_count == 8 + len(proposals)
    assert expanded.weighted_travel_time_h <= baseline.weighted_travel_time_h
    assert expanded.multimodal_access_idx >= baseline.multimodal_access_idx
    assert expanded.tarkhov_connectivity_idx >= baseline.tarkhov_connectivity_idx
    assert len(nodes_b) == len(nodes_p) == len(cities)
    # Модель считает ровно переданный набор: shortlist, а не все кандидаты.
    shortlisted = calculate_network_graph_metrics(cities, routes, proposals[:10])[1]
    assert shortlisted.active_routes_count == 8 + min(10, len(proposals))
    pd.testing.assert_frame_equal(routes, before)


def test_dev3_low_fare_does_not_create_proposed_edges(live_network):
    from src.models.unit_economics import evaluate_routes_by_aircraft_and_rw_gap

    cities, routes, _ = live_network
    table, summary = evaluate_routes_by_aircraft_and_rw_gap(routes, avg_fare_rub=100., subsidy_cut_pct=100.)
    proposals = table.loc[table.proposal_bucket.eq("propose_new"), "pair_key"].tolist()
    assert summary.proposed_new_count == 0 and proposals == []
    baseline, expanded, _, _ = calculate_network_graph_metrics(cities, routes, proposals)
    # Возможные пересадки по уже имеющимся рёбрам не являются новыми маршрутами.
    assert baseline.active_routes_count == expanded.active_routes_count == 8


def test_legacy_population_cannot_silently_ignore_lambda(small_network):
    cities = small_network[0].assign(effective_population_mln=[1., 2., 3.]).drop(
        columns=["population_city_mln", "agglomeration_members"])
    assert np.isfinite(calculate_gravity_matrix(cities)).all().all()
    with pytest.raises(ValueError, match="lam"):
        calculate_gravity_matrix(cities, lam=.9)


@pytest.mark.parametrize("mode", ["potential", "anomaly"])
def test_field_zero_mass_stays_finite(small_network, mode):
    cities, routes, scores = small_network
    cities["population_city_mln"] = 0.
    scores = [replace(s, total_score=0.) for s in scores]
    field = compute_gravity_anomaly_field(cities, routes, scores, mode=mode, grid_w=4, grid_h=3)
    assert np.isfinite(field.z_values).all()
    assert field.barycenter_lat == pytest.approx(cities.lat.mean())
    assert field.barycenter_lon == pytest.approx(cities.lon.mean())


@pytest.fixture
def complete():
    df = pd.DataFrame({
        "iata": [f"AA{c}" for c in "ABCDEFGHIJKL"],
        "city_name": [f"Синтетический {n}" for n in range(12)],
        "region": "Тест", "population_mln": np.linspace(1, 3, 12),
        "airport_pax_mln": np.linspace(1, 5, 12),
        "dist_to_mow_km": np.linspace(400, 2500, 12),
        "dist_to_svx_km": np.linspace(1600, 200, 12),
        "competitor_gap_score": np.linspace(80, 20, 12),
        "tourism_demand_score": np.linspace(10, 90, 12),
        "moscow_transfer_share_pct": np.linspace(20, 70, 12),
        "airport_feasible": True,
    })
    for criterion in METRICS:
        df[f"src_{criterion}"] = "test_fixture_only"
        df[f"status_{criterion}"] = "derived"
        df[f"period_{criterion}"] = "2025"
        df[f"method_{criterion}"] = "СИНТЕТИЧЕСКИЙ тест свойств, не фактическая оценка"
    return df


def test_normalizer_boundaries_and_index():
    source = pd.Series([30, 10, 20], index=["c", "a", "b"], name="x")
    assert min_max_normalize(source).to_dict() == {"c": 100, "a": 0, "b": 50}
    assert min_max_normalize(source, reverse=True).to_dict() == {"c": 0, "a": 100, "b": 50}
    assert min_max_normalize(pd.Series([8, 8])).tolist() == [50, 50]


@pytest.mark.parametrize("values", [[], [1, np.nan], [1, np.inf], [1, "bad"]])
def test_normalizer_rejects_unknown(values):
    with pytest.raises(ValueError):
        min_max_normalize(pd.Series(values))


def test_case_contributions_scale_and_nonmutation(complete):
    before = complete.copy(deep=True)
    result = score_cities(complete)
    assert len(result.top3) == 3
    assert result.table.total_score.between(0, 100).all()
    assert sum(result.weights.values()) == pytest.approx(1)
    assert result.weights["population"] == pytest.approx(.24)
    assert result.weights["moscow_transfer"] == pytest.approx(.20)
    parts = result.table.filter(like="contribution_").sum(axis=1)
    np.testing.assert_allclose(parts, result.table.total_score)
    pd.testing.assert_frame_equal(complete, before)


def test_weight_rescaling_and_shuffle_invariant(complete):
    a = score_cities(complete)
    b = score_cities(complete.sample(frac=1, random_state=4), ScoringWeights(30, 20, 30, 20))
    pd.testing.assert_frame_equal(a.table[["iata", "rank", "total_score"]], b.table[["iata", "rank", "total_score"]])


@pytest.mark.parametrize("weights", [ScoringWeights(0, 0, 0, 0), ScoringWeights(-1, 1, 1, 1),
                                   ScoringWeights(np.nan, 1, 1, 1), ScoringWeights(np.inf, 1, 1, 1)])
def test_invalid_weights(weights):
    with pytest.raises(ValueError):
        effective_weights(weights, mode="case")


def test_distance_accounts_for_both_hubs(complete):
    result = prepare_features(complete)
    np.testing.assert_allclose(result.distance_to_nearest_hub_km, np.minimum(complete.dist_to_mow_km, complete.dist_to_svx_km))


def test_distance_derived_from_svx_row(complete):
    df = complete.drop(columns="dist_to_svx_km")
    df.loc[0, "iata"] = "SVX"
    df["lat"], df["lon"] = 56.741, 60.804
    df.loc[1, "lat"] += 1
    result = prepare_features(df)
    assert result.loc[0, "dist_to_svx_km"] == 0
    assert result.loc[1, "dist_to_svx_km"] == pytest.approx(111.195, abs=.01)


@pytest.mark.parametrize("problem", ["short", "duplicate", "nan", "outside"])
def test_bad_inputs(complete, problem):
    if problem == "short":
        complete = complete.head(9)
    elif problem == "duplicate":
        complete.loc[1, "iata"] = complete.loc[0, "iata"]
    elif problem == "nan":
        complete.loc[0, "population_mln"] = np.nan
    else:
        complete.loc[0, "moscow_transfer_share_pct"] = 101
    with pytest.raises(ValueError):
        score_cities(complete)


def test_case_missing_transfer_never_silent_fallback(complete):
    df = complete.drop(columns="moscow_transfer_share_pct")
    with pytest.raises(ValueError, match="moscow_transfer_share_pct"):
        score_cities(df, mode="case")
    result = score_cities(df, mode="exploratory")
    assert result.table.result_status.eq("preliminary").all()
    assert "moscow_transfer" not in result.weights


def test_sources_periods_and_estimates_are_required(complete):
    complete.loc[0, "src_population"] = ""
    with pytest.raises(ValueError, match="src"):
        score_cities(complete)
    complete.loc[0, "src_population"] = "test_fixture_only"
    complete.loc[0, "period_population"] = "2024"
    with pytest.raises(ValueError, match="period_population"):
        score_cities(complete)
    complete.loc[0, "period_population"] = "2025"
    complete.loc[0, "status_moscow_transfer"] = "estimated"
    with pytest.raises(ValueError, match="диапазон"):
        score_cities(complete)
    complete.loc[0, "low_moscow_transfer"] = 10
    complete.loc[0, "high_moscow_transfer"] = 30
    assert len(score_cities(complete).top3) == 3


def test_airport_gate_and_reference_hub(complete):
    complete.loc[0, "iata"] = "SVX"
    complete.loc[1, "airport_feasible"] = False
    hub = score_cities(complete)
    assert not hub.table.set_index("iata").loc["SVX", "eligible"]
    assert not hub.table.set_index("iata").loc["AAB", "eligible"]
    assert score_cities(complete, hypothesis="p2p").table.set_index("iata").loc["SVX", "eligible"]
    complete["airport_feasible"] = None
    with pytest.raises(ValueError, match="airport_feasible"):
        score_cities(complete)


def test_ties_are_stable_and_disclosed(complete):
    for col in ["population_mln", "dist_to_mow_km", "dist_to_svx_km", "competitor_gap_score",
                "tourism_demand_score", "moscow_transfer_share_pct"]:
        complete[col] = complete[col].iloc[0]
    result = score_cities(complete.sample(frac=1, random_state=1))
    assert result.top3.iata.tolist() == ["AAA", "AAB", "AAC"]
    assert result.table.cutoff_tie.all()


def test_increasing_benefit_never_reduces_own_score(complete):
    before = score_cities(complete).table.set_index("iata").loc["AAA", "total_score"]
    complete.loc[0, "moscow_transfer_share_pct"] += 5
    after = score_cities(complete).table.set_index("iata").loc["AAA", "total_score"]
    assert after - before == pytest.approx(1.0)


def test_sensitivity_reproducible_and_is_weights_only(complete):
    result = score_cities(complete)
    a = weight_sensitivity(result, n_samples=200, seed=5)
    b = weight_sensitivity(result, n_samples=200, seed=5)
    pd.testing.assert_frame_equal(a, b)
    assert a.top3_frequency.sum() == pytest.approx(3)
    fixed = weight_sensitivity(result, relative_change=0, n_samples=10)
    assert set(fixed.loc[fixed.top3_frequency.eq(1), "iata"]) == set(result.top3.iata)


def test_compatible_dto(complete):
    rows = get_scored_cities(ScoringWeights(), data=complete)
    assert all(isinstance(row, CityScoreDTO) for row in rows)
    assert sum(row.is_top3 for row in rows) == 3
    with pytest.warns(UserWarning, match="Предварительный"):
        get_scored_cities(ScoringWeights(), data=complete, mode="exploratory")


def test_reference_snapshot_is_honestly_preliminary():
    from src.scoring.city_scorer import load_features
    reference = Path(__file__).resolve().parents[1] / "reference/dev1_e364ac7.csv"
    data = load_features(reference)
    assert len(data) >= 10
    result = score_cities(data, mode="exploratory")
    assert len(result.top3) == 3
    assert result.top3.result_status.eq("preliminary").all()
    assert len(result.audit) == len(data) * len(METRICS)
    with pytest.raises(ValueError, match="moscow_transfer_share_pct"):
        score_cities(data, mode="case")


def test_cli_exports_auditable_files(complete, tmp_path, monkeypatch):
    from src.scoring.__main__ import main
    input_path, output = tmp_path / "input.csv", tmp_path / "results"
    complete.to_csv(input_path, index=False)
    monkeypatch.setattr(sys, "argv", ["scoring", "--input", str(input_path),
                                    "--output", str(output), "--samples", "20"])
    assert main() == 0
    metadata = json.loads((output / "run_metadata.json").read_text(encoding="utf-8"))
    assert metadata["mode"] == "case"
    assert len(metadata["input_sha256"]) == 64
    assert len(pd.read_csv(output / "top3.csv")) == 3
    assert len(pd.read_csv(output / "data_audit.csv")) == len(complete) * len(METRICS)


def test_cli_rejects_missing_data_before_export(complete, tmp_path, monkeypatch):
    from src.scoring.__main__ import main
    input_path, output = tmp_path / "input.csv", tmp_path / "results"
    complete.drop(columns="moscow_transfer_share_pct").to_csv(input_path, index=False)
    monkeypatch.setattr(sys, "argv", ["scoring", "--input", str(input_path), "--output", str(output),
                                    "--mode", "case"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert not output.exists()


def test_distance_sweet_spot_rewards_optimum_and_penalizes_tails():
    source = pd.Series([350.0, 800.0, 1150.0, 1500.0, 2100.0, 10000.0],
                       index=list("abcdef"), name="distance")
    scores = distance_sweet_spot_score(source)
    assert scores.idxmax() == "c"
    assert scores.loc["c"] == 100
    assert scores.loc["b"] == pytest.approx(scores.loc["d"])
    assert scores.loc["a"] < scores.loc["b"] < scores.loc["c"]
    assert scores.loc["e"] < scores.loc["d"] < scores.loc["c"]
    assert scores.loc["f"] == 35
    assert scores.index.equals(source.index)
    assert scores.name == source.name
    assert distance_sweet_spot_score(pd.Series([600]), optimal_km=600).iloc[0] == 100


@pytest.mark.parametrize("values", [[], [-1], [np.nan], [np.inf], ["bad"]])
def test_distance_sweet_spot_rejects_invalid_distances(values):
    with pytest.raises(ValueError):
        distance_sweet_spot_score(pd.Series(values))


@pytest.mark.parametrize("optimum", [0, -1, np.nan, np.inf, "bad", True])
def test_distance_sweet_spot_rejects_invalid_optimum(optimum):
    with pytest.raises(ValueError):
        distance_sweet_spot_score(pd.Series([100]), optimum)


@pytest.mark.parametrize("column", ["moscow_transfer_share_pct", "airport_feasible", "src_population"])
def test_auto_falls_back_on_missing_case_columns(complete, column):
    with pytest.warns(UserWarning, match="auto выбрал exploratory"):
        result = score_cities(complete.drop(columns=column))
    assert result.mode == "exploratory"
    assert set(result.weights) == {"population", "hub_distance", "competitor_gap", "tourism_demand"}
    assert result.table.result_status.eq("preliminary").all()
    assert any(column in text for text in result.limitations)


def test_auto_does_not_hide_invalid_complete_data(complete):
    complete.loc[0, "moscow_transfer_share_pct"] = 101
    with pytest.raises(ValueError, match="диапазона"):
        score_cities(complete)


def test_default_api_reads_dev1_parquet_and_keeps_all_cities(tmp_path):
    from src.scoring.city_scorer import load_features
    data = load_features(Path(__file__).resolve().parents[1] / "reference/dev1_e364ac7.csv")
    path = tmp_path / "cities_features.parquet"
    data.to_parquet(path, index=False)
    with pytest.warns(UserWarning, match="auto выбрал exploratory"):
        rows = get_scored_cities(ScoringWeights(), path=path)
    assert len(rows) == 12
    assert {c.iata for c in rows} == set(data.iata)
    assert "SVX" in {c.iata for c in rows}
    assert sum(c.is_top3 for c in rows) == 3
    assert [c.rank for c in rows] == list(range(1, 13))
    for city in rows:
        for field in ("total_score", "population_mln", "airport_pax_mln"):
            value = getattr(city, field)
            assert value == round(value, 2)


def test_explicit_hub_api_keeps_svx_for_map_but_not_top3(complete):
    complete.loc[0, "iata"] = "SVX"
    rows = get_scored_cities(ScoringWeights(), data=complete, hypothesis="hub")
    assert len(rows) == len(complete)
    svx = next(c for c in rows if c.iata == "SVX")
    assert not svx.is_top3
    assert svx.rank == len(rows)
    assert sum(c.is_top3 for c in rows) == 3


def test_minimal_base_schema_does_not_require_coordinates_or_svx(complete):
    base = complete[["iata", "city_name", "region", "population_mln", "airport_pax_mln",
                     "dist_to_mow_km", "competitor_gap_score", "tourism_demand_score"]]
    with pytest.warns(UserWarning):
        rows = get_scored_cities(ScoringWeights(), data=base)
    assert len(rows) == len(base)


def test_distance_score_does_not_depend_on_svx_proximity(complete):
    before = score_cities(complete).table.set_index("iata")
    complete["dist_to_svx_km"] = 0
    after = score_cities(complete).table.set_index("iata")
    pd.testing.assert_series_equal(before.score_hub_distance, after.score_hub_distance)


def test_dto_rounding_does_not_change_order(complete):
    complete["tourism_demand_score"] = 50.0
    complete.loc[11, "tourism_demand_score"] = 50.001
    weights = ScoringWeights(0, 0, 0, 1)
    with pytest.warns(UserWarning):
        rows = get_scored_cities(weights, data=complete, mode="exploratory")
    assert all(c.total_score == 50 for c in rows)
    assert rows[0].iata == "AAL"
    assert rows[0].rank == 1


def test_cli_auto_exports_actual_selected_mode(complete, tmp_path, monkeypatch):
    from src.scoring.__main__ import main
    path, output = tmp_path / "input.csv", tmp_path / "results"
    complete.drop(columns="moscow_transfer_share_pct").to_csv(path, index=False)
    monkeypatch.setattr(sys, "argv", ["scoring", "--input", str(path), "--output", str(output), "--samples", "20"])
    with pytest.warns(UserWarning, match="auto выбрал exploratory"):
        assert main() == 0
    metadata = json.loads((output / "run_metadata.json").read_text(encoding="utf-8"))
    assert metadata["requested_mode"] == "auto"
    assert metadata["mode"] == "exploratory"
    assert metadata["distance_scoring"]["input"] == "dist_to_mow_km"
