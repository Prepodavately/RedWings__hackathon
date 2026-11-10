"""
Единый контракт входных и выходных данных между модулями.
ВЛАДЕЛЕЦ: Tech Lead + Вся команда (Замораживается в 1-й час хакатона!)
"""

from dataclasses import dataclass
from typing import Literal

ScenarioType = Literal["base", "conservative"]
HypothesisCode = Literal["hub", "p2p"]


@dataclass(frozen=True)
class ScoringWeights:
    """Входные веса для ранжирования городов-кандидатов (Dev 4 -> Dev 2)"""
    w_population: float = 0.30
    w_hub_distance: float = 0.20
    w_competitor_gap: float = 0.30
    w_tourism_demand: float = 0.20


@dataclass(frozen=True)
class CityScoreDTO:
    """Выходной контракт скоринга одного города (Dev 2 -> Dev 4)"""
    iata: str
    city_name: str
    region: str
    population_mln: float
    airport_pax_mln: float
    total_score: float
    rank: int
    is_top3: bool


@dataclass(frozen=True)
class FinModelInput:
    """Входные ползунки дашборда для расчета юнит-экономики (Dev 4 -> Dev 3)"""
    load_factor_pct: float = 84.0
    avg_fare_rub: float = 8400.0
    weekly_freq_per_route: int = 5
    aircraft_seats: int = 100
    active_routes_count: int = 10
    scenario: ScenarioType = "base"
    hub_iata: str = "KUF"


@dataclass(frozen=True)
class HypothesisResultDTO:
    """Выходной контракт расчета одной гипотезы (Dev 3 -> Dev 4)"""
    code: HypothesisCode
    title: str
    annual_passengers: int
    annual_revenue_mln_rub: float
    ebitdar_mln_rub: float
    ebitdar_margin_pct: float
    market_share_delta_pct: float
    required_aircraft_sj100: int
    breakeven_load_factor_pct: float


@dataclass(frozen=True)
class ComparisonBundleDTO:
    """Итоговый пакет сравнения двух гипотез для рендера на дашборде"""
    hub: HypothesisResultDTO
    p2p: HypothesisResultDTO
    winner: HypothesisCode
    rationale: str
