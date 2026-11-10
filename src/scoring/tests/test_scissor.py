"""Геометрические контрольные примеры транзитного индекса, без данных пассажиров."""
import numpy as np
import pandas as pd
import pytest

from src.scoring.city_scorer import calculate_scissor_hub_index


@pytest.fixture
def line():
    cities = pd.DataFrame({"iata": ["AAA", "BBB", "CCC"], "lat": [0., 0., 0.], "lon": [0., 5., 10.]})
    # Огромные веса рейсов, начинающихся/заканчивающихся в BBB, не транзитны.
    gravity = pd.DataFrame([[0., 100., 2.], [200., 0., 300.], [5., 400., 0.]],
                           index=cities.iata, columns=cities.iata)
    return cities, gravity


def test_collinear_hub_sums_both_directions_once_and_excludes_endpoints(line):
    cities, gravity = line
    before_cities, before_gravity = cities.copy(deep=True), gravity.copy(deep=True)
    result = calculate_scissor_hub_index(cities, gravity)
    rows = result.set_index("iata")
    assert rows.loc["BBB", "scissor_hub_index"] == 7
    assert rows.loc["BBB", "eligible_directed_pairs"] == 2
    assert rows.loc["BBB", "eligible_undirected_pairs"] == 1
    assert rows.loc["AAA", "scissor_hub_index"] == rows.loc["CCC", "scissor_hub_index"] == 0
    assert rows.loc["AAA", "scissor_rank"] == rows.loc["CCC", "scissor_rank"] == 2
    pairs = pd.DataFrame(result.attrs["pair_details"])
    assert len(pairs) == 6
    assert (pairs.hub_iata != pairs.origin_iata).all()
    assert (pairs.hub_iata != pairs.dest_iata).all()
    assert (pairs.origin_iata != pairs.dest_iata).all()
    assert not pairs.duplicated(["hub_iata", "origin_iata", "dest_iata"]).any()
    pd.testing.assert_frame_equal(cities, before_cities)
    pd.testing.assert_frame_equal(gravity, before_gravity)


def test_fifteen_percent_boundary_is_strict_and_threshold_is_configurable(line):
    cities, gravity = line
    cities.loc[1, "lon"] = 10.75  # 0→10.75→10: 11.5 / 10 = 1.15
    at_boundary = calculate_scissor_hub_index(cities, gravity).set_index("iata")
    above_boundary = calculate_scissor_hub_index(cities, gravity, max_detour_pct=15.01).set_index("iata")
    assert at_boundary.loc["BBB", "scissor_hub_index"] == 0
    assert above_boundary.loc["BBB", "scissor_hub_index"] == 7
    assert calculate_scissor_hub_index(cities, gravity, max_detour_pct=0).scissor_hub_index.eq(0).all()


def test_aligns_by_iata_without_attrs_and_preserves_scaling(line):
    cities, gravity = line
    baseline = calculate_scissor_hub_index(cities, gravity)
    shuffled = gravity.loc[["CCC", "AAA", "BBB"], ["BBB", "CCC", "AAA"]].copy()
    shuffled.index = shuffled.index.str.lower()
    shuffled.attrs = {}
    actual = calculate_scissor_hub_index(cities.iloc[::-1], shuffled)
    pd.testing.assert_frame_equal(actual, baseline)
    scaled = calculate_scissor_hub_index(cities, gravity * 3)
    np.testing.assert_allclose(scaled.scissor_hub_index, baseline.scissor_hub_index * 3)


def test_zero_direct_distance_is_audited_and_does_not_divide_by_zero(line):
    cities, gravity = line
    cities.loc[2, "lon"] = 0
    result = calculate_scissor_hub_index(cities, gravity)
    pairs = pd.DataFrame(result.attrs["pair_details"])
    undefined = pairs.loc[~pairs.distance_ratio_defined]
    assert len(undefined) == 2
    assert undefined.detour_ratio.isna().all()
    assert (~undefined.eligible).all() and undefined.contribution.eq(0).all()
    assert np.isfinite(result.scissor_hub_index).all()


def test_zero_gravity_does_not_create_transit_mass(line):
    cities, gravity = line
    result = calculate_scissor_hub_index(cities, gravity * 0).set_index("iata")
    assert result.scissor_hub_index.eq(0).all()
    assert result.scissor_rank.eq(1).all()
    assert result.loc["BBB", "eligible_directed_pairs"] == 2
    assert result.loc["BBB", "positive_gravity_directed_pairs"] == 0


@pytest.mark.parametrize("value", [-1, np.nan, np.inf, True, "bad"])
def test_rejects_invalid_threshold(line, value):
    with pytest.raises(ValueError, match="max_detour_pct"):
        calculate_scissor_hub_index(*line, max_detour_pct=value)


@pytest.mark.parametrize("problem", ["duplicate", "missing", "extra", "negative", "nan", "inf", "diagonal", "text"])
def test_rejects_invalid_gravity(line, problem):
    cities, gravity = line
    if problem == "duplicate":
        gravity.index = ["AAA", "BBB", "BBB"]
    elif problem == "missing":
        gravity = gravity.drop(index="CCC")
    elif problem == "extra":
        gravity["DDD"] = 0
    elif problem == "diagonal":
        gravity.iloc[0, 0] = 1
    else:
        if problem == "text":
            gravity = gravity.astype(object)
        gravity.iloc[0, 1] = {"negative": -1, "nan": np.nan, "inf": np.inf, "text": "bad"}[problem]
    with pytest.raises(ValueError, match="gravity_df"):
        calculate_scissor_hub_index(cities, gravity)


@pytest.mark.parametrize("column,value", [("lat", 91), ("lon", np.nan), ("iata", "AAA")])
def test_rejects_invalid_coordinates_or_duplicate_city(line, column, value):
    cities, gravity = line
    cities.loc[1, column] = value
    with pytest.raises(ValueError):
        calculate_scissor_hub_index(cities, gravity)
