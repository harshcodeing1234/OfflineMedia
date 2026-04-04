from flask_login import UserMixin #type:ignore
from datetime import datetime
from database import db

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True)
    name = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    avatar = db.Column(db.String(200))
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    scrapes = db.relationship('Scrape', backref='user', lazy=True)

class Scrape(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    ttl = db.Column(db.Integer, nullable=False)
    platforms = db.Column(db.String(100), default='all')
    status = db.Column(db.String(20), default='pending')
    progress = db.Column(db.Integer, default=0)
    total_videos = db.Column(db.Integer, default=0)
    downloaded_videos = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
    logs = db.Column(db.Text, default='')
    videos = db.relationship('Video', backref='scrape', lazy='selectin', cascade='all, delete-orphan')

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    scrape_id = db.Column(db.Integer, db.ForeignKey('scrape.id'), nullable=False)
    platform = db.Column(db.String(20), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    filename = db.Column(db.String(200))
    status = db.Column(db.String(20), default='pending')
    likes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    comments = db.relationship('Comment', backref='video', lazy=True, cascade='all, delete-orphan')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'), nullable=True)
    filename = db.Column(db.String(200), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'), nullable=True)
    filename = db.Column(db.String(200), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('filename', 'user_id', name='unique_filename_user_like'),)

class SavedVideo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    platform = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('filename', 'user_id', name='unique_saved_video'),)

class WatchHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    platform = db.Column(db.String(20), nullable=False)
    watched_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('filename', 'user_id', name='unique_watch_history'),)
