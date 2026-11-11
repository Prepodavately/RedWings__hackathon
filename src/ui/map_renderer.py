"""Geographic comparison, clickable route map, aircraft range rings, and Russia gravity map for Dev 1–2."""
from dataclasses import asdict
from math import asin, atan2, cos, degrees, radians, sin
from typing import List

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.schemas.contracts import CityScoreDTO

DEFAULT_CITY_COORDS = {
    'KUF': (53.5049, 50.1643),
    'KZN': (55.6062, 49.2787),
    'UFA': (54.5575, 55.8744),
    'GOJ': (56.2301, 43.7840),
    'SVX': (56.7431, 60.8027),
    'PEE': (57.9145, 56.0212),
    'CEK': (55.3058, 61.5033),
    'MRV': (44.2251, 43.0819),
    'TJM': (57.1896, 65.3243),
    'VOG': (48.7825, 44.3455),
    'GSV': (51.7128, 46.1711),
    'OMS': (54.9670, 73.3105),
}

# Характеристики типов ВС в стратегии Red Wings (Dev 2 range_weight + Dev 3 sj100_fleet / Волны до 2030)
AIRCRAFT_SPECS = {
    'sj100_basic': {
        'name': 'SJ-100 Basic (100 мест)',
        'seats': 100,
        'min_km': 350,
        'opt_low_km': 600,
        'opt_high_km': 1600,
        'max_km': 2450,
        'note': 'Основной региональный борт 2027–2028 (поставки ОАК), CASK на 19–24% ниже CRJ-200',
    },
    'sj100_lr': {
        'name': 'SSJ-100 / SJ-100 LR (100 мест)',
        'seats': 100,
        'min_km': 400,
        'opt_low_km': 700,
        'opt_high_km': 2200,
        'max_km': 3050,
        'note': 'Действующий резерв SSJ (до 6 бортов) + модификация увеличенной дальности',
    },
    'tu214': {
        'name': 'Ту-214 (210 мест · Волна 3)',
        'seats': 210,
        'min_km': 1100,
        'opt_low_km': 1400,
        'opt_high_km': 4200,
        'max_km': 5200,
        'note': 'Магистральный борт Волны 3 (2029–2030: 8 Ту-214 + 28 SJ-100) для дальних линий >2000 км',
    },
    'crj200': {
        'name': 'CRJ-200 (50 мест · Конкуренты)',
        'seats': 50,
        'min_km': 300,
        'opt_low_km': 450,
        'opt_high_km': 1200,
        'max_km': 1450,
        'note': 'Флот региональных конкурентов (ЮВТ Аэро): узкая ёмкость, ограниченный радиус 1450 км',
    },
}

CITY_TEXT_POS = {
    'GOJ': 'top right',
    'KZN': 'top right',
    'KUF': 'bottom left',
    'GSV': 'bottom right',
    'VOG': 'bottom right',
    'MRV': 'bottom right',
    'PEE': 'top right',
    'UFA': 'top left',
    'SVX': 'top right',
    'CEK': 'bottom right',
    'TJM': 'top right',
    'OMS': 'middle right',
}

RUSSIA_CROP_POLYGON = [
    (30.0, 69.8), (33.5, 69.3), (38.0, 68.2), (40.5, 66.5), (37.5, 64.5),
    (40.2, 65.5), (43.5, 66.8), (44.2, 68.5), (49.5, 67.8), (54.5, 68.5),
    (60.0, 69.8), (64.5, 69.2), (68.5, 70.0), (72.5, 70.0), (73.5, 68.5),
    (76.0, 70.0), (80.0, 70.0), (80.0, 51.0), (76.5, 53.5), (73.5, 53.6),
    (70.8, 55.2), (65.0, 54.4), (61.2, 53.5), (61.0, 50.8), (55.5, 50.6),
    (51.0, 51.2), (49.8, 49.5), (48.2, 46.2), (47.5, 44.5), (48.3, 41.4),
    (46.0, 41.8), (43.5, 42.8), (40.0, 43.4), (38.0, 44.6), (36.5, 45.2),
    (33.5, 44.5), (32.6, 45.5), (34.8, 46.2), (33.0, 46.6), (36.8, 47.0),
    (38.2, 47.8), (38.0, 49.5), (35.5, 50.5), (34.0, 52.0), (31.5, 52.2),
    (31.0, 54.5), (30.8, 55.8), (28.2, 56.2), (27.8, 57.5), (28.0, 59.5),
    (30.2, 60.0), (28.5, 61.0), (30.5, 62.5), (29.8, 65.5), (29.0, 67.8),
    (30.0, 69.8),
]

NOVAYA_ZEMLYA_POLYGON = [
    (52.5, 70.6), (57.8, 70.8), (61.0, 73.5), (65.0, 74.0), (56.5, 73.5), (52.5, 70.6),
]

FEDERAL_DISTRICT_LINES = [
    [(31.5, 56.2), (35.5, 57.8), (39.5, 58.8), (45.0, 59.2), (50.5, 61.2), (59.2, 60.5)],
    [(34.0, 51.8), (38.5, 51.5), (41.8, 51.2), (43.0, 53.5), (42.2, 56.5), (45.0, 59.2)],
    [(41.8, 51.2), (44.0, 50.5), (46.8, 49.8), (49.8, 49.5)],
    [(59.5, 61.5), (59.0, 58.5), (58.2, 56.2), (57.8, 53.5), (59.5, 51.5)],
    [(68.5, 70.0), (72.0, 66.0), (74.5, 62.0), (70.8, 57.5), (70.8, 55.2)],
]


def _geo_circle(lat_deg: float, lon_deg: float, radius_km: float, steps: int = 72) -> tuple[list[float], list[float]]:
    """Строит геодезическую окружность заданного радиуса (км) вокруг аэропорта для отображения боевого радиуса ВС."""
    earth_r = 6371.0
    ang_dist = radius_km / earth_r
    lat1 = radians(lat_deg)
    lon1 = radians(lon_deg)
    lats, lons = [], []
    for i in range(steps + 1):
        brng = radians(i * (360.0 / steps))
        lat2 = asin(sin(lat1) * cos(ang_dist) + cos(lat1) * sin(ang_dist) * cos(brng))
        lon2 = lon1 + atan2(
            sin(brng) * sin(ang_dist) * cos(lat1),
            cos(ang_dist) - sin(lat1) * sin(lat2),
        )
        lats.append(degrees(lat2))
        lons.append(degrees(lon2))
    return lats, lons


def _classify_route_range(distance_km: float, spec: dict) -> str:
    if distance_km > spec['max_km']:
        return f"❌ Свыше дальности ({spec['max_km']} км)"
    if distance_km < spec['min_km']:
        return f"⚠️ Короткое плечо (<{spec['min_km']} км, риск ЖД)"
    if spec['opt_low_km'] <= distance_km <= spec['opt_high_km']:
        return '✅ Оптимум плеча ВС'
    return '☑️ Допустимо (вне пика CASK)'


def _points_in_polygon(lon_pts: np.ndarray, lat_pts: np.ndarray, polygon: list[tuple[float, float]]) -> np.ndarray:
    inside = np.zeros(lon_pts.shape, dtype=bool)
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        intersect = ((yi > lat_pts) != (yj > lat_pts)) & (
            lon_pts < (xj - xi) * (lat_pts - yi) / ((yj - yi) + 1e-12) + xi
        )
        inside ^= intersect
        j = i
    return inside


@st.cache_data(show_spinner=False)
def _cached_cropped_grid():
    lons = np.linspace(27.5, 80.0, 125)
    lats = np.linspace(41.2, 70.5, 85)
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    mask = _points_in_polygon(lon_grid, lat_grid, RUSSIA_CROP_POLYGON) | _points_in_polygon(
        lon_grid, lat_grid, NOVAYA_ZEMLYA_POLYGON
    )
    return lons, lats, lon_grid, lat_grid, mask


def _dashed_leg(start, end, segments=32):
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


def _resolve_coordinates(routes_df: pd.DataFrame | None) -> dict[str, tuple[float, float]]:
    coordinates = dict(DEFAULT_CITY_COORDS)
    if routes_df is not None:
        coordinates.update(routes_df.attrs.get('city_coordinates', {}))
        if not routes_df.empty and {'origin_iata', 'lat_o', 'lon_o', 'dest_iata', 'lat_d', 'lon_d'}.issubset(routes_df.columns):
            for row in routes_df.itertuples():
                coordinates[row.origin_iata] = (float(row.lat_o), float(row.lon_o))
                coordinates[row.dest_iata] = (float(row.lat_d), float(row.lon_d))
    return coordinates


def _render_russia_gravity_map(routes_df: pd.DataFrame, scored_cities: List[CityScoreDTO]) -> None:
    """Рендерит сфокусированную карту гравитационного притяжения (Европейская часть, ПФО, Урал, Сибирь)."""
    coordinates = _resolve_coordinates(routes_df)

    ctrl1, ctrl2 = st.columns(2)
    gamma = ctrl1.slider(
        'Коэффициент затухания гравитации (γ)',
        min_value=1.0,
        max_value=2.6,
        value=1.6,
        step=0.1,
        key='gravity_gamma_slider',
    )
    sj100_radius_km = ctrl2.slider(
        'Эффективный радиус притяжения ВС, км',
        min_value=650,
        max_value=2100,
        value=1250,
        step=50,
        key='gravity_radius_slider',
    )

    lons, lats, lon_grid, lat_grid, inside_russia = _cached_cropped_grid()

    route_freq_by_city: dict[str, int] = {}
    for row in routes_df.itertuples():
        route_freq_by_city[row.origin_iata] = route_freq_by_city.get(row.origin_iata, 0) + 1
        route_freq_by_city[row.dest_iata] = route_freq_by_city.get(row.dest_iata, 0) + 1

    field = np.zeros_like(lon_grid, dtype=float)
    total_mass = 0.0
    bary_lat = 0.0
    bary_lon = 0.0

    inv_kernel_r2 = (gamma * 0.85) / max(40000.0, (sj100_radius_km * 0.42) ** 2)
    inv_halo_r2 = (gamma * 0.45) / max(90000.0, (sj100_radius_km * 0.78) ** 2)

    for city in scored_cities:
        if city.iata not in coordinates:
            continue
        c_lat, c_lon = coordinates[city.iata]
        d_lat_km = (lat_grid - c_lat) * 111.0
        d_lon_km = (lon_grid - c_lon) * 111.0 * 0.58
        d2 = d_lat_km * d_lat_km + d_lon_km * d_lon_km

        network_boost = 1.0 + 0.11 * route_freq_by_city.get(city.iata, 0)
        city_mass = (
            0.62 * (city.total_score / 100.0) ** 1.35
            + 0.38 * (city.population_mln * city.airport_pax_mln) ** 0.38
        ) * network_boost

        total_mass += city_mass
        bary_lat += city_mass * c_lat
        bary_lon += city_mass * c_lon

        t1 = 1.0 + d2 * inv_kernel_r2
        t2 = 1.0 + d2 * inv_halo_r2
        field += city_mass * (1.55 / (t1 * t1) + 0.85 / t2)

    if total_mass > 0:
        bary_lat /= total_mass
        bary_lon /= total_mass

    russia_vals = field[inside_russia]
    f_min = float(russia_vals.min()) if russia_vals.size else 0.0
    f_max = float(russia_vals.max()) if russia_vals.size else 1.0

    norm_field = np.full_like(field, np.nan, dtype=float)
    if f_max > f_min:
        norm_field[inside_russia] = -100.0 + 180.0 * ((field[inside_russia] - f_min) / (f_max - f_min))

    geophysical_colorscale = [
        [0.00, '#3a98db'],
        [0.16, '#4cafdc'],
        [0.32, '#66c7c6'],
        [0.48, '#8adaa8'],
        [0.62, '#bae886'],
        [0.75, '#eeec6c'],
        [0.88, '#fec44f'],
        [0.95, '#fc8038'],
        [1.00, '#e3262a'],
    ]

    fig = go.Figure()

    fig.add_trace(
        go.Contour(
            x=lons,
            y=lats,
            z=norm_field,
            zmin=-100,
            zmax=80,
            ncontours=18,
            connectgaps=False,
            colorscale=geophysical_colorscale,
            contours=dict(coloring='fill', showlines=True, showlabels=False),
            line=dict(color='rgba(15, 23, 42, 0.55)', width=1.15, smoothing=1.0),
            colorbar=dict(
                orientation='h',
                y=-0.12,
                len=0.65,
                thickness=12,
                title=dict(text='Индекс гравитационного притяжения (-100 .. +80)', side='bottom'),
                tickvals=[-100, -50, 0, 40, 80],
            ),
            hovertemplate='Долгота: %{x:.1f}°E<br>Широта: %{y:.1f}°N<br>Индекс притяжения: %{z:+.1f}<extra></extra>',
            name='Поле притяжения РФ',
        )
    )

    for idx, line_pts in enumerate(FEDERAL_DISTRICT_LINES):
        fig.add_trace(
            go.Scatter(
                x=[pt[0] for pt in line_pts],
                y=[pt[1] for pt in line_pts],
                mode='lines',
                line=dict(color='rgba(255, 255, 255, 0.9)', width=1.4),
                hoverinfo='skip',
                showlegend=idx == 0,
                name='Границы округов РФ',
            )
        )

    fig.add_trace(
        go.Scatter(
            x=[37.6173],
            y=[55.7558],
            mode='markers+text',
            text=['MOW'],
            textposition='top left',
            textfont=dict(color='#0f172a', size=10.5),
            marker=dict(size=7, color='#0f172a', line=dict(width=1.5, color='#ffffff')),
            name='MOW (Москва)',
        )
    )

    fig.add_trace(
        go.Scatter(
            x=[bary_lon],
            y=[bary_lat],
            mode='markers',
            marker=dict(size=11, color='#facc15', symbol='diamond', line=dict(width=1.8, color='#78350f')),
            hovertemplate=f'<b>Барицентр сети</b><br>{bary_lat:.2f}°N, {bary_lon:.2f}°E<extra></extra>',
            name='Барицентр сети',
        )
    )

    for is_top in (False, True):
        subset = [c for c in scored_cities if c.is_top3 == is_top and c.iata in coordinates]
        fig.add_trace(
            go.Scatter(
                x=[coordinates[c.iata][1] for c in subset],
                y=[coordinates[c.iata][0] for c in subset],
                mode='markers+text',
                text=[c.iata for c in subset],
                textposition=[CITY_TEXT_POS.get(c.iata, 'top right') for c in subset],
                textfont=dict(color='#0f172a', size=10.5 if is_top else 9.5),
                marker=dict(
                    size=[max(8, min(15, int(5 + c.total_score * 0.1))) for c in subset],
                    color='#ef4444' if is_top else '#ffffff',
                    line=dict(width=1.6, color='#0f172a'),
                ),
                hovertext=[
                    f'<b>#{c.rank} · {c.city_name} ({c.iata})</b><br>Балл: {c.total_score:.2f}'
                    for c in subset
                ],
                hoverinfo='text',
                name='Топ-3 полюса' if is_top else 'Кандидаты',
            )
        )

    fig.update_layout(
        height=500,
        plot_bgcolor='#fdfbf0',
        paper_bgcolor='#fdfbf0',
        font=dict(color='#1e293b'),
        margin=dict(l=10, r=10, t=10, b=60),
        xaxis=dict(range=[27.5, 80.0], showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(
            range=[41.2, 70.5],
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            scaleanchor='x',
            scaleratio=1.45,
        ),
        legend=dict(orientation='h', y=1.04, x=0.0, bgcolor='rgba(253,251,240,0.85)'),
    )

    st.plotly_chart(fig, use_container_width=True)


def render_route_network_map(routes_df: pd.DataFrame, scored_cities: List[CityScoreDTO]) -> None:
    if routes_df.empty:
        st.info('Для этой сети пока нет маршрутов в витрине Dev 1.')
        return

    top_col1, top_col2 = st.columns([3, 3])
    view_mode = top_col1.radio(
        'Режим карты',
        ['routes', 'gravity'],
        format_func=lambda m: (
            '✈️ Маршруты и крюк через Москву (по умолчанию)'
            if m == 'routes'
            else '🌌 Гравитация (Изолинии поля притяжения)'
        ),
        horizontal=True,
        key='map_renderer_mode',
    )

    aircraft_key = top_col2.selectbox(
        '✈️ Тип ВС и фильтр дальности полёта',
        list(AIRCRAFT_SPECS.keys()),
        format_func=lambda k: f"{AIRCRAFT_SPECS[k]['name']} · до {AIRCRAFT_SPECS[k]['max_km']} км",
        key='aircraft_type_selector',
    )
    ac_spec = AIRCRAFT_SPECS[aircraft_key]
    st.caption(
        f"**{ac_spec['name']}**: оптимум плеча **{ac_spec['opt_low_km']}–{ac_spec['opt_high_km']} км**, "
        f"макс. практическая дальность **{ac_spec['max_km']} км**. {ac_spec['note']}."
    )

    if view_mode == 'gravity':
        _render_russia_gravity_map(routes_df, scored_cities)
    else:
        options = ['Все маршруты сети'] + routes_df['route_code'].tolist()
        names = {row.route_code: f'{row.origin_city} → {row.dest_city} · {row.route_code} ({row.distance_km:,.0f} км)' for row in routes_df.itertuples()}
        if 'map_focus' not in st.session_state or st.session_state['map_focus'] not in options:
            st.session_state['map_focus'] = routes_df['route_code'].iloc[0]

        focus_col, ring_col = st.columns([4, 2])
        focus = focus_col.selectbox(
            '🔍 Выберите маршрут (списком или кликом по точке маршрута на карте ниже)',
            options,
            format_func=lambda value: names.get(value, value),
            key='map_focus',
        )
        show_ring = ring_col.checkbox('Показать кольца дальности ВС на карте', value=True, key='show_ac_ring')

        figure = go.Figure()
        coordinates = _resolve_coordinates(routes_df)

        selected = None
        if focus != options[0]:
            selected = routes_df.loc[routes_df['route_code'] == focus].iloc[0]

        # 1. Кольца боевого радиуса и оптимума выбранного типа ВС вокруг аэропорта вылета
        if show_ring:
            ring_origin_iata = selected.origin_iata if selected is not None else routes_df.iloc[0].origin_iata
            if ring_origin_iata in coordinates:
                o_lat, o_lon = coordinates[ring_origin_iata]
                opt_lats, opt_lons = _geo_circle(o_lat, o_lon, ac_spec['opt_high_km'])
                max_lats, max_lons = _geo_circle(o_lat, o_lon, ac_spec['max_km'])
                figure.add_trace(
                    go.Scattergeo(
                        lat=opt_lats,
                        lon=opt_lons,
                        mode='lines',
                        line=dict(width=1.4, color='#059669', dash='dot'),
                        name=f"Оптимум ВС ({ac_spec['opt_high_km']} км из {ring_origin_iata})",
                        hoverinfo='name',
                    )
                )
                figure.add_trace(
                    go.Scattergeo(
                        lat=max_lats,
                        lon=max_lons,
                        mode='lines',
                        line=dict(width=1.5, color='#475569', dash='dash'),
                        name=f"Предел дальности ВС ({ac_spec['max_km']} км из {ring_origin_iata})",
                        hoverinfo='name',
                    )
                )

        # 2. Все линии маршрутов + кликабельные маркеры на середине каждого маршрута
        mid_lats, mid_lons, mid_codes, mid_texts, mid_colors = [], [], [], [], []
        for index, row in enumerate(routes_df.itertuples()):
            out_of_range = row.distance_km > ac_spec['max_km']
            line_color = '#dc2626' if out_of_range else '#3b82f6'
            figure.add_trace(
                go.Scattergeo(
                    lat=[row.lat_o, row.lat_d],
                    lon=[row.lon_o, row.lon_d],
                    mode='lines',
                    line=dict(width=1.6, color=line_color),
                    opacity=0.72,
                    text=f'{row.origin_city} → {row.dest_city}<br>{row.distance_km:,.0f} км · {row.flight_time_min:,.0f} мин',
                    hoverinfo='text',
                    name='Маршруты сети',
                    legendgroup='network',
                    showlegend=index == 0,
                )
            )
            mid_lats.append(0.5 * (row.lat_o + row.lat_d))
            mid_lons.append(0.5 * (row.lon_o + row.lon_d))
            mid_codes.append(row.route_code)
            mid_texts.append(
                f'<b>Кликните для выбора: {row.origin_city} → {row.dest_city} ({row.route_code})</b><br>'
                f'{row.distance_km:,.0f} км · {_classify_route_range(row.distance_km, ac_spec)}'
            )
            mid_colors.append('#dc2626' if out_of_range else '#2563eb')

        # Кликабельные точки на дугах маршрутов (позволяют выбрать маршрут прямым кликом на карте в Streamlit!)
        figure.add_trace(
            go.Scattergeo(
                lat=mid_lats,
                lon=mid_lons,
                customdata=mid_codes,
                mode='markers',
                marker=dict(size=9, color=mid_colors, symbol='diamond-open', line=dict(width=2, color=mid_colors)),
                hovertext=mid_texts,
                hoverinfo='text',
                name='Точки выбора маршрута (клик)',
            )
        )

        # 3. Выделенный маршрут и крюк через Москву
        if selected is not None:
            origin = (selected.lat_o, selected.lon_o)
            destination = (selected.lat_d, selected.lon_d)
            moscow = (55.7558, 37.6173)
            lats, lons = _dashed_leg(origin, moscow)
            lat2, lon2 = _dashed_leg(moscow, destination)
            figure.add_trace(go.Scattergeo(lat=lats + lat2, lon=lons + lon2, mode='lines',
                line=dict(width=2.2, color='#e11d48'), name=f'Через Москву · ×{selected.moscow_detour_ratio:.2f}',
                hoverinfo='name'))
            figure.add_trace(go.Scattergeo(lat=[moscow[0]], lon=[moscow[1]], mode='markers+text',
                marker=dict(size=8, color='#e11d48'), text=['Москва'], textposition='top left',
                name='Москва · пересадка', showlegend=False))
            figure.add_trace(go.Scattergeo(lat=[origin[0], destination[0]], lon=[origin[1], destination[1]],
                mode='lines', line=dict(width=3.4, color='#059669'),
                name=f'Напрямую · {selected.distance_km:,.0f} км / {selected.flight_time_min:,.0f} мин', hoverinfo='name'))

        mapped = [city for city in scored_cities if city.iata in coordinates]
        for top in (False, True):
            cities = [city for city in mapped if city.is_top3 == top]
            figure.add_trace(go.Scattergeo(lat=[coordinates[c.iata][0] for c in cities],
                lon=[coordinates[c.iata][1] for c in cities], mode='markers+text',
                text=[c.iata for c in cities],
                textposition=[CITY_TEXT_POS.get(c.iata, 'top right') for c in cities],
                marker=dict(size=12 if top else 8, color='#ef4056' if top else '#ffffff', line=dict(width=1.5, color='#0f172a')),
                hovertext=[f'#{c.rank} · {c.city_name} ({c.iata})<br>Балл: {c.total_score:.2f}<br>Население: {c.population_mln:.3f} млн<br>Поток аэропорта: {c.airport_pax_mln:.3f} млн' for c in cities],
                hoverinfo='text', name='Топ-3 скоринга' if top else 'Другие кандидаты'))

        figure.update_geos(lonaxis=dict(range=[30, 78]), lataxis=dict(range=[41.5, 62.5]),
            projection_type='mercator', showland=True, landcolor='#e7edf3',
            showocean=True, oceancolor='#c8ddeb', showcountries=True, countrycolor='#a1b4c4',
            showlakes=True, lakecolor='#c8ddeb', coastlinecolor='#8aa9c1', bgcolor='rgba(0,0,0,0)')
        figure.update_layout(height=560, margin=dict(l=0, r=0, t=10, b=10), legend=dict(orientation='h', y=-.04))

        event = st.plotly_chart(
            figure,
            use_container_width=True,
            config={'displaylogo': False, 'scrollZoom': True},
            on_select='rerun',
            selection_mode=('points',),
            key='interactive_routes_plotly',
        )
        # Обработка клика по маршруту прямо на карте Plotly
        if event and hasattr(event, 'selection') and event.selection and event.selection.get('points'):
            for pt in event.selection['points']:
                cdata = pt.get('customdata')
                if isinstance(cdata, str) and cdata in options and st.session_state.get('map_focus') != cdata:
                    st.session_state['map_focus'] = cdata
                    st.rerun()

        if len(mapped) < len(scored_cities):
            st.caption(f'Координаты доступны для {len(mapped)} из {len(scored_cities)} городов; остальные не нанесены на карту.')
        if selected is not None:
            direct, transit, railway, range_col = st.columns(4)
            direct.metric('Прямой рейс', _number(selected.flight_time_min, ' мин', 0))
            direct.caption(_number(selected.distance_km, ' км', 0))
            transit.metric('Плечо через Москву', _number(selected.moscow_detour_ratio, ' ×', 2))
            transit.caption('Коэффициент длины пути')
            railway.metric('Поезд', _number(selected.rail_travel_hours, ' ч'))
            railway.caption('Слабая конкуренция ж/д' if selected.rail_weak_competitor else 'Проверить конкуренцию ж/д')
            range_col.metric('Дальность ВС', _classify_route_range(float(selected.distance_km), ac_spec).split()[0])
            range_col.caption(_classify_route_range(float(selected.distance_km), ac_spec))
        st.caption('Карта соединяет города; это не трассы полётов. Геометрический крюк через Москву не доказывает наличие удобной стыковки или экономию заданного числа часов.')

    with st.expander('Рейтинг всех 12 городов'):
        ranking = pd.DataFrame([asdict(city) for city in scored_cities])
        st.dataframe(ranking.rename(columns={'rank': 'Место', 'city_name': 'Город', 'iata': 'IATA',
            'total_score': 'Балл', 'population_mln': 'Население, млн', 'airport_pax_mln': 'Поток аэропорта, млн'}),
            hide_index=True, use_container_width=True)
    st.subheader('Основания выбора маршрутов и проверка по дальности ВС')
    st.caption('pax — оценка Dev 1, а не наблюдённый спрос. Статус дальности проверяет плечо маршрута относительно выбранного типа самолёта.')
    table_df = routes_df.copy()
    table_df['aircraft_range_status'] = table_df['distance_km'].map(lambda d: _classify_route_range(float(d), ac_spec))
    labels = {'route_code': 'Код', 'origin_city': 'Откуда', 'dest_city': 'Куда', 'distance_km': 'Км',
        'aircraft_range_status': f"Статус дальности ({ac_spec['name'].split(' (')[0]})",
        'flight_time_min': 'Время, мин', 'moscow_detour_ratio': 'Крюк через Мск, ×',
        'rail_travel_hours': 'Поезд, ч', 'competitor_flights_weekly': 'Рейсов конкурентов/нед.',
        'own_flights_weekly': 'Рейсов RW/нед.', 'competitor_carriers': 'Конкуренты',
        'competitor_fare_rub': 'Тариф конкурентов, ₽', 'subsidy_eligible': 'Направление в ПП №1242',
        'launch_quarter': 'Квартал запуска (план)', 'freq': 'Частота витрины', 'pax': 'Поток Dev 1 (оценка)',
        'proof_source': 'Источник / метод оценки', 'route_code_source': 'Источник номера рейса'}
    st.dataframe(table_df[[c for c in labels if c in table_df]].rename(columns=labels),
                 hide_index=True, use_container_width=True)
    st.download_button('Скачать маршруты и источники · CSV', table_df.to_csv(index=False).encode('utf-8-sig'),
                       file_name='red_wings_routes.csv', mime='text/csv', key='download_routes')
