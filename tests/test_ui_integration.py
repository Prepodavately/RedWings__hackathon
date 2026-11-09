import os
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from src.schemas.contracts import FinModelInput,ScoringWeights
from src.ui.provider_bridge import load_routes,ProviderNotReady
from src.ui.map_renderer import make_route_figure
from src.ui.kpi_cards import build_strategy_grid
ROOT=Path(__file__).resolve().parents[1]


def test_route_aliases_and_validation():
    frame=pd.DataFrame([dict(origin_iata='AAA',dest_iata='BBB',lat_o=50,lon_o=40,lat_d=55,lon_d=60)])
    r=load_routes(lambda *a:frame,'hub','AAA')
    assert r.origin.iloc[0]=='AAA' and r.dest_lon.iloc[0]==60
    with pytest.raises(ProviderNotReady):load_routes(lambda *a:None,'hub','AAA')


def test_no_invented_real_coordinates():
    fig,missing=make_route_figure(pd.DataFrame([dict(origin='AAA',dest='BBB')]),[],False)
    assert len(missing)==1 and not fig.data


def test_real_network_and_full_candidate_layer():
    from src.parsers.build_dataset import build_processed_tables,build_cities_features,get_network_routes
    from src.scoring.city_scorer import get_scored_cities
    build_processed_tables(); features=build_cities_features()
    cities=get_scored_cities(ScoringWeights(),data=features,hypothesis='hub')
    for h in ['hub','p2p']:
        r=load_routes(get_network_routes,h,'KUF')
        assert len(r)==10 and len({tuple(sorted(x)) for x in zip(r.origin,r.dest)})==10
        r.attrs['city_coordinates']={x.iata:(x.lon,x.lat) for x in features.itertuples()}
        fig,missing=make_route_figure(r,cities,False,r.iloc[0].to_dict())
        assert not missing and sum(len(t.lon) for t in fig.data if 'markers' in t.mode)==12
        assert any(t.name=='Через Москву' for t in fig.data)


@pytest.mark.parametrize('mode',['0','1'])
def test_app_runs_and_recalculates(mode):
    with patch.dict(os.environ,{'USE_MOCKS':mode}):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=60).run()
        assert not app.exception and not app.error and len(app.metric)>=8
        before=[m.value for m in app.metric]
        app.slider(key='rw_load').set_value(70.0).run()
        assert not app.exception and not app.error and [m.value for m in app.metric]!=before
        app.radio(key='rw_scenario').set_value('conservative').run()
        assert not app.exception and not app.error
        app.selectbox(key='rw_detour').set_value(1).run()
        assert not app.exception and not app.error
        app.slider(key='rw_w_population').set_value(100)
        app.slider(key='rw_w_tourism_demand').set_value(0).run()
        assert not app.exception and not app.error
        app.selectbox(key='rw_live_hub').set_value(app.selectbox(key='rw_live_hub').value).run()
        assert not app.exception


def test_real_grid_and_sensitivity():
    from src.parsers.build_dataset import build_cities_features
    from src.scoring.city_scorer import score_cities,get_scored_cities,weight_sensitivity
    from src.models.unit_economics import evaluate_hypotheses
    f=build_cities_features();result=score_cities(f,ScoringWeights(),hypothesis='hub')
    cities=get_scored_cities(ScoringWeights(),data=f,hypothesis='hub');top=[c for c in cities if c.is_top3]
    grid=build_strategy_grid(evaluate_hypotheses,FinModelInput(hub_iata=top[0].iata),top)
    assert len(grid)==117 and set(grid.winner)<={'hub','p2p'}
    sensitivity=weight_sensitivity(result,n_samples=200)
    assert sensitivity.top3_frequency.between(0,1).all()
    assert abs(sensitivity.top3_frequency.sum()-3)<1e-8


def test_heatmap_loss_overlay_and_marker():
    from src.ui.kpi_cards import make_strategy_heatmap
    rows=[]
    for fare in range(6000,12001,500):
        for frequency in range(2,11):
            rows.append(dict(fare=fare,frequency=frequency,winner='p2p',hub=-20,p2p=-10 if fare==6000 else 5))
    frame=pd.DataFrame(rows)
    fig,inside=make_strategy_heatmap(frame,FinModelInput())
    assert inside
    assert sum(pd.notna(fig.data[1].z).flatten())==9
    assert fig.data[-1].name=='Ваш сценарий'
    outside,inside=make_strategy_heatmap(frame,FinModelInput(avg_fare_rub=13500))
    assert not inside and all(t.name!='Ваш сценарий' for t in outside.data)
