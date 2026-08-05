import os
import threading
from datetime import timedelta
from flask import Flask
from flask_login import LoginManager
from backend.database import db, init_db
from backend.models import User, Video
from config import CACHE_FOLDER, SERVER_URL
from backend.scraper import cleanup_expired_videos
from backend.cache_store import cache
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Load secret key and database connection URL from environment variables
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

db_url = os.environ.get('DATABASE_URL')
if not db_url:
    raise RuntimeError("DATABASE_URL environment variable is missing. Please set your PostgreSQL URI in the .env file.")

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 3,
    'pool_recycle': 1800,
    'pool_pre_ping': True,
    'max_overflow': 2
}
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)
app.config['SESSION_PERMANENT'] = True

# Initialize database
init_db(app)

# Initialize Cache (Defaults to SimpleCache for zero-dependency local runs and Termux support)
# Future switch to Redis:
# 1. Run: pip install redis
# 2. Switch configuration to:
#    app.config['CACHE_TYPE'] = 'RedisCache'
#    app.config['CACHE_REDIS_URL'] = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

app.config['CACHE_TYPE'] = 'SimpleCache' # comment, if uncomment redits
app.config['CACHE_DEFAULT_TIMEOUT'] = 300
cache.init_app(app)

# Initialize Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'views.auth'  # Updated to point to modular blueprint views

@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Import and register Blueprints
from routes.views import views_bp
from routes.auth import auth_bp
from routes.videos import videos_bp
from routes.admin import admin_bp

app.register_blueprint(views_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(videos_bp)
app.register_blueprint(admin_bp)

if __name__ == '__main__':
    # Ensure cache folder exists
    os.makedirs(CACHE_FOLDER, exist_ok=True)
    
    # Set restrictive permissions (owner only)
    try:
        os.chmod(CACHE_FOLDER, 0o700)
    except:
        pass
        
    # Create .nomedia file to hide from gallery apps
    nomedia_path = os.path.join(CACHE_FOLDER, '.nomedia')
    if not os.path.exists(nomedia_path):
        open(nomedia_path, 'w').close()
    
    # Create default admin user on startup if not present
    with app.app_context():
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            from werkzeug.security import generate_password_hash
            admin_user = User(
                username='admin',
                email='admin@offlinemedia.com',
                name='Admin User',
                password=generate_password_hash('admin123'),
                is_admin=True
            )
            db.session.add(admin_user)
            db.session.commit()
            print("[Admin Setup] Created default admin user: admin / admin123")

    # Start the background video cache cleanup worker thread
    cleanup_thread = threading.Thread(target=cleanup_expired_videos, args=(app, db, Video, CACHE_FOLDER), daemon=True)
    cleanup_thread.start()
    
    # Run server
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)
