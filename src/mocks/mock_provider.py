"""
Провайдер тестовых данных (моков) для параллельной верстки дашборда.
ВЛАДЕЛЕЦ ФАЙЛА: Dev 4 + Tech Lead
"""

from typing import List
import pandas as pd
from src.schemas.contracts import (
    ScoringWeights,
    CityScoreDTO,
    FinModelInput,
    HypothesisResultDTO,
    ComparisonBundleDTO,
)


def get_scored_cities(weights: ScoringWeights) -> List[CityScoreDTO]:
    """Возвращает тестовый список городов Топ-3 для верстки UI"""
    return [
        CityScoreDTO("KUF", "Самара", "ПФО", 2.74, 3.58, 89.26, 1, True),
        CityScoreDTO("GOJ", "Нижний Новгород", "ПФО", 2.08, 1.48, 73.91, 2, True),
        CityScoreDTO("SVX", "Екатеринбург", "УФО", 2.24, 7.95, 71.40, 3, True),
    ]


def evaluate_hypotheses(
    params: FinModelInput, top_cities: List[CityScoreDTO]
) -> ComparisonBundleDTO:
    """Возвращает тестовый расчет двух гипотез для верстки KPI-карточек"""
    hub = HypothesisResultDTO("hub", "Гипотеза А: Хаб", 443040, 3818.9, 154.9, 4.1, 0.407, 15, 81.4)
    p2p = HypothesisResultDTO("p2p", "Гипотеза Б: Прямые рейсы", 449280, 4471.6, 1054.6, 23.6, 0.413, 13, 63.5)
    return ComparisonBundleDTO(hub=hub, p2p=p2p, winner="p2p", rationale="Мок-обоснование для верстки.")


def get_network_routes(hypothesis: str, hub_iata: str = "KUF") -> pd.DataFrame:
    """Возвращает тестовый DataFrame маршрутов для карты Plotly/Folium"""
    return pd.DataFrame([
        {"origin": "KUF", "dest": "GOJ", "freq": 5, "pax": 44200},
        {"origin": "KUF", "dest": "PEE", "freq": 4, "pax": 35800},
    ])
