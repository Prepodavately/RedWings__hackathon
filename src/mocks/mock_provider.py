"""Synthetic fixtures for UI demonstration; no verified traffic or forecasts."""
from dataclasses import asdict
from math import asin, ceil, cos, radians, sin, sqrt

import pandas as pd

from src.schemas.contracts import CityScoreDTO, ComparisonBundleDTO, HypothesisResultDTO

# City-centre coordinates are only for a clearly labelled demonstration map.
CITIES = [
    ('KUF', 'Самара', 53.20, 50.15), ('KZN', 'Казань', 55.79, 49.12),
    ('UFA', 'Уфа', 54.74, 55.97), ('GOJ', 'Нижний Новгород', 56.33, 44.01),
    ('SVX', 'Екатеринбург', 56.84, 60.60), ('PEE', 'Пермь', 58.01, 56.25),
    ('CEK', 'Челябинск', 55.16, 61.40), ('MRV', 'Минеральные Воды', 44.21, 43.13),
    ('TJM', 'Тюмень', 57.15, 65.53), ('VOG', 'Волгоград', 48.71, 44.52),
    ('GSV', 'Саратов', 51.53, 46.03), ('OMS', 'Омск', 54.99, 73.37),
]


def get_scored_cities(weights):
    values = list(asdict(weights).values())
    total = sum(values)
    values = [value / total for value in values] if total > 0 else [.3, .2, .3, .2]
    scores = [sum(w * v for w, v in zip(values, [95-i*5, 40+(i*13)%60, 90-(i*17)%65, 30+(i*23)%70])) for i in range(12)]
    order = sorted(range(12), key=lambda i: scores[i], reverse=True)
    return [CityScoreDTO(CITIES[i][0], CITIES[i][1], 'ДЕМО', round(1+i*.1, 2),
        round(1+i*.2, 2), round(scores[i], 2), rank, rank <= 3) for rank, i in enumerate(order, 1)]


def evaluate_hypotheses(params, top_cities):
    if params.hub_iata not in {city.iata for city in top_cities}:
        raise ValueError('Выбранный хаб должен присутствовать в списке городов')
    conservative = params.scenario == 'conservative'
    demand, cost_factor, subsidy_rate = (.87, 1.08, 95000) if conservative else (1., 1., 145000)
    flights = params.active_routes_count * params.weekly_freq_per_route * 2 * 52
    capacity = flights * params.aircraft_seats
    results = []
    for code in ['hub', 'p2p']:
        hub = code == 'hub'
        bonus = (3.2 if params.weekly_freq_per_route >= 6 else -2.5 if params.weekly_freq_per_route <= 3 else 0) if hub else (2.4 if params.weekly_freq_per_route <= 5 else 0)
        load = max(0, min(95, (params.load_factor_pct + bonus) * demand))
        passengers = round(capacity * load / 100)
        fare = params.avg_fare_rub * (.935 if hub else 1.055)
        subsidy = flights * (.45 if hub else .65) * subsidy_rate
        revenue = passengers * fare + subsidy
        costs = flights * (645000 if hub else 635000) * cost_factor + ((365e6 if conservative else 310e6) if hub else 115e6)
        profit = revenue - costs
        fleet = max(3 if hub else 2, ceil(params.active_routes_count * params.weekly_freq_per_route * (5.2 if hub else 4.6) / 18))
        results.append(HypothesisResultDTO(code, 'Гипотеза А: Хаб' if hub else 'Гипотеза Б: Прямые рейсы',
            passengers, revenue / 1e6, profit / 1e6, 100 * profit / revenue if revenue else 0,
            100 * passengers / 108900000, fleet, 100 * (costs - subsidy) / (capacity * fare)))
    hub, p2p = results
    winner = 'hub' if hub.ebitdar_mln_rub > p2p.ebitdar_mln_rub else 'p2p'
    return ComparisonBundleDTO(hub, p2p, winner, 'ДЕМО: условные коэффициенты для проверки интерфейса. Не является результатом модели Dev 3.')


def _distance(a, b):
    lat_a, lon_a, lat_b, lon_b = map(radians, (*a, *b))
    value = sin((lat_b-lat_a)/2)**2 + cos(lat_a)*cos(lat_b)*sin((lon_b-lon_a)/2)**2
    return 12742 * asin(min(1, sqrt(value)))


def get_network_routes(hypothesis, hub_iata='KUF'):
    lookup = {city[0]: city for city in CITIES}
    if hypothesis not in ('p2p', 'hub') or hub_iata not in lookup:
        raise ValueError('Неизвестная гипотеза или город хаба')
    pairs = [('KUF','GOJ'), ('KUF','PEE'), ('GOJ','UFA'), ('GOJ','MRV'), ('UFA','VOG'),
             ('KUF','CEK'), ('UFA','OMS'), ('GOJ','SVX'), ('KZN','CEK'), ('GSV','SVX')]
    if hypothesis == 'hub':
        pairs = [(hub_iata, city[0]) for city in CITIES if city[0] != hub_iata][:10]
    rows = []
    for index, (origin, destination) in enumerate(pairs):
        a, b = lookup[origin], lookup[destination]
        distance = _distance(a[2:], b[2:])
        detour = (_distance(a[2:], (55.7558, 37.6173)) + _distance((55.7558, 37.6173), b[2:])) / distance
        rows.append(dict(route_code=f'DEMO-{origin}-{destination}', route_code_source='ДЕМО',
            origin_iata=origin, origin_city=a[1], dest_iata=destination, dest_city=b[1],
            lat_o=a[2], lon_o=a[3], lat_d=b[2], lon_d=b[3], distance_km=round(distance),
            flight_time_min=round(30 + distance / 650 * 60), freq=5, pax=20000 + 1000*index,
            own_flights_weekly=2 if index < 3 else 0, competitor_flights_weekly=index % 4,
            competitor_carriers='ДЕМО', competitor_fare_rub=7000+200*index, subsidy_eligible=False,
            launch_quarter='Q3 2026' if index < 3 else 'Q2 2027' if index < 6 else 'Q1 2028',
            moscow_detour_ratio=round(detour, 2), rail_travel_hours=round(distance / 60, 1),
            rail_weak_competitor=distance / 60 > 12, belf_no_subsidy_pct=85.0,
            crj200_cask_advantage_pct=10.0, proof_source='ДЕМО: синтетические значения; наблюдения спроса отсутствуют.'))
    result = pd.DataFrame(rows)
    result.attrs['city_coordinates'] = {city[0]: city[2:] for city in CITIES}
    return result
