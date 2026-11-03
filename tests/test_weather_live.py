import unittest
from unittest.mock import patch
from weather_live import recommend,signature,outfit,CATALOG
from pilot import create_app

def forecast(temp=24,wet=0,wind=5):
    return {'timezone':'America/New_York','current':{'time':'2026-11-02T12:00','temperature_2m':temp,'apparent_temperature':temp,'precipitation':wet,'wind_speed_10m':wind,'weather_code':0},'hourly':{'time':[f'2026-11-02T{h}:00' for h in range(12,19)],'apparent_temperature':[temp]*7,'precipitation':[wet]*7,'precipitation_probability':[60 if wet else 0]*7,'wind_speed_10m':[wind]*7}}

class WeatherTests(unittest.TestCase):
    def test_temperature_precipitation_and_wind_combinations(self):
        for temp,wet,wind,expected in [(25,0,5,'sun'),(15,0,5,'mild'),(25,0,30,'mild'),(15,1,5,'rain'),(25,1,5,'warmrain'),(3,0,5,'cold'),(3,1,5,'coldrain')]:
            self.assertEqual(recommend(forecast(temp,wet,wind))['scenario'],expected)
    def test_forecast_rain_and_cold_affect_recommendation(self):
        data=forecast();data['hourly']['precipitation_probability'][2]=70
        self.assertEqual(recommend(data)['scenario'],'warmrain')
        data['hourly']['apparent_temperature'][3]=4
        self.assertEqual(recommend(data)['scenario'],'coldrain')
    def test_missing_and_invalid_forecast_is_not_sunny(self):
        data=forecast();data['current']['apparent_temperature']=None
        with self.assertRaises((TypeError,ValueError)):recommend(data)
        data=forecast();data['hourly']['time']=[]
        with self.assertRaises(ValueError):recommend(data)
    def test_preference_changes_invalidate_matching_signature(self):
        self.assertNotEqual(signature({},'sun'),signature({'wardrobe':{'sun':[1,0,0]}},'sun'))
        self.assertIn('Cotton T-shirt',outfit({'wardrobe':{'sun':[1,0,0]}},'sun'))
    def test_profile_validation_privacy_and_weather_route(self):
        app=create_app(store_path=':memory:',fashn_autostart=False);c=app.test_client();c.get('/')
        with c.session_transaction() as s:h={'X-CSRF-Token':s['csrf']}
        path='/api/weather/profile';loc={'label':'NYC','latitude':40.71427,'longitude':-74.00597}
        self.assertEqual(c.post(path,json={'location':loc}).status_code,403)
        self.assertEqual(c.post(path,headers=h,json={'location':{'latitude':200}}).status_code,400)
        w={k:[0,0,0] for k in CATALOG}
        self.assertEqual(c.post(path,headers=h,json={'location':loc,'wardrobe':w,'auto_generation':False}).status_code,200)
        self.assertEqual(c.get(path).json['profile']['location']['latitude'],40.71)
        self.assertEqual(app.test_client().get(path).json['profile'],{})
        with patch.object(app.extensions['weather_client'],'forecast',return_value=recommend(forecast())):
            self.assertEqual(c.get('/api/weather/today').json['scenario'],'sun')
        with patch.object(app.extensions['weather_client'],'forecast',side_effect=RuntimeError()):
            self.assertEqual(c.get('/api/weather/today').status_code,503)
        c.delete('/api/pilot',headers=h);self.assertEqual(c.get(path).json['profile'],{})
        app.extensions['pilot_pool'].shutdown();app.extensions['pilot_store'].db.close()
