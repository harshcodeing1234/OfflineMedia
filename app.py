from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, session #type:ignore
from flask_login import LoginManager, login_user, logout_user, login_required, current_user #type:ignore
from werkzeug.security import generate_password_hash, check_password_hash #type:ignore
from database import db, init_db
from models import User, Scrape, Video, Comment, Like
from datetime import datetime, timedelta #type:ignore
import os
import threading
from concurrent.futures import ThreadPoolExecutor
import warnings
from config import CACHE_FOLDER, THREAD_POOL_WORKERS, SERVER_URL
from scraper import run_scraper_session, download_video_task, cleanup_expired_videos
from utils import safe_query_or_404, safe_list_query, safe_file_operation

warnings.filterwarnings('ignore')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 20,
    'pool_recycle': 3600,
    'pool_pre_ping': True,
    'max_overflow': 10
}
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)
app.config['SESSION_PERMANENT'] = True

init_db(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth'

os.makedirs(CACHE_FOLDER, exist_ok=True)

executor = ThreadPoolExecutor(max_workers=THREAD_POOL_WORKERS)

@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Auth routs...
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('auth'))

@app.route('/auth')
def auth():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('auth.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data['username']).first()
    if user and check_password_hash(user.password, data['password']):
        login_user(user, remember=True)
        session.permanent = True
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Invalid credentials'})

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    if User.query.filter_by(username=data.get('username', '')).first():
        return jsonify({'success': False, 'message': 'Username exists'})
    if User.query.filter_by(email=data.get('email', '')).first():
        return jsonify({'success': False, 'message': 'Email exists'})
    user = User(
        username=data['username'],
        email=data.get('email'),
        name=data.get('name'),
        password=generate_password_hash(data['password'])
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth'))

# Dashboard....
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/scrapp')
@login_required
def scrapp():
    return render_template('scrapp.html')

@app.route('/play')
@login_required
def play():
    return render_template('play.html')

@app.route('/polling')
@login_required
def polling():
    return render_template('polling.html')

@app.route('/about')
@login_required
def about():
    return render_template('about.html')

@app.route('/contact')
@login_required
def contact():
    return render_template('contact.html')

# Api routes
@app.route('/api/user')
@login_required
def get_user():
    return jsonify({
        'username': current_user.username,
        'name': current_user.name or current_user.username,
        'email': current_user.email,
        'phone': current_user.phone,
        'avatar': current_user.avatar
    })

@app.route('/api/user/update', methods=['POST'])
@login_required
def update_user():
    from werkzeug.security import generate_password_hash #type:ignore
    data = request.json
    
    if 'name' in data:
        current_user.name = data['name']
    if 'email' in data:
        current_user.email = data['email']
    if 'phone' in data:
        current_user.phone = data['phone']
    if 'avatar' in data:
        current_user.avatar = data['avatar']
    if 'password' in data and data['password']:
        current_user.password = generate_password_hash(data['password'])
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/stats')
@login_required
def get_stats():
    total_scraps = Scrape.query.filter_by(user_id=current_user.id).count()
    total_videos = Video.query.join(Scrape).filter(
        Scrape.user_id == current_user.id,
        Video.status == 'ready'
    ).count()
    
    # Count likes by getting filenames from user's videos
    total_likes = db.session.query(Like).join(
        Video, Like.filename == Video.filename
    ).join(Scrape).filter(
        Scrape.user_id == current_user.id
    ).count()
    
    cache_size = sum(
        os.path.getsize(os.path.join(CACHE_FOLDER, f)) 
        for f in os.listdir(CACHE_FOLDER) 
        if os.path.isfile(os.path.join(CACHE_FOLDER, f))
    ) if os.path.exists(CACHE_FOLDER) else 0
    
    return jsonify({
        'total_videos': total_videos,
        'total_scraps': total_scraps,
        'cache_size_mb': round(cache_size / (1024 * 1024), 1),
        'total_likes': total_likes
    })

@app.route('/api/scraping-status')
@login_required
def scraping_status():
    active = db.session.query(db.exists().where(
        (Scrape.user_id == current_user.id) & 
        (Scrape.status.in_(['scraping', 'downloading']))
    )).scalar()
    return jsonify({'is_scraping': active})

@app.route('/api/scrapes')
@login_required
def get_scrapes():
    scrapes = Scrape.query.filter_by(user_id=current_user.id).order_by(Scrape.created_at.desc()).all()
    return jsonify([{
        'id': s.id,
        'duration': s.duration,
        'ttl': s.ttl,
        'status': s.status,
        'progress': s.progress,
        'total_videos': s.total_videos,
        'downloaded_videos': s.downloaded_videos,
        'video_count': len(s.videos),
        'created_at': s.created_at.isoformat(),
        'started_at': s.started_at.isoformat() if s.started_at else None,
        'expires_at': s.expires_at.isoformat() if s.expires_at else None,
        'status_text': f"{'Scraping...' if s.status == 'scraping' else f'Downloading {s.downloaded_videos}/{s.total_videos}' if s.status == 'downloading' else s.status.title()}"
    } for s in scrapes])

@app.route('/api/scrape', methods=['POST'])
@login_required
def create_scrape():
    data = request.json
    scrape = Scrape(
        user_id=current_user.id,
        duration=data['duration'],
        ttl=data['ttl'],
        platforms=data.get('platforms', 'all'),
        status='pending'
    )
    db.session.add(scrape)
    db.session.commit()
    
    # Start scraping in background
    threading.Thread(target=run_scraper, args=(scrape.id, data['duration'], data['ttl'], data.get('platforms', 'all')), daemon=True).start()
    
    return jsonify({'success': True, 'scrape_id': scrape.id})


def run_scraper(scrape_id, duration, ttl, platforms):
    """Wrapper for scraper session"""
    with app.app_context():
        run_scraper_session(scrape_id, duration, ttl, platforms, db, Video, Scrape, executor, download_video, CACHE_FOLDER)


def download_video(video_id, url, scrape_id):
    """Wrapper for download task"""
    download_video_task(video_id, url, scrape_id, app, db, Video, Scrape, CACHE_FOLDER)

@app.route('/api/videos')
@login_required
def get_videos():
    import random
    
    # Get all video files from cache folder
    video_files = []
    if os.path.exists(CACHE_FOLDER):
        for f in os.listdir(CACHE_FOLDER):
            if f.endswith(('.mp4', '.webm', '.mkv', '.avi', '.mov')):
                video_files.append(f)
    
    # Remove duplicates and shuffle
    video_files = list(set(video_files))
    random.shuffle(video_files)
    
    # Get DB records for metadata
    db_videos = {v.filename: v for v in Video.query.join(Scrape).filter(
        Scrape.user_id == current_user.id
    ).all()}
    
    # Get user's likes by filename
    user_likes = {like.filename for like in Like.query.filter_by(user_id=current_user.id).all()}
    
    # Get likes count per filename
    from sqlalchemy import func
    likes_count = dict(db.session.query(Like.filename, func.count(Like.id)).group_by(Like.filename).all())
    
    # Get comments count per filename
    comments_count = dict(db.session.query(Comment.filename, func.count(Comment.id)).group_by(Comment.filename).all())
    
    result = []
    for i, filename in enumerate(video_files):
        v = db_videos.get(filename)
        result.append({
            'id': v.id if v else i,
            'platform': v.platform if v else 'Unknown',
            'filename': filename,
            'url': v.url if v else '',
            'likes': likes_count.get(filename, 0),
            'liked': filename in user_likes,
            'comment_count': comments_count.get(filename, 0),
            'scrape_id': v.scrape_id if v else None
        })
    
    return jsonify(result)

@app.route('/api/scrape-logs/<int:scrape_id>')
@login_required
def get_scrape_logs(scrape_id):
    scrape, error, code = safe_query_or_404(Scrape, scrape_id, current_user.id)
    if error:
        return jsonify(error), code
    return jsonify({
        'logs': scrape.logs if hasattr(scrape, 'logs') else [],
        'status': scrape.status
    })

@app.route('/api/scrape/<int:scrape_id>/stop', methods=['POST'])
@login_required
def stop_scrape(scrape_id):
    scrape, error, code = safe_query_or_404(Scrape, scrape_id, current_user.id)
    if error:
        return jsonify(error), code
    scrape.status = 'stopped'
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/scrape/<int:scrape_id>/delete', methods=['DELETE'])
@login_required
def delete_scrape(scrape_id):
    scrape, error, code = safe_query_or_404(Scrape, scrape_id, current_user.id)
    if error:
        return jsonify(error), code
    
    # Delete video files before cascade delete
    for video in scrape.videos:
        if video.filename:
            filepath = os.path.join(CACHE_FOLDER, video.filename)
            safe_file_operation(os.remove, filepath)
    
    db.session.delete(scrape)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/video/<filename>/like', methods=['POST'])
@login_required
def like_video(filename):
    print(f"❤️ Like request for video {filename}")
    
    # Check if user already liked
    like = Like.query.filter_by(filename=filename, user_id=current_user.id).first()
    
    if like:
        # Unlike
        db.session.delete(like)
        liked = False
    else:
        # Like
        new_like = Like(filename=filename, user_id=current_user.id)
        db.session.add(new_like)
        liked = True
    
    db.session.commit()
    
    # Get total likes count
    total_likes = Like.query.filter_by(filename=filename).count()
    print(f"Video {filename} now has {total_likes} likes (liked={liked})")
    return jsonify({'likes': total_likes, 'liked': liked})

@app.route('/api/video/<filename>/comment', methods=['POST'])
@login_required
def add_comment(filename):
    data = request.json
    comment = Comment(filename=filename, user_id=current_user.id, text=data['text'])
    db.session.add(comment)
    db.session.commit()
    
    # Get total comments count
    total_comments = Comment.query.filter_by(filename=filename).count()
    return jsonify({'success': True, 'comment_count': total_comments})

@app.route('/api/video/<filename>/comments')
@login_required
def get_comments(filename):
    comments = Comment.query.filter_by(filename=filename).order_by(Comment.created_at.desc()).all()
    user_cache = {}
    result = []
    for c in comments:
        if c.user_id not in user_cache:
            user = User.query.get(c.user_id)
            user_cache[c.user_id] = {
                'username': user.username if user else 'Unknown',
                'avatar': user.avatar if user else None
            }
        result.append({
            'id': c.id,
            'username': user_cache[c.user_id]['username'],
            'avatar': user_cache[c.user_id]['avatar'],
            'text': c.text,
            'created_at': c.created_at.isoformat()
        })
    return jsonify(result)

@app.route('/api/comment/<int:comment_id>', methods=['PUT'])
@login_required
def edit_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    comment.text = data['text']
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/comment/<int:comment_id>', methods=['DELETE'])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    db.session.delete(comment)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/cache/<path:filename>')
@login_required
def serve_video(filename):
    return send_from_directory(CACHE_FOLDER, filename)

if __name__ == '__main__':
    cleanup_thread = threading.Thread(target=cleanup_expired_videos, args=(app, db, Video, CACHE_FOLDER), daemon=True)
    cleanup_thread.start()
    app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)
