"""Evidence-aware transit, route economics, digital and growth panels."""
import json
from dataclasses import asdict
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from src.scoring.city_scorer import calculate_scissor_hub_index
from src.models.unit_economics import evaluate_digital_one_click_impact, project_path_to_top2_airline


def route_economics(routes, seats=100, load=84.0, fare=None):
    """One operated leg, zero subsidies; missing costs/fares stay unknown."""
    frame = routes.copy(deep=True)
    frame['used_fare_rub'] = pd.to_numeric(frame.competitor_fare_rub, errors='coerce') if fare is None else float(fare)
    frame['used_fare_rub'] = frame.used_fare_rub.where(frame.used_fare_rub > 0)
    frame['cost_rub'] = pd.to_numeric(frame.flight_cost_rub, errors='coerce').where(lambda x: x > 0)
    frame['belf_raw_pct'] = frame.cost_rub / (seats * frame.used_fare_rub) * 100
    frame['contribution_rub'] = seats * load / 100 * frame.used_fare_rub - frame.cost_rub
    frame['passes_cost_test'] = frame.contribution_rub.ge(0) & frame.contribution_rub.notna()
    frame['input_load_pct'] = load
    frame['seats'] = seats
    return frame


def render_route_economics(routes, params):
    st.subheader('Какие направления покрывают стоимость рейса без субсидий?')
    st.caption('Отдельный расчёт на одно плечо: билетный доход минус стоимость рейса Dev 1. Без аренды, общих расходов, перегонов и цифровых эффектов; это не прибыль всей сети. Фильтр не меняет сеть и KPI на других вкладках.')
    use_slider = st.checkbox('Применить тариф из боковой панели ко всем парам',key='rw_route_fare')
    frame = route_economics(routes,params.aircraft_seats,params.load_factor_pct,params.avg_fare_rub if use_slider else None)
    st.info('Стоимость Dev 1 = 385 000 ₽ + 310 ₽ × расстояние. Это допущение для SJ-100, не фактическая себестоимость. По умолчанию тарифы взяты из таблицы конкурентов, включая её медианные подстановки; минимальный тариф 4 500 ₽ здесь не подставляется.')
    a,b,c=st.columns(3)
    a.metric('Покрывают стоимость рейса',int(frame.passes_cost_test.sum()))
    b.metric('Требуют загрузки выше 100%',int(frame.belf_raw_pct.gt(100).sum()))
    c.metric('Не хватает данных',int(frame.contribution_rub.isna().sum()))
    names=dict(zip(frame.origin_iata,frame.origin_city))
    matrix=frame.pivot(index='origin_iata',columns='dest_iata',values='contribution_rub').reindex(index=sorted(names),columns=sorted(names))/1000
    limit=max(1,float(np.nanmax(np.abs(matrix.to_numpy()))))
    labels=[names[x]+' · '+x for x in matrix.index]
    fig=go.Figure(go.Heatmap(z=matrix.to_numpy(),x=labels,y=labels,zmin=-limit,zmax=limit,zmid=0,colorscale=[[0,'#bc2948'],[.5,'#f5f7fa'],[1,'#138576']],xgap=2,ygap=2,colorbar_title='тыс. ₽',hovertemplate='%{y} → %{x}<br>Доход минус стоимость: %{z:.1f} тыс. ₽<extra></extra>'))
    fig.update_layout(height=680,xaxis_tickangle=-45,yaxis_autorange='reversed')
    st.plotly_chart(fig,use_container_width=True)
    st.caption('Серые/пустые ячейки — нет значения или перелёт в тот же город. Порог загрузки не обрезается на 100%: невозможная безубыточность остаётся видимой.')
    only=st.checkbox('Только пары, покрывающие стоимость рейса',key='rw_route_positive')
    shown=frame.loc[frame.passes_cost_test] if only else frame
    cols=['origin_city','dest_city','distance_km','used_fare_rub','fare_source','cost_rub','belf_raw_pct','contribution_rub','pax','freq','proof_source']
    st.dataframe(shown[[x for x in cols if x in shown]],hide_index=True,use_container_width=True)
    st.download_button('Скачать экономику без субсидий',frame.to_csv(index=False).encode('utf-8-sig'),'route_economics_no_subsidy.csv')
    st.warning('Положительный результат при заданной загрузке не подтверждает спрос. Сопоставьте pax/freq Dev 1 с планируемой частотой; недостающий спрос не создаётся ползунком.')


def render_transit(cities,matrix,ranking):
    st.subheader('Транзитный индекс: где удобнее пересадка?')
    threshold=st.slider('Допустимый геометрический крюк, %',0.0,30.0,15.0,1.0,key='rw_transit_threshold')
    result=calculate_scissor_hub_index(cities,matrix,max_detour_pct=threshold)
    details=pd.DataFrame(result.attrs['pair_details'])
    result['eligible_new_hub']=result.iata.map(ranking.set_index('iata').eligible)
    result['new_hub_rank']=result.loc[result.eligible_new_hub,'scissor_hub_index'].rank(ascending=False,method='min')
    allowed=result.loc[result.eligible_new_hub].copy()
    st.plotly_chart(px.bar(allowed.sort_values('scissor_hub_index'),x='scissor_hub_index',y='city_name',orientation='h',color_discrete_sequence=['#247AAB'],labels={'city_name':'','scissor_hub_index':'Геометрический транзитный индекс'}),use_container_width=True)
    st.caption('Порог строгий: крюк ровно на границе не проходит. Используется та же гравитационная матрица с текущими λ и γ. Индекс не меняет финансовый расчёт и не доказывает спрос, готовность расписания или экономию на ТО.')
    names=cities.set_index('iata').city_name.to_dict()
    hub=st.selectbox('Рассмотреть пересадку через',allowed.iata.tolist(),format_func=lambda x:names[x],key='rw_transit_hub')
    selected=details.loc[(details.hub_iata==hub)&details.eligible].copy()
    st.dataframe(selected,hide_index=True,use_container_width=True)
    if not selected.empty:
        pair=st.selectbox('Показать путь на карте',list(range(len(selected))),format_func=lambda i:names[selected.iloc[i].origin_iata]+' → '+names[selected.iloc[i].dest_iata],key='rw_transit_pair')
        row=selected.iloc[pair]; coords=cities.set_index('iata')
        fig=go.Figure()
        for codes,label,color in [([row.origin_iata,row.dest_iata],'Напрямую','#b2becd'),([row.origin_iata,hub,row.dest_iata],'Через выбранный город','#b82444')]:
            fig.add_trace(go.Scattergeo(lon=[coords.loc[x,'lon'] for x in codes],lat=[coords.loc[x,'lat'] for x in codes],text=[names[x] for x in codes],mode='lines+markers+text',textposition='top center',name=label,line=dict(color=color,width=3)))
        fig.update_geos(fitbounds='locations',showland=True,landcolor='#e7edf3',countrycolor='white')
        fig.update_layout(height=430,margin=dict(l=0,r=0,t=25,b=0))
        st.plotly_chart(fig,use_container_width=True)
        st.caption(f'Прямой путь {row.direct_km:.0f} км; через {names[hub]} {row.via_km:.0f} км; крюк {row.detour_pct:.2f}%. Не фактические трассы и не время поездки.')
    st.download_button('Скачать транзитный рейтинг',result.to_csv(index=False).encode('utf-8-sig'),'transit_ranking.csv')
    st.download_button('Скачать все транзитные комбинации',details.to_csv(index=False).encode('utf-8-sig'),'transit_pairs.csv')


def render_digital(params,top):
    st.subheader('Цифровые сервисы: проверить эффект, а не обещать его')
    a=st.checkbox('Составные поездки с партнёрами (Virtual Interline)',value=True,key='rw_digital_interline')
    b=st.checkbox('Допуслуги и покупка в один клик',value=True,key='rw_digital_ancillary')
    c=st.checkbox('Самообслуживание при сбоях',value=True,key='rw_digital_recovery')
    result=evaluate_digital_one_click_impact(params,top,enable_virtual_interline=a,enable_one_click_ancillary=b,enable_auto_disruption_recovery=c)
    base,digital=result['p2p_base'],result['p2p_digital']
    x,y,z=st.columns(3)
    x.metric('EBITDAR после, млн ₽',f"{digital['ebitdar_mln_rub']:,.1f}",f"{result['total_ebitdar_uplift_mln_rub']:+,.1f}")
    y.metric('Перевозки на рейсах RW',f"{digital['annual_passengers']:,}",f"{digital['annual_passengers']-base['annual_passengers']:+,}")
    z.metric('Загрузка после, %',f"{result['digital_effective_load_factor_pct']:.1f}")
    uplift=result['ebitdar_uplift_mln_rub']
    labels=['До цифровизации','Составная поездка','Допуслуги','Самообслуживание','После цифровизации']
    fig=go.Figure(go.Waterfall(x=labels,measure=['absolute','relative','relative','relative','total'],y=[base['ebitdar_mln_rub'],*uplift.values(),0],connector_line_color='#a4b1c2'))
    fig.update_layout(yaxis_title='EBITDAR, млн ₽',height=420)
    st.plotly_chart(fig,use_container_width=True)
    st.info(result['assumptions']+' Это заданные гипотезы, не результаты A/B-теста. Прирост ограничен кресельной ёмкостью; пассажиры на рейсах партнёров не добавляются к RW.')
    st.caption('EBITDAR включает сценарные субсидии и не равен чистой прибыли. Эффекты не прибавляются повторно к основным KPI сети. Для проверки нужны воронка продаж, маржа на заказ, допвыручка и обращения на 1 000 заказов.')
    st.dataframe(pd.DataFrame([dict(variant='До',**base),dict(variant='После',**digital)]),hide_index=True,use_container_width=True)
    st.download_button('Скачать сценарий цифровизации',json.dumps({'params':asdict(params),**result},ensure_ascii=False,indent=2),'digital_scenario.json')


def render_growth(params,top):
    st.subheader('Путь к масштабу перевозчика №2')
    st.caption('Рабочая метрика — годовые перевозки отдельной авиакомпании. Исторический ориентир 2025 года: «Победа» 13,8 млн; RW 2,7 млн. Рейтинг будущих лет не известен.')
    growth=st.slider('Годовой рост ориентира конкурента, %',0.0,15.0,0.0,.5,key='rw_growth_benchmark')
    cannibal=st.slider('Переток с существующих рейсов RW, %',0.0,50.0,0.0,5.0,key='rw_growth_cannibal')
    rows=project_path_to_top2_airline(params,top,benchmark_growth_pct=growth,cannibalization_pct=cannibal)
    frame=pd.DataFrame(rows)
    plotted=frame.loc[frame.wave_id>0]
    long=plotted.melt(id_vars='period',value_vars=['total_pax_mln','fleet_constrained_total_pax_mln','reference_second_pax_mln'],var_name='Оценка',value_name='Млн перевозок')
    long['Оценка']=long['Оценка'].map({'total_pax_mln':'Расчёт сети без ограничения флота','fleet_constrained_total_pax_mln':'С учётом выделенного флота','reference_second_pax_mln':'Ориентир второго перевозчика'})
    st.plotly_chart(px.line(long,x='period',y='Млн перевозок',color='Оценка',markers=True),use_container_width=True)
    st.warning('Волны 65/120 маршрутов и смешанный флот — сценарии команды, не подтверждённые поставки. Экономика SJ-100 масштабирована приближённо; спрос и будущий рейтинг не доказаны. Планирование до 2030 года дополняет первый этап до 2028 года.')
    cols=['period','routes_count','weekly_freq_per_route','total_pax_mln','fleet_total','fleet_required_model','fleet_gap','fleet_constrained_total_pax_mln','reference_second_pax_mln','gap_to_reference_mln','reference_exceeded_with_fleet']
    st.dataframe(plotted[cols],hide_index=True,use_container_width=True)
    st.caption('Волны — альтернативные годовые масштабы сети: пассажиры волн не складываются. Цифровизация волн 2–3 включена один раз по сценарию Dev 3. Переток уменьшает чистый прирост пассажиров; потери выручки старой сети ещё не оценены.')
    st.markdown('[Red Wings: итоги 2025](https://flyredwings.com/en/press/news/red-wings-perevezla-za-god-na-rossijskix-samoletax-2-mln-passazhirov-i-2-sovy/) · [Росавиация: рынок и рейтинг](https://www.favt.gov.ru/novosti-novosti?id=17763) · [«Победа»: 13,8 млн](https://www.interfax.ru/business/1067812)')
    st.download_button('Скачать расчёт пути к №2',frame.to_csv(index=False).encode('utf-8-sig'),'growth_scenario.csv')
