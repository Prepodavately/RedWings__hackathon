"""Financial views. All real calculations are delegated to Dev 3."""
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.schemas.contracts import CityScoreDTO, ComparisonBundleDTO, FinModelInput

P2P_COLOR = '#ef4056'
HUB_COLOR = '#548bff'


def render_comparison_kpis(comparison: ComparisonBundleDTO,
        fin_input: FinModelInput | None = None,
        scored_cities: list[CityScoreDTO] | None = None) -> None:
    winner = getattr(comparison, comparison.winner)
    banner = st.success if winner.ebitdar_mln_rub >= 0 else st.warning
    verdict = 'Лидер в текущем сценарии' if winner.ebitdar_mln_rub >= 0 else 'Меньший убыток; запуск пока не обоснован'
    banner(f'{verdict}: {winner.title}. {comparison.rationale}')
    st.caption('Сравнение двух гипотез при одинаковом числе маршрутов и заданной частоте. EBITDAR — результат до процентов, налогов, амортизации и аренды; это не чистая прибыль.')
    columns = st.columns(2)
    for column, result, other in zip(columns, [comparison.p2p, comparison.hub], [comparison.hub, comparison.p2p]):
        with column:
            st.subheader('Б · Прямые рейсы' if result.code == 'p2p' else 'А · Региональный хаб')
            st.metric('Пассажиропоток в год', f'{result.annual_passengers / 1000:,.1f} тыс.',
                      f'{(result.annual_passengers - other.annual_passengers) / 1000:+,.1f} тыс.')
            st.metric('Выручка с субсидиями', f'{result.annual_revenue_mln_rub:,.1f} млн ₽',
                      f'{result.annual_revenue_mln_rub - other.annual_revenue_mln_rub:+,.1f} млн ₽')
            st.metric('EBITDAR', f'{result.ebitdar_mln_rub:,.1f} млн ₽',
                      f'{result.ebitdar_mln_rub - other.ebitdar_mln_rub:+,.1f} млн ₽')
            st.caption(f'Маржа EBITDAR: {result.ebitdar_margin_pct:.1f}%')
            st.metric('Прирост доли рынка РФ', f'{result.market_share_delta_pct:+.3f} п.п.',
                      f'{result.market_share_delta_pct - other.market_share_delta_pct:+.3f} п.п.')
            st.metric('Безубыточная загрузка · BELF', f'{result.breakeven_load_factor_pct:.1f}%',
                      f'{result.breakeven_load_factor_pct - other.breakeven_load_factor_pct:+.1f} п.п.', delta_color='inverse')
            st.metric('Потребный флот SJ-100', f'{result.required_aircraft_sj100} бортов',
                      f'{result.required_aircraft_sj100 - other.required_aircraft_sj100:+d}', delta_color='inverse')
    st.caption('Дельты — относительно второй гипотезы. Доля рынка считается от фиксированных 108,9 млн перевозок. Загрузка меняется в модели с тарифом и сценарием; значение ползунка — входная цель.')
    figure = go.Figure()
    for label, values, color in [
        ('Выручка', [r.annual_revenue_mln_rub for r in (comparison.p2p, comparison.hub)], '#548bff'),
        ('Операционные расходы', [r.annual_revenue_mln_rub - r.ebitdar_mln_rub for r in (comparison.p2p, comparison.hub)], '#93a4ba'),
        ('EBITDAR', [r.ebitdar_mln_rub for r in (comparison.p2p, comparison.hub)], P2P_COLOR),
    ]:
        figure.add_bar(name=label, x=['P2P', 'Хаб'], y=values, marker_color=color)
    figure.update_layout(barmode='group', yaxis_title='млн ₽ / год', height=360, legend_orientation='h')
    st.plotly_chart(figure, use_container_width=True)
    if fin_input is None or scored_cities is None:
        return
    if os.getenv('USE_MOCKS', '0') == '1':
        st.info('ДЕМО: эластичность и цифровизация Dev 3 доступны в режиме USE_MOCKS=0.')
        return
    from src.models.unit_economics import evaluate_digital_one_click_impact, simulate_fare_elasticity_curve
    st.subheader('Чувствительность к цене билета')
    curve = pd.DataFrame(simulate_fare_elasticity_curve(fin_input, scored_cities))
    figure = go.Figure()
    for code, title, color in [('p2p', 'P2P', P2P_COLOR), ('hub', 'Хаб', HUB_COLOR)]:
        figure.add_scatter(x=curve['fare_rub'], y=curve[f'{code}_ebitdar_mln_rub'],
                           mode='lines+markers', name=title, line=dict(color=color, width=3))
    figure.add_vline(x=fin_input.avg_fare_rub, line_dash='dot', annotation_text='Текущий тариф')
    figure.add_hline(y=0, line_color='#93a4ba', line_dash='dot')
    figure.update_layout(xaxis_title='Средний тариф OW, ₽', yaxis_title='EBITDAR, млн ₽', height=350)
    st.plotly_chart(figure, use_container_width=True)
    st.caption('Ценовая эластичность — сценарная зависимость Dev 3, не оценка на транзакциях авиакомпании.')
    st.subheader('Цифровые сервисы · «В один клик»')
    controls = st.columns(3)
    flags = [col.checkbox(label, value=True, key=key) for col, label, key in zip(controls,
        ['Virtual Interline · стыковки', 'One-Click Ancillary · допуслуги', 'Auto-Disruption Recovery · сбои'],
        ['digital_interline', 'digital_ancillary', 'digital_recovery'])]
    impact = evaluate_digital_one_click_impact(fin_input, scored_cities,
        enable_virtual_interline=flags[0], enable_one_click_ancillary=flags[1], enable_auto_disruption_recovery=flags[2])
    base, digital = impact['p2p_base'], impact['p2p_digital']
    left, right = st.columns(2)
    left.metric('Дополнительный EBITDAR P2P', f"{impact['total_ebitdar_uplift_mln_rub']:+,.1f} млн ₽")
    right.metric('BELF с цифровыми сервисами', f"{digital['breakeven_load_factor_pct']:.1f}%",
                 f"{digital['breakeven_load_factor_pct'] - base['breakeven_load_factor_pct']:+.1f} п.п.", delta_color='inverse')
    st.caption(impact['assumptions'])
    st.caption('Эффект показан отдельно поверх P2P и не добавлен к карточкам базового сравнения. BELF в контракте ограничен диапазоном модели.')
    with st.expander('Разложение эффекта цифровизации'):
        st.dataframe(pd.DataFrame({'Сервис': ['Virtual Interline', 'One-Click Ancillary', 'Auto-Disruption Recovery'],
            'Прирост EBITDAR, млн ₽': list(impact['ebitdar_uplift_mln_rub'].values())}), hide_index=True, use_container_width=True)
        st.caption(f"BELF без ограничения диапазона: {impact['digital_belf_unclipped_pct']:.1f}%. Все эффекты требуют проверки пилотом.")


def render_route_economics(fin_input: FinModelInput, routes_df: pd.DataFrame) -> None:
    """Additional P2P route P&L, kept separate from the aggregate hypothesis model."""
    if os.getenv('USE_MOCKS', '0') == '1' or routes_df.empty:
        return
    from src.models.unit_economics import evaluate_route_level_economics
    st.subheader('Проверка маршрутов P2P без субсидий')
    st.caption('Отдельная помаршрутная модель Dev 3 с затратами по расстоянию. Её суммы могут отличаться от укрупнённых карточек выше. Каждая строка — пара рейсов туда и обратно.')
    retention = st.slider('Сохранение сценарной субсидии, %', 0, 100, 100, 10, key='subsidy_retention')
    result = evaluate_route_level_economics(fin_input, routes_df, subsidy_retention_pct=float(retention))
    left, right = st.columns(2)
    left.metric('EBITDAR при выбранной поддержке', f"{result['total_ebitdar_mln_rub']:,.1f} млн ₽")
    right.metric('EBITDAR без субсидий', f"{result['total_ebitdar_no_subsidy_mln_rub']:,.1f} млн ₽")
    rows = pd.DataFrame(result['routes_pnl'])
    # Dev 1 pax is directional; the backend's demand comparison is not a bidirectional demand cap.
    rows = rows.drop(columns=['scenario_exceeds_dev1_demand'], errors='ignore')
    labels = {
        'route_code': 'Код', 'origin_iata': 'Откуда', 'dest_iata': 'Куда',
        'distance_km': 'Км', 'weekly_round_trips': 'Пар/нед.',
        'annual_passengers': 'Перевозки в год (сценарий)',
        'effective_load_factor_pct': 'Расчётная загрузка, %',
        'effective_fare_rub': 'Расчётный тариф OW, ₽',
        'annual_revenue_mln_rub': 'Выручка, млн ₽',
        'annual_cost_mln_rub': 'Расходы, млн ₽',
        'annual_subsidy_mln_rub': 'Субсидия (допущение), млн ₽',
        'ebitdar_mln_rub': 'EBITDAR, млн ₽',
        'ebitdar_no_subsidy_mln_rub': 'EBITDAR без субсидий, млн ₽',
        'belf_no_subsidy_pct': 'BELF без субсидий, %',
        'dev1_estimated_passengers': 'Оценка Dev 1 (одно направление)',
        'proof_source': 'Источник / метод оценки',
    }
    st.dataframe(rows[list(labels)].rename(columns=labels), hide_index=True, use_container_width=True)
    with st.expander('Полный помаршрутный расчёт Dev 3'):
        st.dataframe(rows, hide_index=True, use_container_width=True)
    st.caption('Возможность субсидирования направления не подтверждает субсидию Red Wings. pax Dev 1 — оценка одного направления; загрузка финансовой модели не ограничена подтверждённым спросом.')
