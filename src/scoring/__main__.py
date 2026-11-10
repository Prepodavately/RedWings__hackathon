"""python -m src.scoring --input cities.parquet --mode exploratory --output work/scoring"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from src.schemas.contracts import ScoringWeights
from src.scoring.city_scorer import (
    AIRPORT_ACCESS_HOURS, DEFAULT_DATA_PATH, calculate_effective_population,
    calculate_gravity_matrix, calculate_scissor_hub_index, load_features, score_cities, weight_sensitivity,
)


def _gravity_tables(cities: pd.DataFrame, routes: pd.DataFrame | None,
                    lam: float, gamma: float, *, with_scissor: bool = False,
                    max_detour_pct: float = 15.0) -> tuple[dict[str, pd.DataFrame], dict]:
    """Подготовить проверяемые слагаемые модели до записи каких-либо файлов."""
    cities = cities.copy(deep=True)
    population = calculate_effective_population(cities, lam)
    cities["effective_population_mln"] = population
    details = pd.DataFrame(population.attrs["catchment_details"], columns=[
        "iata", "satellite", "satellite_population", "access_time_h", "time_source",
        "within_two_hours", "decay_weight", "effective_contribution_mln",
    ])
    member_sum = details.groupby("iata")["satellite_population"].sum()
    cities["population_from_members_mln"] = (
        cities["population_city_mln"].astype(float) + cities["iata"].map(member_sum).fillna(0) / 1e6
    )
    cities["population_members_gap_mln"] = cities["population_mln"] - cities["population_from_members_mln"]
    matrix = calculate_gravity_matrix(cities, routes, gamma)
    cities["purchasing_power_index"] = cities["iata"].map(matrix.attrs["purchasing_power_index"])
    cities["gravity_hub_potential"] = cities["iata"].map(matrix.sum(axis=1))
    potential = cities[["iata", "city_name", "effective_population_mln", "purchasing_power_index",
                        "gravity_hub_potential", "eligible", "rank", "total_score"]].copy()
    potential = potential.sort_values(["gravity_hub_potential", "iata"], ascending=[False, True])
    potential["gravity_rank_all"] = np.arange(1, len(potential) + 1)
    potential["gravity_rank_eligible"] = pd.Series(pd.NA, index=potential.index, dtype="Int64")
    potential.loc[potential["eligible"], "gravity_rank_eligible"] = np.arange(1, int(potential["eligible"].sum()) + 1)
    pairs = pd.DataFrame({
        "origin_iata": np.repeat(matrix.index.to_numpy(), len(matrix)),
        "dest_iata": np.tile(matrix.columns.to_numpy(), len(matrix)),
        "gravity_index": matrix.to_numpy().ravel(),
        **{key: np.asarray(matrix.attrs[key]).ravel() for key in (
            "distance_km", "range_weight", "competitor_flights_weekly", "competition_observed",
        )},
    })
    pairs = pairs.loc[pairs["origin_iata"] != pairs["dest_iata"]].copy()
    if routes is not None and "proof_source" in routes:
        proof = routes[["origin_iata", "dest_iata", "proof_source"]].copy()
        for col in ("origin_iata", "dest_iata"):
            proof[col] = proof[col].str.strip().str.upper()
        proof = proof.loc[proof["origin_iata"].isin(matrix.index) & proof["dest_iata"].isin(matrix.columns)]
        pairs = pairs.merge(proof, on=["origin_iata", "dest_iata"], how="left", validate="one_to_one")
    pairs["frequency_status"] = np.where(pairs["competition_observed"], "provided_by_dev1", "assumed_zero_missing")
    large_attrs = {"distance_km", "range_weight", "competitor_flights_weekly", "competition_observed"}
    metadata = {key: value for key, value in matrix.attrs.items() if key not in large_attrs}
    metadata.update({
        "formula": "P_eff_i * P_eff_j * sqrt(q_i*q_j) * W(d) / (d**gamma * (1+F_ij))",
        "population_formula": "P_city + sum(P_sat * exp(-lam*t) for t <= 2h)",
        "catchment": {key: value for key, value in population.attrs.items() if key != "catchment_details"},
        "access_time_overrides_h": AIRPORT_ACCESS_HOURS,
        "range_values": [0, 1, 1, 0],
        "range_interpolation": "linear; zero outside [300, 3000] km; scenario, not aircraft certification",
        "population_reconciliation": cities.loc[cities["population_members_gap_mln"].abs() > 1e-6,
            ["iata", "population_mln", "population_from_members_mln", "population_members_gap_mln"]].to_dict("records"),
        "linear_score_population": "unchanged_population_mln",
    })
    tables = {"effective_population": cities, "catchment_details": details,
              "gravity_matrix": matrix.reset_index(), "gravity_pairs": pairs,
              "gravity_hub_potential": potential}
    if with_scissor:
        scissor = calculate_scissor_hub_index(cities, matrix, max_detour_pct=max_detour_pct)
        tables["scissor_hub_index"] = scissor[[
            "iata", "city_name", "scissor_rank", "scissor_hub_index", "eligible_directed_pairs",
            "eligible_undirected_pairs", "positive_gravity_directed_pairs", "valid_directed_pairs",
            "eligible", "exclusion_reason",
        ]]
        tables["scissor_pairs"] = pd.DataFrame(scissor.attrs["pair_details"])
        metadata["scissor"] = {key: value for key, value in scissor.attrs.items() if key != "pair_details"}
    return tables, metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Dev 2: скоринг 10+ городов с аудитом и чувствительностью")
    parser.add_argument("--input", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--output", type=Path, default=Path("work/scoring"))
    parser.add_argument("--mode", choices=["auto", "case", "exploratory"], default="auto")
    parser.add_argument("--hypothesis", choices=["hub", "p2p"], default="hub")
    parser.add_argument("--weights-json", type=Path, help="JSON с четырьмя полями ScoringWeights")
    parser.add_argument("--moscow-transfer-weight", type=float, default=0.20)
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--relative-change", type=float, default=0.20)
    parser.add_argument("--with-gravity", action="store_true", help="Экспорт изохроны и гравитационной модели")
    parser.add_argument("--routes", type=Path, help="routes_proof.parquet/CSV; без файла F=0 с пометкой допущения")
    parser.add_argument("--lam", type=float, default=0.45, help="Затухание по времени доезда, 1/час")
    parser.add_argument("--gamma", type=float, default=1.15, help="Степень затухания гравитации по расстоянию")
    parser.add_argument("--with-scissor", action="store_true", help="Индекс транзитного перекрёстка; требует --with-gravity")
    parser.add_argument("--max-detour-pct", type=float, default=15.0, help="Крюк строго менее этого процента; сценарное допущение")
    args = parser.parse_args()
    if args.routes is not None and not args.with_gravity:
        parser.error("--routes используется вместе с --with-gravity")
    if args.with_scissor and not args.with_gravity:
        parser.error("--with-scissor используется вместе с --with-gravity")
    try:
        values = json.loads(args.weights_json.read_text(encoding="utf-8")) if args.weights_json else {}
        weights = ScoringWeights(**values)
        features = load_features(args.input)
        input_snapshot = None if args.input.is_file() else features.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")
        input_hash = hashlib.sha256(args.input.read_bytes() if input_snapshot is None else input_snapshot).hexdigest()
        result = score_cities(features, weights, mode=args.mode,
                              hypothesis=args.hypothesis, moscow_transfer_weight=args.moscow_transfer_weight)
        sensitivity = weight_sensitivity(result, n_samples=args.samples,
                                         relative_change=args.relative_change, seed=args.seed)
        extra_tables, gravity_metadata = {}, None
        if args.with_gravity:
            routes = load_features(args.routes) if args.routes is not None else None
            extra_tables, gravity_metadata = _gravity_tables(
                result.table, routes, args.lam, args.gamma,
                with_scissor=args.with_scissor, max_detour_pct=args.max_detour_pct,
            )
            gravity_metadata["routes_file"] = args.routes.name if args.routes is not None else None
            gravity_metadata["routes_sha256"] = hashlib.sha256(args.routes.read_bytes()).hexdigest() if args.routes is not None else None
    except (ValueError, TypeError, FileNotFoundError) as exc:
        parser.error(str(exc))
    args.output.mkdir(parents=True, exist_ok=True)
    tables = {"ranked_cities": result.table, "top3": result.top3,
              "data_audit": result.audit, "weight_sensitivity": sensitivity, **extra_tables}
    for name, table in tables.items():
        table.to_csv(args.output / f"{name}.csv", index=False, encoding="utf-8-sig")
    if input_snapshot is not None:
        (args.output / "fallback_input.csv").write_bytes(input_snapshot)
    metadata = {
        "requested_mode": args.mode, "mode": result.mode, "hypothesis": result.hypothesis,
        "distance_scoring": {"input": "dist_to_mow_km", "optimal_km": 1150.0,
                             "formula": "round(max(35, 100 - 65 * abs(d - 1150) / 1200), 2)"},
        "input_file": args.input.name,
        "input_source": features.attrs.get("input_source", "file"),
        "input_sha256": input_hash,
        "input_hash_kind": "file_bytes" if input_snapshot is None else "fallback_input_csv_bytes",
        "input_snapshot": None if input_snapshot is None else "fallback_input.csv",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_weights": asdict(weights), "effective_weights": result.weights,
        "normalization_bounds": result.normalization_bounds,
        "sensitivity": {"samples": args.samples, "seed": args.seed,
                        "relative_change": args.relative_change, "scope": "weights_only"},
        "limitations": result.limitations,
        "cutoff_tie": bool(result.table["cutoff_tie"].any()),
        "gravity": gravity_metadata,
    }
    (args.output / "run_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Режим: {result.mode}; гипотеза: {result.hypothesis}")
    print(result.top3[["rank", "iata", "city_name", "total_score", "result_status"]].to_string(index=False))
    for limitation in result.limitations:
        print(f"- {limitation}")
    print(f"Файлы: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
