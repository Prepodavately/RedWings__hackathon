"""Integrated team dashboard. Real providers by default; explicit mock mode."""
import os
import hashlib
import warnings
from dataclasses import asdict, replace
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from src.ui.sidebar_controls import render_sidebar_controls
from src.ui.kpi_cards import render_comparison_kpis, render_strategy_heatmap
from src.ui.map_renderer import render_route_network_map
from src.ui.provider_bridge import load_routes
from src.ui.research_panels import render_research, render_route_passport

ROOT=Path(__file__).parent

@st.cache_data(show_spinner='Подготовка таблиц команды…')
def prepare_data(signature):
    from src.parsers.build_dataset import build_processed_tables, build_cities_features
    build_processed_tables()
    return build_cities_features()


def main():
    st.set_page_config(page_title='Red Wings · Network Lab',page_icon='✈',layout='wide')
    from src.ui.visual_style import apply_style, hero
    apply_style();hero()
    mode=os.getenv('USE_MOCKS','0')
    if mode not in {'0','1'}:st.error('USE_MOCKS должен быть 0 или 1');return
    demo=mode=='1'
    st.warning('ДЕМО: искусственные данные и условная экономика.' if demo else 'Модули команды подключены. Это сценарная модель: спрос, затраты и субсидии частично заданы допущениями, а не наблюдениями.')
    weights,params=render_sidebar_controls()
    result=None;features=None
    try:
        if demo:
            from src.mocks.mock_provider import get_scored_cities, evaluate_hypotheses, get_network_routes
            cities=get_scored_cities(weights)
            top=[c for c in cities if c.is_top3 and c.iata!='SVX']
        else:
            from src.parsers.build_dataset import get_network_routes
            from src.scoring.city_scorer import score_cities, get_scored_cities
            from src.models.unit_economics import evaluate_hypotheses
            files=sorted((ROOT/'data/raw').glob('*'))+sorted((ROOT/'src/parsers').glob('*.py'))
            signature=hashlib.sha256(b''.join(f.read_bytes() for f in files if f.is_file())).hexdigest()
            features=prepare_data(signature)
            with warnings.catch_warnings():
                warnings.simplefilter('ignore',UserWarning)
                result=score_cities(features,weights,mode='auto',hypothesis='hub')
                cities=get_scored_cities(weights,data=features,mode='auto',hypothesis='hub')
            top=[c for c in cities if c.is_top3]
            if result.mode!='case':st.warning('Рейтинг предварительный: нет полного набора доказательств для режима case. Подробнее во вкладке «Источники и план».')
        options=[c.iata for c in top]
        if not options:raise ValueError('Нет допустимых кандидатов на хаб')
        if st.session_state.get('rw_live_hub') not in options:st.session_state['rw_live_hub']=options[0]
        names={c.iata:c.city_name for c in cities}
        hub=st.sidebar.selectbox('Хаб из актуального топ-3',options,format_func=lambda x:names[x]+' · '+x,key='rw_live_hub')
        networks={h:load_routes(get_network_routes,h,hub) for h in ['hub','p2p']}
        counts={h:len({tuple(sorted((a,b))) for a,b in zip(r.origin,r.dest)}) for h,r in networks.items()}
        if any(not 8<=n<=12 for n in counts.values()):raise ValueError(f'Сеть вне диапазона 8–12 уникальных пар: {counts}')
        params=replace(params,hub_iata=hub)
        def economics(p,c):
            # Each hypothesis is calculated with the size of its own visible network.
            if counts['hub']==counts['p2p']:
                return evaluate_hypotheses(replace(p,active_routes_count=counts['hub']),c)
            raise ValueError('Сети имеют разное число маршрутов. Для сравнения согласуйте единый набор с Dev 1 и Dev 3.')
        params=replace(params,active_routes_count=counts['hub'])
        st.sidebar.info(f"В расчёте и на карте: {counts['hub']} маршрутов хаба, {counts['p2p']} P2P. Размер сети задаёт Dev 1.")
        comparison=economics(params,top)
    except Exception as exc:st.error(f'Не удалось собрать данные и расчёт: {exc}');return
    tabs=st.tabs(['Обзор решения','Маршрутная сеть','Города и устойчивость','Стресс-тест','Источники и план'])
    with tabs[0]:
        render_comparison_kpis(comparison)
        st.caption('Пассажиры считаются по участкам перелёта, не как уникальные люди. Прирост доли предполагает отсутствие перетока с существующих рейсов RW.')
        rows=[]
        for scenario in ['base','conservative']:
            b=economics(replace(params,scenario=scenario),top)
            for item in [b.hub,b.p2p]:rows.append({'scenario':scenario,**asdict(item)})
        st.subheader('Обе стратегии в обоих сценариях')
        summary=pd.DataFrame(rows)
        summary['Стратегия']=summary.code.map({'hub':'Хаб','p2p':'P2P'})
        summary['Сценарий']=summary.scenario.map({'base':'Базовый','conservative':'Осторожный'})
        fig=px.bar(summary,x='Сценарий',y='ebitdar_mln_rub',color='Стратегия',barmode='group',color_discrete_map={'Хаб':'#D82F4C','P2P':'#247AAB'},labels={'ebitdar_mln_rub':'EBITDAR, млн ₽'},text_auto='.0f')
        fig.add_hline(y=0,line_color='#8998AC')
        st.plotly_chart(fig,use_container_width=True)
        with st.expander('Все показатели сценариев'):st.dataframe(summary,hide_index=True,use_container_width=True)
    with tabs[1]:
        strategy=st.radio('Сеть',['hub','p2p'],index=0 if comparison.winner=='hub' else 1,format_func=lambda x:'Новый хаб' if x=='hub' else 'Прямые рейсы',horizontal=True)
        routes=networks[strategy].copy()
        if features is not None:routes.attrs['city_coordinates']={r.iata:(r.lon,r.lat) for r in features.itertuples()}
        routes['proposed_base_fare_rub']=params.avg_fare_rub
        render_route_network_map(routes,cities,demo)
        render_route_passport(routes)
    with tabs[2]:
        frame=result.table if result is not None else pd.DataFrame([asdict(c) for c in cities])
        st.plotly_chart(px.bar(frame.sort_values('total_score'),y='city_name',x='total_score',orientation='h',color='is_top3',color_discrete_map={True:'#D82F4C',False:'#C6D3E4'},labels={'city_name':'','total_score':'Итоговый балл','is_top3':'Топ-3'},height=490),use_container_width=True)
        st.dataframe(frame,hide_index=True,use_container_width=True)
        render_research(result,params,demo)
    with tabs[3]:
        render_strategy_heatmap(economics,params,top)
        st.subheader('Запас до безубыточности')
        rows=[]
        for load in range(50,96,5):
            b=economics(replace(params,load_factor_pct=float(load)),top)
            for item in [b.hub,b.p2p]:rows.append({'Загрузка на входе, %':load,'Стратегия':item.title,'EBITDAR, млн ₽':item.ebitdar_mln_rub})
        fig=px.line(pd.DataFrame(rows),x='Загрузка на входе, %',y='EBITDAR, млн ₽',color='Стратегия',color_discrete_map={comparison.hub.title:'#D82F4C',comparison.p2p.title:'#247AAB'},markers=True);fig.add_hline(y=0,line_dash='dash')
        st.plotly_chart(fig,use_container_width=True)
    with tabs[4]:
        st.subheader('Происхождение и ограничения')
        st.json({'mode':mode,'weights':asdict(weights),'params':asdict(params),'network_pairs':counts})
        if result is not None:
            for line in result.limitations:st.write('• '+line)
            st.dataframe(result.audit,hide_index=True,use_container_width=True)
            st.download_button('Скачать аудит критериев',result.audit.to_csv(index=False).encode('utf-8-sig'),'scoring_audit.csv')
        for h,r in networks.items():
            st.write(f'**{h}: {len(r)} строк, {counts[h]} уникальных пар**')
            missing={c:int(r[c].isna().sum()) if c in r else len(r) for c in ['proof_source','competitor_fare_rub','flight_time_min','launch_quarter']}
            st.write({'Пустые значения':missing})
            st.download_button('Скачать сеть '+h,r.to_csv(index=False).encode('utf-8-sig'),h+'_network.csv')
        st.subheader('Предложенные кварталы запуска')
        launch_rows=[]
        for code,frame in networks.items():
            if 'launch_quarter' in frame:
                for quarter,count in frame.groupby('launch_quarter').size().items():launch_rows.append({'Стратегия':code,'Квартал':quarter,'Маршрутов':int(count)})
        if launch_rows:
            st.dataframe(pd.DataFrame(launch_rows),hide_index=True,use_container_width=True)
            st.caption('Кварталы переданы Dev 1. Это предложение, не проверенное расписание и не план поставок. Запуск до второй половины 2027 года требует обоснования существующим флотом.')
        st.info('Годовая экономика — полный год после доступности самолётов. Кварталы запуска из данных не означают подтверждённый план флота. Субсидия на маршрут не гарантирована наличием его в перечне другого перевозчика.')
        if features is not None:
            st.dataframe(features,hide_index=True,use_container_width=True)
            st.download_button('Скачать исходные признаки',features.to_csv(index=False).encode('utf-8-sig'),'features.csv')

if __name__=='__main__':main()
