"""Live catchment and directed gravity analysis using Dev 2's agreed model."""
import json
import hashlib
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from src.scoring.city_scorer import calculate_effective_population, calculate_gravity_matrix


def build_analysis(features, routes, ranking, lam=0.45, gamma=1.15):
    cities = features.copy(deep=True)
    population = calculate_effective_population(cities, lam=lam)
    details = pd.DataFrame(population.attrs['catchment_details'])
    cities['effective_population_mln'] = population
    matrix = calculate_gravity_matrix(cities, routes, gamma=gamma)
    satellites = details.groupby('iata').satellite_population.sum() if not details.empty else pd.Series(dtype=float)
    cities['component_population_mln'] = cities.population_city_mln + cities.iata.map(satellites).fillna(0) / 1e6
    cities['population_gap_people'] = ((cities.population_mln - cities.component_population_mln) * 1e6).round().astype(int)
    comparison = ranking[['iata', 'city_name', 'eligible', 'total_score', 'rank']].copy()
    comparison['gravity_index'] = comparison.iata.map(matrix.sum(axis=1))
    comparison['gravity_rank'] = np.nan
    allowed = comparison.eligible.astype(bool)
    comparison.loc[allowed, 'gravity_rank'] = comparison.loc[allowed, 'gravity_index'].rank(ascending=False, method='min')
    rows = []
    attrs = matrix.attrs
    for i, origin in enumerate(matrix.index):
        for j, dest in enumerate(matrix.columns):
            if origin != dest:
                rows.append(dict(origin=origin, dest=dest, gravity_index=float(matrix.iloc[i, j]),
                    distance_km=attrs['distance_km'][i][j],
                    competitor_flights_weekly=attrs['competitor_flights_weekly'][i][j],
                    competition_observed=attrs['competition_observed'][i][j],
                    range_weight=attrs['range_weight'][i][j]))
    pairs = pd.DataFrame(rows).sort_values(['gravity_index', 'origin', 'dest'], ascending=[False, True, True])
    return cities, details, matrix, comparison, pairs


def make_gravity_figure(matrix, cities):
    names = cities.set_index('iata').city_name.to_dict()
    labels = [f'{names[c]} · {c}' for c in matrix.index]
    z = matrix.to_numpy().copy()
    np.fill_diagonal(z, np.nan)
    observed = np.array(matrix.attrs['competition_observed'])
    custom = np.stack([np.array(matrix.attrs['distance_km']).round(0).astype(str),
                       np.where(observed, np.array(matrix.attrs['competitor_flights_weekly']).astype(str), 'нет наблюдения')], axis=-1)
    fig = go.Figure(go.Heatmap(z=z, x=labels, y=labels, customdata=custom,
        colorscale=[[0,'#F1F5FA'],[.35,'#80B4CE'],[.7,'#247AAB'],[1,'#12233F']],
        xgap=2, ygap=2, colorbar=dict(title='Индекс'),
        hovertemplate='Откуда: %{y}<br>Куда: %{x}<br>Потенциал: %{z:.6f}<br>Расстояние: %{customdata[0]} км<br>Рейсы конкурентов/нед.: %{customdata[1]}<extra></extra>'))
    fig.update_layout(height=700, margin=dict(l=10,r=20,t=20,b=20),
        xaxis=dict(title='Куда',tickangle=-45), yaxis=dict(title='Откуда',autorange='reversed'))
    return fig


def render_gravity_panel(features, routes, ranking, weights=None):
    st.subheader('Какие связи имеют наибольший потенциал?')
    st.info('Гравитация — относительный модельный индекс, не пассажиропоток и не выручка. Эти расчёты не меняют выбранный хаб или финансовые KPI автоматически.')
    a,b = st.columns(2)
    lam = a.slider('Влияние времени доезда λ, 1/ч',0.0,1.0,0.45,0.05,key='gravity_lambda')
    gamma = b.slider('Влияние расстояния γ',0.5,2.0,1.15,0.05,key='gravity_gamma')
    cities, details, matrix, comparison, pairs = build_analysis(features,routes,ranking,lam,gamma)
    a,b,c = st.columns(3)
    a.metric('Городов в матрице',len(matrix))
    b.metric('Направлений А → Б',len(pairs))
    c.metric('Без наблюдения конкуренции',matrix.attrs['missing_competition_pairs'])
    if matrix.attrs['missing_competition_pairs']:
        st.warning('Неизвестные частоты заменяются нулём по модели Dev 2. Это может завышать потенциал; неизвестность не означает отсутствие рейсов.')
    st.plotly_chart(make_gravity_figure(matrix,cities),use_container_width=True)
    st.caption('Строка — отправление, столбец — назначение. Обратное направление учитывается отдельно. Диагональ скрыта; нулевой индекс возможен из-за фильтра расстояний. Общий набор из 12 городов сохраняется, включая Екатеринбург как пункт назначения.')
    names = cities.set_index('iata').city_name.to_dict()
    shown = pairs.head(15).copy()
    shown['Направление'] = shown.origin.map(names)+' → '+shown.dest.map(names)
    st.plotly_chart(px.bar(shown.sort_values('gravity_index'),x='gravity_index',y='Направление',orientation='h',labels={'gravity_index':'Относительный потенциал'},height=530,color_discrete_sequence=['#247AAB']),use_container_width=True)
    st.subheader('Охват аэропорта: город и спутники')
    st.caption('Город учитывается целиком. Вклад спутников уменьшается с временем доезда; учитываются только спутники в пределах 2 часов. Времена заданы сценарием, дорожные изохроны не строились.')
    pop = cities[['city_name','population_mln','effective_population_mln']].rename(columns={'population_mln':'Заявленная агломерация','effective_population_mln':'Эффективное население'})
    melted = pop.melt(id_vars='city_name',var_name='Оценка',value_name='Млн человек')
    st.plotly_chart(px.bar(melted,y='city_name',x='Млн человек',color='Оценка',barmode='group',orientation='h',labels={'city_name':''},height=630,color_discrete_map={'Заявленная агломерация':'#C6D3E4','Эффективное население':'#247AAB'}),use_container_width=True)
    gaps = cities.loc[cities.population_gap_people.abs()>1,['city_name','population_gap_people']]
    if not gaps.empty:
        st.warning('Сумма города и перечисленных спутников расходится с заявленной агломерацией: '+ '; '.join(f'{r.city_name}: {r.population_gap_people:+,} чел.' for r in gaps.itertuples())+'. Это расхождение исходных данных, не эффект времени доезда.')
    with st.expander('Слагаемые охвата и принятые времена'):
        st.dataframe(details,hide_index=True,use_container_width=True)
        st.dataframe(cities[['city_name','population_city_mln','component_population_mln','population_mln','effective_population_mln','population_gap_people']],hide_index=True,use_container_width=True)
    st.subheader('Почему рейтинги расходятся?')
    st.caption('Обычный скоринг оценивает профиль города по выбранным весам; гравитация — сумму исходящих связей с учётом населения, зарплаты, расстояния и конкурентов. Места сравниваются среди одинаковых допустимых кандидатов нового хаба. Это разные вопросы, поэтому баллы не усредняются.')
    eligible = comparison.loc[comparison.eligible].sort_values('rank')
    long = eligible.melt(id_vars=['city_name'],value_vars=['rank','gravity_rank'],var_name='Метод',value_name='Место')
    long['Метод'] = long['Метод'].map({'rank':'Обычный скоринг','gravity_rank':'Гравитация'})
    fig = px.scatter(long,x='Место',y='city_name',color='Метод',symbol='Метод',labels={'city_name':''},height=500,color_discrete_map={'Обычный скоринг':'#D82F4C','Гравитация':'#247AAB'})
    fig.update_traces(marker_size=13)
    fig.update_xaxes(dtick=1)
    st.plotly_chart(fig,use_container_width=True)
    st.dataframe(comparison.rename(columns={'rank':'Место скоринга','gravity_rank':'Место гравитации','eligible':'Допустим для нового хаба'}),hide_index=True,use_container_width=True)
    with st.expander('Формулы и воспроизводимость'):
        st.code('P_eff = P_city + Σ P_sat × exp(−λt), t ≤ 2 ч\nG_ij = P_eff_i × P_eff_j × sqrt(q_i q_j) × W(d) / (d^γ × (1 + F_ij))')
        st.write('q — зарплата региона относительно среднего кандидатов. W=0 до 300 и от 3000 км, W=1 на 800–1500 км; между границами линейный переход. Расстояния геодезические, не фактические трассы. Нулевая конкуренция не учитывает существующие рейсы RW как конкурента.')
    metadata = {'created_at_utc':datetime.now(timezone.utc).isoformat(),'lambda':lam,'gamma':gamma,'status':'scenario_index_not_passengers','linear_weights':weights,
        'input_sha256':{name:hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest() for name,frame in [('features',features),('routes',routes),('ranking',ranking)]},
        'missing_competition_pairs':matrix.attrs['missing_competition_pairs']}
    for label,frame,name in [('матрицу',matrix,'gravity_matrix'),('направления',pairs,'gravity_pairs'),('охват',cities,'catchment'),('сравнение',comparison,'method_comparison')]:
        st.download_button('Скачать '+label,frame.to_csv(index=name=='gravity_matrix').encode('utf-8-sig'),name+'.csv',key='export_'+name)
    st.download_button('Скачать параметры расчёта',json.dumps(metadata,ensure_ascii=False,indent=2),'gravity_metadata.json',mime='application/json')
