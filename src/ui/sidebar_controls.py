"""Controls use the frozen Dev 2/3 contracts; no financial logic lives here."""
from typing import Tuple

import streamlit as st

from src.schemas.contracts import FinModelInput, ScoringWeights

CITY_LABELS = {
    'KUF': 'Самара (Курумоч)', 'KZN': 'Казань', 'UFA': 'Уфа',
    'GOJ': 'Нижний Новгород', 'SVX': 'Екатеринбург', 'PEE': 'Пермь',
    'CEK': 'Челябинск', 'MRV': 'Минеральные Воды', 'TJM': 'Тюмень',
    'VOG': 'Волгоград', 'GSV': 'Саратов', 'OMS': 'Омск',
}


def render_sidebar_controls() -> Tuple[ScoringWeights, FinModelInput]:
    with st.sidebar:
        st.header('⚙️ Параметры моделирования')
        scenario = st.radio('Сценарий рынка', ['base', 'conservative'],
            format_func=lambda value: {
                'base': 'Базовый сценарий (поставки SJ-100 с 2027-H2)',
                'conservative': 'Осторожный / Стресс (сдвиг SJ-100 + секвестр субсидий)',
            }[value], key='scenario')
        hub = st.selectbox('Региональный хаб · гипотеза А', list(CITY_LABELS),
            format_func=lambda code: f'{code} — {CITY_LABELS[code]}', key='hub_iata')
        if hub == 'SVX':
            st.caption('SVX — действующая база RW. Здесь это сценарий развития базы; в рейтинге новых хабов Dev 2 он исключён.')
        load = st.slider('Целевая загрузка кресел (SLF, %)', 65.0, 95.0, 84.0, 0.5, key='load_factor_pct')
        fare = st.slider('Средний тариф OW (₽)', 5500.0, 13500.0, 8400.0, 100.0, key='avg_fare_rub')
        frequency = st.slider('Частота рейсов в неделю (пар/маршрут)', 2, 10, 5, key='weekly_freq_per_route')
        routes = st.slider('Количество маршрутов в сети', 8, 12, 10, key='active_routes_count')
        seats = st.slider('Кресел в SJ-100', 93, 103, 100, key='aircraft_seats')
        st.caption('OW — билет в одну сторону. Одна пара рейсов — туда и обратно. Финансы — год работы полностью развёрнутой сети.')
        with st.expander('⚖️ Веса скоринга городов', expanded=False):
            values = [st.slider(label, 0.0, 1.0, default, 0.05, key=key) for label, default, key in [
                ('Вес: Население агломерации', .30, 'w_population'),
                ('Вес: Оптимум плеча SJ-100 (до Мск)', .20, 'w_hub_distance'),
                ('Вес: Свободная ниша (100% − доля лидера)', .30, 'w_competitor_gap'),
                ('Вес: ПСП и авиаподвижность', .20, 'w_tourism_demand'),
            ]]
            if sum(values) == 0:
                st.info('Все веса равны нулю: применены исходные 0,30 / 0,20 / 0,30 / 0,20.')
                values = [.30, .20, .30, .20]
            total = sum(values)
            weights = ScoringWeights(*(value / total for value in values))
            st.caption('Веса нормируются до суммы 1. Это приоритеты команды: проверяйте устойчивость тройки при их изменении.')
    return weights, FinModelInput(load_factor_pct=load, avg_fare_rub=fare,
        weekly_freq_per_route=frequency, aircraft_seats=seats,
        active_routes_count=routes, scenario=scenario, hub_iata=hub)
