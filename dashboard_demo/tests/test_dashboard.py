import unittest
from pathlib import Path
import pandas as pd
from model import *
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).resolve().parents[1]
class ModelTests(unittest.TestCase):
 def setUp(self):
  self.cities=validate_cities(pd.read_csv(ROOT/'data/cities.csv'))
  self.routes=demo_routes(self.cities,'Казань')
 def test_one_route(self):
  route=self.routes.iloc[:1].copy();route['demand_year']=1e9;route['weekly_roundtrips']=1;route['fare_rub']=1000
  s,d=calculate(route,seats=100,load=.5,months=12)
  self.assertEqual(d.passengers.iloc[0],5200);self.assertEqual(s.revenue.iloc[0],5200000)
 def test_zero_period_and_load(self):
  for kwargs in [{'months':0},{'load':0}]:
   s,d=calculate(self.routes,**kwargs);self.assertEqual(s.passengers.sum(),0);self.assertEqual(s.revenue.sum(),0)
 def test_demand_cap(self):
  s,d=calculate(self.routes,load=1);self.assertTrue((d.passengers<=d.demand_year).all())
 def test_cannibalisation(self):
  s,d=calculate(self.routes,net_fraction=0);self.assertEqual(s.share_delta_pp.sum(),0);self.assertGreater(s.revenue.sum(),0)
 def test_weights(self):
  self.assertEqual(list(score_cities(self.cities,DEFAULT_WEIGHTS).city),list(score_cities(self.cities,{k:v*3 for k,v in DEFAULT_WEIGHTS.items()}).city))
  with self.assertRaises(ValueError):score_cities(self.cities,{k:0 for k in CRITERIA})
 def test_bad_routes(self):
  bad=self.routes.copy();bad.loc[0,'weekly_roundtrips']=-1
  with self.assertRaises(ValueError):validate_routes(bad,self.cities)
  bad=self.routes.copy();bad.loc[0,'block_hours']=float('inf')
  with self.assertRaises(ValueError):validate_routes(bad,self.cities)
 def test_ui(self):
  app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
  self.assertFalse(app.exception,str(app.exception))
  app.radio(key='scenario').set_value('Осторожный').run();self.assertFalse(app.exception,str(app.exception))
  app.slider(key='months').set_value(0).run();self.assertFalse(app.exception,str(app.exception))
  app.slider(key='months').set_value(12).run()
  app.selectbox(key='hub').set_value('Самара').run();self.assertFalse(app.exception,str(app.exception))
  for k in CRITERIA:app.slider(key='weight_'+k).set_value(0)
  app.run();self.assertFalse(app.exception,str(app.exception))
  app.button[0].click().run();self.assertFalse(app.exception,str(app.exception))
if __name__=='__main__':unittest.main()
