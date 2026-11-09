import pandas as pd

from src.parsers.build_dataset import (
    MAX_ROUTES,
    ROUTES_PATH,
    CITIES_PATH,
    build_processed_tables,
    get_network_routes,
)


def _build_once():
    build_processed_tables()


def test_cities_have_sources_and_population():
    _build_once()
    cities = pd.read_parquet(CITIES_PATH)
    assert len(cities) >= 10
    assert cities["population_mln"].notna().all()
    assert cities["src_population"].str.contains("rosstat_cities.csv").all()


def test_routes_are_capped_and_sourced():
    _build_once()
    for hypothesis in ("p2p", "hub"):
        routes = get_network_routes(hypothesis, "KUF")
        assert 8 <= len(routes) <= MAX_ROUTES
        assert routes["proof_source"].notna().all()
        assert not routes["proof_source"].str.contains("nan").any()
        assert (routes["origin"] != routes["dest"]).all()


def test_competitor_counts_exclude_own_operator():
    _build_once()
    routes = pd.read_parquet(ROUTES_PATH)
    row = routes[(routes["origin"] == "SVX") & (routes["dest"] == "UFA")].iloc[0]
    # Utair 14/нед — конкурент; Red Wings 4/нед — собственный рейс, в конкуренты не входит
    assert row["competitor_flights_weekly"] == 14
    assert "Red Wings уже выполняет 4" in row["proof_source"]


def test_unmeasured_pair_is_marked_not_zero():
    _build_once()
    routes = pd.read_parquet(ROUTES_PATH)
    # Пара KUF→OVB не занесена в competitor_schedules.csv: частота не измерена, а не 0
    row = routes[(routes["origin"] == "KUF") & (routes["dest"] == "OVB")].iloc[0]
    assert pd.isna(row["competitor_flights_weekly"])
    assert "НЕ ИЗМЕРЕНО" in row["proof_source"]
