from flask import render_template, request, jsonify, flash, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from app import app, db
from models import User, WeatherData, Avatar, UserProfile
import logging
import os
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


@app.route('/')
def index():
    """Splash screen landing page for WeatherAvatar"""
    return redirect(url_for('daily.today'))





@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login and signup route"""
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Validate required fields
        if not email or not password:
            flash('Email and password are required.', 'error')
            return render_template('login.html', title='Login - WeatherAvatar')
        
        if form_type == 'login':
            # Handle login
            user = User.query.filter_by(email=email).first()
            if user and user.password_hash and check_password_hash(user.password_hash, password):
                session['user_id'] = user.id
                session['user_email'] = user.email
                flash('Login successful!', 'success')
                return redirect(url_for('weather'))
            else:
                flash('Invalid email or password.', 'error')
        
        elif form_type == 'signup':
            # Handle signup
            confirm_password = request.form.get('confirm_password')
            
            if not confirm_password:
                flash('Please confirm your password.', 'error')
            elif password != confirm_password:
                flash('Passwords do not match.', 'error')
            elif User.query.filter_by(email=email).first():
                flash('Email already registered.', 'error')
            else:
                # Create new user
                username = email.split('@')[0] if '@' in email else email
                password_hash = generate_password_hash(password)
                
                new_user = User()
                new_user.username = username
                new_user.email = email
                new_user.password_hash = password_hash
                
                try:
                    db.session.add(new_user)
                    db.session.commit()
                    
                    session['user_id'] = new_user.id
                    session['user_email'] = new_user.email
                    flash('Account created successfully! Please complete your profile.', 'success')
                    return redirect(url_for('profile'))
                except Exception as e:
                    db.session.rollback()
                    logger.error(f'Error creating user: {e}')
                    flash('Error creating account. Please try again.', 'error')
    
    return render_template('login.html', title='Login - WeatherAvatar')


@app.route('/logout')
def logout():
    """Logout route"""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    """Profile creation and editing route"""
    # Check if user is logged in
    if 'user_id' not in session:
        flash('Please log in to create your profile.', 'error')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    user = User.query.get(user_id)
    
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        height = request.form.get('height')
        gender = request.form.get('gender')
        body_type = request.form.get('body_type')
        
        # Validate required fields
        if not height or not gender or not body_type:
            flash('All fields are required.', 'error')
            return render_template('profile.html', title='Create Profile - WeatherAvatar')
        
        try:
            height = int(height)
            if height < 100 or height > 250:
                flash('Height must be between 100-250 cm.', 'error')
                return render_template('profile.html', title='Create Profile - WeatherAvatar')
        except ValueError:
            flash('Invalid height value.', 'error')
            return render_template('profile.html', title='Create Profile - WeatherAvatar')
        
        # Check if profile already exists
        existing_profile = UserProfile.query.filter_by(user_id=user_id).first()
        
        if existing_profile:
            # Update existing profile
            existing_profile.height = height
            existing_profile.gender = gender
            existing_profile.body_type = body_type
            existing_profile.updated_at = db.func.now()
        else:
            # Create new profile
            new_profile = UserProfile()
            new_profile.user_id = user_id
            new_profile.height = height
            new_profile.gender = gender
            new_profile.body_type = body_type
            db.session.add(new_profile)
        
        try:
            db.session.commit()
            flash('Profile saved successfully!', 'success')
            return redirect(url_for('avatar_preview'))
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error saving profile: {e}')
            flash('Error saving profile. Please try again.', 'error')
    
    return render_template('profile.html', title='Create Profile - WeatherAvatar')


@app.route('/mockups')
def mockups():
    """Route for previewing uploaded mockups and designs"""
    return render_template('mockups.html', title='Design Mockups - WeatherAvatar')


@app.route('/weather')
def weather():
    """Weather selection and display route"""
    # Check if user is logged in
    if 'user_id' not in session:
        flash('Please log in to view weather.', 'error')
        return redirect(url_for('login'))
    
    return render_template('weather.html', title='Your Weather - WeatherAvatar')


@app.route('/avatar')
def avatar_preview():
    """Avatar preview route"""
    # Check if user is logged in
    if 'user_id' not in session:
        flash('Please log in to view your avatar.', 'error')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    user = User.query.get(user_id)
    
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('login'))
    
    # Get user profile
    profile = UserProfile.query.filter_by(user_id=user_id).first()
    
    if not profile:
        flash('Please create your profile first.', 'info')
        return redirect(url_for('profile'))
    
    return render_template('avatar.html', profile=profile, title='Your Avatar - WeatherAvatar')


def get_weather_data(lat, lon, location_name=None):
    """Fetch weather data from OpenWeatherMap API"""
    try:
        api_key = os.environ.get('OPENWEATHER_API_KEY')
        if not api_key:
            raise Exception('Weather API key not configured')
        
        url = f"https://api.openweathermap.org/data/2.5/weather"
        params = {
            'lat': lat,
            'lon': lon,
            'appid': api_key,
            'units': 'imperial'  # Use Fahrenheit
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Save weather data to database
        weather_record = WeatherData()
        weather_record.location = location_name or f"{lat},{lon}"
        weather_record.temperature = data['main']['temp']
        weather_record.description = data['weather'][0]['description'].title()
        weather_record.humidity = data['main']['humidity']
        weather_record.wind_speed = data['wind'].get('speed', 0)
        
        try:
            db.session.add(weather_record)
            db.session.commit()
        except Exception as e:
            logger.warning(f'Could not save weather data: {e}')
            db.session.rollback()
        
        return {
            'location': location_name or data.get('name', 'Unknown'),
            'temperature': round(data['main']['temp']),
            'description': data['weather'][0]['description'].title(),
            'humidity': data['main']['humidity'],
            'wind_speed': data['wind'].get('speed', 0),
            'icon': data['weather'][0]['icon']
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f'Weather API request failed: {e}')
        raise Exception('Unable to fetch weather data')
    except Exception as e:
        logger.error(f'Weather data processing failed: {e}')
        raise Exception('Weather service temporarily unavailable')


@app.route('/api/weather/coords/<float:lat>/<float:lon>')
def api_weather_coords(lat, lon):
    """API endpoint for weather data by coordinates"""
    try:
        weather_data = get_weather_data(lat, lon)
        return jsonify(weather_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/weather/city/<city>')
def api_weather_city(city):
    """API endpoint for weather data by city name"""
    try:
        api_key = os.environ.get('OPENWEATHER_API_KEY')
        if not api_key:
            return jsonify({'error': 'Weather API key not configured'}), 500
        
        # First get coordinates for the city
        geocoding_url = f"https://api.openweathermap.org/geo/1.0/direct"
        geocoding_params = {
            'q': city,
            'limit': 1,
            'appid': api_key
        }
        
        geo_response = requests.get(geocoding_url, params=geocoding_params, timeout=10)
        geo_response.raise_for_status()
        
        geo_data = geo_response.json()
        if not geo_data:
            return jsonify({'error': 'City not found'}), 404
        
        lat = geo_data[0]['lat']
        lon = geo_data[0]['lon']
        location_name = f"{geo_data[0]['name']}, {geo_data[0].get('country', '')}"
        
        weather_data = get_weather_data(lat, lon, location_name)
        return jsonify(weather_data)
        
    except requests.exceptions.RequestException as e:
        logger.error(f'Weather API request failed: {e}')
        return jsonify({'error': 'Unable to fetch weather data'}), 400
    except Exception as e:
        logger.error(f'Weather API error: {e}')
        return jsonify({'error': 'Weather service temporarily unavailable'}), 500


@app.route('/outfit')
def outfit():
    return redirect(url_for('daily.today'))


@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors"""
    return render_template('error.html', code=404, message='This page wandered off.'), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    db.session.rollback()
    logger.error(f'Internal server error: {error}')
    return render_template('error.html', code=500, message='Something went wrong. Please try again.'), 500


# Context processor to make common variables available in all templates
@app.context_processor
def inject_common_vars():
    """Inject common variables into all templates"""
    return {
        'app_name': 'WeatherAvatar',
        'version': '1.0.0'
    }
