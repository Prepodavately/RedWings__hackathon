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
    if fin_input is not None and scored_cities is not None:
        render_financial_monte_carlo(fin_input, scored_cities)
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


def render_route_economics(fin_input: FinModelInput, routes_df: pd.DataFrame, result: dict | None = None) -> None:
    """Additional P2P route P&L, kept separate from the aggregate hypothesis model."""
    if os.getenv('USE_MOCKS', '0') == '1' or routes_df.empty:
        return
    from src.models.unit_economics import evaluate_route_level_economics
    st.subheader('Помаршрутный P&L выбранного ядра P2P')
    st.caption('Отдельная помаршрутная модель Dev 3 с затратами по расстоянию. Её суммы могут отличаться от укрупнённых карточек выше. Каждая строка — пара рейсов туда и обратно.')
    if result is None:
        result = evaluate_route_level_economics(fin_input, routes_df)
    left, right = st.columns(2)
    left.metric('EBITDAR при выбранной поддержке', f"{result['total_ebitdar_mln_rub']:,.1f} млн ₽")
    right.metric('EBITDAR без субсидий', f"{result['total_ebitdar_no_subsidy_mln_rub']:,.1f} млн ₽")
    if not result['routes_pnl']:
        st.info('Ядро пустое: при этих условиях маршруты не отобраны. Расчёт не запущенной сети равен нулю, это не доказательство безубыточной работы.')
        return
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


def _five_aircraft_without_subsidies():
    """Change resource limits only; preserve the user's commercial assumptions."""
    st.session_state['available_aircraft_2028'] = 5
    st.session_state['subsidy_cut_pct'] = 100


def render_fleet_stress(fin_input: FinModelInput, routes_df: pd.DataFrame):
    st.subheader('Стресс-тест · ограниченный флот и секвестр субсидий')
    mocks = os.getenv('USE_MOCKS', '0') == '1'
    left, right = st.columns(2)
    available = left.slider('Доступно бортов SJ-100 к 2028 г.', 3, 15, 15,
                            key='available_aircraft_2028', disabled=mocks)
    cut = right.slider('Секвестр госсубсидий ПП №1242, %', 0, 100, 0, 10,
                       key='subsidy_cut_pct', disabled=mocks)
    st.button('Показать: 5 бортов · 0 ₽ субсидий', key='preset_five_no_subsidy',
              on_click=_five_aircraft_without_subsidies, disabled=mocks)
    st.caption('Секвестр 100% = субсидии отменены; 0% = ставка модели сохранена. Кнопка меняет только эти два ограничения, сохраняя тариф, загрузку и частоту. Ограничения действуют на блок ядра сети и его помаршрутный расчёт.')
    if mocks:
        st.info('ДЕМО: ресурсный стресс требует реального модуля Dev 3; численные результаты здесь не имитируются.')
        return None
    from src.models.unit_economics import evaluate_route_level_economics
    result = evaluate_route_level_economics(fin_input, routes_df,
        subsidy_retention_pct=float(100 - cut), available_aircraft_limit=available)
    hub = result['classic_hub_reference']
    metrics = hub['metrics']
    p2p_column, hub_column = st.columns(2)
    p2p_column.metric('Ядро P2P · EBITDAR', f"{result['total_ebitdar_mln_rub']:+,.1f} млн ₽")
    p2p_column.caption(f"Отобрано {result['selected_routes_count']} из {len(routes_df)} пар; нужно {result['required_aircraft_sj100']} из {available} бортов.")
    hub_column.metric('Хаб при том же лимите · EBITDAR',
                      f"{metrics['ebitdar_mln_rub']:+,.1f} млн ₽" if metrics else 'Не запускается')
    hub_column.caption(f"Поддерживается {hub['supported_routes_count']} из {len(routes_df)} лучей. Это укрупнённый хабовый расчёт Dev 3, не оптимизация расписания.")
    profit = result['total_ebitdar_mln_rub']
    if not result['operations_started']:
        st.warning('При этих ограничениях P2P-сеть не запускается: положительный вклад маршрутов или необходимый флот отсутствует.')
    elif profit > 0 and metrics and metrics['ebitdar_mln_rub'] < 0:
        st.success('При текущих допущениях ядро P2P прибыльно, а доступный хабовый сценарий убыточен.')
    elif profit > 0:
        st.info('Ядро P2P прибыльно. Вывод о хабе проверяйте по его результату выше: преимущество не фиксируется заранее.')
    else:
        st.warning('Ядро P2P не покрывает расходы при выбранных условиях. Положительный результат не гарантирован.')
    if not hub['full_requested_network_supported']:
        st.caption('Полная запрошенная хабовая сеть не помещается в лимит флота; уменьшенный хаб показан отдельно. Возможность организации стыковок не подтверждена.')
    st.caption('P2P отбирает маршруты с положительным вкладом по маржинальности, затем учитывает все 115 млн ₽ постоянных расходов. Это эвристический отбор, не доказанный максимум прибыли. Хаб и P2P используют разные модели затрат Dev 3.')
    with st.expander('Состав ядра и исключённые направления'):
        for title, rows in [('Ядро P2P', result['routes_pnl']), ('Исключённые маршруты', result['excluded_routes'])]:
            st.markdown(f'**{title}**')
            if rows:
                frame = pd.DataFrame(rows)
                st.dataframe(frame[['origin_iata', 'dest_iata', 'contribution_margin_pct', 'contribution_mln_rub']].rename(columns={
                    'origin_iata': 'Откуда', 'dest_iata': 'Куда', 'contribution_margin_pct': 'Маржинальность до постоянных затрат, %',
                    'contribution_mln_rub': 'Вклад до постоянных затрат, млн ₽'}), hide_index=True, use_container_width=True)
            else:
                st.caption('Нет маршрутов.')
    return result


@st.cache_data(show_spinner=False)
def _financial_monte_carlo(fin_input, scored_cities):
    from src.models.unit_economics import run_financial_monte_carlo
    return run_financial_monte_carlo(fin_input, scored_cities, n_samples=1000, seed=42)


def render_financial_monte_carlo(fin_input: FinModelInput, scored_cities: list[CityScoreDTO]):
    st.subheader('Финансовый Монте-Карло · 1000 стресс-сценариев спроса, субсидий и керосина')
    if os.getenv('USE_MOCKS', '0') == '1':
        st.info('ДЕМО: вероятности Монте-Карло доступны только с реальным модулем Dev 3.')
        return
    result = _financial_monte_carlo(fin_input, scored_cities)
    left, right = st.columns(2)
    left.metric('P2P · P(EBITDAR > 0)', f"{result['p2p_prob_positive_ebitdar_pct']:.1f}%")
    right.metric('Хаб · P(EBITDAR > 0)', f"{result['hub_prob_positive_ebitdar_pct']:.1f}%")
    rows = []
    figure = go.Figure()
    for code, label, color in [('p2p', 'P2P', P2P_COLOR), ('hub', 'Хаб', HUB_COLOR)]:
        values = result[f'{code}_ebitdar_p5_p50_p95']
        rows.append({'Гипотеза': label, 'P5, млн ₽': values[0], 'Медиана, млн ₽': values[1], 'P95, млн ₽': values[2]})
        figure.add_bar(x=['P5', 'Медиана', 'P95'], y=values, name=label, marker_color=color)
    figure.add_hline(y=0, line_dash='dot', line_color='#93a4ba')
    figure.update_layout(barmode='group', height=320, yaxis_title='EBITDAR, млн ₽ / год', legend_orientation='h')
    st.plotly_chart(figure, use_container_width=True)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption('Независимый стресс полной сети с параметрами боковой панели. Лимит бортов и ручной секвестр из блока ядра здесь не применяются: функция Dev 3 сама разыгрывает субсидии от 0 до 100%. Рост цены керосина представлен общим множителем переменных расходов, без отдельной топливной модели.')
    st.caption('Это доля прибыльных исходов при заданных распределениях, не вероятность, измеренная по истории. P5/P95 — квантили EBITDAR, не доверительный интервал вероятности. Одинаковые шоки применяются к обеим стратегиям; seed=42 обеспечивает воспроизводимость.')
    with st.expander('Распределения и параметры финансового стресса'):
        st.markdown('Загрузка: **−12…+4 п.п.**; тариф: **85…105%** исходного; переменные расходы: **100…120%**; сохранение субсидий: **0…100%**. Факторы независимые, равномерные.')
        st.json(result['assumptions'])


def render_svx_kuf_comparison(fin_input: FinModelInput, scored_cities: list[CityScoreDTO]):
    st.subheader('Самара (KUF) vs база Екатеринбург (SVX) · проверка каннибализации')
    if os.getenv('USE_MOCKS', '0') == '1':
        st.info('ДЕМО: сравнение KUF/SVX требует модулей Dev 1–3.')
        return
    from src.models.unit_economics import evaluate_svx_kuf_cannibalization
    result = evaluate_svx_kuf_cannibalization(fin_input, scored_cities)
    rows = []
    for key, title in [('classic_hub', 'Классический хаб KUF'), ('scissor_hybrid', 'Узел-ножницы KUF')]:
        item = result[key]
        rows.append({'Архитектура': title, 'EBITDAR новой сети, млн ₽': item['ebitdar_mln_rub'],
            'Отвлечение транзита SVX (допущение), %': item['svx_cannibalization_pct'],
            'Потеря маржи SVX, млн ₽': item['svx_margin_loss_mln_rub'],
            'Новая сеть минус потеря SVX, млн ₽': item['net_ebitdar_after_svx_cannibalization_mln_rub']})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.info('Отсутствие каннибализации не доказано. В модели заложены 15% для классического хаба и 2,5% для узла-ножниц; маржинальный пул SVX — 1000 млн ₽. Это даёт потери 150 и 25 млн ₽, а не фактическую отчётность базы.')
    geometry = pd.DataFrame(result['corridor_routes'])
    geometry['Проверка коридора'] = (geometry['svx_detour_pct'] > 40) & geometry['kuf_passes_15pct_detour']
    st.markdown('**Какие пары действительно подходят для обмена пассажирами в KUF**')
    st.dataframe(geometry[['origin_iata', 'dest_iata', 'svx_detour_pct', 'kuf_detour_pct', 'kuf_passes_15pct_detour', 'Проверка коридора']].rename(columns={
        'origin_iata': 'Откуда', 'dest_iata': 'Куда', 'svx_detour_pct': 'Крюк через SVX, %',
        'kuf_detour_pct': 'Крюк через KUF, %', 'kuf_passes_15pct_detour': 'KUF: крюк <15%'}), hide_index=True, use_container_width=True)
    st.caption(f"Из {len(geometry)} проверенных пар {result['geometrically_supported_kuf_routes_count']} проходят порог KUF <15%; одновременно SVX >40% и KUF <15% — {int(geometry['Проверка коридора'].sum())}. В выборке Dev 3 есть и Пермь, поэтому это не исключительно меридиан «Поволжье ↔ Юг». Геометрия не измеряет переток пассажиров.")
    left, right = st.columns(2)
    left.metric('Новая база ТОиР KUF · CAPEX', f"{result['scissor_new_base_capex_mln_rub']:.0f} млн ₽")
    right.metric('Постоянные расходы узла-ножниц', f"{result['scissor_total_fixed_cost_mln_rub']:.0f} млн ₽ / год")
    st.caption('Нулевой CAPEX новой базы ТОиР — проектное допущение; остальные инвестиции не оценены. Операционные расходы сети и координации сохранены. Этот блок оценивает полную сеть с отдельным фиксированным хабом KUF, независимо от выбора хаба на карте, лимита бортов и ручного секвестра.')
    feeder = result['feeder']
    st.caption(f"Фидер {feeder['flight_code']} · SVX → KUF: {feeder['observed_weekly_flights']} рейсов/неделю по витрине Dev 1. Возможный подвоз не добавлен в выручку без оценки спроса.")
    with st.expander('Источники и ограничения сравнения KUF/SVX'):
        st.write(feeder['source'])
        st.json(result['assumptions'])


def render_assumptions_audit(fin_input: FinModelInput, subsidy_retention_pct: float):
    with st.expander('Прозрачность допущений и проверка по действующим рейсам Red Wings (WZ-*)'):
        if os.getenv('USE_MOCKS', '0') == '1':
            st.info('ДЕМО: аудит фактических расписаний отключён, чтобы не смешивать их с синтетическими данными.')
            return
        import json
        from pathlib import Path
        from src.models.unit_economics import get_assumptions_audit_table, evaluate_route_level_economics
        audit = get_assumptions_audit_table()
        assumption = next(row for row in audit['assumptions'] if row['assumption'] == 'sj100_distance_cost')
        coefficients = assumption['value']
        st.markdown('**Стоимость одного плеча SJ-100, базовая формула**')
        st.code(f"C_плеча = {coefficients['fixed_rub']:,.0f} ₽ + {coefficients['rub_per_km']:,.0f} ₽/км × расстояние_км", language=None)
        st.caption('Помаршрутная модель дополнительно умножает стоимость на коэффициент сценария и кресла/100; постоянные 115 млн ₽/год учитываются отдельно, один раз на выбранную сеть.')
        st.warning('Проверены происхождение расписаний и сопоставление маршрутов. Эмпирическая калибровка себестоимости пока невозможна: фактических затрат Red Wings в данных нет.')
        flights = pd.DataFrame(audit['rw_flight_validation'])
        codes = ['WZ-5343', 'WZ-5305', 'WZ-1033']
        selected = flights[flights['flight_code'].isin(codes)].copy()
        selected['source_urls'] = selected['source_urls'].map(lambda values: '\n'.join(values))
        selected['observation_weeks'] = selected['observation_weeks'].map(lambda values: ', '.join(values))
        columns = {'flight_code': 'Рейс', 'origin_iata': 'Откуда', 'dest_iata': 'Куда',
            'weekly_flights_observed': 'Наблюдалось рейсов/нед.', 'observation_weeks': 'Неделя наблюдения',
            'distance_km': 'Км', 'model_flight_cost_rub': 'Стоимость плеча по базовой формуле, ₽',
            'actual_flight_cost_rub': 'Фактическая стоимость, ₽ (нет данных)', 'source_urls': 'Источник расписания'}
        st.dataframe(selected[list(columns)].rename(columns=columns), hide_index=True, use_container_width=True)
        missing = set(codes) - set(selected['flight_code'])
        if missing:
            st.warning('В аудите отсутствуют примеры: ' + ', '.join(sorted(missing)))
        if not selected.empty:
            full = pd.read_parquet(Path(__file__).resolve().parents[2] / 'data/processed/routes_proof.parquet')
            sample = selected[['flight_code', 'origin_iata', 'dest_iata']].merge(full,
                on=['origin_iata', 'dest_iata'], validate='one_to_one').rename(columns={'flight_code': 'route_code'})
            result = evaluate_route_level_economics(fin_input, sample, subsidy_retention_pct=subsidy_retention_pct)
            pnl = pd.DataFrame(result['routes_pnl'])
            st.markdown('**Справочный P&L этих трёх пар на основе routes_proof.parquet**')
            st.dataframe(pnl[['route_code', 'weekly_round_trips', 'annual_passengers', 'annual_cost_mln_rub',
                'annual_revenue_mln_rub', 'ebitdar_mln_rub', 'ebitdar_no_subsidy_mln_rub', 'proof_source']].rename(columns={
                'route_code': 'Рейс', 'weekly_round_trips': 'Плановых пар/нед.', 'annual_passengers': 'Перевозки (сценарий)',
                'annual_cost_mln_rub': 'Расходы, млн ₽', 'annual_revenue_mln_rub': 'Выручка, млн ₽',
                'ebitdar_mln_rub': 'EBITDAR, млн ₽', 'ebitdar_no_subsidy_mln_rub': 'EBITDAR без субсидий, млн ₽',
                'proof_source': 'Источник / метод'}), hide_index=True, use_container_width=True)
            st.caption('Это отдельный сценарий трёх пар при текущем тарифе, загрузке, частоте и секвестре. Все 115 млн ₽ постоянных затрат распределены на эти пары. Лимит бортов здесь не применяется. Расчёт не является фактической прибылью рейсов WZ и не прибавляется к результату ядра сети.')
        st.markdown('**Реестр коэффициентов и источников**')
        assumptions = pd.DataFrame(audit['assumptions'])
        assumptions['value'] = assumptions['value'].map(lambda value: json.dumps(value, ensure_ascii=False))
        st.dataframe(assumptions.rename(columns={'assumption': 'Допущение', 'value': 'Значение', 'unit': 'Единицы',
            'source': 'Источник', 'status': 'Статус', 'limitation': 'Ограничение'}), hide_index=True, use_container_width=True)
        st.markdown('Для калибровки нужны: ' + '; '.join(audit['calibration']['needed']) + '.')
        st.download_button('Скачать аудит и контрольные суммы · JSON', json.dumps(audit, ensure_ascii=False, indent=2),
                           'red_wings_assumptions_audit.json', 'application/json', key='download_assumptions')
