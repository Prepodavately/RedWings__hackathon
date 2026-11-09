"""
Загрузчик данных Росстата (население агломераций) и Росавиации (пассажиропоток).
ВЛАДЕЛЕЦ ФАЙЛА: Dev 1 (Data & Parsing)
"""

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

ROSSTAT_FILE = "rosstat_cities.csv"
ROSAVIATSIA_FILE = "rosaviatsia_2025.csv"


def load_rosstat_and_rosaviatsia(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """
    Объединяет таблицы городов (Росстат) и аэропортов (Росавиация) по IATA-коду.

    Возвращает DataFrame с городами-кандидатами. Колонки src_* фиксируют,
    из какого файла взята каждая группа данных (для proof_source).
    """
    cities = pd.read_csv(raw_dir / ROSSTAT_FILE, dtype={"iata": str})
    airports = pd.read_csv(raw_dir / ROSAVIATSIA_FILE, dtype={"iata": str})

    cities["src_population"] = f"data/raw/{ROSSTAT_FILE} (население города, колонка source)"
    airports["src_airport_pax"] = (
        f"data/raw/{ROSAVIATSIA_FILE} (Росавиация, пассажиропоток аэропорта 2025)"
    )

    merged = cities.merge(airports, on="iata", how="left", validate="one_to_one")

    missing = merged.loc[merged["airport_pax_2025_mln"].isna(), "iata"].tolist()
    if missing:
        raise ValueError(f"Нет данных Росавиации для аэропортов: {missing}")

    return merged.reset_index(drop=True)
