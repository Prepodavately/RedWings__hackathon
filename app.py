"""Dev 4: shared Streamlit entry point, USE_MOCKS=1 or USE_MOCKS=0."""
import os
import json
from dataclasses import asdict, replace
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from src.ui.sidebar_controls import render_sidebar_controls
from src.ui.kpi_cards import render_comparison_kpis
from src.ui.map_renderer import render_route_network_map
from src.ui.roadmap_chart import render_sj100_roadmap
from src.ui.provider_bridge import get_providers, load_comparison, load_routes, ProviderNotReady


def main():
    st.set_page_config(page_title='Red Wings · Network Lab',page_icon='✈',layout='wide')
    st.markdown('''<style>.block-container{max-width:1450px;padding-top:2rem}h1{letter-spacing:-1.4px}div[data-testid="stMetric"]{border:1px solid #dce1eb;border-radius:12px;padding:16px}div[data-testid="stMetricValue"]{font-size:1.8rem}.eyebrow{color:#c9233e;font-weight:800;letter-spacing:3px;font-size:12px}</style>''',unsafe_allow_html=True)
    st.markdown('<div class="eyebrow">RED WINGS / NETWORK LAB</div>',unsafe_allow_html=True)
    st.title('Где начинается следующий маршрут')
    st.caption('Новый региональный хаб или прямые рейсы · Дашборд команды')
    mode=os.getenv('USE_MOCKS','1')
    if mode not in {'0','1'}:st.error('USE_MOCKS должен быть 0 или 1.');return
    use_mocks=mode=='1'
    if use_mocks:
        st.warning('USE_MOCKS=1 · Заглушки команды возвращают постоянные числа. Ползунки передаются провайдеру, но текущие заглушки их игнорируют. Это демонстрация интерфейса, не проверенный бизнес-расчёт.')
    else:st.info('USE_MOCKS=0 · Подключены модули Dev 1–3. Интерфейс не подменяет их результаты демонстрационными.')
    weights,params=render_sidebar_controls()
    try:
        scoring,economics,network=get_providers(use_mocks)
        cities,comparison=load_comparison(scoring,economics,weights,params)
    except (ProviderNotReady,NotImplementedError,FileNotFoundError,ImportError) as exc:
        st.error(str(exc));st.info('Для работы над интерфейсом запустите USE_MOCKS=1. Для настоящих расчётов дождитесь реализации модулей команды.');return
    except Exception as exc:
        st.error(f'Ошибка расчётного модуля: {type(exc).__name__}: {exc}');return
    tabs=st.tabs(['01 · Сравнение','02 · Города','03 · Проверка сценариев','04 · Данные и запуск'])
    with tabs[0]:
        render_comparison_kpis(comparison)
        st.subheader('Маршрутная сеть')
        selected=st.radio('Стратегия на карте',['hub','p2p'],format_func=lambda x:{'hub':'Новый хаб','p2p':'Прямые рейсы'}[x],horizontal=True,key='rw_network')
        routes=None
        try:
            routes=load_routes(network,selected,params.hub_iata)
            render_route_network_map(routes,cities,use_mocks=use_mocks)
        except Exception as exc:st.error(f'Маршруты недоступны: {exc}')
    with tabs[1]:
        st.subheader('Рейтинг от модуля скоринга')
        frame=pd.DataFrame([asdict(c) for c in cities]).sort_values('rank')
        if len(frame)<10:st.warning(f'Сейчас в ответе {len(frame)} города. Для лонглиста требуется не менее 10.')
        if frame[frame.is_top3].iata.isin(['SVX','MOW','SVO','VKO','DME','ZIA']).any():
            st.warning('В топ-3 провайдера есть действующая база в Москве или Екатеринбурге. Она не подходит в качестве нового дополнительного хаба; состав кандидатов должен проверить Dev 2.')
        fig=px.bar(frame.sort_values('total_score'),x='total_score',y='city_name',orientation='h',color_discrete_sequence=['#c9233e'],labels={'total_score':'Оценка провайдера','city_name':''})
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='white',margin=dict(t=10,l=0,r=10,b=0),height=360)
        st.plotly_chart(fig,use_container_width=True)
        st.dataframe(frame,hide_index=True,use_container_width=True)
        st.download_button('Скачать рейтинг · CSV',frame.to_csv(index=False).encode('utf-8-sig'),'city_scores.csv','text/csv')
        st.caption('Интерфейс не меняет баллы, места и флаг is_top3. За расчёт рейтинга отвечает провайдер.')
    with tabs[2]:
        st.subheader('Сравнение обоих сценариев')
        st.caption('Для каждого сценария вызывается evaluate_hypotheses с теми же параметрами и соответствующим scenario. В текущих заглушках ответы совпадают.')
        try:
            bundles={scenario:load_comparison(scoring,economics,weights,replace(params,scenario=scenario))[1] for scenario in ['base','conservative']}
            rows=[]
            for scenario,bundle in bundles.items():
                for result in [bundle.hub,bundle.p2p]: rows.append({'scenario':scenario,**asdict(result)})
            scenario_frame=pd.DataFrame(rows)
            st.dataframe(scenario_frame,hide_index=True,use_container_width=True)
            st.download_button('Скачать 4 варианта · CSV',scenario_frame.to_csv(index=False).encode('utf-8-sig'),'scenarios.csv','text/csv')
        except Exception as exc:st.error(f'Не удалось сравнить сценарии: {exc}')
        st.subheader('Проверить снижение загрузки')
        test_load=st.slider('Тестовая загрузка, %',0.0,100.0,max(0.0,params.load_factor_pct-10),1.0,key='rw_test_load')
        try:
            _,alternative=load_comparison(scoring,economics,weights,replace(params,load_factor_pct=test_load))
            st.dataframe(pd.DataFrame([{'Стратегия':base.title,'Текущая выручка, млн ₽':base.annual_revenue_mln_rub,'При тестовой загрузке, млн ₽':alt.annual_revenue_mln_rub,'Разница, млн ₽':alt.annual_revenue_mln_rub-base.annual_revenue_mln_rub} for base,alt in [(comparison.hub,alternative.hub),(comparison.p2p,alternative.p2p)]]),hide_index=True,use_container_width=True)
        except Exception as exc:st.error(f'Проверка загрузки недоступна: {exc}')
    with tabs[3]:
        st.subheader('Переданные параметры')
        payload={'use_mocks':use_mocks,'weights':asdict(weights),'financial_input':asdict(params)}
        st.json(payload)
        st.download_button('Скачать параметры · JSON',json.dumps(payload,ensure_ascii=False,indent=2),'parameters.json','application/json')
        st.subheader('Проверяемость данных')
        if routes is not None:
            for field in ['source','method']:
                if field not in routes.columns:st.warning(f'В таблице нет поля {field}. Для защиты по каждому маршруту нужны источник и/или метод оценки пассажиров и частоты.')
            st.dataframe(routes,hide_index=True,use_container_width=True)
        st.markdown('''Перед защитой команда должна согласовать:
- единицы `weekly_freq_per_route` и `freq`: вылеты или обороты;
- единицу `market_share_delta_pct`: проценты или процентные пункты;
- период и направление учёта `pax`, правила учёта пересадочных пассажиров;
- источники и методы оценок для каждого маршрута;
- реальный расчёт флота, стыковок и расписания.
''')
        settings=Path(__file__).parent/'config/settings.yaml'
        if settings.exists():
            import yaml
            try:
                config=yaml.safe_load(settings.read_text()) or {}
                baseline=config.get('market',{}).get('red_wings_base_passengers_2025')
                if baseline is not None and baseline!=2700000:
                    st.warning(f'Проверить базу сравнения: config/settings.yaml содержит {baseline:,} пассажиров Red Wings за 2025 год; в предоставленной справке кейса — 2 700 000. Интерфейс не исправляет константы модели автоматически.')
            except (ValueError,TypeError,yaml.YAMLError) as exc:st.warning(f'Не удалось прочитать настройки: {exc}')
        render_sj100_roadmap(routes,comparison)
    st.divider();st.caption('Учебный проект команды · Не официальный продукт Red Wings')

if __name__=='__main__':main()
