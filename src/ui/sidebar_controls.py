"""Dev 4: controls using the shared dataclass contracts."""
from dataclasses import asdict
from typing import Tuple
import streamlit as st
from src.schemas.contracts import ScoringWeights, FinModelInput

WEIGHT_LABELS = {
    'w_population': 'Население',
    'w_hub_distance': 'Удалённость от действующих хабов',
    'w_competitor_gap': 'Свобода от конкуренции',
    'w_tourism_demand': 'Туристический спрос',
}


def reset_controls():
    for key in list(st.session_state):
        if key.startswith('rw_'):
            del st.session_state[key]


def render_sidebar_controls() -> Tuple[ScoringWeights, FinModelInput]:
    defaults = FinModelInput()
    with st.sidebar:
        st.markdown('### Условия сравнения')
        st.button('Вернуть исходные настройки', on_click=reset_controls)
        scenario = st.radio('Сценарий', ['base', 'conservative'],
                            format_func=lambda x: {'base': 'Базовый', 'conservative': 'Осторожный'}[x], key='rw_scenario')
        load = st.slider('Загрузка кресел, %', 65.0, 95.0, defaults.load_factor_pct, 1.0, key='rw_load')
        fare = st.slider('Средний тариф, ₽', 5500.0, 13500.0, defaults.avg_fare_rub, 100.0, key='rw_fare')
        frequency = st.slider('Частота на маршрут за неделю', 2, 10, defaults.weekly_freq_per_route, key='rw_frequency',
                              help='По ТЗ: парные оборотные рейсы в неделю на маршрут.')
        hub = defaults.hub_iata
        with st.expander('Флот и размер сети'):
            seats = st.number_input('Кресел в самолёте', 93, 103, defaults.aircraft_seats, key='rw_seats')
            routes = defaults.active_routes_count
        st.divider()
        with st.expander('Веса скоринга городов', expanded=True):
            raw = {key: st.slider(label, 0, 100, round(asdict(ScoringWeights())[key]*100), key='rw_'+key)
                   for key, label in WEIGHT_LABELS.items()}
        total = sum(raw.values())
        if total == 0:
            st.warning('Нужен хотя бы один ненулевой вес. Применены исходные веса контракта.')
            weights = ScoringWeights()
        else:
            weights = ScoringWeights(**{key: value/total for key, value in raw.items()})
        st.caption('Веса нормированы: сумма = 1. Обоснование критериев и их значимости готовит Dev 2.')
    return weights, FinModelInput(load_factor_pct=load, avg_fare_rub=fare,
        weekly_freq_per_route=frequency, aircraft_seats=seats,
        active_routes_count=routes, scenario=scenario, hub_iata=hub)
