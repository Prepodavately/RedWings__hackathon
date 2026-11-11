"""Display provider results; deltas compare each strategy with its alternative."""
from dataclasses import asdict
import pandas as pd
import streamlit as st


def render_comparison_kpis(comparison):
    verdict = st.warning if max(comparison.hub.ebitdar_mln_rub, comparison.p2p.ebitdar_mln_rub)<0 else st.success
    verdict(('Вердикт: прямые рейсы' if comparison.winner == 'p2p' else 'Вердикт: региональный хаб') + '\n\n' + comparison.rationale)
    for col, result, other in zip(st.columns(2), [comparison.p2p, comparison.hub], [comparison.hub, comparison.p2p]):
        with col:
            from html import escape
            st.markdown('<div class="rw-strategy '+('hub' if result.code=='hub' else '')+'">'+escape(result.title)+'</div>',unsafe_allow_html=True)
            st.metric('Пассажиры, тыс. / год', f'{result.annual_passengers/1000:,.1f}', f'{(result.annual_passengers-other.annual_passengers)/1000:+.1f} тыс.')
            st.metric('Выручка, млн ₽', f'{result.annual_revenue_mln_rub:,.1f}', f'{result.annual_revenue_mln_rub-other.annual_revenue_mln_rub:+.1f} млн ₽')
            st.metric('Прирост доли рынка, п.п.', f'{result.market_share_delta_pct:+.3f}', f'{result.market_share_delta_pct-other.market_share_delta_pct:+.3f} п.п.')
            st.metric('EBITDAR, млн ₽', f'{result.ebitdar_mln_rub:,.1f}', f'{result.ebitdar_mln_rub-other.ebitdar_mln_rub:+.1f} млн ₽')
            st.caption(f'Безубыточная загрузка: {result.breakeven_load_factor_pct:.1f}% · SJ-100: {result.required_aircraft_sj100} · Маржа: {result.ebitdar_margin_pct:.1f}%')
    st.caption('BELF модели ограничен диапазоном 55–96% для хаба и 52–96% для P2P; за границами это индикатор, не точный порог. Выручка включает сценарные субсидии.')
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


def make_strategy_heatmap(grid, params):
    import numpy as np
    import plotly.graph_objects as go
    fares=sorted(grid.fare.unique());freqs=sorted(grid.frequency.unique())
    ordered=grid.set_index(['fare','frequency']).reindex(pd.MultiIndex.from_product([fares,freqs]))
    difference=(ordered.hub-ordered.p2p).to_numpy()
    loss=((ordered.hub<0)&(ordered.p2p<0)).to_numpy()
    maximum=max(float(np.abs(difference).max()),1)
    # Hue is provider winner; intensity is absolute EBITDAR difference, not probability.
    strength=.35+.65*np.abs(difference)/maximum
    z=np.where(ordered.winner.to_numpy()=='hub',strength,-strength)
    z=np.where(loss,np.nan,z).reshape(len(fares),len(freqs))
    state=np.where(loss,'Обе стратегии убыточны',np.where(ordered.winner=='hub','Лидер модели: хаб','Лидер модели: P2P'))
    custom=np.array(list(zip(ordered.hub,ordered.p2p,difference,state)),dtype=object).reshape(len(fares),len(freqs),4)
    hover='<b>%{customdata[3]}</b><br>Тариф: %{y:,.0f} ₽<br>Оборотов в неделю: %{x}<br>EBITDAR хаба: %{customdata[0]:,.1f} млн ₽<br>EBITDAR P2P: %{customdata[1]:,.1f} млн ₽<br>Хаб − P2P: %{customdata[2]:+,.1f} млн ₽<extra></extra>'
    fig=go.Figure(go.Heatmap(x=freqs,y=fares,z=z,customdata=custom,hovertemplate=hover,zmin=-1,zmax=1,xgap=3,ygap=3,showscale=False,colorscale=[[0,'#075684'],[.325,'#B8E0F0'],[.5,'#FFFFFF'],[.675,'#F6CBD4'],[1,'#B21F3C']]))
    fig.add_trace(go.Heatmap(x=freqs,y=fares,z=np.where(loss.reshape(len(fares),len(freqs)),1,np.nan),customdata=custom,hovertemplate=hover,xgap=3,ygap=3,showscale=False,colorscale=[[0,'#D2D8E2'],[1,'#D2D8E2']]))
    for label,color in [('P2P','#247AAB'),('Хаб','#D82F4C'),('Обе убыточны','#B1BBCB')]:
        fig.add_trace(go.Scatter(x=[None],y=[None],mode='markers',marker=dict(size=12,color=color,symbol='square'),name=label))
    inside=6000<=params.avg_fare_rub<=12000 and 2<=params.weekly_freq_per_route<=10
    if inside:
        fig.add_trace(go.Scatter(x=[params.weekly_freq_per_route],y=[params.avg_fare_rub],mode='markers',marker=dict(size=18,color='#12233F',symbol='diamond',line=dict(width=3,color='white')),name='Ваш сценарий',hovertemplate='Текущие настройки<br>%{y:,.0f} ₽ · %{x} оборотов<extra></extra>'))
    fig.update_layout(height=580,xaxis=dict(title='Парных оборотов на маршрут в неделю',dtick=1,range=[1.5,10.5]),yaxis=dict(title='Базовый тариф в одну сторону, ₽',tickformat=',.0f',dtick=1000,range=[5750,12250]),legend=dict(orientation='h',y=1.12),margin=dict(t=65,l=70,r=20,b=55))
    return fig,inside


def render_strategy_heatmap(economics, params, top_cities):
    st.subheader('Карта выбора стратегии')
    st.caption('117 сочетаний тарифа и частоты · Наведите курсор на ячейку, чтобы сравнить результаты.')
    try:
        grid=build_strategy_grid(economics,params,top_cities)
        loss=(grid.hub<0)&(grid.p2p<0)
        a,b,c=st.columns(3)
        a.metric('P2P лидирует без убытка',f'{((grid.winner=="p2p")&~loss).sum()} / 117')
        b.metric('Хаб лидирует без убытка',f'{((grid.winner=="hub")&~loss).sum()} / 117')
        c.metric('Обе стратегии убыточны',f'{loss.sum()} / 117')
        fig,inside=make_strategy_heatmap(grid,params)
        st.plotly_chart(fig,use_container_width=True,config={'displaylogo':False})
        st.caption('Цвет — лидер по правилу Dev 3; насыщенность — абсолютная разница EBITDAR внутри этой сетки. Серые ячейки: запуск обеих стратегий убыточен. Число ячеек не является вероятностью успеха.')
        if not inside:st.info('Ваш тариф вне диапазона карты 6 000–12 000 ₽. Маркер не показан; основные KPI рассчитаны по вашему тарифу.')
        if grid.winner.nunique()==1:st.info('Лидер одинаков во всей сетке. Изменение насыщенности показывает разницу в экономике, а не смену победителя.')
        st.download_button('↓ Скачать все 117 расчётов',grid.to_csv(index=False).encode('utf-8-sig'),'strategy_grid.csv','text/csv')
    except Exception as exc:st.error(f'Тепловая карта недоступна: {exc}')
