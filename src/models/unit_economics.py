"""
Калькулятор юнит-экономики для двух бизнес-гипотез:
Гипотеза А (Новый региональный хаб) vs Гипотеза Б (Прямые рейсы P2P).
ВЛАДЕЛЕЦ ФАЙЛА: Dev 3 (FinModel)
"""

from typing import List
from src.schemas.contracts import FinModelInput, CityScoreDTO, ComparisonBundleDTO


def evaluate_hypotheses(
    params: FinModelInput, top_cities: List[CityScoreDTO]
) -> ComparisonBundleDTO:
    """
    TODO (Dev 3): Вставьте финансово-математическую модель расчета пассажиропотока,
    выручки, EBITDAR и прироста доли рынка РФ (от 108.9 млн пасс.) сюда.
    """
    pass
