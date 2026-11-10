"""
Точка входа Streamlit-дашборда (Red Wings Network Strategy).
ВЛАДЕЛЕЦ ФАЙЛА: Dev 4 (Streamlit & GIS UI)
"""

import os
import streamlit as st

# Контракты данных
from src.schemas.contracts import ScoringWeights, FinModelInput

# UI-компоненты (Dev 4)
from src.ui.sidebar_controls import render_sidebar_controls
from src.ui.kpi_cards import render_comparison_kpis
from src.ui.map_renderer import render_route_network_map
from src.ui.roadmap_chart import render_sj100_roadmap

# Переключатель режима: USE_MOCKS=1 (работа на заглушках) / USE_MOCKS=0 (реальные модули Dev 1-3)
USE_MOCKS = os.getenv("USE_MOCKS", "1") == "1"

if USE_MOCKS:
    from src.mocks.mock_provider import (
        get_scored_cities,
        evaluate_hypotheses,
        get_network_routes,
    )
else:
    from src.scoring.city_scorer import get_scored_cities
    from src.models.unit_economics import evaluate_hypotheses
    from src.parsers.build_dataset import get_network_routes


def main() -> None:
    st.set_page_config(page_title="Red Wings Strategy 2028", layout="wide")
    # TODO (Dev 4): Вставьте вызов компонентов дашборда сюда
    pass


if __name__ == "__main__":
    main()
