"""
Конкуренты: прямые рейсы и частоты на парах городов.
ВЛАДЕЛЕЦ ФАЙЛА: Dev 1 (Data & Parsing)

Источник — курируемый файл data/raw/competitor_schedules.csv. Каждая строка —
перевозчик на паре А→Б за неделю, с колонкой source (URL страницы расписания).
Автоматического парсинга здесь нет: прежний парсер возвращал нули и захардкоженный
источник, поэтому удалён. Пары без строк считаются «не измерено».
"""

from typing import List, Tuple

import pandas as pd

from src.parsers.rosstat_loader import RAW_DIR

COMPETITOR_FILE = RAW_DIR / "competitor_schedules.csv"
REQUIRED_COLUMNS = {"origin", "dest", "carrier", "weekly_flights", "own_operator", "week", "source", "note"}


def load_competitor_schedules() -> pd.DataFrame:
    """Читает курируемую таблицу рейсов конкурентов и проверяет колонки."""
    df = pd.read_csv(COMPETITOR_FILE, dtype={"origin": str, "dest": str})
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"В {COMPETITOR_FILE.name} нет колонок: {sorted(missing)}")
    if "min_fare_rub" not in df.columns:
        df["min_fare_rub"] = float("nan")
    df["weekly_flights"] = df["weekly_flights"].astype(int)
    df["own_operator"] = df["own_operator"].astype(bool)
    return df


def fetch_competitor_routes(pairs: List[Tuple[str, str]]) -> pd.DataFrame:
    """Возвращает строки курируемой таблицы для заданных пар (origin, dest)."""
    df = load_competitor_schedules()
    wanted = set(pairs)
    mask = [(o, d) in wanted for o, d in zip(df["origin"], df["dest"])]
    return df[mask].reset_index(drop=True)
