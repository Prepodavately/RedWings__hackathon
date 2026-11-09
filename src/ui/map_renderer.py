"""
Отрисовка интерактивной карты маршрутной сети (8-12 маршрутов) на базе Plotly / Folium.
ВЛАДЕЛЕЦ ФАЙЛА: Dev 4 (Streamlit UI)
"""

from typing import List
import pandas as pd
from src.schemas.contracts import CityScoreDTO


def render_route_network_map(
    routes_df: pd.DataFrame, scored_cities: List[CityScoreDTO]
) -> None:
    """
    TODO (Dev 4): Вставьте код отрисовки карты маршрутов сюда.
    """
    pass
