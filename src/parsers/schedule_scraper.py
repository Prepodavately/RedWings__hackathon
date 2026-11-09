"""
Конкуренты: прямые рейсы и тарифы на парах городов.
ВЛАДЕЛЕЦ ФАЙЛА: Dev 1 (Data & Parsing)

Источник — data/raw/schedules_raw.json: список записей, по одной на перевозчика
на паре А→Б за неделю. Поля записи:
  origin_iata, dest_iata, carrier, weekly_flights (int), own_operator (bool — рейсы
  самой Red Wings), week, source (URL страницы расписания), note, min_fare_rub (int или null).

Автоматического парсинга здесь нет: прежний парсер возвращал нули и захардкоженный
источник, поэтому удалён. Пары без записей считаются «не измерено».
"""

from typing import List, Tuple

import pandas as pd

from src.parsers.rosstat_loader import RAW_DIR

SCHEDULES_FILE = RAW_DIR / "schedules_raw.json"
REQUIRED_KEYS = {
    "origin_iata", "dest_iata", "carrier", "weekly_flights", "own_operator",
    "week", "source", "note", "min_fare_rub",
}


def load_schedules() -> pd.DataFrame:
    """Читает schedules_raw.json и проверяет структуру записей."""
    import json

    records = json.loads(SCHEDULES_FILE.read_text(encoding="utf-8"))
    if not records:
        raise ValueError(f"{SCHEDULES_FILE.name} пуст: нет данных о рейсах конкурентов")
    bad = [r for r in records if not REQUIRED_KEYS <= set(r)]
    if bad:
        raise ValueError(f"В {SCHEDULES_FILE.name} у записей нет полей: {sorted(REQUIRED_KEYS)}")
    df = pd.DataFrame(records)
    df["origin_iata"] = df["origin_iata"].astype(str)
    df["dest_iata"] = df["dest_iata"].astype(str)
    df["weekly_flights"] = df["weekly_flights"].astype(int)
    df["own_operator"] = df["own_operator"].astype(bool)
    df["min_fare_rub"] = pd.to_numeric(df["min_fare_rub"], errors="coerce")
    return df


def fetch_competitor_routes(
    pairs: List[Tuple[str, str]], use_cache: bool = True
) -> pd.DataFrame:
    """
    Возвращает записи из schedules_raw.json для заданных пар (origin, dest).
    use_cache сохранён для совместимости с сигнатурой из main: данные всегда читаются из кэша.
    """
    df = load_schedules()
    wanted = set(pairs)
    mask = [(o, d) in wanted for o, d in zip(df["origin_iata"], df["dest_iata"])]
    return df[mask].reset_index(drop=True)
