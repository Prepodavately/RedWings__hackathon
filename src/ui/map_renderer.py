"""Geographic comparison and source transparency for the Dev 1 route table."""
from dataclasses import asdict
from typing import List

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.schemas.contracts import CityScoreDTO


def _dashed_leg(start, end, segments=24):
    # Scattergeo has no line.dash: small separated segments make a dashed trace.
    latitudes, longitudes = [], []
    for step in range(segments):
        for fraction in (step / segments, (step + .55) / segments):
            latitudes.append(start[0] + (end[0] - start[0]) * fraction)
            longitudes.append(start[1] + (end[1] - start[1]) * fraction)
        latitudes.append(None)
        longitudes.append(None)
    return latitudes, longitudes


def _number(value, suffix='', precision=1):
    return 'нет данных' if pd.isna(value) else f'{float(value):,.{precision}f}{suffix}'


def render_route_network_map(routes_df: pd.DataFrame, scored_cities: List[CityScoreDTO]) -> None:
    if routes_df.empty:
        st.info('Для этой сети пока нет маршрутов в витрине Dev 1.')
        return
    options = ['Все маршруты сети'] + routes_df['route_code'].tolist()
    names = {row.route_code: f'{row.origin_city} → {row.dest_city} · {row.route_code}' for row in routes_df.itertuples()}
    focus = st.selectbox('🔍 Фокус на маршруте (Сравнение с крюком через Москву)', options,
        format_func=lambda value: names.get(value, value), key='map_focus')
    figure = go.Figure()
    for index, row in enumerate(routes_df.itertuples()):
        figure.add_trace(go.Scattergeo(lat=[row.lat_o, row.lat_d], lon=[row.lon_o, row.lon_d],
            mode='lines', line=dict(width=2, color='#6199d4'), opacity=.65,
            text=f'{row.origin_city} → {row.dest_city}<br>{row.distance_km:,.0f} км · {row.flight_time_min:,.0f} мин',
            hoverinfo='text', name='Маршруты сети', legendgroup='network', showlegend=index == 0))
    selected = None
    if focus != options[0]:
        selected = routes_df.loc[routes_df['route_code'] == focus].iloc[0]
        origin = (selected.lat_o, selected.lon_o)
        destination = (selected.lat_d, selected.lon_d)
        moscow = (55.7558, 37.6173)
        lats, lons = _dashed_leg(origin, moscow)
        lat2, lon2 = _dashed_leg(moscow, destination)
        figure.add_trace(go.Scattergeo(lat=lats + lat2, lon=lons + lon2, mode='lines',
            line=dict(width=3, color='#ff5267'), name=f'Через Москву · ×{selected.moscow_detour_ratio:.2f}',
            hoverinfo='name'))
        figure.add_trace(go.Scattergeo(lat=[moscow[0]], lon=[moscow[1]], mode='markers+text',
            marker=dict(size=10, color='#ff5267'), text=['Москва'], textposition='top left',
            name='Москва · пересадка', showlegend=False))
        figure.add_trace(go.Scattergeo(lat=[origin[0], destination[0]], lon=[origin[1], destination[1]],
            mode='lines', line=dict(width=5, color='#17c89a'),
            name=f'Напрямую · {selected.distance_km:,.0f} км / {selected.flight_time_min:,.0f} мин', hoverinfo='name'))
    coordinates = dict(routes_df.attrs.get('city_coordinates', {}))
    for row in routes_df.itertuples():
        coordinates[row.origin_iata] = (row.lat_o, row.lon_o)
        coordinates[row.dest_iata] = (row.lat_d, row.lon_d)
    mapped = [city for city in scored_cities if city.iata in coordinates]
    for top in (False, True):
        cities = [city for city in mapped if city.is_top3 == top]
        figure.add_trace(go.Scattergeo(lat=[coordinates[c.iata][0] for c in cities],
            lon=[coordinates[c.iata][1] for c in cities], mode='markers+text',
            text=[c.iata for c in cities], textposition='top center',
            marker=dict(size=15 if top else 9, color='#ef4056' if top else '#d8e6f4', line=dict(width=1, color='#143451')),
            hovertext=[f'#{c.rank} · {c.city_name} ({c.iata})<br>Балл: {c.total_score:.2f}<br>Население: {c.population_mln:.3f} млн<br>Поток аэропорта: {c.airport_pax_mln:.3f} млн' for c in cities],
            hoverinfo='text', name='Топ-3 скоринга' if top else 'Другие кандидаты'))
    figure.update_geos(lonaxis=dict(range=[30, 80]), lataxis=dict(range=[41, 63]),
        projection_type='mercator', showland=True, landcolor='#e7edf3',
        showocean=True, oceancolor='#c8ddeb', showcountries=True, countrycolor='#a1b4c4',
        showlakes=True, lakecolor='#c8ddeb', coastlinecolor='#8aa9c1', bgcolor='rgba(0,0,0,0)')
    figure.update_layout(height=580, margin=dict(l=0, r=0, t=10, b=10), legend=dict(orientation='h', y=-.04))
    st.plotly_chart(figure, use_container_width=True, config={'displaylogo': False, 'scrollZoom': True})
    if len(mapped) < len(scored_cities):
        st.caption(f'Координаты доступны для {len(mapped)} из {len(scored_cities)} городов; остальные не нанесены на карту.')
    if selected is not None:
        direct, transit, railway = st.columns(3)
        direct.metric('Прямой рейс SJ-100', _number(selected.flight_time_min, ' мин', 0))
        direct.caption(_number(selected.distance_km, ' км', 0))
        transit.metric('Плечо через Москву', _number(selected.moscow_detour_ratio, ' ×', 2))
        transit.caption('Коэффициент длины пути. Время пересадки не оценено.')
        railway.metric('Поезд', _number(selected.rail_travel_hours, ' ч'))
        railway.caption('Слабая конкуренция ж/д по оценке Dev 1' if selected.rail_weak_competitor else 'Проверить конкуренцию ж/д')
    st.caption('Карта соединяет города; это не трассы полётов. Геометрический крюк через Москву не доказывает наличие удобной стыковки или экономию заданного числа часов.')
    with st.expander('Рейтинг всех 12 городов'):
        ranking = pd.DataFrame([asdict(city) for city in scored_cities])
        st.dataframe(ranking.rename(columns={'rank': 'Место', 'city_name': 'Город', 'iata': 'IATA',
            'total_score': 'Балл', 'population_mln': 'Население, млн', 'airport_pax_mln': 'Поток аэропорта, млн'}),
            hide_index=True, use_container_width=True)
    st.subheader('Основания выбора маршрутов')
    st.caption('pax — оценка Dev 1, а не наблюдённый спрос. Частота витрины и частота планируемой сети — разные показатели. proof_source содержит источник или метод оценки.')
    labels = {'route_code': 'Код', 'origin_city': 'Откуда', 'dest_city': 'Куда', 'distance_km': 'Км',
        'flight_time_min': 'Время, мин', 'moscow_detour_ratio': 'Крюк через Мск, ×',
        'rail_travel_hours': 'Поезд, ч', 'competitor_flights_weekly': 'Рейсов конкурентов/нед.',
        'own_flights_weekly': 'Рейсов RW/нед.', 'competitor_carriers': 'Конкуренты',
        'competitor_fare_rub': 'Тариф конкурентов, ₽', 'subsidy_eligible': 'Направление в ПП №1242',
        'launch_quarter': 'Квартал запуска (план)', 'freq': 'Частота витрины', 'pax': 'Поток Dev 1 (оценка)',
        'proof_source': 'Источник / метод оценки', 'route_code_source': 'Источник номера рейса'}
    st.dataframe(routes_df[[c for c in labels if c in routes_df]].rename(columns=labels),
                 hide_index=True, use_container_width=True)
    st.download_button('Скачать маршруты и источники · CSV', routes_df.to_csv(index=False).encode('utf-8-sig'),
                       file_name='red_wings_routes.csv', mime='text/csv', key='download_routes')
