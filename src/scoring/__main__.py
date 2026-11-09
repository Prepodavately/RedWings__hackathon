"""python -m src.scoring --input cities.parquet --mode exploratory --output work/scoring"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from src.schemas.contracts import ScoringWeights
from src.scoring.city_scorer import DEFAULT_DATA_PATH, load_features, score_cities, weight_sensitivity


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
    args = parser.parse_args()
    try:
        values = json.loads(args.weights_json.read_text(encoding="utf-8")) if args.weights_json else {}
        weights = ScoringWeights(**values)
        result = score_cities(load_features(args.input), weights, mode=args.mode,
                              hypothesis=args.hypothesis, moscow_transfer_weight=args.moscow_transfer_weight)
        sensitivity = weight_sensitivity(result, n_samples=args.samples,
                                         relative_change=args.relative_change, seed=args.seed)
    except (ValueError, TypeError, FileNotFoundError) as exc:
        parser.error(str(exc))
    args.output.mkdir(parents=True, exist_ok=True)
    for name, table in (("ranked_cities", result.table), ("top3", result.top3),
                        ("data_audit", result.audit), ("weight_sensitivity", sensitivity)):
        table.to_csv(args.output / f"{name}.csv", index=False, encoding="utf-8-sig")
    metadata = {
        "requested_mode": args.mode, "mode": result.mode, "hypothesis": result.hypothesis,
        "distance_scoring": {"input": "dist_to_mow_km", "optimal_km": 1150.0,
                             "formula": "max(35, 100 - 65 * abs(d - 1150) / 1200)"},
        "input_file": args.input.name,
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_weights": asdict(weights), "effective_weights": result.weights,
        "normalization_bounds": result.normalization_bounds,
        "sensitivity": {"samples": args.samples, "seed": args.seed,
                        "relative_change": args.relative_change, "scope": "weights_only"},
        "limitations": result.limitations,
        "cutoff_tie": bool(result.table["cutoff_tie"].any()),
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
