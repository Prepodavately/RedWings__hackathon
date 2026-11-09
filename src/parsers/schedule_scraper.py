"""
Парсер расписаний рейсов и тарифов конкурентов (BeautifulSoup / Requests).
ВЛАДЕЛЕЦ ФАЙЛА: Dev 1 (Data & Parsing)
"""

from typing import List, Tuple
import pandas as pd


def fetch_competitor_routes(
    pairs: List[Tuple[str, str]], use_cache: bool = True
) -> pd.DataFrame:
    """
    TODO (Dev 1): Вставьте код парсинга частот и цен конкурентов сюда.
    Результат кэшируйте в data/raw/schedules_raw.json.
    """
    pass
