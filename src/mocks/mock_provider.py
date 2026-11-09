"""Synthetic interactive fixtures. NOT verified traffic, tariffs or economic forecasts."""
import math
from dataclasses import asdict
import pandas as pd
from src.schemas.contracts import CityScoreDTO, HypothesisResultDTO, ComparisonBundleDTO

CITIES = [('KUF','Самара',50.15,53.20),('GOJ','Нижний Новгород',44.01,56.33),('UFA','Уфа',55.97,54.74),('KZN','Казань',49.12,55.79),('MRV','Минеральные Воды',43.13,44.21),('PEE','Пермь',56.25,58.01),('SVX','Екатеринбург',60.60,56.84),('CEK','Челябинск',61.40,55.16),('TJM','Тюмень',65.53,57.15),('VOG','Волгоград',44.52,48.71),('GSV','Саратов',46.03,51.53),('OMS','Омск',73.37,54.99)]


def get_scored_cities(weights):
    values=list(asdict(weights).values())
    scores=[sum(w*v for w,v in zip(values,[95-i*5,40+(i*13)%60,90-(i*17)%65,30+(i*23)%70])) for i in range(12)]
    order=sorted(range(12),key=lambda i:scores[i],reverse=True)
    return [CityScoreDTO(CITIES[i][0],CITIES[i][1],'ДЕМО',round(1+i*.1,2),round(1+i*.2,2),round(scores[i],2),rank,rank<=3) for rank,i in enumerate(order,1)]


def evaluate_hypotheses(params,top_cities):
    conservative=params.scenario=='conservative'
    demand,cost_factor,subsidy=(.87,1.08,95000) if conservative else (1.,1.,145000)
    flights=params.active_routes_count*params.weekly_freq_per_route*2*52
    seats=flights*params.aircraft_seats
    results=[]
    for code in ['hub','p2p']:
        hub=code=='hub'
        bonus=(3.2 if params.weekly_freq_per_route>=6 else -2.5 if params.weekly_freq_per_route<=3 else 0) if hub else (2.4 if params.weekly_freq_per_route<=5 else 0)
        load=max(0,min(95,(params.load_factor_pct+bonus)*demand))
        pax=round(seats*load/100)
        fare=params.avg_fare_rub*(.935 if hub else 1.055)
        support=flights*(.45 if hub else .65)*subsidy
        revenue=pax*fare+support
        # Literal formula from team specification; cost per flight vs rotation needs Dev 3 review.
        cost=flights*(645000 if hub else 635000)*cost_factor+((365e6 if conservative else 310e6) if hub else 115e6)
        margin=revenue-cost
        results.append(HypothesisResultDTO(code,'Гипотеза А: Хаб' if hub else 'Гипотеза Б: Прямые рейсы',pax,revenue/1e6,margin/1e6,100*margin/revenue if revenue else 0,100*pax/108900000,math.ceil(flights*2/(365*8)),100*(cost-support)/(seats*fare) if seats*fare else 0))
    hub,p2p=results
    winner='hub' if hub.ebitdar_mln_rub>p2p.ebitdar_mln_rub else 'p2p'
    return ComparisonBundleDTO(hub,p2p,winner,'ДЕМО: выбрана большая EBITDAR по условным коэффициентам ТЗ; это не подтверждённая стратегия. Флот — грубая оценка по 2 ч на участок и 8 ч налёта в сутки.')


def get_network_routes(hypothesis,hub_iata='KUF'):
    lookup={c[0]:c for c in CITIES}
    pairs=[('KUF','GOJ'),('KUF','PEE'),('GOJ','UFA'),('GOJ','MRV'),('UFA','VOG'),('KUF','CEK'),('UFA','OMS'),('GOJ','SVX'),('KZN','CEK'),('GSV','SVX'),('TJM','OMS'),('KZN','MRV')]
    if hypothesis=='hub':pairs=[(hub_iata,c[0]) for c in CITIES if c[0]!=hub_iata]
    rows=[]
    for i,(o,d) in enumerate(pairs):
        a,b=lookup[o],lookup[d]
        rows.append(dict(route_code=f'DEMO-{i+1:03}',origin_iata=o,origin_city=a[1],dest_iata=d,dest_city=b[1],lat_o=a[3],lon_o=a[2],lat_d=b[3],lon_d=b[2],competitor_flights_weekly=i%4,competitor_fare_rub=7000+200*i,subsidy_eligible=False,launch_quarter='Q1 2028',proof_source='ДЕМО — искусственная строка для проверки UI; доказательство спроса отсутствует.'))
    return pd.DataFrame(rows[:10])
