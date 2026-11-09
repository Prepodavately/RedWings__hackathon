"""
Смоук-тесты соблюдения контрактов данных между модулями.
ВЛАДЕЛЕЦ ФАЙЛА: Tech Lead / Вся команда
"""

from src.schemas.contracts import ScoringWeights, FinModelInput
from src.mocks.mock_provider import get_scored_cities, evaluate_hypotheses


def test_contracts_smoke() -> None:
    weights = ScoringWeights()
    cities = get_scored_cities(weights)
    assert len(cities) >= 3
    assert sum(1 for c in cities if c.is_top3) == 3

    fin_in = FinModelInput()
    bundle = evaluate_hypotheses(fin_in, cities)
    assert bundle.winner in ("hub", "p2p")
