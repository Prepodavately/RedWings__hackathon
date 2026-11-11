"""Scenario switching, staged network rollout and fleet-constrained growth."""
import os
from dataclasses import replace

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.schemas.contracts import CityScoreDTO, ComparisonBundleDTO, FinModelInput


@st.cache_data(show_spinner=False)
def _switching_grid(params, cities, mocks):
    if mocks:
        from src.mocks.mock_provider import evaluate_hypotheses
    else:
        from src.models.unit_economics import evaluate_hypotheses
    differences, labels = [], []
    for fare in range(6000, 12001, 1000):
        diff_row, label_row = [], []
        for frequency in range(2, 11):
            result = evaluate_hypotheses(replace(params, weekly_freq_per_route=frequency, avg_fare_rub=float(fare)), cities)
            delta = result.p2p.ebitdar_mln_rub - result.hub.ebitdar_mln_rub
            both_negative = max(result.p2p.ebitdar_mln_rub, result.hub.ebitdar_mln_rub) < 0
            diff_row.append(delta)
            label_row.append(f'{result.winner.upper()}{"*" if both_negative else ""}<br>{delta:+.0f}')
        differences.append(diff_row)
        labels.append(label_row)
    return differences, labels


def render_sj100_roadmap(routes_df: pd.DataFrame, comparison: ComparisonBundleDTO,
        fin_input: FinModelInput | None = None, scored_cities: list[CityScoreDTO] | None = None) -> None:
    mocks = os.getenv('USE_MOCKS', '0') == '1'
    if fin_input is not None and scored_cities is not None:
        st.subheader('Где побеждает P2P, а где хаб')
        differences, labels = _switching_grid(fin_input, scored_cities, mocks)
        bound = max(1.0, max(abs(value) for row in differences for value in row))
        figure = go.Figure(go.Heatmap(x=list(range(2, 11)), y=list(range(6000, 12001, 1000)),
            z=differences, text=labels, texttemplate='%{text}',
            colorscale=[[0, '#548bff'], [.5, '#f1f4f9'], [1, '#ef4056']], zmin=-bound, zmax=bound,
            colorbar_title='Δ EBITDAR<br>млн ₽',
            hovertemplate='Частота: %{x} пар/нед.<br>Тариф: %{y} ₽<br>P2P − хаб: %{z:.1f} млн ₽<extra></extra>'))
        figure.update_layout(height=430, xaxis_title='Пар рейсов на маршрут в неделю', yaxis_title='Тариф OW, ₽')
        st.plotly_chart(figure, use_container_width=True)
        st.caption('* Обе гипотезы убыточны: подпись указывает меньший убыток. Красный — преимущество P2P, синий — хаба. Остальные параметры взяты из боковой панели.')
    st.subheader('Очереди запуска сети')
    if not routes_df.empty and 'launch_quarter' in routes_df:
        counts = routes_df.groupby('launch_quarter').size()
        def quarter_key(value):
            parts = str(value).replace('-', ' ').split()
            year = next((int(p) for p in parts if p.isdigit() and len(p) == 4), 9999)
            quarter = next((int(p[1:]) for p in parts if p.startswith('Q') and p[1:].isdigit()), 0)
            return year, quarter
        periods = sorted(counts.index, key=quarter_key)
        figure = go.Figure(go.Bar(x=periods, y=counts.reindex(periods), marker_color='#ef4056',
                                  text=counts.reindex(periods), textposition='outside'))
        figure.update_layout(height=290, yaxis_title='Количество маршрутов', yaxis_dtick=1)
        st.plotly_chart(figure, use_container_width=True)
    st.markdown('**Q3 2026:** направления присутствия RW, действующий парк. **Q2 2027:** выход на пары с присутствием конкурентов. **Q1 2028:** новые направления после начала поставок SJ-100.')
    st.caption('Кварталы — очереди из витрины, а не факт запуска. Прошедшие сроки требуют актуализации. Рейсы конкурентов показывают предложение, но не подтверждают объём спроса. До 2027-H2 новые SJ-100 не закладываются.')
    if mocks:
        st.info('ДЕМО: график поставок и волны до 2030 года показываются только с реальным модулем Dev 3.')
        return
    from src.models.sj100_fleet import build_sj100_delivery_roadmap
    result = getattr(comparison, comparison.winner)
    st.subheader('Потребность и план доступности флота')
    roadmap = pd.DataFrame(build_sj100_delivery_roadmap(result.required_aircraft_sj100, fin_input.scenario if fin_input else 'base'))
    figure = go.Figure()
    for field, title, color in [('existing_ssj_reserve_allocated', 'Резерв действующего SSJ', '#93a4ba'),
                               ('new_sj100_delivered_cumulative', 'Новые SJ-100 (сценарий)', '#ef4056')]:
        figure.add_bar(x=roadmap['quarter'], y=roadmap[field], name=title, marker_color=color)
    figure.add_hline(y=result.required_aircraft_sj100, line_dash='dot', annotation_text='Потребность выбранного лидера')
    figure.update_layout(barmode='stack', height=340, yaxis_title='Бортов', legend_orientation='h')
    st.plotly_chart(figure, use_container_width=True)
    st.caption('График Dev 3 — плановое допущение, не подтверждённые поставки. Резерв SSJ требует согласования; новые борта замещают его без двойного счёта. Потребность — укрупнённая оценка, без проверки расписания и ТО.')
    if fin_input is None or scored_cities is None:
        return
    from src.models.unit_economics import project_path_to_top2_airline
    st.subheader('Путь к №2 · целевой масштаб и ограничение флота')
    waves = pd.DataFrame(project_path_to_top2_airline(fin_input, scored_cities))
    # Baseline is an existing network, so the new-fleet constraint is not applied to it.
    constrained = waves['fleet_constrained_total_pax_mln'].fillna(waves['total_pax_mln'])
    figure = go.Figure()
    figure.add_scatter(x=waves['period'], y=waves['total_pax_mln'], name='Расчёт без лимита флота',
                       mode='lines+markers', line=dict(color='#93a4ba', dash='dash'))
    figure.add_scatter(x=waves['period'], y=constrained, name='С учётом выделенного флота',
                       mode='lines+markers', line=dict(color='#ef4056', width=4))
    figure.update_layout(height=350, yaxis_title='Пассажиропоток, млн / год', legend_orientation='h')
    st.plotly_chart(figure, use_container_width=True)
    labels = {'period': 'Период', 'title': 'Волна', 'routes_count': 'Маршрутов',
        'fleet_total': 'Выделено бортов', 'fleet_required_model': 'Нужно бортов', 'fleet_gap': 'Дефицит бортов',
        'total_pax_mln': 'Поток без лимита, млн', 'fleet_constrained_total_pax_mln': 'Поток с лимитом, млн',
        'weekly_freq_per_route': 'Пар/нед.', 'fleet_constrained_market_share_pct': 'Доля с лимитом, %'}
    st.dataframe(waves[list(labels)].rename(columns=labels), hide_index=True, use_container_width=True)
    max_gap = int(waves['fleet_gap'].fillna(0).max())
    if max_gap:
        st.warning(f'В сценарии не хватает до {max_gap} бортов. Расчётный поток без лимита флота нельзя считать обеспеченным прогнозом.')
    st.info('База 4,465 млн пассажиров, рынок 108,9 млн, пороги конкурентов и смешанный флот — входные допущения командной модели. Выход на №2 не доказан: нужны единый период статистики, полный рейтинг и динамика конкурентов, подтверждение спроса и поставок.')
    st.caption('Волны 2028–2030 — масштабирование P2P с цифровизацией. Финансовый эффект старой сети в расчёт новой сети не включён; модель SJ-100 переносится на смешанный флот приближённо. Квартальный запуск и годовой темп не следует суммировать.')
    st.download_button('Скачать волны развития · CSV', waves.to_csv(index=False).encode('utf-8-sig'),
                       'red_wings_growth_waves.csv', 'text/csv', key='download_waves')
