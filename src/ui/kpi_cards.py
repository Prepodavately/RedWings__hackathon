"""Display provider results; deltas compare each strategy with its alternative."""
from dataclasses import asdict
import pandas as pd
import streamlit as st


def render_comparison_kpis(comparison):
    st.success(('Вердикт: прямые рейсы' if comparison.winner == 'p2p' else 'Вердикт: региональный хаб') + '\n\n' + comparison.rationale)
    for col, result, other in zip(st.columns(2), [comparison.p2p, comparison.hub], [comparison.hub, comparison.p2p]):
        with col:
            st.subheader(result.title)
            st.metric('Пассажиры, тыс. / год', f'{result.annual_passengers/1000:,.1f}', f'{(result.annual_passengers-other.annual_passengers)/1000:+.1f} тыс.')
            st.metric('Выручка, млн ₽', f'{result.annual_revenue_mln_rub:,.1f}', f'{result.annual_revenue_mln_rub-other.annual_revenue_mln_rub:+.1f} млн ₽')
            st.metric('Прирост доли рынка, п.п.', f'{result.market_share_delta_pct:+.3f}', f'{result.market_share_delta_pct-other.market_share_delta_pct:+.3f} п.п.')
            st.metric('EBITDAR, млн ₽', f'{result.ebitdar_mln_rub:,.1f}', f'{result.ebitdar_mln_rub-other.ebitdar_mln_rub:+.1f} млн ₽')
            st.caption(f'Безубыточная загрузка: {result.breakeven_load_factor_pct:.1f}% · SJ-100: {result.required_aircraft_sj100} · Маржа: {result.ebitdar_margin_pct:.1f}%')
    st.caption('Дельты — относительно другой стратегии. Доля рынка: процентные пункты по формуле ТЗ с постоянным рынком 108,9 млн пассажиров. EBITDAR — результат до процентов, налогов, амортизации и аренды.')
    st.download_button('Скачать сравнение · CSV', pd.DataFrame([asdict(comparison.hub), asdict(comparison.p2p)]).to_csv(index=False).encode('utf-8-sig'), 'comparison.csv', 'text/csv')


def build_strategy_grid(economics, params, top_cities):
    from dataclasses import replace
    rows=[]
    for fare in range(6000,12001,500):
        for freq in range(2,11):
            bundle=economics(replace(params,avg_fare_rub=float(fare),weekly_freq_per_route=freq),top_cities)
            if bundle is None or bundle.winner not in ('hub','p2p'):
                raise ValueError('Модель не вернула результат для тепловой карты.')
            rows.append({'fare':fare,'frequency':freq,'winner':bundle.winner,'hub':bundle.hub.ebitdar_mln_rub,'p2p':bundle.p2p.ebitdar_mln_rub})
    return pd.DataFrame(rows)


def render_strategy_heatmap(economics, params, top_cities):
    import plotly.express as px
    st.subheader('Где меняется победитель')
    st.caption('117 вызовов модели: тариф 6 000–12 000 ₽ × 2–10 оборотов в неделю. Остальные параметры взяты из панели слева.')
    try:
        grid=build_strategy_grid(economics,params,top_cities)
        values=grid.assign(value=(grid.winner=='hub').astype(int)).pivot(index='fare',columns='frequency',values='value')
        fig=px.imshow(values,origin='lower',aspect='auto',zmin=0,zmax=1,color_continuous_scale=[[0,'#167d9a'],[.499,'#167d9a'],[.5,'#cf2944'],[1,'#cf2944']],labels=dict(x='Оборотов в неделю',y='Тариф, ₽',color='Победитель'))
        fig.update_coloraxes(colorbar=dict(tickvals=[0,1],ticktext=['P2P','Хаб']))
        st.plotly_chart(fig,use_container_width=True)
        if grid.winner.nunique()==1:st.info('В пределах этой сетки победитель не меняется. Граница переключения не обнаружена.')
        if ((grid.hub<0)&(grid.p2p<0)).any():st.warning('В части точек обе стратегии убыточны по EBITDAR. Победа в сравнении не означает прибыльность.')
        st.download_button('Скачать сетку сценариев',grid.to_csv(index=False).encode('utf-8-sig'),'strategy_grid.csv','text/csv')
    except Exception as exc:st.error(f'Тепловая карта недоступна: {exc}')
