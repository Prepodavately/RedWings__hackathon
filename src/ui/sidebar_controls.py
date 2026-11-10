"""
Боковая панель управления ползунками допущений и весами скоринга.
ВЛАДЕЛЕЦ ФАЙЛА: Dev 4 (Streamlit UI)
"""

from typing import Tuple
from src.schemas.contracts import ScoringWeights, FinModelInput


def render_sidebar_controls() -> Tuple[ScoringWeights, FinModelInput]:
    """
    TODO (Dev 4): Вставьте st.sidebar.slider(...) для весов скоринга и параметров финмодели сюда.
    """
    return ScoringWeights(), FinModelInput()
