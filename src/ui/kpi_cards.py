"""Dev 4: render provider results without recomputing the economics."""
from dataclasses import asdict
import pandas as pd
import streamlit as st
from src.schemas.contracts import ComparisonBundleDTO


def render_comparison_kpis(comparison: ComparisonBundleDTO) -> None:
    for col, result in zip(st.columns(2), [comparison.hub, comparison.p2p]):
        with col:
            st.subheader(result.title)
            a, b = st.columns(2)
            a.metric('Пассажиры / год', f'{result.annual_passengers:,}'.replace(',', ' '))
            b.metric('Выручка, млн ₽', f'{result.annual_revenue_mln_rub:,.1f}')
            a, b = st.columns(2)
            a.metric('EBITDAR, млн ₽', f'{result.ebitdar_mln_rub:,.1f}')
            b.metric('Необходимо SJ-100', str(result.required_aircraft_sj100))
            st.caption(f'Маржа EBITDAR: {result.ebitdar_margin_pct:.1f}% · Безубыточная загрузка: {result.breakeven_load_factor_pct:.1f}%')
            st.write(f'Изменение доли рынка (поле контракта): **{result.market_share_delta_pct:g}**')
    st.caption('EBITDAR — результат до процентов, налогов, амортизации и аренды. Единица market_share_delta_pct пока не закреплена в контракте: проценты и процентные пункты нельзя смешивать.')
    st.info('Вывод расчётного модуля: '+ ('новый хаб' if comparison.winner=='hub' else 'прямые рейсы') + '. '+comparison.rationale)
    st.download_button('Скачать сравнение · CSV', pd.DataFrame([asdict(comparison.hub),asdict(comparison.p2p)]).to_csv(index=False).encode('utf-8-sig'), 'comparison.csv', 'text/csv')
