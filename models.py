from app import db
from flask_login import UserMixin
from datetime import datetime


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    # ensure password hash field has length of at least 256
    password_hash = db.Column(db.String(256))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<User {self.username}>'


class WeatherData(db.Model):
    """Model to store weather data for locations"""
    id = db.Column(db.Integer, primary_key=True)
    location = db.Column(db.String(100), nullable=False)
    temperature = db.Column(db.Float)
    description = db.Column(db.String(200))
    humidity = db.Column(db.Integer)
    wind_speed = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<WeatherData {self.location} - {self.temperature}°>'


class UserProfile(db.Model):
    """Model to store user profile information"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    height = db.Column(db.Integer)  # Height in cm
    gender = db.Column(db.String(20))  # male, female, non-binary, prefer-not-to-say
    body_type = db.Column(db.String(20))  # slim, average, athletic, curvy
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    user = db.relationship('User', backref=db.backref('profile', uselist=False))
    
    def __repr__(self):
        return f'<UserProfile {self.user_id} - {self.gender}/{self.body_type}>'


class Avatar(db.Model):
    """Model to store avatar configurations"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    avatar_type = db.Column(db.String(50))  # e.g., 'sunny', 'rainy', 'cloudy'
    config_data = db.Column(db.Text)  # JSON string for avatar configuration
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Avatar {self.name} - {self.avatar_type}>'
