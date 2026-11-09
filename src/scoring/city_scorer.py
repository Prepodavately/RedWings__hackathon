"""
Ранжирование 10+ городов-кандидатов с весами и выбор Топ-3.
ВЛАДЕЛЕЦ ФАЙЛА: Dev 2 (Scoring Engine)
"""

from typing import List
from src.schemas.contracts import ScoringWeights, CityScoreDTO


def get_scored_cities(weights: ScoringWeights) -> List[CityScoreDTO]:
    """
    TODO (Dev 2): Вставьте формулу взвешенного скоринга сюда.
    На выход возвращает отсортированный список CityScoreDTO (где первые 3 имеют is_top3=True).
    """
    pass
