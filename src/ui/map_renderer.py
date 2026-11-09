"""Geographic network and explicitly geometric Moscow detour comparison."""
import math
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Approximate city centres, for mock visualization only (not airport data).
DEMO_CENTRES = {'KUF':(50.15,53.20),'GOJ':(44.01,56.33),'UFA':(55.97,54.74),'KZN':(49.12,55.79),'MRV':(43.13,44.21),'PEE':(56.25,58.01),'SVX':(60.60,56.84),'CEK':(61.40,55.16),'TJM':(65.53,57.15),'VOG':(44.52,48.71),'GSV':(46.03,51.53),'OMS':(73.37,54.99)}
MOSCOW = (37.62,55.75)


def distance_km(a,b):
    lon1,lat1,lon2,lat2=map(math.radians,(*a,*b))
    h=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371*2*math.asin(min(1, math.sqrt(h)))


def route_points(row,use_mocks):
    result=[]
    for prefix in ['origin','dest']:
        try:
            lat,lon=float(row.get(prefix+'_lat')),float(row.get(prefix+'_lon'))
            point=(lon,lat) if math.isfinite(lat) and math.isfinite(lon) and abs(lat)<=90 and abs(lon)<=180 else None
        except (TypeError,ValueError):point=None
        result.append(point or (DEMO_CENTRES.get(row[prefix]) if use_mocks else None))
    return result


def make_route_figure(routes_df,scored_cities,use_mocks=False,selected_route=None):
    fig=go.Figure(); missing=[]; points={}
    for row in routes_df.to_dict('records'):
        a,b=route_points(row,use_mocks)
        if a is None or b is None:
            missing.append(f"{row['origin']} → {row['dest']}");continue
        points[row['origin']]=a;points[row['dest']]=b
        fig.add_trace(go.Scattergeo(lon=[a[0],b[0]],lat=[a[1],b[1]],mode='lines',line=dict(color='#cb2440',width=2),name=f"{row['origin']} → {row['dest']}",showlegend=False))
    points.update(routes_df.attrs.get('city_coordinates', {}))
    for city in scored_cities:
        if city.iata not in points and use_mocks and city.iata in DEMO_CENTRES:points[city.iata]=DEMO_CENTRES[city.iata]
    lookup={c.iata:c for c in scored_cities}
    for top in [False,True]:
        codes=[code for code in points if bool(getattr(lookup.get(code),'is_top3',False))==top]
        if codes:fig.add_trace(go.Scattergeo(lon=[points[c][0] for c in codes],lat=[points[c][1] for c in codes],mode='markers+text',text=[getattr(lookup.get(c),'city_name',c) for c in codes],textposition='top center',marker=dict(size=15 if top else 8,color='#cb2440' if top else '#172a45'),name='Топ-3' if top else 'Города'))
    if selected_route is not None:
        a,b=route_points(selected_route,use_mocks)
        if a and b:
            for pts,name,color,dash in [([a,MOSCOW,b],'Через Москву','#d92344','dash'),([a,b],'Прямой маршрут','#119968','solid')]:
                fig.add_trace(go.Scattergeo(lon=[v[0] for v in pts],lat=[v[1] for v in pts],mode='lines',line=dict(color=color,width=4,dash=dash),name=name))
    fig.update_geos(scope='asia',projection_type='natural earth',showland=True,landcolor='#e7edf3',showcountries=True,countrycolor='white',showocean=True,oceancolor='#f6f9fc',lonaxis_range=[25,90],lataxis_range=[38,68])
    fig.update_layout(height=560,margin=dict(l=0,r=0,t=10,b=0),legend=dict(orientation='h'))
    return fig,missing


def render_route_network_map(routes_df,scored_cities,use_mocks=False):
    if routes_df.empty:st.warning('Нет маршрутов.');return
    choices=['Вся сеть']+[f"{r.origin} → {r.dest}" for r in routes_df.itertuples()]
    index=st.selectbox('Сравнить с пересадкой в Москве',range(len(choices)),format_func=lambda i:choices[i],key='rw_detour')
    row=routes_df.iloc[index-1].to_dict() if index else None
    fig,missing=make_route_figure(routes_df,scored_cities,use_mocks,row)
    st.plotly_chart(fig,use_container_width=True)
    if missing:st.warning('Нет координат маршрутов: '+', '.join(missing))
    if row:
        a,b=route_points(row,use_mocks)
        if a and b:
            direct=distance_km(a,b);via=distance_km(a,MOSCOW)+distance_km(MOSCOW,b)
            st.info(f'Геометрическая длина: напрямую {direct:.0f} км · через Москву {via:.0f} км · крюк {via/direct:.2f}×' if direct else 'Совпадающие точки маршрута.')
            st.caption('Расстояния по большой окружности; Москва — условный центр города. Это не фактические трассы. Экономия времени требует расписаний и длительности стыковки.')
            if 'flight_time_min' in row:st.write(f"Прямой перелёт по данным провайдера: {row['flight_time_min']} мин.")
    if use_mocks:st.caption('ДЕМО: условные данные и приблизительные центры городов, не координаты аэропортов.')
    absent=[c.iata for c in scored_cities if c.iata not in set(routes_df.origin)|set(routes_df.dest)]
    if absent and not use_mocks:st.warning('Города вне маршрутов без координат в CityScoreDTO: '+', '.join(absent)+'. Dev 1 должен передать их координаты для полного слоя кандидатов.')
    if not 8<=len(routes_df)<=12:st.warning('Итоговая сеть должна содержать 8–12 маршрутов.')
    st.dataframe(routes_df,use_container_width=True,hide_index=True)
    st.download_button('Скачать маршруты · CSV',routes_df.to_csv(index=False).encode('utf-8-sig'),'routes.csv','text/csv')
