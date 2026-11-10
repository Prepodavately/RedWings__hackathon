"""Ручные контрольные примеры и свойства модели; население здесь синтетическое."""
import math

import numpy as np
import pandas as pd
import pytest

from src.scoring import city_scorer as scorer


@pytest.fixture
def catchment():
    return pd.DataFrame({
        "iata": ["KUF"], "population_city_mln": [1.0],
        "agglomeration_members": ["Городской округ Тольятти (662,683); Район (100 000)"],
    }, index=["original"])


@pytest.fixture
def pair():
    # На экваторе 1000 км по большой окружности, W=1.
    return pd.DataFrame({
        "iata": ["AAA", "BBB"], "lat": [0.0, 0.0],
        "lon": [0.0, math.degrees(1000 / 6371)],
        "effective_population_mln": [2.0, 3.0], "avg_wage_rub_region": [50_000, 200_000],
    })


def test_effective_population_units_decay_index_and_nonmutation(catchment):
    before = catchment.copy(deep=True)
    result = scorer.calculate_effective_population(catchment)
    expected = 1 + .662683 * math.exp(-.45 * .75) + .1 * math.exp(-.45 * .65)
    assert result.iloc[0] == pytest.approx(expected)
    assert result.index.equals(catchment.index)
    assert result.name == "effective_population_mln"
    assert scorer.calculate_effective_population(catchment, lam=0).iloc[0] == pytest.approx(1.762683)
    assert [r["time_source"] for r in result.attrs["catchment_details"]] == ["scenario_override", "scenario_default"]
    pd.testing.assert_frame_equal(catchment, before)


def test_effective_population_airport_specific_override_and_two_hour_boundary(catchment, monkeypatch):
    catchment["agglomeration_members"] = "Муниципальный район Волжский (100,000)"
    default = scorer.calculate_effective_population(catchment).iloc[0]
    assert default == pytest.approx(1 + .1 * math.exp(-.45 * .65))
    monkeypatch.setitem(scorer.AIRPORT_ACCESS_HOURS, "KUF", {"волжский": 2.0})
    assert scorer.calculate_effective_population(catchment).iloc[0] == pytest.approx(1 + .1 * math.exp(-.9))
    monkeypatch.setitem(scorer.AIRPORT_ACCESS_HOURS, "KUF", {"волжский": 2.01})
    result = scorer.calculate_effective_population(catchment)
    assert result.iloc[0] == 1
    assert not result.attrs["catchment_details"][0]["within_two_hours"]


@pytest.mark.parametrize("members", [None, np.nan, "Город (1,2)", "Город (-100)", "Город (100); город (100)"])
def test_unknown_or_ambiguous_members_are_not_silently_dropped(catchment, members):
    catchment["agglomeration_members"] = members
    with pytest.raises(ValueError):
        scorer.calculate_effective_population(catchment)


def test_explicit_empty_catchment_preserves_core(catchment):
    catchment["agglomeration_members"] = ""
    assert scorer.calculate_effective_population(catchment).iloc[0] == 1


@pytest.mark.parametrize("lam", [-1, np.inf, np.nan, True])
def test_invalid_lambda(catchment, lam):
    with pytest.raises(ValueError):
        scorer.calculate_effective_population(catchment, lam)


def test_range_filter_boundaries_and_linear_transitions():
    distances = np.array([0, 299, 300, 550, 800, 1150, 1500, 2250, 3000, 4000])
    np.testing.assert_allclose(scorer._gravity_range_weight(distances), [0, 0, 0, .5, 1, 1, 1, .5, 0, 0])


def test_gravity_matches_hand_calculation_and_does_not_mutate(pair):
    before = pair.copy(deep=True)
    matrix = scorer.calculate_gravity_matrix(pair)
    expected = 2 * 3 * math.sqrt(.4 * 1.6) / (1000 ** 1.15)
    assert matrix.loc["AAA", "BBB"] == pytest.approx(expected)
    np.testing.assert_array_equal(matrix.values, matrix.values.T)
    assert np.diag(matrix).tolist() == [0, 0]
    assert matrix.attrs["missing_competition_pairs"] == 2
    assert matrix.attrs["gravity_hub_potential"] == matrix.sum(axis=1).to_dict()
    pd.testing.assert_frame_equal(pair, before)


def test_directional_competition_and_missing_observation(pair):
    routes = pd.DataFrame({"origin_iata": ["aaa", "BBB"], "dest_iata": ["BBB", "AAA"],
                           "competitor_flights_weekly": [1, np.nan]})
    before = routes.copy(deep=True)
    base = scorer.calculate_gravity_matrix(pair)
    result = scorer.calculate_gravity_matrix(pair, routes)
    assert result.loc["AAA", "BBB"] == pytest.approx(base.loc["AAA", "BBB"] / 2)
    assert result.loc["BBB", "AAA"] == pytest.approx(base.loc["BBB", "AAA"])
    assert result.attrs["missing_competition_pairs"] == 1
    pd.testing.assert_frame_equal(routes, before)
    routes.loc[1, "competitor_flights_weekly"] = 0
    observed_zero = scorer.calculate_gravity_matrix(pair, routes)
    np.testing.assert_array_equal(result, observed_zero)
    assert observed_zero.attrs["missing_competition_pairs"] == 0


def test_gravity_scaling_and_permutation(pair):
    base = scorer.calculate_gravity_matrix(pair)
    changed = pair.copy()
    changed["avg_wage_rub_region"] *= 100
    np.testing.assert_allclose(scorer.calculate_gravity_matrix(changed), base)
    changed.loc[0, "effective_population_mln"] *= 2
    np.testing.assert_allclose(scorer.calculate_gravity_matrix(changed), base * 2)
    shuffled = scorer.calculate_gravity_matrix(pair.iloc[::-1])
    np.testing.assert_allclose(shuffled.loc[base.index, base.columns], base)
    assert scorer.calculate_gravity_matrix(pair, gamma=2).loc["AAA", "BBB"] < base.loc["AAA", "BBB"]


def test_coincident_coordinates_and_empty_routes_do_not_divide_by_zero(pair):
    pair["lon"] = 0.0
    matrix = scorer.calculate_gravity_matrix(pair, pd.DataFrame())
    assert np.isfinite(matrix).all().all()
    assert (matrix == 0).all().all()


@pytest.mark.parametrize("frequency", [-1, np.inf, "bad"])
def test_invalid_frequency(pair, frequency):
    routes = pd.DataFrame({"origin_iata": ["AAA"], "dest_iata": ["BBB"], "competitor_flights_weekly": [frequency]})
    with pytest.raises(ValueError, match="competitor_flights_weekly"):
        scorer.calculate_gravity_matrix(pair, routes)


def test_duplicate_direction_requires_explicit_aggregation(pair):
    routes = pd.DataFrame({"origin_iata": ["AAA"] * 2, "dest_iata": ["BBB"] * 2,
                           "competitor_flights_weekly": [1, 2]})
    with pytest.raises(ValueError, match="повтор пары"):
        scorer.calculate_gravity_matrix(pair, routes)


@pytest.mark.parametrize("column,value", [("lat", 91), ("lon", np.nan), ("avg_wage_rub_region", 0),
                                         ("effective_population_mln", -1), ("iata", "BBB")])
def test_invalid_city_inputs(pair, column, value):
    pair.loc[0, column] = value
    with pytest.raises(ValueError):
        scorer.calculate_gravity_matrix(pair)


@pytest.mark.parametrize("gamma", [0, -1, np.nan, np.inf, True])
def test_invalid_gamma(pair, gamma):
    with pytest.raises(ValueError):
        scorer.calculate_gravity_matrix(pair, gamma=gamma)


def test_gravity_derives_default_effective_population(pair):
    cities = pair.drop(columns="effective_population_mln").assign(population_city_mln=[2., 3.], agglomeration_members="")
    np.testing.assert_allclose(scorer.calculate_gravity_matrix(cities), scorer.calculate_gravity_matrix(pair))
