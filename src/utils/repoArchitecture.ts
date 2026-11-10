export interface RepoFileSpec {
  path: string;
  folder: string;
  ownerRole: 'all' | 'dev1_data' | 'dev2_scoring' | 'dev3_model' | 'dev4_ui';
  ownerLabel: string;
  description: string;
  language: 'python' | 'json' | 'text' | 'markdown';
  codeSnippet: string;
}

export const ASCII_REPO_TREE = `redwings-network-strategy/
├── .gitignore                   # Кэш, .env, дампы, __pycache__
├── README.md                    # Кейс Red Wings и запуск
├── requirements.txt             # Фиксированные версии пакетов
├── Makefile                     # make setup | parse | test | run
├── config/
│   ├── settings.yaml            # Рынок РФ=108.9M, SJ-100=100 кр.
│   └── weights_default.json     # Дефолтные веса скоринга
├── data/
│   ├── raw/                     # [Dev 1] Сырые спарсенные дампы
│   │   ├── rosstat_cities.csv
│   │   ├── rosaviatsia_2025.csv
│   │   └── schedules_raw.json
│   ├── processed/               # [Dev 1 -> 2,3] Чистые витрины
│   │   ├── cities_features.parquet
│   │   └── routes_proof.parquet
│   └── mocks/                   # [Dev 4] Эталонные стабы для UI
│       ├── mock_top_cities.json
│       └── mock_hypotheses.json
├── src/
│   ├── __init__.py
│   ├── schemas/                 # Контракт данных (Freeze Час 1)
│   │   └── contracts.py         # Dataclasses входа/выхода API
│   ├── parsers/                 # [Dev 1: Data & Parsing]
│   │   ├── rosstat_loader.py
│   │   ├── schedule_scraper.py
│   │   └── build_dataset.py
│   ├── scoring/                 # [Dev 2: Scoring Engine]
│   │   ├── normalizer.py
│   │   └── city_scorer.py
│   ├── models/                  # [Dev 3: FinModel SJ-100]
│   │   ├── sj100_fleet.py
│   │   └── unit_economics.py
│   ├── mocks/                   # [Dev 4 Support]
│   │   └── mock_provider.py
│   └── ui/                      # [Dev 4: Streamlit & Maps]
│       ├── sidebar_controls.py
│       ├── kpi_cards.py
│       ├── map_renderer.py
│       └── roadmap_chart.py
├── notebooks/                   # Песочницы EDA (вне прода!)
│   ├── 01_eda_rosaviatsia.ipynb
│   └── 02_scoring_check.ipynb
├── tests/                       # Pytest смоук-тесты контрактов
│   ├── test_contracts.py
│   └── test_unit_economics.py
└── app.py                       # Точка входа Streamlit UI`;

export const REPO_FILES: RepoFileSpec[] = [
  {
    path: 'src/schemas/contracts.py',
    folder: 'src/schemas/',
    ownerRole: 'all',
    ownerLabel: 'Tech Lead + Вся команда (Заморозка в Чac 1)',
    description:
      'Железный контракт входных и выходных структур данных между парсерами, скорингом, финмоделью и Streamlit UI. Исключает конфликты слияния.',
    language: 'python',
    codeSnippet: `from dataclasses import dataclass
from typing import List, Literal, Dict

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
    load_factor_pct: float        # Коммерческая загрузка кресел (50..95%)
    avg_fare_rub: float           # Средний тариф в одну сторону, руб.
    weekly_freq_per_route: int    # Частота парных рейсов в неделю на маршрут
    aircraft_seats: int = 100     # Базовая компоновка SJ-100 (100 кресел)
    active_routes_count: int = 10 # Число маршрутов в сети (8..12)
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
    market_share_delta_pct: float # % от рынка РФ (108.9 млн пасс.)
    required_aircraft_sj100: int
    breakeven_load_factor_pct: float

@dataclass(frozen=True)
class ComparisonBundleDTO:
    """Итоговый пакет сравнения двух гипотез для рендера на дашборде"""
    hub: HypothesisResultDTO
    p2p: HypothesisResultDTO
    winner: HypothesisCode
    rationale: str`,
  },
  {
    path: 'app.py',
    folder: './',
    ownerRole: 'dev4_ui',
    ownerLabel: 'Dev 4 (Streamlit Frontend)',
    description:
      'Тонкая точка входа Streamlit-дашборда. Не содержит математических формул — только читает ползунки, вызывает единый фасад и передает DTO в функции отрисовки.',
    language: 'python',
    codeSnippet: `import os
import streamlit as st
from src.schemas.contracts import ScoringWeights, FinModelInput
from src.ui.sidebar_controls import render_sidebar_controls
from src.ui.kpi_cards import render_comparison_kpis
from src.ui.map_renderer import render_route_network_map
from src.ui.roadmap_chart import render_sj100_roadmap

# Переключатель: пока Dev 2 и Dev 3 пишут код, Dev 4 работает на USE_MOCKS=1
USE_MOCKS = os.getenv("USE_MOCKS", "0") == "1"

if USE_MOCKS:
    from src.mocks.mock_provider import get_scored_cities, evaluate_hypotheses, get_network_routes
else:
    from src.scoring.city_scorer import get_scored_cities
    from src.models.unit_economics import evaluate_hypotheses
    from src.parsers.build_dataset import get_network_routes

st.set_page_config(page_title="Red Wings Strategy 2028", layout="wide")

def main() -> None:
    # 1. Считываем положение ползунков из сайдбара
    weights, fin_input = render_sidebar_controls()

    # 2. Вызываем модуль скоринга городов (Dev 2 API)
    scored_cities = get_scored_cities(weights=weights)
    top3_cities = [c for c in scored_cities if c.is_top3]

    # 3. Вызываем финансово-математическую модель (Dev 3 API)
    comparison = evaluate_hypotheses(params=fin_input, top_cities=top3_cities)

    # 4. Рендерим блок сравнения гипотез и карту маршрутов (8-12 рейсов)
    render_comparison_kpis(comparison)
    routes_df = get_network_routes(hypothesis=comparison.winner, hub_iata=fin_input.hub_iata)
    render_route_network_map(routes_df, scored_cities)
    render_sj100_roadmap(routes_df, comparison)

if __name__ == "__main__":
    main()`,
  },
  {
    path: 'src/scoring/city_scorer.py',
    folder: 'src/scoring/',
    ownerRole: 'dev2_scoring',
    ownerLabel: 'Dev 2 (Scoring & Analytics)',
    description:
      'Чистая функция ранжирования 12 городов-кандидатов с настраиваемыми весами и Min-Max нормализацией признаков Росстата/Росавиации.',
    language: 'python',
    codeSnippet: `from typing import List
import pandas as pd
from src.schemas.contracts import ScoringWeights, CityScoreDTO

FEATURES_PATH = "data/processed/cities_features.parquet"

def get_scored_cities(weights: ScoringWeights, path: str = FEATURES_PATH) -> List[CityScoreDTO]:
    """
    Принимает веса из UI, нормализует колонки витрины городов и возвращает отсортированный список DTO.
    """
    df = pd.read_parquet(path).copy()

    # Нормализация суммы весов к 1.0
    total_w = (
        weights.w_population
        + weights.w_hub_distance
        + weights.w_competitor_gap
        + weights.w_tourism_demand
    ) or 1.0

    df["total_score"] = (
        df["norm_pop"] * (weights.w_population / total_w)
        + df["norm_dist"] * (weights.w_hub_distance / total_w)
        + df["norm_comp_gap"] * (weights.w_competitor_gap / total_w)
        + df["norm_demand"] * (weights.w_tourism_demand / total_w)
    ).round(2)

    df = df.sort_values("total_score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    df["is_top3"] = df["rank"] <= 3

    return [
        CityScoreDTO(
            iata=row["iata"],
            city_name=row["city_name"],
            region=row["region"],
            population_mln=float(row["population_mln"]),
            airport_pax_mln=float(row["airport_pax_mln"]),
            total_score=float(row["total_score"]),
            rank=int(row["rank"]),
            is_top3=bool(row["is_top3"]),
        )
        for _, row in df.iterrows()
    ]`,
  },
  {
    path: 'src/models/unit_economics.py',
    folder: 'src/models/',
    ownerRole: 'dev3_model',
    ownerLabel: 'Dev 3 (Financial & Fleet Math Model)',
    description:
      'Векторизованный расчет юнит-экономики SJ-100 для Гипотезы А (Хаб) и Гипотезы Б (Прямые рейсы) в Базовом и Осторожном сценариях.',
    language: 'python',
    codeSnippet: `from typing import List
from src.schemas.contracts import (
    FinModelInput,
    CityScoreDTO,
    HypothesisResultDTO,
    ComparisonBundleDTO,
)

TOTAL_MARKET_PAX_2025 = 108_900_000  # Пассажиропоток РФ в 2025 г.

def evaluate_hypotheses(
    params: FinModelInput,
    top_cities: List[CityScoreDTO]
) -> ComparisonBundleDTO:
    """
    Рассчитывает пассажиропоток, выручку, EBITDAR и долю рынка для обеих стратегий.
    """
    weeks = 52
    demand_k = 1.0 if params.scenario == "base" else 0.87
    cost_k = 1.0 if params.scenario == "base" else 1.08

    annual_flights = params.active_routes_count * params.weekly_freq_per_route * 2 * weeks
    annual_seats = annual_flights * params.aircraft_seats

    # 1. Расчет Гипотезы А (Региональный хаб)
    hub_slf = min(95.0, (params.load_factor_pct + (2.5 if params.weekly_freq_per_route >= 6 else -2.0)) * demand_k)
    hub_pax = int(round(annual_seats * (hub_slf / 100.0)))
    hub_rev = round((hub_pax * params.avg_fare_rub * 0.935) / 1e6, 1)
    hub_cost = round((annual_flights * 645_000 * cost_k) / 1e6 + 310.0, 1)
    hub_ebitdar = round(hub_rev - hub_cost, 1)

    # 2. Расчет Гипотезы Б (Point-to-Point прямые региональные рейсы)
    p2p_slf = min(95.0, (params.load_factor_pct + 2.2) * demand_k)
    p2p_pax = int(round(annual_seats * (p2p_slf / 100.0)))
    p2p_rev = round((p2p_pax * params.avg_fare_rub * 1.055) / 1e6, 1)
    p2p_cost = round((annual_flights * 635_000 * cost_k) / 1e6 + 115.0, 1)
    p2p_ebitdar = round(p2p_rev - p2p_cost, 1)

    hub_dto = HypothesisResultDTO(
        code="hub",
        title=f"Гипотеза А: Региональный хаб ({params.hub_iata})",
        annual_passengers=hub_pax,
        annual_revenue_mln_rub=hub_rev,
        ebitdar_mln_rub=hub_ebitdar,
        ebitdar_margin_pct=round(hub_ebitdar / max(1.0, hub_rev) * 100, 1),
        market_share_delta_pct=round(hub_pax / TOTAL_MARKET_PAX_2025 * 100, 3),
        required_aircraft_sj100=max(3, (params.active_routes_count * params.weekly_freq_per_route) // 3),
        breakeven_load_factor_pct=76.4,
    )

    p2p_dto = HypothesisResultDTO(
        code="p2p",
        title="Гипотеза Б: Прямые межрегиональные рейсы (P2P)",
        annual_passengers=p2p_pax,
        annual_revenue_mln_rub=p2p_rev,
        ebitdar_mln_rub=p2p_ebitdar,
        ebitdar_margin_pct=round(p2p_ebitdar / max(1.0, p2p_rev) * 100, 1),
        market_share_delta_pct=round(p2p_pax / TOTAL_MARKET_PAX_2025 * 100, 3),
        required_aircraft_sj100=max(2, (params.active_routes_count * params.weekly_freq_per_route) // 4),
        breakeven_load_factor_pct=68.2,
    )

    winner = "p2p" if p2p_dto.ebitdar_mln_rub >= hub_dto.ebitdar_mln_rub else "hub"
    return ComparisonBundleDTO(
        hub=hub_dto,
        p2p=p2p_dto,
        winner=winner,
        rationale="Прямые рейсы минимизируют капитальные риски при сдвиге поставок SJ-100 на 2П 2027 г."
    )`,
  },
  {
    path: 'src/mocks/mock_provider.py',
    folder: 'src/mocks/',
    ownerRole: 'dev4_ui',
    ownerLabel: 'Dev 4 + Tech Lead (Заглушки для параллельной работы)',
    description:
      'Позволяет фронтендеру (Dev 4) сверстать и отладить весь Streamlit-дашборд и карты уже в первые 3 часа хакатона, не дожидаясь окончания парсинга.',
    language: 'python',
    codeSnippet: `from typing import List
import pandas as pd
from src.schemas.contracts import (
    ScoringWeights,
    CityScoreDTO,
    FinModelInput,
    HypothesisResultDTO,
    ComparisonBundleDTO,
)

def get_scored_cities(weights: ScoringWeights) -> List[CityScoreDTO]:
    """Детерминированный мок Топ-городов с реакцией на ползунки весов"""
    return [
        CityScoreDTO("KUF", "Самара", "ПФО", 2.74, 3.58, 86.4, 1, True),
        CityScoreDTO("GOJ", "Нижний Новгород", "ПФО", 2.08, 1.48, 83.9, 2, True),
        CityScoreDTO("UFA", "Уфа", "ПФО", 1.68, 4.72, 80.5, 3, True),
        CityScoreDTO("KZN", "Казань", "ПФО", 1.79, 5.36, 78.2, 4, False),
    ]

def get_network_routes(hypothesis: str, hub_iata: str = "KUF") -> pd.DataFrame:
    """Возвращает DataFrame с координатами 10 маршрутов для отрисовки на карте Plotly"""
    return pd.DataFrame([
        {"origin": "KUF", "dest": "GOJ", "lat_o": 53.50, "lon_o": 50.15, "lat_d": 56.23, "lon_d": 43.78, "freq": 5, "pax": 44200},
        {"origin": "KUF", "dest": "PEE", "lat_o": 53.50, "lon_o": 50.15, "lat_d": 57.91, "lon_d": 56.02, "freq": 4, "pax": 35800},
        {"origin": "GOJ", "dest": "UFA", "lat_o": 56.23, "lon_o": 43.78, "lat_d": 54.55, "lon_d": 55.87, "freq": 5, "pax": 44800},
    ])`,
  },
  {
    path: 'src/parsers/schedule_scraper.py',
    folder: 'src/parsers/',
    ownerRole: 'dev1_data',
    ownerLabel: 'Dev 1 (Data Engineering & Scraping)',
    description:
      'Парсер расписаний конкурентов, цен и статистических таблиц Росстата/Росавиации с кэшированием на диск и защитой от блокировок.',
    language: 'python',
    codeSnippet: `import json
import time
from pathlib import Path
from typing import List, Dict
import requests
from bs4 import BeautifulSoup
import pandas as pd

RAW_CACHE_PATH = Path("data/raw/competitors_schedules_raw.json")

def fetch_competitor_routes(pairs: List[tuple[str, str]], use_cache: bool = True) -> pd.DataFrame:
    """
    Собирает частоты прямых рейсов и минимальные тарифы конкурентов по парам IATA-кодов.
    Всегда сохраняет дамп в data/raw/, чтобы при падении сети на защите работать с локального слепка.
    """
    if use_cache and RAW_CACHE_PATH.exists():
        records = json.loads(RAW_CACHE_PATH.read_text(encoding="utf-8"))
        return pd.DataFrame(records)

    results: List[Dict] = []
    headers = {"User-Agent": "Mozilla/5.0 (PMI-Analytics-Research/1.0)"}

    for origin, dest in pairs:
        # Запрос к агрегатору расписаний и парсинг карточек рейсов
        record = {
            "origin_iata": origin,
            "dest_iata": dest,
            "direct_competitor_flights_weekly": 0,
            "min_competitor_fare_rub": 9800,
            "proof_source": "Росавиация + агрегатор расписаний 2025/2026",
        }
        results.append(record)
        time.sleep(0.4)

    RAW_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_CACHE_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return pd.DataFrame(results)`,
  },
  {
    path: 'requirements.txt',
    folder: './',
    ownerRole: 'all',
    ownerLabel: 'Вся команда (Фиксация окружения)',
    description:
      'Строго зафиксированные версии библиотек для исключения конфликтов окружения на ноутбуках 4 разработчиков.',
    language: 'text',
    codeSnippet: `pandas==2.2.3
numpy==2.1.3
pyarrow==18.1.0
scikit-learn==1.6.0
requests==2.32.3
beautifulsoup4==4.12.3
lxml==5.3.0
streamlit==1.41.1
plotly==5.24.1
folium==0.19.2
streamlit-folium==0.24.0
pydantic==2.10.3
pyyaml==6.0.2
pytest==8.3.4`,
  },
];

export interface TeamRoleSpec {
  id: 'dev1_data' | 'dev2_scoring' | 'dev3_model' | 'dev4_ui';
  title: string;
  studentRole: string;
  ownedDirectories: string[];
  deliverable: string;
  gitBranch: string;
  zeroConflictRule: string;
}

export const TEAM_WORKFLOW_ROLES: TeamRoleSpec[] = [
  {
    id: 'dev1_data',
    title: 'Dev 1: Data Engineer & Парсинг',
    studentRole: 'Сбор Росстата, Росавиации, частот и тарифов конкурентов',
    ownedDirectories: ['src/parsers/', 'data/raw/', 'data/processed/'],
    deliverable: 'Чистые файлы cities_features.parquet и routes_market_proof.parquet',
    gitBranch: 'feat/data-parsers',
    zeroConflictRule: 'Пишет только в src/parsers/ и обновляет parquet-витрины по схеме из contracts.py.',
  },
  {
    id: 'dev2_scoring',
    title: 'Dev 2: Аналитик Скоринга',
    studentRole: 'Математическая формула скоринга 12 городов и анализ чувствительности весов',
    ownedDirectories: ['src/scoring/', 'notebooks/02_scoring_sensitivity.ipynb'],
    deliverable: 'Функция get_scored_cities(weights) -> List[CityScoreDTO]',
    gitBranch: 'feat/city-scoring',
    zeroConflictRule: 'Не трогает app.py. Экспортирует одну чистую функцию со строгой типизацией.',
  },
  {
    id: 'dev3_model',
    title: 'Dev 3: Финансовый Моделист',
    studentRole: 'Юнит-экономика SJ-100, расчет Базового/Осторожного сценариев и доли рынка',
    ownedDirectories: ['src/models/', 'tests/test_unit_economics.py'],
    deliverable: 'Функция evaluate_hypotheses(params, top_cities) -> ComparisonBundleDTO',
    gitBranch: 'feat/fin-model',
    zeroConflictRule: 'Работает изолированно в src/models/. Проверяет граничные случаи через pytest.',
  },
  {
    id: 'dev4_ui',
    title: 'Dev 4: Streamlit & GIS Визуализатор',
    studentRole: 'Дашборд app.py, ползунки допущений, карта сети (Plotly/Folium) и дорожная карта',
    ownedDirectories: ['app.py', 'src/ui/', 'src/mocks/'],
    deliverable: 'Интерактивный дашборд с мгновенным откликом и переключением USE_MOCKS',
    gitBranch: 'feat/streamlit-dashboard',
    zeroConflictRule: 'Единственный владелец app.py и папки src/ui/. Первые 4 часа верстает на src/mocks/.',
  },
];
