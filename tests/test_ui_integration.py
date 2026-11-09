import os
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from src.schemas.contracts import ScoringWeights,FinModelInput
from src.mocks import mock_provider
from src.ui.provider_bridge import load_comparison,load_routes,get_providers,ProviderNotReady
from src.ui.map_renderer import make_route_figure
ROOT=Path(__file__).resolve().parents[1]


def test_forwarding_contracts():
    weights=ScoringWeights(.1,.2,.3,.4);params=FinModelInput(load_factor_pct=73,scenario='conservative')
    with patch.object(mock_provider,'get_scored_cities', wraps=mock_provider.get_scored_cities) as scoring, patch.object(mock_provider,'evaluate_hypotheses', wraps=mock_provider.evaluate_hypotheses) as economics:
        cities,bundle=load_comparison(scoring,economics,weights,params)
        scoring.assert_called_once_with(weights)
        economics.assert_called_once_with(params,[c for c in cities if c.is_top3])
        assert bundle.p2p.annual_passengers==449280


def test_incomplete_backend_has_no_mock_fallback():
    scoring,economics,_=get_providers(False)
    with pytest.raises(ProviderNotReady):load_comparison(scoring,economics,ScoringWeights(),FinModelInput())


def test_routes_contract():
    with pytest.raises(ProviderNotReady):load_routes(lambda *a: None,'hub','KUF')
    with pytest.raises(ProviderNotReady):load_routes(lambda *a: pd.DataFrame({'city':['X']}),'hub','KUF')


def test_real_map_does_not_use_mock_centres():
    r=mock_provider.get_network_routes('hub');cities=mock_provider.get_scored_cities(ScoringWeights())
    fig,missing=make_route_figure(r,cities,False)
    assert not fig.data and len(missing)==2
    fig,missing=make_route_figure(r,cities,True)
    assert len(fig.data)==3 and not missing


def test_map_uses_provider_coordinates():
    r=pd.DataFrame([{'origin':'AAA','dest':'BBB','origin_lat':50,'origin_lon':40,'dest_lat':55,'dest_lon':60}])
    fig,missing=make_route_figure(r,[],False)
    assert not missing and list(fig.data[0].x)==[40,60]


def test_mock_ui_and_input_forwarding():
    with patch.dict(os.environ,{'USE_MOCKS':'1'}),patch.object(mock_provider,'evaluate_hypotheses',wraps=mock_provider.evaluate_hypotheses) as economics:
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        assert not app.exception
        assert len(app.metric)==8
        app.slider(key='rw_load').set_value(65.0)
        app.slider(key='rw_fare').set_value(9000.0)
        app.radio(key='rw_scenario').set_value('conservative').run()
        assert not app.exception
        assert any(call.args[0].load_factor_pct==65 and call.args[0].avg_fare_rub==9000 and call.args[0].scenario=='conservative' for call in economics.call_args_list)
        assert {call.args[0].scenario for call in economics.call_args_list}=={'base','conservative'}
        app.radio(key='rw_network').set_value('p2p').run();assert not app.exception
        app.text_input(key='rw_hub').set_value('GOJ').run();assert not app.exception
        app.button[0].click().run();assert app.slider(key='rw_load').value==84.0 and not app.exception


def test_zero_weights_and_invalid_hub():
    with patch.dict(os.environ,{'USE_MOCKS':'1'}):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        for key in ['w_population','w_hub_distance','w_competitor_gap','w_tourism_demand']:app.slider(key='rw_'+key).set_value(0)
        app.run();assert not app.exception
        app.text_input(key='rw_hub').set_value('SVX').run()
        assert app.error and not app.exception


def test_real_ui_shows_not_ready():
    with patch.dict(os.environ,{'USE_MOCKS':'0'}):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        assert not app.exception and app.error
        assert len(app.metric)==0
