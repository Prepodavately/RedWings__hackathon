"""Thin adapter: preserve team contracts, never silently substitute demo data."""
import importlib
import pandas as pd
from src.schemas.contracts import CityScoreDTO, ComparisonBundleDTO


class ProviderNotReady(ValueError):
    pass


def get_providers(use_mocks):
    if use_mocks:
        m=importlib.import_module('src.mocks.mock_provider')
        return m.get_scored_cities,m.evaluate_hypotheses,m.get_network_routes
    return (importlib.import_module('src.scoring.city_scorer').get_scored_cities,
            importlib.import_module('src.models.unit_economics').evaluate_hypotheses,
            importlib.import_module('src.parsers.build_dataset').get_network_routes)


def load_comparison(scoring,economics,weights,params):
    cities=scoring(weights)
    if not isinstance(cities,list) or not cities or not all(isinstance(c,CityScoreDTO) for c in cities):
        raise ProviderNotReady('Dev 2: get_scored_cities должен вернуть непустой список CityScoreDTO. Сейчас модуль не готов или нарушен контракт.')
    top=[c for c in cities if c.is_top3]
    if not top:raise ProviderNotReady('Dev 2: в рейтинге не обозначены города is_top3.')
    comparison=economics(params,top)
    if not isinstance(comparison,ComparisonBundleDTO) or comparison.winner not in ('hub','p2p'):
        raise ProviderNotReady('Dev 3: evaluate_hypotheses должен вернуть ComparisonBundleDTO. Сейчас модуль не готов или нарушен контракт.')
    return cities,comparison


def load_routes(provider,hypothesis,hub_iata):
    routes=provider(hypothesis,hub_iata)
    if not isinstance(routes,pd.DataFrame):raise ProviderNotReady('Dev 1: get_network_routes должен вернуть DataFrame. Модуль маршрутов пока не готов.')
    if not {'origin','dest'}<=set(routes.columns):raise ProviderNotReady('Dev 1: в таблице маршрутов нужны origin и dest.')
    return routes
