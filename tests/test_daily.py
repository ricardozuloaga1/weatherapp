import os
import unittest
from unittest.mock import patch
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
from app import app
import requests

class DailyTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_daily_view_is_available_without_account(self):
        self.assertEqual(self.client.get('/today').status_code, 200)
        self.assertIn(b'Your day, dressed.', self.client.get('/today').data)
        self.assertEqual(self.client.get('/outfit').location, '/today')
        self.assertEqual(self.client.get('/').location, '/today')

    def test_missing_page_returns_404_without_template_error(self):
        self.assertEqual(self.client.get('/missing-page').status_code, 404)

    def test_invalid_coordinates_never_call_weather_service(self):
        with patch('daily.get_json') as get:
            for query in ['', '?lat=nan&lon=1', '?lat=91&lon=1', '?lat=1&lon=-181', '?lat=1&lon=inf']:
                self.assertEqual(self.client.get('/api/daily-weather'+query).status_code, 400)
            get.assert_not_called()

    def test_city_selection_returns_multiple_results(self):
        with patch('daily.get_json', return_value={'results':[{'name':'Paris','admin1':'Texas','country':'United States','latitude':33.6,'longitude':-95.5},{'name':'Paris','country':'France','latitude':48.8,'longitude':2.3}]}):
            response=self.client.get('/api/locations?q=Paris')
            self.assertEqual(response.status_code,200)
            self.assertEqual(len(response.json['locations']),2)
            self.assertEqual(response.json['locations'][0]['name'],'Paris, Texas, United States')

    def test_upstream_failure_is_explicit_not_sample_weather(self):
        with patch('daily.get_json', side_effect=requests.Timeout):
            response=self.client.get('/api/daily-weather?lat=10&lon=-66')
            self.assertEqual(response.status_code,502)
            self.assertIn('error',response.json)
            self.assertNotIn('source',response.json)

    def test_forecast_uses_requested_coordinates_and_does_not_share_history(self):
        data={'timezone':'America/Caracas','current':{'time':'2026-10-27T14:00','temperature_2m':24,'apparent_temperature':26,'wind_speed_10m':12,'weather_code':2},'hourly':{'time':['2026-10-27T14:00'],'temperature_2m':[24],'apparent_temperature':[26],'precipitation_probability':[35],'wind_speed_10m':[12],'weather_code':[2]},'daily':{'temperature_2m_max':[27],'temperature_2m_min':[20]}}
        with patch('daily.get_json', return_value=data) as get:
            response=self.client.get('/api/daily-weather?lat=10&lon=-66')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json['source'],'live')
            self.assertEqual(response.json['hours'][0]['feels'],26)
            self.assertEqual(get.call_args.args[1]['longitude'],-66)
            other=app.test_client()
            other.get('/api/daily-weather?lat=-33&lon=151')
            self.assertEqual(get.call_args.args[1]['latitude'],-33)
            self.assertEqual(get.call_args.args[1]['longitude'],151)

    def test_missing_forecast_values_fail_cleanly(self):
        with patch('daily.get_json',return_value={}):
            self.assertEqual(self.client.get('/api/daily-weather?lat=10&lon=-66').status_code,502)

if __name__ == '__main__':
    unittest.main()
