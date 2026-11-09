"""Проверки свойств скоринга; синтетические значения не являются данными городов."""
import json
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
    metadata = json.loads((output / "run_metadata.json").read_text())
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
    metadata = json.loads((output / "run_metadata.json").read_text())
    assert metadata["requested_mode"] == "auto"
    assert metadata["mode"] == "exploratory"
    assert metadata["distance_scoring"]["input"] == "dist_to_mow_km"
