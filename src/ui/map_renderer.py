"""Dev 4: geographic route schematic, with explicit missing-data handling."""
from html import escape
from typing import List
import math
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from src.schemas.contracts import CityScoreDTO

# Approximate city centres for the existing mocks, NOT airport coordinates.
DEMO_CENTRES = {'KUF': (50.15,53.20), 'GOJ': (44.01,56.33), 'PEE': (56.25,58.01)}


def make_route_figure(routes_df, scored_cities, use_mocks=False):
    fig = go.Figure(); missing=[]; points={}
    names={c.iata:c.city_name for c in scored_cities}
    def coordinate(row, prefix, code):
        lat,lon=row.get(prefix+'_lat'),row.get(prefix+'_lon')
        try:
            lat,lon=float(lat),float(lon)
            if math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180:return lon,lat
        except (TypeError,ValueError):pass
        return DEMO_CENTRES.get(code) if use_mocks else None
    for row in routes_df.to_dict('records'):
        origin,dest=str(row['origin']),str(row['dest'])
        a,b=coordinate(row,'origin',origin),coordinate(row,'dest',dest)
        if a is None or b is None:
            missing.append(origin+' → '+dest);continue
        points[origin]=a;points[dest]=b
        text=f'{escape(origin)} → {escape(dest)}<br>Частота: {escape(str(row.get("freq", "не указана")))}<br>Пассажиры: {escape(str(row.get("pax", "не указаны")))}'
        fig.add_trace(go.Scatter(x=[a[0],b[0]],y=[a[1],b[1]],mode='lines',line=dict(color='#cb2440',width=2),text=[text,text],hoverinfo='text',showlegend=False))
    if points:
        fig.add_trace(go.Scatter(x=[p[0] for p in points.values()],y=[p[1] for p in points.values()],mode='markers+text',text=[escape(names.get(code,code)) for code in points],textposition='top center',marker=dict(size=11,color='#172a45',line=dict(color='white',width=2)),hoverinfo='text',showlegend=False))
    fig.update_layout(height=430,plot_bgcolor='#edf2f7',paper_bgcolor='rgba(0,0,0,0)',margin=dict(l=10,r=15,t=35,b=10),xaxis=dict(title='Долгота',gridcolor='white'),yaxis=dict(title='Широта',gridcolor='white'))
    return fig, missing


def render_route_network_map(routes_df: pd.DataFrame, scored_cities: List[CityScoreDTO], use_mocks=False) -> None:
    if routes_df.empty:
        st.warning('Провайдер не вернул маршруты.');return
    if not {'origin','dest'} <= set(routes_df.columns):
        st.error('Для карты нужны колонки origin и dest.');return
    fig, missing=make_route_figure(routes_df,scored_cities,use_mocks)
    if fig.data:st.plotly_chart(fig,use_container_width=True)
    if missing:st.warning('Нет корректных координат: '+', '.join(missing)+'. Добавьте origin_lat, origin_lon, dest_lat, dest_lon.')
    if use_mocks:st.caption('Демо: приблизительные центры городов KUF, GOJ, PEE. Это географическая схема, не аэропортовая карта и не реальные воздушные трассы.')
    else:st.caption('Географическая схема по координатам провайдера. Линии соединяют конечные точки, не показывают реальные воздушные трассы.')
    if not 8<=len(routes_df)<=12:st.warning(f'Провайдер вернул {len(routes_df)} строк маршрутов. Для итоговой сети кейс требует 8–12 маршрутов.')
    st.dataframe(routes_df,use_container_width=True,hide_index=True)
    st.download_button('Скачать маршруты · CSV',routes_df.to_csv(index=False).encode('utf-8-sig'),'routes.csv','text/csv')
