"""Replace score_cities and calculate with the team's verified models."""
import math
import pandas as pd

CRITERIA = {'population_score':'Размер рынка', 'transfer_score':'Спрос на пересадки', 'competition_score':'Свобода от конкуренции', 'tourism_score':'Туристический спрос', 'airport_score':'Возможности аэропорта'}
DEFAULT_WEIGHTS = dict(zip(CRITERIA, [25,25,20,15,15]))

def validate_cities(df):
    required = ['city','lat','lon','source','data_status',*CRITERIA]
    missing=set(required)-set(df.columns)
    if missing: raise ValueError('В cities.csv отсутствуют: '+', '.join(sorted(missing)))
    if len(df)<3 or df.city.duplicated().any(): raise ValueError('Нужно минимум 3 уникальных города.')
    for k in ['lat','lon',*CRITERIA]:
        df[k]=pd.to_numeric(df[k],errors='raise')
        if not df[k].map(math.isfinite).all(): raise ValueError(f'{k}: нужны конечные числа.')
    if not df.lat.between(-90,90).all() or not df.lon.between(-180,180).all(): raise ValueError('Некорректные координаты.')
    for k in CRITERIA:
        if not df[k].between(0,100).all(): raise ValueError(f'{k}: допустимы баллы от 0 до 100.')
    if df[required].isna().any().any(): raise ValueError('Есть пропуски в обязательных полях.')
    return df

def score_cities(cities, weights):
    total=sum(weights.values())
    if total<=0: raise ValueError('Хотя бы один вес должен быть больше нуля.')
    result=cities.copy()
    result['score']=sum(result[k]*weights[k]/total for k in CRITERIA)
    return result.sort_values(['score','city'],ascending=[False,True]).reset_index(drop=True)

def validate_routes(df,cities):
    required=['strategy','origin','destination','demand_year','weekly_roundtrips','fare_rub','block_hours','source','data_status']
    missing=set(required)-set(df.columns)
    if missing: raise ValueError('В routes.csv отсутствуют: '+', '.join(sorted(missing)))
    if df[required].isna().any().any(): raise ValueError('Есть пропуски в маршрутах.')
    if set(df.strategy)!= {'Хаб','Прямые рейсы'}: raise ValueError('Нужны обе стратегии: Хаб и Прямые рейсы.')
    if not set(df.origin).union(df.destination)<=set(cities.city): raise ValueError('Все города маршрутов должны присутствовать в cities.csv.')
    if (df.origin==df.destination).any(): raise ValueError('Начало и конец маршрута совпадают.')
    seen=set()
    for row in df.itertuples():
        key=(row.strategy,*sorted([row.origin,row.destination]))
        if key in seen: raise ValueError('Дублируется пара городов внутри стратегии.')
        seen.add(key)
    for k in ['demand_year','weekly_roundtrips','fare_rub','block_hours']:
        df[k]=pd.to_numeric(df[k],errors='raise')
        if not df[k].map(math.isfinite).all() or (df[k]<0).any(): raise ValueError(f'{k}: нужны неотрицательные конечные числа.')
    if (df.block_hours<=0).any(): raise ValueError('Время полёта должно быть положительным.')
    return df

def demo_routes(cities, hub):
    names=list(cities.city)
    rows=[]
    pairs=[(hub,c) for c in names if c!=hub][:10]
    direct=[('Екатеринбург',c) for c in names if c not in ['Екатеринбург','Москва']][:5]+[('Москва',c) for c in reversed(names) if c not in ['Москва','Екатеринбург']][:5]
    coords=cities.set_index('city')
    for strategy,network in [('Хаб',pairs),('Прямые рейсы',direct)]:
        for i,(a,b) in enumerate(network):
            ra,rb=coords.loc[a],coords.loc[b]
            lat1,lat2=map(math.radians,[ra.lat,rb.lat]); dl=math.radians(rb.lon-ra.lon)
            central=2*math.asin(min(1,math.sqrt(math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dl/2)**2)))
            hours=round(6371*central/650+0.45,2)
            rows.append(dict(strategy=strategy,origin=a,destination=b,demand_year=21000+i*2700,weekly_roundtrips=3+i%3,fare_rub=5500+i*450,block_hours=hours,source='Синтетический пример: demand=21000+2700*i; частота=3+i%3; тариф=5500+450*i; время≈расстояние/650+0.45. Не расписание авиакомпании.',data_status='Демо'))
    return pd.DataFrame(rows)

def calculate(routes, seats=100, load=.85, fare_factor=1, demand_factor=1, months=12, market=108900000, baseline=2700000, net_fraction=1, daily_hours=9, reserve=.15, positioning=.1):
    """All passengers are passenger-segments; each pair is bidirectional."""
    if not(0<=load<=1 and 0<=net_fraction<=1 and 0<=months<=12) or market<=0 or daily_hours<=0: raise ValueError('Некорректные параметры модели.')
    d=routes.copy(); fraction=months/12
    d['flights']=d.weekly_roundtrips*2*52*fraction
    d['capacity']=d.flights*seats
    d['passengers']=pd.concat([d.capacity*load,d.demand_year*demand_factor*fraction],axis=1).min(axis=1)
    d['revenue']=d.passengers*d.fare_rub*fare_factor
    d['net_passengers']=d.passengers*net_fraction
    d['effective_load']=(d.passengers/d.capacity.replace(0,float('nan'))).fillna(0)
    summary=[]
    for strategy,group in d.groupby('strategy',sort=False):
        weekly_hours=(group.weekly_roundtrips*2*(group.block_hours+.75)).sum()
        extra=positioning if strategy=='Прямые рейсы' else 0
        # Coarse resource bound; not a validated aircraft rotation schedule.
        fleet=math.ceil(weekly_hours*(1+extra)/(7*daily_hours)*(1+reserve)) if months>0 else 0
        passengers=group.passengers.sum(); net=group.net_passengers.sum()
        summary.append(dict(strategy=strategy,passengers=passengers,revenue=group.revenue.sum(),net_passengers=net,share_pct=(baseline+net)/market*100,share_delta_pp=net/market*100,fleet=fleet))
    return pd.DataFrame(summary),d
