"""
Смоук-тесты соблюдения контрактов данных между модулями.
ВЛАДЕЛЕЦ ФАЙЛА: Tech Lead / Вся команда
"""

from src.schemas.contracts import ScoringWeights, FinModelInput
from src.mocks.mock_provider import get_scored_cities, evaluate_hypotheses


def test_contracts_smoke() -> None:
    weights = ScoringWeights()
    cities = get_scored_cities(weights)
    assert len(cities) >= 3
    assert sum(1 for c in cities if c.is_top3) == 3

    fin_in = FinModelInput()
    bundle = evaluate_hypotheses(fin_in, cities)
    assert bundle.winner in ("hub", "p2p")


# ---------------------------------------------------------------- витрины Dev 1

import dataclasses
import typing

import pandas as pd
import pytest

from src.parsers.build_dataset import CITIES_PATH, ROUTES_PATH
from src.schemas import contracts

RW_EXISTING_PAIRS = {
    "KZN-SVX", "KUF-SVX", "GOJ-SVX", "SVX-UFA",   # existing_core
    "GSV-SVX", "OMS-SVX", "GOJ-KUF", "KUF-TJM",   # existing_thin
}
STATUSES = set(typing.get_args(contracts.RouteRwStatus))


@pytest.fixture(scope="module")
def routes() -> pd.DataFrame:
    df = pd.read_parquet(ROUTES_PATH)
    df["pair"] = ["-".join(sorted(k)) for k in zip(df["origin_iata"], df["dest_iata"])]
    return df


def test_new_contracts_are_frozen_dataclasses() -> None:
    for name in ("AircraftSpecDTO", "GravityFieldGridDTO", "CityGraphNodeDTO",
                 "NetworkGraphMetricsDTO", "FleetGapSummaryDTO"):
        cls = getattr(contracts, name)
        assert dataclasses.is_dataclass(cls) and cls.__dataclass_params__.frozen, name
    assert set(typing.get_args(contracts.AircraftModelId)) == {
        "sj100_basic", "sj100_lr", "tu214", "mc21_310", "crj200"}
    assert set(typing.get_args(contracts.MapLensMode)) == {
        "routes_gap", "aircraft_range", "gravity_lens"}


def test_routes_132_rows_66_pairs(routes: pd.DataFrame) -> None:
    assert len(routes) == 132
    assert routes["pair"].nunique() == 66
    assert not routes.duplicated(["origin_iata", "dest_iata"]).any()


def test_rw_existing_8_pairs_16_rows(routes: pd.DataFrame) -> None:
    existing = routes[routes["rw_network_status"].isin(["existing_core", "existing_thin"])]
    assert len(existing) == 16
    assert set(existing["pair"]) == RW_EXISTING_PAIRS


def test_statuses_sum_to_66_pairs(routes: pd.DataFrame) -> None:
    assert set(routes["rw_network_status"]) <= STATUSES
    assert (routes.groupby("pair")["rw_network_status"].nunique() == 1).all()
    assert routes.drop_duplicates("pair")["rw_network_status"].value_counts().sum() == 66


def test_status_rules(routes: pd.DataFrame) -> None:
    g = routes.groupby("pair")
    own = g["own_flights_weekly"].transform("max")
    comp = g["competitor_flights_weekly"].transform("max")
    st = routes["rw_network_status"]
    assert (st[own >= 4] == "existing_core").all()
    assert (st[(own >= 1) & (own < 4)] == "existing_thin").all()
    assert (st[(own == 0) & (comp == 0)] == "new_blue_ocean").all()
    assert (st[(own == 0) & (comp > 0)] == "new_head_to_head").all()


def test_time_columns(routes: pd.DataFrame) -> None:
    cols = ["air_door_to_door_h", "moscow_via_time_h", "rail_travel_hours",
            "access_time_origin_h", "access_time_dest_h"]
    assert not routes[cols].isna().any().any()
    assert (routes["air_door_to_door_h"] == ((routes["flight_time_min"] + 90) / 60).round(2)).all()
    assert (routes["moscow_via_time_h"] > routes["air_door_to_door_h"]).all()
    assert routes["access_time_origin_h"].between(0.45, 2.0).all()


def test_cities_features_columns() -> None:
    cities = pd.read_parquet(CITIES_PATH)
    need = ["iata", "city_name", "region", "lat", "lon", "population_mln", "population_city_mln",
            "agglomeration_members", "avg_wage_rub_region", "airport_pax_mln", "dist_to_mow_km",
            "competitor_gap_score", "tourism_demand_score"]
    assert not set(need) - set(cities.columns)
    assert len(cities) == 12 and not cities[need].isna().any().any()
    member = r"[^;()]+ \(\d{1,3}(?:,\d{3})+\)"
    assert cities["agglomeration_members"].str.fullmatch(rf"{member}(?:; {member})*").all()
