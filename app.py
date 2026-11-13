"""Red Wings dashboard: UI orchestration over the frozen Dev 1–3 contracts.

AI assistance: interface implementation, contract review and UI smoke checks.
No backend coefficients or data are rewritten by this module.
"""
import os
import warnings
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.ui.kpi_cards import (
    render_comparison_kpis, render_route_economics, render_fleet_stress,
    render_svx_kuf_comparison, render_assumptions_audit, render_network_graph_kpis,
)
from src.ui.map_renderer import render_network_lenses, render_route_network_map
from src.ui.roadmap_chart import render_sj100_roadmap
from src.ui.sidebar_controls import gravity_matrix_options, render_sidebar_controls

USE_MOCKS = os.getenv('USE_MOCKS', '0') == '1'
ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / 'src/scoring/reports/hub'

if USE_MOCKS:
    from src.mocks.mock_provider import evaluate_hypotheses, get_network_routes, get_scored_cities
else:
    from src.models.sj100_fleet import get_aircraft_gravity_knots
    from src.models.unit_economics import evaluate_hypotheses
    from src.parsers.build_dataset import get_network_routes
    from src.scoring.city_scorer import (
        calculate_gravity_matrix, calculate_network_graph_metrics, get_scored_cities, load_features,
    )


@st.cache_data(show_spinner=False)
def _load_report(path, modified_ns):
    """mtime participates in cache invalidation when teammates update reports."""
    return pd.read_csv(path)


def _report(filename):
    path = REPORTS / filename
    if not path.exists():
        st.info(f'Отчёт Dev 2 ещё не доступен: {filename}')
        return None
    return _load_report(str(path), path.stat().st_mtime_ns)


@st.cache_data(max_entries=32, show_spinner=False)
def _live_gravity(features, routes, aircraft_id, options):
    return calculate_gravity_matrix(
        features, routes, distance_knots_km=get_aircraft_gravity_knots(aircraft_id), **options,
    )


@st.cache_data(max_entries=32, show_spinner=False)
def _graph_metrics(features, routes, proposed_pairs, lam):
    return calculate_network_graph_metrics(features, routes, proposed_pairs, lam=lam)


def _render_scoring(cities, features=None, market_routes=None, aircraft_id=None, proposed_pairs=None):
    st.subheader('12 городов · текущий скоринг')
    table = pd.DataFrame([asdict(city) for city in cities])
    figure = go.Figure(go.Bar(x=table['total_score'], y=table['city_name'], orientation='h',
        marker_color=['#ef4056' if top else '#6796c9' for top in table['is_top3']],
        text=table['total_score'].round(1), textposition='outside'))
    figure.update_layout(height=420, yaxis_autorange='reversed', xaxis_title='Баллы скоринга', margin=dict(l=10, r=35, t=10, b=10))
    st.plotly_chart(figure, use_container_width=True)
    st.dataframe(table.rename(columns={'iata': 'IATA', 'city_name': 'Город', 'region': 'Регион',
        'rank': 'Место', 'is_top3': 'Топ-3', 'population_mln': 'Население, млн',
        'airport_pax_mln': 'Поток аэропорта, млн', 'total_score': 'Балл'}), hide_index=True, use_container_width=True)
    st.caption('Веса меняют рейтинг городов. Финансовая модель Dev 3 использует укрупнённые коэффициенты: изменение хаба само по себе не меняет EBITDAR гипотезы. Это ограничение модели, а не одинаковая экономика всех аэропортов.')
    if USE_MOCKS:
        st.info('ДЕМО: отчёты реального скоринга не смешиваются с синтетическими городами.')
        return
    st.subheader('Гравитация, охват аэропортов и узел-ножницы')
    options = gravity_matrix_options()
    matrix = _live_gravity(features, market_routes, aircraft_id, options)
    st.markdown('**Потенциал направлений «город → город»**')
    names = {city.iata: city.city_name for city in cities}
    figure = go.Figure(go.Heatmap(
        x=[f'{code} · {names.get(code, code)}' for code in matrix.columns],
        y=[f'{code} · {names.get(code, code)}' for code in matrix.index],
        z=matrix.to_numpy(), colorscale=[[0, '#f1f4f9'], [.4, '#6199d4'], [1, '#bd2548']],
        colorbar_title='Индекс', hovertemplate='%{y} → %{x}<br>Потенциал: %{z:.6g}<extra></extra>',
    ))
    figure.update_layout(height=580, xaxis_tickangle=-55, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(figure, use_container_width=True, key='live_gravity_matrix')
    st.caption(f'Параметры карты: {aircraft_id} · γ {options["gamma"]:.1f} · λ {options["lam"]:.2f} · '
               f'рейсы RW {"исключены" if options["exclude_existing_rw"] else "учтены"}. '
               'Цвет показывает относительный индекс потенциала.')
    render_network_graph_kpis(*_graph_metrics(features, market_routes, proposed_pairs, options['lam']))

    st.info('Справочные отчёты Dev 2 ниже используют исходные параметры. В отборе нового хаба SVX исключён.')
    gravity = _report('gravity_hub_potential.csv')
    if gravity is not None:
        live = table[['iata', 'rank', 'total_score']].rename(columns={'rank': 'Текущий ранг', 'total_score': 'Текущий балл'})
        merged = gravity.merge(live, on='iata', validate='one_to_one')
        st.markdown('**Обычный скоринг и гравитационная модель**')
        st.dataframe(merged[['city_name', 'iata', 'Текущий ранг', 'Текущий балл', 'gravity_rank_eligible', 'gravity_hub_potential', 'eligible']].rename(columns={
            'city_name': 'Город', 'gravity_rank_eligible': 'Ранг гравитации (новый хаб)',
            'gravity_hub_potential': 'Гравитационный потенциал', 'eligible': 'Допущен как новый хаб'}), hide_index=True, use_container_width=True)
    population = _report('effective_population.csv')
    if population is not None:
        st.markdown('**Охват аэропортов с учётом доступности**')
        figure = go.Figure()
        for field, label, color in [('population_mln', 'Население агломерации', '#93a4ba'),
                                    ('effective_population_mln', 'Эффективное население', '#ef4056')]:
            figure.add_bar(x=population['iata'], y=population[field], name=label, marker_color=color)
        figure.update_layout(height=330, barmode='group', yaxis_title='млн человек', legend_orientation='h')
        st.plotly_chart(figure, use_container_width=True)
        st.caption('Эффективное население учитывает сценарное время доезда и затухание доступности. Это не измеренные автомобильные изохроны и не отдельная оценка пассажиропотока.')
        with st.expander('Метод и источники охвата'):
            columns = [c for c in ['iata', 'city_name', 'population_city_mln', 'population_mln', 'effective_population_mln', 'agglomeration_members', 'source_rosstat'] if c in population]
            st.dataframe(population[columns], hide_index=True, use_container_width=True)
    scissor = _report('scissor_hub_index.csv')
    if scissor is not None:
        st.markdown('**Транзитный индекс · узел-ножницы**')
        st.dataframe(scissor.rename(columns={'city_name': 'Город', 'scissor_rank': 'Место',
            'scissor_hub_index': 'Транзитный индекс', 'eligible_undirected_pairs': 'Подходящих пар',
            'eligible': 'Допущен', 'exclusion_reason': 'Причина исключения'}), hide_index=True, use_container_width=True)
        st.caption('Геометрический потенциал стыковок по модели Dev 2. Для реального транзита дополнительно нужны согласованные волны, минимальное время стыковки и инфраструктура аэропорта.')


def main():
    st.set_page_config(page_title='Red Wings Strategy 2026–2028', page_icon='✈️', layout='wide')
    st.markdown('''<style>
    .block-container{max-width:1450px;padding-top:2rem}
    [data-testid="stMetric"]{border:1px solid #8b9db333;border-radius:14px;padding:16px}
    [data-testid="stMetricLabel"]{font-size:.85rem}
    [data-testid="stMetricValue"]{font-size:1.65rem}
    .rw-kicker{color:#ef4056;font-weight:700;letter-spacing:.16em;font-size:.8rem}
    .rw-subtitle{color:#8192a6;font-size:1rem;margin-bottom:1.5rem}
    </style><div class="rw-kicker">RED WINGS / STRATEGY LAB</div>''', unsafe_allow_html=True)
    st.title('Новый хаб или прямые рейсы?')
    st.markdown('<div class="rw-subtitle">108,9 млн перевозок · 12 городов-кандидатов · запуск до 2028 · горизонт стратегии 2030</div>', unsafe_allow_html=True)
    if USE_MOCKS:
        st.warning('ДЕМОНСТРАЦИОННЫЙ РЕЖИМ · Синтетические данные. Не использовать результаты как обоснование стратегии.')
    else:
        st.caption('Модули Dev 1–3 подключены. Источники, оценки и сценарные допущения раскрыты в соответствующих блоках.')
    weights, requested = render_sidebar_controls()
    with warnings.catch_warnings(record=True) as notices:
        warnings.simplefilter('always', UserWarning)
        cities = get_scored_cities(weights)
    if notices:
        st.caption('Предварительный скоринг · exploratory. Доля трансфера через Москву и часть проверок аэропортов отсутствуют; рейтинг опирается на четыре доступных критерия.')
        with st.expander('Статус исходных данных скоринга'):
            for notice in dict.fromkeys(str(item.message) for item in notices):
                st.write(notice)
    # Use the same feasible count in both strategies, the map and route-level P&L.
    # The provider currently returns ten pairs; never fabricate the missing 11th/12th.
    networks = {code: get_network_routes(code, hub_iata=requested.hub_iata) for code in ('p2p', 'hub')}
    count = min(requested.active_routes_count, *(len(frame) for frame in networks.values()))
    if count < 1:
        st.error('Нет маршрутов для сопоставимого расчёта обеих гипотез. Проверьте витрину Dev 1.')
        return
    params = replace(requested, active_routes_count=count)
    if count < requested.active_routes_count:
        st.info(f'Выбрано {requested.active_routes_count} маршрутов; провайдер позволяет сравнить {count}. Сравнение гипотез и очереди запуска используют {count}.')
    comparison = evaluate_hypotheses(params, cities)
    selected = st.radio('Сеть для очередей запуска', ['p2p', 'hub'],
        index=0 if comparison.winner == 'p2p' else 1,
        format_func=lambda code: 'Б · Прямые рейсы' if code == 'p2p' else f'А · Хаб {params.hub_iata}',
        horizontal=True, key='display_network')
    routes = networks[selected].head(count).copy()
    st.caption(f'Расчётная сеть: {count} пар городов · {params.weekly_freq_per_route} пар рейсов/неделю на маршрут · {count * params.weekly_freq_per_route * 2 * 52:,} вылетов в год. Лидер модели: {comparison.winner.upper()}.')
    battle, network, scoring, cannibalization, roadmap = st.tabs([
        '💰 Битва гипотез', '🗺️ Три линзы карты',
        '🏆 Скоринг и транзит', '🧭 KUF vs SVX', '🚀 Дорожная карта и путь к №2'])
    with battle:
        stress = render_fleet_stress(params, networks['p2p'].head(count).copy())
        st.divider()
        st.subheader('Сравнение полной сети · без ресурсного лимита')
        st.caption('Карточки ниже — исходная модель обеих гипотез при заданном сценарии рынка. Лимит бортов и ручной секвестр применяются к отдельному стресс-тесту выше; Монте-Карло самостоятельно разыгрывает уровень субсидий.')
        render_comparison_kpis(comparison, params, cities)
        render_route_economics(params, networks['p2p'].head(count).copy(), stress)
        render_assumptions_audit(params, float(100 - st.session_state.get('subsidy_cut_pct', 0)))
    with network:
        if USE_MOCKS:
            render_route_network_map(routes, cities)
        else:
            features = load_features()
            market_routes = pd.read_parquet(ROOT / 'data/processed/routes_proof.parquet')
            aircraft_id, proposed_pairs = render_network_lenses(features, market_routes, cities, params)
    with scoring:
        if USE_MOCKS:
            _render_scoring(cities)
        else:
            _render_scoring(cities, features, market_routes, aircraft_id, proposed_pairs)
    with cannibalization:
        render_svx_kuf_comparison(params, cities)
    with roadmap:
        st.caption(f'Очереди запуска: {selected.upper()}; график потребности пилота: лидер {comparison.winner.upper()}. Волны федерального роста ниже рассчитаны моделью P2P.')
        render_sj100_roadmap(routes, comparison, params, cities)
    st.divider()
    st.caption('Red Wings · Кейс «Связанность территорий». Результаты сценарные; окончательное решение требует проверки спроса, расписания, флота и условий субсидирования.')


if __name__ == '__main__':
    main()
