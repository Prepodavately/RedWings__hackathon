"""Стыковка с загрузчиком Dev 1 и воспроизводимость новых отчётов."""
import hashlib
import json
import sys

import numpy as np
import pandas as pd
import pytest

from src.parsers import rosstat_loader
from src.scoring import city_scorer as scorer
from src.scoring.__main__ import main
from src.schemas.contracts import ScoringWeights


def test_missing_default_uses_loader_and_does_not_write_parquet(tmp_path, monkeypatch):
    path = tmp_path / "cities_features.parquet"
    monkeypatch.setattr(scorer, "DEFAULT_DATA_PATH", path)
    expected = rosstat_loader.load_rosstat_and_rosaviatsia()
    monkeypatch.setattr(rosstat_loader, "load_rosstat_and_rosaviatsia", lambda: expected)
    with pytest.warns(UserWarning, match="загрузчик Dev 1"):
        actual = scorer.load_features()
    pd.testing.assert_frame_equal(actual, expected)
    actual.loc[0, "city_name"] = "changed"
    assert expected.loc[0, "city_name"] != "changed"
    with pytest.warns(UserWarning):
        dtos = scorer.get_scored_cities(ScoringWeights())
    assert len(dtos) == 12 and any(row.iata == "SVX" for row in dtos)
    assert sum(row.is_top3 for row in dtos) == 3
    assert not path.exists()


def test_custom_missing_or_corrupt_file_does_not_trigger_loader(tmp_path, monkeypatch):
    def forbidden():
        raise AssertionError("loader must not run")
    monkeypatch.setattr(rosstat_loader, "load_rosstat_and_rosaviatsia", forbidden)
    with pytest.raises(FileNotFoundError):
        scorer.load_features(tmp_path / "typo.parquet")
    corrupt = tmp_path / "cities_features.parquet"
    corrupt.write_bytes(b"invalid parquet")
    monkeypatch.setattr(scorer, "DEFAULT_DATA_PATH", corrupt)
    with pytest.raises(ValueError):
        scorer.load_features()


def test_cli_fallback_exports_hash_of_actual_input(tmp_path, monkeypatch):
    path, output = tmp_path / "cities_features.parquet", tmp_path / "reports"
    monkeypatch.setattr(scorer, "DEFAULT_DATA_PATH", path)
    monkeypatch.setattr(sys, "argv", ["scoring", "--input", str(path), "--output", str(output), "--samples", "20"])
    with pytest.warns(UserWarning):
        assert main() == 0
    metadata = json.loads((output / "run_metadata.json").read_text())
    assert metadata["input_hash_kind"] == "fallback_input_csv_bytes"
    assert metadata["input_source"].endswith("load_rosstat_and_rosaviatsia")
    assert hashlib.sha256((output / metadata["input_snapshot"]).read_bytes()).hexdigest() == metadata["input_sha256"]
    assert not path.exists()


def test_gravity_exports_all_pairs_and_keep_linear_ranking(tmp_path, monkeypatch):
    root = scorer.PROJECT_ROOT
    source = root / "data/processed/cities_features.parquet"
    routes = root / "data/processed/routes_proof.parquet"
    monkeypatch.setattr(sys, "argv", ["scoring", "--input", str(source), "--output", str(tmp_path),
        "--samples", "20", "--with-gravity", "--routes", str(routes), "--with-scissor"])
    with pytest.warns(UserWarning):
        assert main() == 0
    matrix = pd.read_csv(tmp_path / "gravity_matrix.csv", index_col=0)
    pairs = pd.read_csv(tmp_path / "gravity_pairs.csv")
    population = pd.read_csv(tmp_path / "effective_population.csv").set_index("iata")
    potential = pd.read_csv(tmp_path / "gravity_hub_potential.csv").set_index("iata")
    metadata = json.loads((tmp_path / "run_metadata.json").read_text())
    assert matrix.shape == (12, 12) and len(pairs) == 132
    assert not pairs.duplicated(["origin_iata", "dest_iata"]).any()
    assert np.isfinite(matrix).all().all() and (np.diag(matrix) == 0).all()
    np.testing.assert_allclose(matrix.sum(axis=1), potential.loc[matrix.index, "gravity_hub_potential"])
    assert (population.effective_population_mln <= population.population_from_members_mln).all()
    assert metadata["gravity"]["routes_sha256"] == hashlib.sha256(routes.read_bytes()).hexdigest()
    top = pd.read_csv(tmp_path / "top3.csv")
    assert top.iata.tolist() == ["KUF", "KZN", "UFA"]
    assert top.total_score.round(2).tolist() == [77.39, 73.78, 64.54]
    assert metadata["gravity"]["population_reconciliation"][0]["iata"] == "MRV"
    scissor = pd.read_csv(tmp_path / "scissor_hub_index.csv").set_index("iata")
    scissor_pairs = pd.read_csv(tmp_path / "scissor_pairs.csv")
    assert len(scissor) == 12 and len(scissor_pairs) == 12 * 11 * 10
    sums = scissor_pairs.groupby("hub_iata").contribution.sum()
    np.testing.assert_allclose(scissor.scissor_hub_index, sums.reindex(scissor.index))
    assert metadata["gravity"]["scissor"]["max_detour_pct"] == 15.0
