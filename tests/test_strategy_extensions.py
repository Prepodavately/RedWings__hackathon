import os
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from src.ui.strategy_extensions import route_economics
from src.models.unit_economics import project_path_to_top2_airline
from src.schemas.contracts import FinModelInput, ScoringWeights
from src.parsers.build_dataset import build_cities_features
from src.scoring.city_scorer import get_scored_cities


def test_route_belf_is_not_clipped_and_unknown_not_profitable():
    source=pd.DataFrame({'competitor_fare_rub':[5000,5000,None], 'flight_cost_rub':[600000,400000,100000]})
    result=route_economics(source,100,84)
    assert result.belf_raw_pct.iloc[0]==120
    assert result.contribution_rub.iloc[0]==-180000
    assert result.contribution_rub.iloc[1]==20000
    assert result.passes_cost_test.tolist()==[False,True,False]
    assert 'belf_raw_pct' not in source


def test_growth_benchmark_and_full_cannibalization():
    cities=get_scored_cities(ScoringWeights(),data=build_cities_features(),hypothesis='hub')
    top=[c for c in cities if c.is_top3]
    rows=project_path_to_top2_airline(FinModelInput(),top,benchmark_growth_pct=5,cannibalization_pct=100)
    assert rows[-1]['reference_second_pax_mln']==pytest.approx(13.8*1.05**5)
    assert all(r['total_pax_mln']==2.7 and r['market_rank_rf'] is None for r in rows)
    assert rows[-1]['fleet_constrained_total_pax_mln']==2.7
    assert not rows[-1]['target_reached']
    with pytest.raises(ValueError):project_path_to_top2_airline(FinModelInput(),top,cannibalization_pct=-1)


def test_new_controls_in_real_app():
    root=Path(__file__).resolve().parents[1]
    with patch.dict(os.environ,{'USE_MOCKS':'0'}):
        app=AppTest.from_file(str(root/'app.py'),default_timeout=90).run()
        assert not app.exception and not app.error
        app.slider(key='rw_transit_threshold').set_value(0.0).run()
        assert not app.exception and not app.error
        app.checkbox(key='rw_route_fare').set_value(True).run()
        app.checkbox(key='rw_route_positive').set_value(True).run()
        for key in ['rw_digital_interline','rw_digital_ancillary','rw_digital_recovery']:
            app.checkbox(key=key).set_value(False)
        app.slider(key='rw_growth_benchmark').set_value(5.0)
        app.slider(key='rw_growth_cannibal').set_value(25.0).run()
        assert not app.exception and not app.error
