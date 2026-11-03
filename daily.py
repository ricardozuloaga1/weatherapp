"""Daily outfit UI and weather adapter. Forecasts never use shared DB history."""
import math
from datetime import datetime, timezone
from flask import Blueprint, jsonify, render_template, request, session
import requests

bp = Blueprint('daily', __name__)


@bp.get('/today')
def today():
    return render_template('daily.html')


def get_json(url, params):
    response = requests.get(url, params=params, timeout=12)
    response.raise_for_status()
    return response.json()


@bp.get('/api/locations')
def locations():
    query = request.args.get('q', '').strip()
    if not 2 <= len(query) <= 120:
        return jsonify(error='Enter a city with at least two characters.'), 400
    try:
        data = get_json('https://geocoding-api.open-meteo.com/v1/search',
                        {'name': query, 'count': 5, 'language': 'en', 'format': 'json'})
        return jsonify(locations=[{
            'name': ', '.join(dict.fromkeys(filter(None, [p['name'], p.get('admin1'), p.get('country')]))),
            'latitude': p['latitude'], 'longitude': p['longitude'],
        } for p in data.get('results', [])])
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return jsonify(error='City search is unavailable. Try again shortly.'), 502


@bp.get('/api/daily-weather')
def daily_weather():
    try:
        lat, lon = float(request.args['lat']), float(request.args['lon'])
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError()
    except (ValueError, KeyError):
        return jsonify(error='A valid latitude and longitude are required.'), 400
    try:
        data = get_json('https://api.open-meteo.com/v1/forecast', {
            'latitude': lat, 'longitude': lon, 'timezone': 'auto', 'forecast_days': 2,
            'current': 'temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m',
            'hourly': 'temperature_2m,apparent_temperature,precipitation_probability,weather_code,wind_speed_10m',
            'daily': 'temperature_2m_max,temperature_2m_min',
        })
        current, hourly = data['current'], data['hourly']
        points = []
        for i, time in enumerate(hourly['time']):
            point = {'time': time, 'temp': hourly['temperature_2m'][i],
                     'feels': hourly['apparent_temperature'][i], 'rain': hourly['precipitation_probability'][i],
                     'wind': hourly['wind_speed_10m'][i], 'code': hourly['weather_code'][i]}
            if all(isinstance(point[k], (int, float)) and math.isfinite(point[k]) for k in ('temp', 'feels', 'rain', 'wind', 'code')):
                points.append(point)
        if not points or any(current.get(k) is None for k in ('temperature_2m', 'apparent_temperature', 'wind_speed_10m', 'weather_code')):
            raise ValueError('Incomplete forecast')
        return jsonify(source='live', time=current['time'], timezone=data['timezone'],
                       fetched_at=datetime.now(timezone.utc).isoformat(),
                       current={'temp': current['temperature_2m'], 'feels': current['apparent_temperature'],
                                'wind': current['wind_speed_10m'], 'code': current['weather_code']},
                       high=data['daily']['temperature_2m_max'][0], low=data['daily']['temperature_2m_min'][0], hours=points)
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
        return jsonify(error='We couldn’t load the forecast. Your previous view is still available; please try again.'), 502
