"""
Единый контракт входных и выходных данных между модулями.
ВЛАДЕЛЕЦ: Tech Lead + Вся команда (Замораживается в 1-й час хакатона!)
"""

from dataclasses import dataclass
from typing import Literal, Tuple

ScenarioType = Literal["base", "conservative"]
HypothesisCode = Literal["hub", "p2p"]
AircraftModelId = Literal["sj100_basic", "sj100_lr", "tu214", "mc21_310", "crj200"]
RouteRwStatus = Literal["existing_core", "existing_thin", "new_blue_ocean", "new_head_to_head"]
MapLensMode = Literal["routes_gap", "aircraft_range", "gravity_lens"]


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


@dataclass(frozen=True)
class AircraftSpecDTO:
    """Характеристики типа ВС для фильтра дальности и CASK (Dev 3/Dev 4)"""
    id: AircraftModelId
    name: str
    seats: int
    min_km: int
    opt_low_km: int
    opt_high_km: int
    max_km: int
    cask_multiplier: float       # относительно SJ-100 Basic = 1.00
    short_haul_penalty: float    # штраф к расходам при distance_km < min_km


@dataclass(frozen=True)
class GravityFieldGridDTO:
    """Сплошное 2D-поле «Линзы гравитации» (Dev 2 -> Dev 4)"""
    lons: Tuple[float, ...]                 # длина W (160)
    lats: Tuple[float, ...]                 # длина H (110)
    z_values: Tuple[Tuple[float, ...], ...] # матрица H x W, нормирована в [-100.0, +100.0]
    barycenter_lat: float
    barycenter_lon: float
    mode: Literal["potential", "anomaly"]


@dataclass(frozen=True)
class CityGraphNodeDTO:
    """Граф-метрики одного города (Dev 2 -> Dev 4)"""
    iata: str
    city_name: str
    weighted_degree_centrality: float       # C_D^w в [0.0, 1.0]
    city_weighted_time_h: float             # средневзвешенное время пути из города i (ч)
    city_multimodal_index: float            # мультимодальный индекс доступности MAI_i


@dataclass(frozen=True)
class NetworkGraphMetricsDTO:
    """Интегральные граф-метрики сети (Dev 2 -> Dev 4)"""
    mode: Literal["baseline_rw", "proposed_network"]
    weighted_travel_time_h: float           # средневзвешенное время по сети T_w (ч)
    tarkhov_connectivity_idx: float         # интегральный индекс связности по Тархову
    multimodal_access_idx: float            # средний мультимодальный индекс сети MAI
    active_routes_count: int                # число активных рёбер e
    avg_degree_centrality: float            # средняя взвешенная центральность


@dataclass(frozen=True)
class FleetGapSummaryDTO:
    """Сводка «флот × рынок» по одному типу ВС (Dev 3 -> Dev 4)"""
    aircraft_id: AircraftModelId
    total_market_pairs: int                 # всего пар O-D (66)
    feasible_for_aircraft_count: int        # сколько пар из 66 в пределах max_km
    optimal_range_count: int                # сколько пар в [opt_low_km, opt_high_km]
    existing_rw_count: int                  # сколько пар уже летает Red Wings (8)
    existing_rw_fit_count: int              # сколько из существующих 8 подходят этому ВС
    proposed_new_count: int                 # сколько НОВЫХ маршрутов предлагаем открыть
    proposed_blue_ocean_count: int          # из них — абсолютных белых пятен (0 конкурентов)
    proposed_annual_pax: int
    proposed_ebitdar_mln_rub: float
    required_aircraft_count: int
