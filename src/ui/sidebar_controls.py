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
        load = st.slider('Загрузка кресел, %', 0.0, 100.0, defaults.load_factor_pct, 1.0, key='rw_load')
        fare = st.slider('Средний тариф, ₽', 0.0, 30000.0, defaults.avg_fare_rub, 100.0, key='rw_fare')
        frequency = st.slider('Частота на маршрут за неделю', 0, 28, defaults.weekly_freq_per_route, key='rw_frequency',
                              help='weekly_freq_per_route передаётся без пересчёта. Команда должна уточнить: вылеты в одну сторону или парные обороты.')
        hub = st.text_input('Код IATA нового хаба', defaults.hub_iata, max_chars=3, key='rw_hub',
                            help='Например, KUF — Самара. Для расчётного модуля передаётся именно IATA, не название города.').strip().upper()
        with st.expander('Флот и размер сети'):
            seats = st.number_input('Кресел в самолёте', 1, 500, defaults.aircraft_seats, key='rw_seats')
            routes = st.slider('Маршрутов в расчёте', 8, 12, defaults.active_routes_count, key='rw_routes')
        st.divider()
        st.markdown('### Веса выбора города')
        raw = {key: st.slider(label, 0, 100, round(asdict(ScoringWeights())[key]*100), key='rw_'+key)
               for key, label in WEIGHT_LABELS.items()}
        total = sum(raw.values())
        if total == 0:
            st.warning('Нужен хотя бы один ненулевой вес. Применены исходные веса контракта.')
            weights = ScoringWeights()
        else:
            weights = ScoringWeights(**{key: value/total for key, value in raw.items()})
        st.caption('Веса нормированы: сумма = 1. Обоснование критериев и их значимости готовит Dev 2.')
        if len(hub) != 3 or not hub.isascii() or not hub.isalpha():
            st.error('Введите три латинские буквы IATA.'); st.stop()
        if hub in {'SVX', 'DME', 'ZIA', 'SVO', 'VKO', 'MOW'}:
            st.error('Для нового хаба выберите город помимо Екатеринбурга и Москвы.'); st.stop()
    return weights, FinModelInput(load_factor_pct=load, avg_fare_rub=fare,
        weekly_freq_per_route=frequency, aircraft_seats=seats,
        active_routes_count=routes, scenario=scenario, hub_iata=hub)
