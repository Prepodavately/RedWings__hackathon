"""Geographic comparison and source transparency for the Dev 1 route table."""
import json
from dataclasses import asdict
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.models.sj100_fleet import AIRCRAFT_CATALOG, get_aircraft_spec
from src.models.unit_economics import compare_all_aircraft_models, evaluate_routes_by_aircraft_and_rw_gap
from src.schemas.contracts import CityScoreDTO, FinModelInput
from src.scoring.city_scorer import compute_gravity_anomaly_field
from src.ui.kpi_cards import render_rw_gap_kpis
from src.ui.sidebar_controls import render_gravity_controls


def _dashed_leg(start, end, segments=24):
    # Split the demo route into visible segments.
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
    _territorial_claims_layer(figure, geographic=True)
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
    figure.update_geos(lonaxis=dict(range=[26, 82]), lataxis=dict(range=[41, 63]),
        projection_type='mercator', showland=True, landcolor='#e7edf3',
        showocean=True, oceancolor='#c8ddeb', showcountries=True, countrycolor='#a1b4c4',
        showlakes=True, lakecolor='#c8ddeb', coastlinecolor='#8aa9c1', bgcolor='rgba(0,0,0,0)')
    figure.update_layout(height=580, margin=dict(l=0, r=0, t=10, b=10), legend=dict(orientation='h', y=-.04))
    st.plotly_chart(figure, use_container_width=True, config={'displaylogo': False, 'scrollZoom': True})
    _territorial_claims_caption()
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


LENSES = {
    'routes_gap': '🧭 Сеть Red Wings (Есть vs Предлагаем)',
    'aircraft_range': '✈️ Дальность и модели ВС',
    'gravity_lens': '🌌 Гравитационная линза (Тепловая карта)',
}

# color, line width, dashed
EXISTING_STYLE = ('#334155', 1.8, False)
GAP_STYLES = {
    'existing_core': (*EXISTING_STYLE, 'Действующий основной'),
    'existing_thin': (*EXISTING_STYLE, 'Действующий с низкой частотой'),
    'new_blue_ocean': ('#059669', 2.4, False, 'Белое пятно'),
    'new_head_to_head': ('#7c3aed', 1.8, True, 'Есть конкуренты'),
}
RANGE_STYLES = {
    'optimal': ('#059669', 2.4, False, 'Оптимальное плечо'),
    'acceptable': ('#3b82f6', 1.8, False, 'Допустимое плечо'),
    'too_short': ('#d97706', 1.8, False, 'Слишком короткое плечо'),
    'out_of_range': ('#dc2626', 1.8, True, 'За пределом дальности'),
}
SPECTRUM = [
    [0.00, '#0029b8'], [0.18, '#0077e6'], [0.32, '#00c4d4'],
    [0.45, '#16c45a'], [0.58, '#65d63a'], [0.72, '#e6e024'],
    [0.84, '#f59e0b'], [0.93, '#ea580c'], [1.00, '#cc1b1b'],
]
MAP_CONFIG = {'displaylogo': False, 'scrollZoom': True}


@st.cache_data(max_entries=32, show_spinner=False)
def _aircraft_market(routes, aircraft_id, assumptions):
    return evaluate_routes_by_aircraft_and_rw_gap(routes, aircraft_id, **assumptions)


@st.cache_data(max_entries=16, show_spinner=False)
def _aircraft_comparison(routes, assumptions):
    return compare_all_aircraft_models(routes, **assumptions)


@st.cache_data(max_entries=16, show_spinner=False)
def _gravity_field(features, routes, cities, parameters):
    return compute_gravity_anomaly_field(features, routes, cities, **parameters)


@st.cache_data(show_spinner=False)
def _gravity_boundaries():
    path = Path(__file__).with_name('assets') / 'gravity_boundaries.json'
    return json.loads(path.read_text(encoding='utf-8'))['layers']


def _geo_base():
    figure = go.Figure()
    figure.update_geos(
        projection_type='mercator', showland=True, landcolor='#edf2f7',
        showocean=True, oceancolor='#d8e8fa', showlakes=True, lakecolor='#d8e8fa',
        showcountries=True, countrycolor='#94a3b8', showcoastlines=True, coastlinecolor='#64748b',
        fitbounds='locations',
    )
    figure.update_layout(height=610, margin=dict(l=0, r=0, t=10, b=20),
                         legend=dict(orientation='h', y=-0.04))
    return figure


def _city_layer(figure, features, cities, *, geographic=True):
    ranked = {city.iata: city for city in cities}
    for top in (False, True):
        rows = [row for row in features.itertuples() if ranked[row.iata].is_top3 == top]
        coords = {'lat': [row.lat for row in rows], 'lon': [row.lon for row in rows]} if geographic else {
            'y': [row.lat for row in rows], 'x': [row.lon for row in rows]}
        trace = go.Scattergeo if geographic else go.Scatter
        figure.add_trace(trace(
            **coords, mode='markers+text', text=[row.iata for row in rows], textposition='top center',
            textfont=dict(color='#0f172a', size=13),
            marker=dict(size=13 if top else 9, color='#ef4444' if top else 'white',
                        line=dict(color='#0f172a', width=1.5)),
            hovertext=[f'{row.city_name} · {ranked[row.iata].total_score:.2f} балла' for row in rows],
            hoverinfo='text', name='Топ-3 скоринга' if top else 'Города-кандидаты',
        ))


def _route_layer(figure, routes, status_column, styles, *, geographic=True):
    for status, group in routes.groupby(status_column):
        color, width, dashed, label = styles[status]
        lat, lon, hover = [], [], []
        for row in group.itertuples():
            ys, xs = [row.lat_o, row.lat_d, None], [row.lon_o, row.lon_d, None]
            lat.extend(ys)
            lon.extend(xs)
            hover.extend([f'{row.origin_city} ↔ {row.dest_city}<br>{row.distance_km:.0f} км · {label}'] * len(ys))
        coordinates = {'lat': lat, 'lon': lon} if geographic else {'y': lat, 'x': lon}
        trace = go.Scattergeo if geographic else go.Scatter
        figure.add_trace(trace(
            **coordinates, mode='lines', line=dict(color=color, width=width, dash='dash' if dashed else 'solid'),
            name=label, hovertext=hover, hoverinfo='text',
        ))


def _set_route_focus():
    selection = st.session_state['rw_gap_map']['selection']
    for point in selection['points']:
        route_code = point.get('customdata')
        if isinstance(route_code, str) and '↔' in route_code:
            st.session_state['rw_gap_focus'] = route_code
            return


def _render_routes_gap(market, summary, features, cities):
    render_rw_gap_kpis(summary)
    existing = market['rw_network_status'].str.startswith('existing_')
    proposals = market['proposal_bucket'].eq('propose_new')
    white_space = market['rw_network_status'].eq('new_blue_ocean')
    filters = {
        'all': (f'Все ({summary.total_market_pairs})', market),
        'existing': (f'Уже есть у RW ({summary.existing_rw_count})', market.loc[existing]),
        'proposed': (f'Предлагаем открыть ({summary.proposed_new_count})', market.loc[proposals]),
        'white': ('Белые пятна (0 конкурентов)', market.loc[white_space]),
    }
    choice = st.radio('Маршруты на карте и в таблице', list(filters),
                      format_func=lambda key: filters[key][0], horizontal=True, key='rw_gap_filter')
    visible = filters[choice][1].copy()
    visible['map_pair'] = visible['pair_key'].map(' ↔ '.join)
    names = {row.map_pair: f'{row.origin_city} ↔ {row.dest_city} · {row.map_pair}' for row in visible.itertuples()}
    options = [''] + list(names)
    if st.session_state.get('rw_gap_focus', '') not in options:
        st.session_state['rw_gap_focus'] = ''
    focus = st.selectbox('Маршрут для сравнения с пересадкой в Москве', options,
                         format_func=lambda key: names.get(key, 'Выберите маршрут'), key='rw_gap_focus')

    figure = go.Figure()
    _boundary_layer(figure)
    _territorial_claims_layer(figure)
    _field_axes(figure, [26, 82], [40, 64])
    figure.update_layout(clickmode='event+select', plot_bgcolor='#edf2f7')
    _route_layer(figure, visible, 'rw_network_status', GAP_STYLES, geographic=False)
    if focus:
        row = visible.loc[visible['map_pair'].eq(focus)].iloc[0]
        moscow = (55.7558, 37.6173)
        figure.add_trace(go.Scatter(
            y=[row.lat_o, moscow[0], row.lat_d], x=[row.lon_o, moscow[1], row.lon_d],
            mode='lines', line=dict(color='#dc2626', width=3, dash='dash'),
            name=f'Через Москву · ×{row.moscow_detour_ratio:.2f}', hoverinfo='name',
        ))
        figure.add_trace(go.Scatter(
            y=[moscow[0]], x=[moscow[1]], mode='markers+text', text=['Москва'],
            textposition='top left', marker=dict(size=10, color='#dc2626'), showlegend=False,
        ))
    _city_layer(figure, features, cities, geographic=False)
    # Plotly selects markers. Give each route a target and keep the selectbox for keyboard access.
    figure.add_trace(go.Scatter(
        y=(visible['lat_o'] + visible['lat_d']) / 2,
        x=(visible['lon_o'] + visible['lon_d']) / 2, mode='markers',
        marker=dict(size=8, color='#64748b', line=dict(color='white', width=1)),
        customdata=visible['map_pair'].tolist(), text=[names[key] for key in visible['map_pair']],
        hoverinfo='text', name='Нажмите точку маршрута', showlegend=False,
    ))
    st.plotly_chart(figure, use_container_width=True, config=MAP_CONFIG, key='rw_gap_map',
                    on_select=_set_route_focus, selection_mode='points')
    _territorial_claims_caption()
    if visible.empty:
        st.info('В этом фильтре нет маршрутов при выбранных параметрах.')
    if focus:
        direct, via, rail = st.columns(3)
        direct.metric('Прямой перелёт с терминалами', _number(row.air_door_to_door_h, ' ч', 2))
        via.metric('Перелёт через Москву', _number(row.moscow_via_time_h, ' ч', 2))
        rail.metric('Поезд', _number(row.rail_travel_hours, ' ч', 2))
        st.caption('Авиа — оценки Dev 1 с терминальным временем. Время доезда показано отдельно в таблице.')

    fields = {
        'origin_city': 'Откуда', 'dest_city': 'Куда', 'distance_km': 'Км',
        'own_flights_weekly': 'Рейсов RW/нед.', 'competitor_flights_weekly': 'Рейсов конкурентов/нед.',
        'air_door_to_door_h': 'Авиа с терминалами, ч', 'moscow_via_time_h': 'Через Москву, ч',
        'rail_travel_hours': 'Поезд, ч', 'access_time_origin_h': 'Доезд в городе отправления, ч',
        'access_time_dest_h': 'Доезд в городе прибытия, ч', 'belf_pct': 'Порог загрузки, %',
        'annual_ebitdar_mln': 'Маршрутный EBITDAR, млн ₽', 'proof_source': 'Источник / метод оценки',
    }
    table = visible[list(fields)].rename(columns=fields).copy()
    table.insert(2, 'Статус рынка', visible['rw_network_status'].map(lambda key: GAP_STYLES[key][3]))
    table.insert(3, 'Предложение модели', visible['proposal_bucket'].eq('propose_new').map({True: 'Да', False: '—'}))
    st.dataframe(table, hide_index=True, use_container_width=True)
    st.download_button('Скачать пары и источники · CSV', visible.drop(columns='map_pair').to_csv(index=False).encode('utf-8-sig'),
                       file_name='red_wings_market_pairs.csv', mime='text/csv', key='rw_gap_download')


def _range_ring(latitude, longitude, distance_km):
    """Sample a geodesic circle on the mean-radius sphere used for map distances."""
    angle = distance_km / 6371.0
    lat, lon = np.radians([latitude, longitude])
    bearing = np.linspace(0, 2 * np.pi, 181)
    ring_lat = np.arcsin(np.sin(lat) * np.cos(angle) + np.cos(lat) * np.sin(angle) * np.cos(bearing))
    ring_lon = lon + np.arctan2(np.sin(bearing) * np.sin(angle) * np.cos(lat),
                               np.cos(angle) - np.sin(lat) * np.sin(ring_lat))
    return np.degrees(ring_lat), (np.degrees(ring_lon) + 180) % 360 - 180


def _render_aircraft_range(market, routes, features, cities, spec, params, assumptions):
    nodes = features.set_index('iata')
    base = st.selectbox('Базовый узел', list(nodes.index), index=list(nodes.index).index(params.hub_iata),
                        format_func=lambda code: f'{nodes.at[code, "city_name"]} ({code})', key='range_base')
    node = nodes.loc[base]
    figure = _geo_base()
    _territorial_claims_layer(figure, geographic=True)
    for radius, color, label in [
        (spec.opt_low_km, '#059669', 'Нижняя граница оптимума'),
        (spec.opt_high_km, '#059669', 'Верхняя граница оптимума'),
        (spec.max_km, '#334155', 'Максимальная дальность'),
    ]:
        lat, lon = _range_ring(node.lat, node.lon, radius)
        figure.add_trace(go.Scattergeo(
            lat=lat, lon=lon, mode='lines',
            line=dict(color=color, width=2, dash='dash'), name=f'{label} · {radius:,} км',
            hoverinfo='name',
        ))
    _route_layer(figure, market, 'aircraft_range_status', RANGE_STYLES)
    _city_layer(figure, features, cities)
    figure.add_trace(go.Scattergeo(lat=[node.lat], lon=[node.lon], mode='markers', name=f'База {base}',
                                  marker=dict(color='#fbbf24', size=14, symbol='star',
                                              line=dict(color='#0f172a', width=1))))
    st.plotly_chart(figure, use_container_width=True, config=MAP_CONFIG, key='aircraft_range_map')
    _territorial_claims_caption()
    st.caption('Кольца показывают расстояния от выбранной базы. Цвет каждого плеча учитывает расстояние между его концами. '
               'Пороги дальности взяты из сценарного каталога Dev 3.')
    results = _aircraft_comparison(routes, assumptions)
    rows = [{
        'Модель': get_aircraft_spec(item.aircraft_id).name,
        'Кресел': get_aircraft_spec(item.aircraft_id).seats,
        'Доступно из всех пар': f'{item.feasible_for_aircraft_count} / {item.total_market_pairs}',
        'В оптимуме': item.optimal_range_count,
        'Новых предложений': item.proposed_new_count,
        'Нужно бортов': item.required_aircraft_count,
        'EBITDAR новых пар, млн ₽': round(item.proposed_ebitdar_mln_rub, 1),
    } for item in results]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption('Потребность в бортах использует единую норму SJ-100. При отсутствии предложений модель показывает минимальный резерв.')


@st.cache_data(show_spinner=False)
def _territorial_claims():
    path = Path(__file__).with_name('assets') / 'territorial_claims.json'
    return json.loads(path.read_text(encoding='utf-8'))


def _territorial_claims_layer(figure, *, geographic=False):
    trace = go.Scattergeo if geographic else go.Scatter
    for index, region in enumerate(_territorial_claims()['regions']):
        lon, lat = [], []
        for ring in region['rings']:
            xs, ys = zip(*ring)
            lon.extend([*xs, None])
            lat.extend([*ys, None])
        coordinates = {'lon': lon, 'lat': lat} if geographic else {'x': lon, 'y': lat}
        figure.add_trace(trace(
            **coordinates, mode='lines', fill='toself', fillcolor='rgba(168,85,247,0.19)',
            line=dict(color='#581c87', width=1.7, dash='dot'),
            name='Территориальные претензии России', legendgroup='territorial_claims',
            showlegend=index == 0, text=region['name'], hoverinfo='text',
            **({} if geographic else {'hoveron': 'fills'}),
        ))


def _territorial_claims_caption():
    source = _territorial_claims()['source']
    st.caption('Фиолетовый слой показывает административные границы Крыма, Севастополя и четырёх '
               'областей Украины, на которые претендует Россия. Генассамблея ООН подтвердила '
               'территориальную целостность Украины в резолюциях [68/262](https://docs.un.org/A/RES/68/262) '
               'и [ES-11/4](https://docs.un.org/A/RES/ES-11/4). '
               f'Геометрия: [Natural Earth]({source}).')


def _boundary_layer(figure):
    for name, lines in _gravity_boundaries().items():
        lon, lat = [], []
        for line in lines:
            for x, y in line:
                lon.append(x)
                lat.append(y)
            lon.append(None)
            lat.append(None)
        figure.add_trace(go.Scatter(
            x=lon, y=lat, mode='lines', line=dict(color='#0f172a', width=1.05 if name == 'countries' else .8),
            hoverinfo='skip', showlegend=False,
        ))


def _field_axes(figure, longitude_range, latitude_range):
    figure.update_layout(height=630, margin=dict(l=10, r=10, t=10, b=25),
                         legend=dict(orientation='h', y=-.04), dragmode='pan')
    figure.update_xaxes(range=longitude_range, visible=False)
    figure.update_yaxes(range=latitude_range, visible=False)


def _render_gravity_lens(features, routes, cities, proposals, summary):
    controls = render_gravity_controls()
    parameters = {key: controls[key] for key in ('gamma', 'lam', 'radius_km', 'mode', 'exclude_existing_rw')}
    field = _gravity_field(features, routes, cities, parameters)
    figure = go.Figure(go.Contour(
        x=field.lons, y=field.lats, z=field.z_values, zmin=-100, zmax=100, autocontour=False,
        contours=dict(start=-100, end=100, size=12.5, coloring='fill'),
        colorscale=SPECTRUM, line=dict(width=.7, color='rgba(15,23,42,0.45)'),
        colorbar=dict(title='Индекс', tickvals=[-100, -50, 0, 50, 100]),
        hovertemplate='Долгота %{x:.1f}°<br>Широта %{y:.1f}°<br>Индекс %{z:.1f}<extra></extra>',
    ))
    _boundary_layer(figure)
    _territorial_claims_layer(figure)
    if controls['show_proposals']:
        lon, lat = [], []
        for route in proposals.itertuples():
            lon.extend([route.lon_o, route.lon_d, None])
            lat.extend([route.lat_o, route.lat_d, None])
        figure.add_trace(go.Scatter(x=lon, y=lat, mode='lines', name='Предложения Dev 3',
                                    line=dict(color='#fff', width=1.4, dash='dash'), hoverinfo='skip'))
    _city_layer(figure, features, cities, geographic=False)
    figure.add_trace(go.Scatter(
        x=[field.barycenter_lon], y=[field.barycenter_lat], mode='markers', name='Барицентр',
        marker=dict(size=15, symbol='diamond', color='#fde047', line=dict(color='#0f172a', width=2)),
        hovertemplate='Барицентр · %{y:.2f}° с. ш., %{x:.2f}° в. д.<extra></extra>',
    ))
    _field_axes(figure, [field.lons[0], field.lons[-1]], [field.lats[0], field.lats[-1]])
    st.plotly_chart(figure, use_container_width=True, config=MAP_CONFIG, key='gravity_field_map')
    _territorial_claims_caption()
    st.caption('Нормированный сценарный индекс от −100 до +100. '
               'Карта показывает потенциал или относительный дефицит в зависимости от режима. Границы: Natural Earth 1:50m.')
    if controls['exclude_existing_rw']:
        st.caption(f'В витрине {summary.existing_rw_count} существующих пар RW. '
                   'При включённом фильтре поле Dev 2 строит потенциал только по направлениям с нулём рейсов RW и конкурентов.')


def render_network_lenses(features: pd.DataFrame, routes: pd.DataFrame,
                          cities: list[CityScoreDTO], params: FinModelInput):
    lens = st.radio('Линза карты', list(LENSES), format_func=LENSES.get, horizontal=True, key='network_lens')
    aircraft_id = st.selectbox('Модель ВС для отбора маршрутов и матрицы', list(AIRCRAFT_CATALOG),
                               index=list(AIRCRAFT_CATALOG).index('sj100_basic'),
                               format_func=lambda key: AIRCRAFT_CATALOG[key].name, key='lens_aircraft')
    spec = get_aircraft_spec(aircraft_id)
    assumptions = {
        'load_factor_pct': params.load_factor_pct,
        'avg_fare_rub': params.avg_fare_rub,
        'weekly_freq': params.weekly_freq_per_route,
        'subsidy_cut_pct': float(st.session_state.get('subsidy_cut_pct', 0)),
    }
    market, summary = _aircraft_market(routes, aircraft_id, assumptions)
    proposals = market.loc[market['proposal_bucket'].eq('propose_new')]
    if lens == 'routes_gap':
        _render_routes_gap(market, summary, features, cities)
    elif lens == 'aircraft_range':
        _render_aircraft_range(market, routes, features, cities, spec, params, assumptions)
    else:
        _render_gravity_lens(features, routes, cities, proposals, summary)
    return aircraft_id, proposals['pair_key'].tolist()
