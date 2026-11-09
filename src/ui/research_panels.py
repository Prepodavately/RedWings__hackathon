"""Evidence-first panels using team functions; no invented forecasts."""
import pandas as pd
import plotly.express as px
import streamlit as st


def render_research(result,params,demo):
    st.subheader('Насколько устойчив топ-3?')
    if result is None:st.info('Проверка доступна на данных команды в USE_MOCKS=0.');return
    from src.scoring.city_scorer import weight_sensitivity
    change=st.slider('Изменение каждого веса, ±%',5,40,20,5)
    sensitivity=weight_sensitivity(result,n_samples=2000,relative_change=change/100,seed=42)
    sensitivity['Попадание в топ-3, %']=sensitivity.top3_frequency*100
    st.plotly_chart(px.bar(sensitivity,x='city_name',y='Попадание в топ-3, %',range_y=[0,100]),use_container_width=True)
    st.caption('2 000 наборов весов с фиксированным seed. Это устойчивость рейтинга при выбранных изменениях, не вероятность успеха хаба. Неопределённость исходных данных здесь не моделируется.')
    st.dataframe(sensitivity,hide_index=True,use_container_width=True)
    st.download_button('Скачать устойчивость',sensitivity.to_csv(index=False).encode('utf-8-sig'),'sensitivity.csv')
    st.subheader('Что произойдёт при повышении тарифа?')
    from src.models.unit_economics import simulate_fare_elasticity_curve
    rows=[]
    for code in ['hub','p2p']:
        for fare,load,revenue,profit in simulate_fare_elasticity_curve(params,code):
            rows.append({'Тариф, ₽':fare,'Загрузка, %':load,'Выручка, млн ₽':revenue,'EBITDAR, млн ₽':profit,'Стратегия':code})
    curve=pd.DataFrame(rows)
    st.plotly_chart(px.line(curve,x='Тариф, ₽',y='EBITDAR, млн ₽',color='Стратегия'),use_container_width=True)
    st.caption('Отдельный эксперимент Dev 3: эластичность −0,65 — допущение. Основные KPI и тепловая карта не включают эту поправку автоматически. Максимум на сетке не доказывает оптимальный рыночный тариф.')
    st.dataframe(curve,hide_index=True,use_container_width=True)


def render_route_passport(routes):
    st.subheader('Паспорт маршрута: откуда цифры?')
    index=st.selectbox('Маршрут для проверки',range(len(routes)),format_func=lambda i:f"{routes.iloc[i]['origin']} → {routes.iloc[i]['dest']}",key='passport_route')
    row=routes.iloc[index]
    st.write(row.get('proof_source','Источник спроса не передан'))
    cols=[c for c in ['distance_km','flight_time_min','pax','freq','competitor_flights_weekly','competitor_fare_rub','fare_source','own_flights_weekly','rail_travel_hours','rail_source','subsidy_eligible','subsidy_check','launch_quarter','route_code_source'] if c in row]
    st.dataframe(pd.DataFrame({'Показатель':cols,'Значение':[str(row[c]) for c in cols]}),hide_index=True,use_container_width=True)
    if row.get('own_flights_weekly',0)>0:st.warning('Red Wings уже присутствует на этой паре. Нельзя считать весь расчётный поток приростом без поправки на существующие рейсы.')
    st.caption('pax и freq из модели спроса Dev 1; KPI Dev 3 рассчитаны по параметрам всей сети. Это разные оценки — их согласованность ещё нужно обосновать.')
