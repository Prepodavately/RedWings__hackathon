from pathlib import Path
import io
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from model import CRITERIA,DEFAULT_WEIGHTS,validate_cities,validate_routes,score_cities,demo_routes,calculate

ROOT=Path(__file__).parent
st.set_page_config(page_title='Red Wings · Лаборатория сети',page_icon='✈',layout='wide')
st.markdown('''<style>
.block-container{padding-top:2rem;max-width:1500px}h1{letter-spacing:-1.5px!important;font-weight:750!important}h2,h3{letter-spacing:-.5px}div[data-testid="stMetric"]{background:white;border:1px solid #E5E8EF;border-radius:12px;padding:17px}div[data-testid="stMetricValue"]{font-size:1.8rem} .eyebrow{color:#c9233e;letter-spacing:3px;font-size:12px;font-weight:800}.intro{color:#64748b;font-size:17px}.stTabs [data-baseweb="tab"]{font-weight:600}footer{visibility:hidden}
</style>''',unsafe_allow_html=True)
st.markdown('<div class="eyebrow">RED WINGS / NETWORK LAB</div>',unsafe_allow_html=True)
st.title('Где начинается следующий маршрут')
st.markdown('<p class="intro">Новый региональный хаб или прямые рейсы · Интерактивный прототип для кейс-чемпионата</p>',unsafe_allow_html=True)
st.warning('ДЕМОНСТРАЦИОННАЯ МОДЕЛЬ. Баллы городов, спрос, тарифы и частоты синтетические. Это проверка интерфейса и допущений, а не рекомендация авиакомпании.')

with st.sidebar:
    st.markdown('### Параметры расчёта')
    scenario=st.radio('Сценарий',['Базовый','Осторожный'],key='scenario')
    st.caption('Осторожный: спрос ×0,75; тариф ×0,90; предел загрузки −10 п. п. Коэффициенты — допущения прототипа.')
    load=st.slider('Предел загрузки, %',0,100,85,key='load')
    tariff=st.slider('Изменение тарифа, %',-50,50,0,key='tariff')
    months=st.slider('Месяцев работы сети в году',0,12,12,key='months')
    available=st.slider('Доступно самолётов',0,20,6,key='available')
    with st.expander('Дополнительные допущения'):
        year=st.selectbox('Год расчёта',[2027,2028],index=1)
        st.caption('В 2027 году по условию новые SJ-100 ожидаются не раньше второго полугодия. При расчёте их эффекта выберите не более 6 месяцев.')
        seats=st.number_input('Кресел на борту',1,500,100)
        net=st.slider('Доля чистого прироста перевозок, %',0,100,100,help='Остальное считаем переносом с существующих рейсов Red Wings.')
        market=st.number_input('Рынок в расчётном году, млн пассажиров',1.0,500.0,108.9,step=1.0)
        baseline=st.number_input('Red Wings без проекта, млн пассажиров',0.0,500.0,2.7,step=.1)
        st.caption('2,7 и 108,9 млн — ориентиры за 2025 год из справки кейса. Для 2027/2028 здесь используется допущение неизменного рынка; замените прогнозом команды.')
        daily=st.slider('Ресурс борта, часов в день',4,14,9)
        reserve=st.slider('Резерв ресурса, %',0,50,15)
        reposition=st.slider('Доп. ресурс для прямых рейсов, %',0,50,10,help='Условная надбавка на позиционирование. Не заменяет расчёт оборотов самолётов.')
    with st.expander('Подключить данные команды'):
        city_file=st.file_uploader('cities.csv',type='csv',key='cities_upload')
        route_file=st.file_uploader('routes.csv — обе стратегии',type='csv',key='routes_upload')
        st.caption('Формат и шаблоны доступны на вкладке «Данные». Загрузка действует в текущей сессии.')
    if st.button('Сбросить основные настройки'):
        for key in ['scenario','load','tariff','months','available',*['weight_'+k for k in CRITERIA]]:st.session_state.pop(key,None)
        st.rerun()
try:
    cities=validate_cities(pd.read_csv(city_file if city_file else ROOT/'data/cities.csv'))
except Exception as e:
    st.error('Не удалось прочитать города: '+str(e));st.stop()

compare,ranking,stress,data_tab=st.tabs(['01  Стратегии и сеть','02  Выбор городов','03  Устойчивость','04  Данные'])
with ranking:
    st.subheader('Почему именно эти города?')
    st.caption('Все критерии приведены к шкале 0–100: больше = лучше. Баллы в комплекте вымышлены, это не население и не статистика спроса. Веса нормируются до суммы 100%.')
    weights={}
    for col,(key,label) in zip(st.columns(5),CRITERIA.items()):
        with col: weights[key]=st.slider(label,0,100,DEFAULT_WEIGHTS[key],key='weight_'+key)
    if sum(weights.values())==0:
        st.error('Все веса равны нулю. Временно применены исходные веса.');weights=DEFAULT_WEIGHTS.copy()
    scores=score_cities(cities,weights)
    base_scores=score_cities(cities,DEFAULT_WEIGHTS)
    scores['rank']=scores.index+1
    base_rank={name:i+1 for i,name in enumerate(base_scores.city)}
    scores['rank_change']=scores.city.map(base_rank)-scores['rank']
    for col,row in zip(st.columns(3),scores.head(3).itertuples()):
        col.metric(f'{row.rank}. {row.city}',f'{row.score:.1f} / 100',f'{row.rank_change:+d} мест к исходным весам')
    fig=px.bar(scores.sort_values('score'),x='score',y='city',orientation='h',color='score',color_continuous_scale=['#f6cbd2','#c9233e'],labels={'score':'Взвешенная оценка','city':''})
    fig.update_layout(height=440,showlegend=False,coloraxis_showscale=False,plot_bgcolor='white',paper_bgcolor='rgba(0,0,0,0)',margin=dict(l=0,r=10,t=10,b=0))
    st.plotly_chart(fig,use_container_width=True)
    st.dataframe(pd.DataFrame({'Критерий':list(CRITERIA.values()),'Вес, %':[round(weights[k]/sum(weights.values())*100,1) for k in CRITERIA]}),hide_index=True)
    st.caption('Расстояния до Москвы/Екатеринбурга и реальные доли пересадочного потока ещё не получены. Участник №2 может расширить CRITERIA и заменить score_cities в model.py.')

with compare:
    left,right=st.columns([2,1])
    with left: st.subheader('Две стратегии. Одинаковые условия.')
    with right: hub=st.selectbox('Хаб для демонстрационной сети',[c for c in cities.city if c not in ['Москва','Екатеринбург']],key='hub')
    try:
        if route_file:
            routes=validate_routes(pd.read_csv(route_file),cities)
            st.info('Используются загруженные маршруты. Выбор демонстрационного хаба их не изменяет.')
        elif {'Москва','Екатеринбург'}<=set(cities.city):routes=demo_routes(cities,hub)
        else: st.error('Для этого набора городов загрузите routes.csv с обеими стратегиями.');st.stop()
    except Exception as e:st.error('Ошибка маршрутов: '+str(e));st.stop()
    if len(cities)<10:st.warning('В условии требуется 10+ городов. В загруженной таблице их меньше.')
    cautious=scenario=='Осторожный'
    params=dict(seats=seats,load=max(0,load/100-(.1 if cautious else 0)),fare_factor=(1+tariff/100)*(.9 if cautious else 1),demand_factor=.75 if cautious else 1,months=months,market=market*1e6,baseline=baseline*1e6,net_fraction=net/100,daily_hours=daily,reserve=reserve/100,positioning=reposition/100)
    totals,details=calculate(routes,**params)
    st.caption(f'{year} · {scenario} · {months} мес. · Пассажиры учитываются на участках перевозки, в обе стороны. Уникальные поездки через хаб модель пока не выделяет.')
    for col,row in zip(st.columns(2),totals.itertuples()):
        with col:
            st.markdown(f'#### {row.strategy}')
            a,b=st.columns(2);a.metric('Перевозки на участках',f'{row.passengers/1000:,.1f} тыс.');b.metric('Выручка',f'{row.revenue/1e6:,.1f} млн ₽')
            a,b=st.columns(2);a.metric('Прирост доли',f'+{row.share_delta_pp:.3f} п. п.');b.metric('Оценка флота',f'{row.fleet} бортов')
            if row.fleet>available:st.error(f'Недостаточно ресурса: требуется {row.fleet}, доступно {available}.')
            else:st.success(f'Ресурсный лимит соблюдён: {row.fleet} из {available}. Расписание ещё нужно проверить.')
    st.caption('Выручка не является прибылью. Расходы на базу, обслуживание, лизинг и субсидии не включены. Автоматический выбор победителя отключён до появления модели команды.')
    if year==2027 and months>6:st.warning('Для эффекта новых SJ-100 в 2027 году по условию кейса нужно уменьшить период работы до 6 месяцев или меньше.')
    st.markdown('#### Сеть маршрутов')
    strategy=st.radio('Показать сеть',['Хаб','Прямые рейсы'],horizontal=True,key='network')
    selected=details[details.strategy==strategy]
    if not 8<=len(selected)<=12:st.warning(f'Сейчас {len(selected)} маршрутов. Для выбранной итоговой сети требуется 8–12.')
    coords=cities.set_index('city');fig=go.Figure();color='#c9233e' if strategy=='Хаб' else '#197b98'
    for row in selected.itertuples():
        a,b=coords.loc[row.origin],coords.loc[row.destination]
        label=f'{row.origin} ↔ {row.destination}<br>{row.weekly_roundtrips:g} оборотов/нед.<br>{row.passengers:,.0f} пасс./период<br>{row.fare_rub*params["fare_factor"]:,.0f} ₽ / участок<br>{row.data_status}'
        fig.add_trace(go.Scatter(x=[a.lon,b.lon],y=[a.lat,b.lat],mode='lines',line=dict(width=2,color=color),text=[label,label],hoverinfo='text',showlegend=False))
    active=set(selected.origin)|set(selected.destination);points=cities[cities.city.isin(active)]
    fig.add_trace(go.Scatter(x=points.lon,y=points.lat,mode='markers+text',marker=dict(size=10,color=color,line=dict(width=2,color='white')),text=points.city,textposition='top center',hovertemplate='%{text}<extra></extra>',showlegend=False))
    fig.update_layout(height=430,plot_bgcolor='#edf2f7',paper_bgcolor='rgba(0,0,0,0)',margin=dict(l=10,r=20,t=30,b=20),xaxis=dict(title='Долгота, ° в. д.',showgrid=True,gridcolor='white'),yaxis=dict(title='Широта, ° с. ш.',showgrid=True,gridcolor='white'))
    st.plotly_chart(fig,use_container_width=True)
    st.caption('Географическая схема по координатам центров городов. Линии показывают пары городов, а не воздушные трассы. Работает без картографического сервиса.')
    st.dataframe(selected[['origin','destination','weekly_roundtrips','passengers','effective_load','revenue','block_hours']].rename(columns={'origin':'Откуда','destination':'Куда','weekly_roundtrips':'Оборотов/нед.','passengers':'Пассажиры','effective_load':'Факт. загрузка (доля)','revenue':'Выручка, ₽','block_hours':'Часов в одну сторону'}),hide_index=True,use_container_width=True)

with stress:
    st.subheader('Когда меняется результат?')
    st.markdown('#### Чувствительность к загрузке')
    sensitivity=[]
    for lf in range(30,101,5):
        p=params.copy();p['load']=lf/100
        result,_=calculate(routes,**p)
        for r in result.itertuples():sensitivity.append({'Загрузка, %':lf,'Выручка, млн ₽':r.revenue/1e6,'Стратегия':r.strategy})
    fig=px.line(pd.DataFrame(sensitivity),x='Загрузка, %',y='Выручка, млн ₽',color='Стратегия',color_discrete_map={'Хаб':'#c9233e','Прямые рейсы':'#197b98'},markers=True)
    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='white',legend=dict(orientation='h',y=1.15),margin=dict(l=0,r=0,t=40,b=0))
    st.plotly_chart(fig,use_container_width=True)
    st.caption('Пассажиропоток ограничен заданным спросом: после его исчерпания рост предела загрузки не увеличивает выручку. Зависимость спроса от цены пока не моделируется.')
    st.markdown('#### Устойчивость рейтинга городов')
    spread=st.slider('Изменение каждого веса, ±%',0,50,20,key='spread')
    import random
    rng=random.Random(42);counts={c:0 for c in cities.city}
    for _ in range(200):
        ws={k:v*rng.uniform(1-spread/100,1+spread/100) for k,v in weights.items()}
        for c in score_cities(cities,ws).head(3).city:counts[c]+=1
    stable=pd.DataFrame({'Город':list(counts),'Попаданий в топ-3, %':[v/2 for v in counts.values()]}).sort_values('Попаданий в топ-3, %',ascending=False)
    st.dataframe(stable,hide_index=True,use_container_width=True)
    st.caption('200 воспроизводимых проб с равномерным изменением весов и последующей нормировкой. Это устойчивость к выбранным изменениям, а не вероятность успеха города. Нулевой вес остаётся нулевым.')
    st.markdown('#### Оба сценария при текущих настройках')
    frames=[]
    for title,is_cautious in [('Базовый',False),('Осторожный',True)]:
        p=params.copy();p.update(load=max(0,load/100-(.1 if is_cautious else 0)),fare_factor=(1+tariff/100)*(.9 if is_cautious else 1),demand_factor=.75 if is_cautious else 1)
        frame,_=calculate(routes,**p);frame.insert(0,'scenario',title);frames.append(frame)
    scenario_results=pd.concat(frames,ignore_index=True)
    st.dataframe(scenario_results.rename(columns={'scenario':'Сценарий','strategy':'Стратегия','passengers':'Пассажиры','revenue':'Выручка, ₽','net_passengers':'Чистый прирост','share_pct':'Доля, %','share_delta_pp':'Прирост, п. п.','fleet':'Бортов'}),hide_index=True)

with data_tab:
    st.subheader('Каждое число должно быть проверяемым')
    st.markdown('**Из справки кейса:** 2,7 млн пассажиров Red Wings и 108,9 млн рынка за 2025 год; около 100 кресел; почти 85% загрузки в первом полугодии 2025 года. Это ориентиры из предоставленного документа, не независимо проверенные текущие показатели.')
    st.markdown('**Создано для демонстрации:** список кандидатов, баллы 0–100, две сети, спрос, тарифы, частоты, сценарные коэффициенты и ресурсные параметры. Прототип не доказывает преимущества хаба и не моделирует реальные стыковки.')
    st.markdown('**Источник условия:** «5 кейс(1).pdf», страницы 2–7; «Кейс_Red_Wings_слайд_v2 (1).pdf». Данные команды загружаются слева. Их статус отображается как указан в файле, автоматически достоверность не проверяется.')
    st.dataframe(routes,hide_index=True,use_container_width=True)
    st.markdown('#### Забрать данные и результаты')
    def csv_bytes(df):return df.to_csv(index=False).encode('utf-8-sig')
    a,b,c=st.columns(3)
    a.download_button('Города · CSV',csv_bytes(cities),'cities.csv','text/csv')
    b.download_button('Маршруты · CSV',csv_bytes(routes),'routes.csv','text/csv')
    c.download_button('4 варианта · CSV',csv_bytes(scenario_results),'scenario_results.csv','text/csv')
    st.download_button('Параметры расчёта · JSON',json.dumps({'year':year,'scenario':scenario,'parameters':params,'weights':weights,'note':'Демонстрационный расчёт; нет модели затрат и реального расписания.'},ensure_ascii=False,indent=2),'parameters.json','application/json')
    with st.expander('Формулы и ограничения',expanded=False):
        st.markdown('''
- Частота — **обороты в неделю**: один оборот = А→Б и Б→А. Спрос — сумма пассажиров на обоих направлениях за полный год.
- Рейсы = обороты × 2 × 52 × месяцы / 12.
- Пассажиры = min(рейсы × кресла × предел загрузки; годовой спрос × коэффициент спроса × месяцы / 12).
- Выручка = пассажиры × тариф за **один участок**, с поправками сценария.
- Чистый прирост = пассажиры × доля чистого прироста. Существующие пассажиры Red Wings повторно не добавляются.
- Прирост доли, п. п. = чистый прирост / рынок расчётного года × 100. Размер рынка фиксируется пользователем, эндогенный рост рынка не моделируется.
- Ресурс борта: рейсы × (полёт + 0,75 ч обслуживания); для прямых рейсов добавляется надбавка на позиционирование. Округление вверх с резервом. Это грубая оценка ресурса, не доказательство выполнимости расписания.
- В хабе не выделены уникальные поездки и стыковки. Оценки пассажиров на участках нужно привести к методике статистики рынка до защиты.
- Цена и спрос в прототипе независимы. Ползунки проверяют допущения, не прогнозируют поведение покупателей.
''')
    st.info('Для интеграции: score_cities(cities, weights) и calculate(routes, **parameters) находятся в model.py. Их можно заменить функциями участников №2 и №3, сохранив формат результата.')
st.divider()
st.caption('RED WINGS / CASE LAB · Прототип команды · Не официальный продукт Red Wings')
