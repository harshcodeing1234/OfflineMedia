from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, session #type:ignore
from flask_login import LoginManager, login_user, logout_user, login_required, current_user #type:ignore
from werkzeug.security import generate_password_hash, check_password_hash #type:ignore
from database import db, init_db
from models import User, Scrape, Video, Comment, Like, SavedVideo, WatchHistory
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

@app.route('/saved')
@login_required
def saved():
    return render_template('saved.html')

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
    from sqlalchemy import func
    
    total_scraps = db.session.query(func.count(Scrape.id)).filter_by(user_id=current_user.id).scalar()
    total_videos = db.session.query(func.count(Video.id)).join(Scrape).filter(
        Scrape.user_id == current_user.id,
        Video.status == 'completed'
    ).scalar()
    total_likes = db.session.query(func.count(Like.id)).join(
        Video, Like.filename == Video.filename
    ).join(Scrape).filter(
        Scrape.user_id == current_user.id
    ).scalar()
    
    # Calculate actual cache size (all files)
    cache_size = sum(os.path.getsize(os.path.join(CACHE_FOLDER, f)) 
                     for f in os.listdir(CACHE_FOLDER) 
                     if os.path.isfile(os.path.join(CACHE_FOLDER, f)))
    
    # Count actual video files
    actual_videos = len([f for f in os.listdir(CACHE_FOLDER) 
                         if f.endswith(('.mp4', '.webm'))])
    
    return jsonify({
        'total_videos': actual_videos,
        'total_scraps': total_scraps or 0,
        'cache_size_mb': round(cache_size / (1024 * 1024), 1),
        'total_likes': total_likes or 0
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
    hashtags = data.get('hashtags', {})
    quantity = data.get('quantity', 100)
    threading.Thread(target=run_scraper, args=(scrape.id, data['duration'], data['ttl'], data.get('platforms', 'all'), hashtags, quantity), daemon=True).start()
    
    return jsonify({'success': True, 'scrape_id': scrape.id})


def run_scraper(scrape_id, duration, ttl, platforms, hashtags=None, quantity=100):
    """Wrapper for scraper session"""
    with app.app_context():
        run_scraper_session(scrape_id, duration, ttl, platforms, hashtags or {}, quantity, db, Video, Scrape, executor, download_video, CACHE_FOLDER)


def download_video(video_id, url, scrape_id):
    """Wrapper for download task"""
    download_video_task(video_id, url, scrape_id, app, db, Video, Scrape, CACHE_FOLDER)

@app.route('/api/videos')
@login_required
def get_videos():
    limit = request.args.get('limit', type=int)
    offset = request.args.get('offset', default=0, type=int)
    
    # Get user's videos from DB
    query = Video.query.join(Scrape).filter(
        Scrape.user_id == current_user.id,
        Video.status == 'completed'
    )
    
    # Shuffle using random order (consistent per session)
    from sqlalchemy import func
    query = query.order_by(func.random())
    
    videos = query.all()
    
    # Clean up orphaned videos first
    orphaned = []
    for v in videos:
        if not os.path.exists(os.path.join(CACHE_FOLDER, v.filename)):
            orphaned.append(v)
    
    for v in orphaned:
        db.session.delete(v)
    
    if orphaned:
        db.session.commit()
        # Re-query after cleanup
        videos = query.all()
    
    # Apply limit/offset after cleanup
    if limit:
        videos = videos[offset:offset+limit] if offset else videos[:limit]
    
    # Get watched videos
    watched_filenames = {h.filename for h in WatchHistory.query.filter_by(user_id=current_user.id).all()}
    
    # Get user's likes
    user_likes = {like.filename for like in Like.query.filter_by(user_id=current_user.id).all()}
    
    # Get likes count
    likes_count = dict(db.session.query(Like.filename, func.count(Like.id)).group_by(Like.filename).all())
    comments_count = dict(db.session.query(Comment.filename, func.count(Comment.id)).group_by(Comment.filename).all())
    
    # Separate unwatched and watched
    unwatched = []
    watched = []
    
    for v in videos:
        video_data = {
            'id': v.id,
            'platform': v.platform,
            'filename': v.filename,
            'url': v.url,
            'likes': likes_count.get(v.filename, 0),
            'liked': v.filename in user_likes,
            'comment_count': comments_count.get(v.filename, 0),
            'scrape_id': v.scrape_id,
            'watched': v.filename in watched_filenames
        }
        
        if v.filename in watched_filenames:
            watched.append(video_data)
        else:
            unwatched.append(video_data)
    
    # Return unwatched first, then watched (only if no unwatched)
    if unwatched:
        return jsonify(unwatched)
    else:
        return jsonify(watched)

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
    
    # Create stop flag file to signal scraping threads
    stop_flag = f"stop_{scrape_id}.flag"
    open(stop_flag, 'w').close()
    
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

@app.route('/api/video/<filename>/save', methods=['POST'])
@login_required
def save_video(filename):
    # Check if already saved
    existing = SavedVideo.query.filter_by(filename=filename, user_id=current_user.id).first()
    
    if existing:
        # Unsave
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'saved': False})
    else:
        # Get platform from video or filename
        video = Video.query.filter_by(filename=filename).first()
        platform = video.platform if video else filename.split('_')[0]
        
        # Copy file to permanent location if needed
        import shutil
        src = os.path.join(CACHE_FOLDER, filename)
        if os.path.exists(src):
            saved_video = SavedVideo(
                user_id=current_user.id,
                filename=filename,
                platform=platform
            )
            db.session.add(saved_video)
            db.session.commit()
            return jsonify({'saved': True})
        else:
            return jsonify({'error': 'Video not found'}), 404

@app.route('/api/saved-videos')
@login_required
def get_saved_videos():
    limit = request.args.get('limit', type=int)
    
    query = SavedVideo.query.filter_by(user_id=current_user.id).order_by(SavedVideo.created_at.desc())
    
    if limit:
        query = query.limit(limit)
    
    saved = query.all()
    
    # Get user's likes
    user_likes = {like.filename for like in Like.query.filter_by(user_id=current_user.id).all()}
    
    # Get likes count
    from sqlalchemy import func
    likes_count = dict(db.session.query(Like.filename, func.count(Like.id)).group_by(Like.filename).all())
    comments_count = dict(db.session.query(Comment.filename, func.count(Comment.id)).group_by(Comment.filename).all())
    
    result = []
    for s in saved:
        # Check if file still exists
        if os.path.exists(os.path.join(CACHE_FOLDER, s.filename)):
            result.append({
                'id': s.id,
                'platform': s.platform,
                'filename': s.filename,
                'likes': likes_count.get(s.filename, 0),
                'liked': s.filename in user_likes,
                'comment_count': comments_count.get(s.filename, 0),
                'created_at': s.created_at.isoformat()
            })
    
    return jsonify(result)

@app.route('/api/saved-video/<int:saved_id>', methods=['DELETE'])
@login_required
def delete_saved_video(saved_id):
    saved = SavedVideo.query.get_or_404(saved_id)
    if saved.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Delete file
    filepath = os.path.join(CACHE_FOLDER, saved.filename)
    safe_file_operation(os.remove, filepath)
    
    db.session.delete(saved)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/cache/<path:filename>')
@login_required
def serve_video(filename):
    return send_from_directory(CACHE_FOLDER, filename)

@app.route('/api/video/<filename>/watch', methods=['POST'])
@login_required
def mark_watched(filename):
    existing = WatchHistory.query.filter_by(filename=filename, user_id=current_user.id).first()
    if not existing:
        video = Video.query.filter_by(filename=filename).first()
        platform = video.platform if video else filename.split('_')[0]
        history = WatchHistory(user_id=current_user.id, filename=filename, platform=platform)
        db.session.add(history)
        db.session.commit()
    return jsonify({'success': True})

@app.route('/history')
@login_required
def history():
    return render_template('history.html')

@app.route('/api/history-videos')
@login_required
def get_history_videos():
    limit = request.args.get('limit', type=int)
    
    query = WatchHistory.query.filter_by(user_id=current_user.id).order_by(WatchHistory.watched_at.desc())
    
    if limit:
        query = query.limit(limit)
    
    history = query.all()
    
    user_likes = {like.filename for like in Like.query.filter_by(user_id=current_user.id).all()}
    from sqlalchemy import func
    likes_count = dict(db.session.query(Like.filename, func.count(Like.id)).group_by(Like.filename).all())
    comments_count = dict(db.session.query(Comment.filename, func.count(Comment.id)).group_by(Comment.filename).all())
    
    result = []
    orphaned = []
    for h in history:
        if os.path.exists(os.path.join(CACHE_FOLDER, h.filename)):
            result.append({
                'id': h.id,
                'platform': h.platform,
                'filename': h.filename,
                'likes': likes_count.get(h.filename, 0),
                'liked': h.filename in user_likes,
                'comment_count': comments_count.get(h.filename, 0),
                'watched_at': h.watched_at.isoformat()
            })
        else:
            orphaned.append(h)
    
    # Clean up orphaned history entries
    for h in orphaned:
        db.session.delete(h)
    
    if orphaned:
        db.session.commit()
    
    return jsonify(result)

if __name__ == '__main__':
    # Protect cache folder
    if not os.path.exists(CACHE_FOLDER):
        os.makedirs(CACHE_FOLDER)
    
    # Set restrictive permissions (owner only)
    try:
        os.chmod(CACHE_FOLDER, 0o700)
    except:
        pass
    
    # Create .nomedia file to hide from gallery apps
    nomedia_path = os.path.join(CACHE_FOLDER, '.nomedia')
    if not os.path.exists(nomedia_path):
        open(nomedia_path, 'w').close()
    
    cleanup_thread = threading.Thread(target=cleanup_expired_videos, args=(app, db, Video, CACHE_FOLDER), daemon=True)
    cleanup_thread.start()
    app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)
