import os
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
from src.parsers.build_dataset import build_processed_tables, build_cities_features
from src.scoring.city_scorer import score_cities
from src.ui.gravity_panel import build_analysis, make_gravity_figure

ROOT=Path(__file__).resolve().parents[1]


def test_live_analysis_alignment_and_unknown_competition():
    build_processed_tables()
    features=build_cities_features()
    routes=pd.read_parquet(ROOT/'data/processed/routes_proof.parquet')
    ranking=score_cities(features,hypothesis='hub').table
    original=features.copy(deep=True)
    cities,details,matrix,comparison,pairs=build_analysis(features,routes,ranking)
    assert matrix.shape==(12,12) and len(pairs)==132
    assert not pairs.duplicated(['origin','dest']).any()
    assert comparison.set_index('iata').loc['SVX','eligible']==False
    assert pd.isna(comparison.set_index('iata').loc['SVX','gravity_rank'])
    assert cities.set_index('iata').loc['MRV','population_gap_people']==61384
    assert matrix.attrs['missing_competition_pairs']==0
    pd.testing.assert_frame_equal(features,original)
    fig=make_gravity_figure(matrix,cities)
    assert np.isnan(np.diag(fig.data[0].z)).all()
    one=routes.iloc[0]
    reduced=routes.iloc[1:]
    _,_,missing,_,missing_pairs=build_analysis(features,reduced,ranking)
    assert missing.attrs['missing_competition_pairs']==1
    row=missing_pairs.query('origin == @one.origin_iata and dest == @one.dest_iata').iloc[0]
    assert not row.competition_observed


def test_population_slider_changes_only_gravity_analysis():
    features=build_cities_features()
    routes=pd.read_parquet(ROOT/'data/processed/routes_proof.parquet')
    ranking=score_cities(features,hypothesis='hub').table
    low=build_analysis(features,routes,ranking,lam=0)
    high=build_analysis(features,routes,ranking,lam=1)
    assert (low[0].effective_population_mln>=high[0].effective_population_mln).all()
    assert not np.allclose(low[2],high[2])
    pd.testing.assert_series_equal(low[3].total_score,high[3].total_score)


def test_app_gravity_controls_and_exports():
    with patch.dict(os.environ,{'USE_MOCKS':'0'}):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=60).run()
        assert not app.exception and not app.error
        app.slider(key='gravity_lambda').set_value(0.0).run()
        app.slider(key='gravity_gamma').set_value(1.5).run()
        assert not app.exception and not app.error
        assert any('Сумма города' in w.value for w in app.warning)
        assert len(app.get('download_button'))>=10
