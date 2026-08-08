import os
import threading
from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import func
from backend.database import db
from backend.models import User, Scrape, Video, Comment, Like, SavedVideo, WatchHistory
from config import CACHE_FOLDER, THREAD_POOL_WORKERS
from backend.utils import safe_query_or_404, safe_file_operation
from backend.scraper import run_scraper_session, download_video_task

admin_bp = Blueprint('admin', __name__)

# Initialize the background scraping task executor.
# On Linux servers (AWS), YouTube downloads spawn a deno process per video for JS challenge solving.
# Running too many concurrently causes load spikes and hung downloads on t3.micro/small.
# Default: 3 on Linux, 10 on Windows/macOS. Override via THREAD_POOL_WORKERS env variable.
import platform as _platform
_default_workers = 8 if _platform.system() == "Linux" else THREAD_POOL_WORKERS
_workers = int(os.environ.get("THREAD_POOL_WORKERS", _default_workers))
executor = ThreadPoolExecutor(max_workers=_workers)
print(f"[Executor] ThreadPoolExecutor initialized with {_workers} workers")

def run_scraper(app_instance, scrape_id, duration, ttl, platforms, hashtags=None, quantity=100):
    """Wrapper for running scraper session in a background thread"""
    with app_instance.app_context():
        try:
            def download_video(video_id, url, scrape_id):
                """Wrapper for download task inside the scraping thread"""
                download_video_task(video_id, url, scrape_id, app_instance, db, Video, Scrape, CACHE_FOLDER)

            run_scraper_session(
                scrape_id, duration, ttl, platforms, hashtags or {}, quantity, 
                db, Video, Scrape, executor, download_video, CACHE_FOLDER
            )
        finally:
            db.session.remove()

@admin_bp.route('/api/stats')
@login_required
def get_stats():
    total_scraps = db.session.query(func.count(Scrape.id)).scalar()
    total_videos = db.session.query(func.count(Video.id)).filter(Video.status == 'completed').scalar()
    total_likes = db.session.query(func.count(Like.id)).scalar()
    
    # Calculate actual cache size (all files)
    cache_size = sum(
        os.path.getsize(os.path.join(CACHE_FOLDER, f)) 
        for f in os.listdir(CACHE_FOLDER) 
        if os.path.isfile(os.path.join(CACHE_FOLDER, f))
    )
    
    actual_videos = len([
        f for f in os.listdir(CACHE_FOLDER) 
        if f.endswith(('.mp4', '.webm'))
    ])
    
    return jsonify({
        'total_videos': actual_videos,
        'total_scraps': total_scraps or 0,
        'cache_size_mb': round(cache_size / (1024 * 1024), 1),
        'total_likes': total_likes or 0
    })

@admin_bp.route('/api/scraping-status')
@login_required
def scraping_status():
    active = db.session.query(db.exists().where(
        Scrape.status.in_(['scraping', 'downloading'])
    )).scalar()
    return jsonify({'is_scraping': active})

@admin_bp.route('/api/scrapes')
@login_required
def get_scrapes():
    scrapes = Scrape.query.order_by(Scrape.created_at.desc()).all()
    return jsonify([{
        'id': s.id,
        'duration': s.duration,
        'ttl': s.ttl,
        'status': s.status,
        'platforms': s.platforms,
        'progress': s.progress,
        'total_videos': s.total_videos,
        'downloaded_videos': s.downloaded_videos,
        'video_count': len(s.videos),
        'created_at': s.created_at.isoformat(),
        'started_at': s.started_at.isoformat() if s.started_at else None,
        'expires_at': s.expires_at.isoformat() if s.expires_at else None,
        'status_text': f"{'Scraping...' if s.status == 'scraping' else f'Downloading {s.downloaded_videos}/{s.total_videos}' if s.status == 'downloading' else s.status.title()}"
    } for s in scrapes])

@admin_bp.route('/api/scrape', methods=['POST'])
@login_required
def create_scrape():
    if not getattr(current_user, 'is_admin', False):
        return jsonify({'error': 'Admin access required'}), 403
        
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
    
    # Start scraping in background thread
    hashtags = data.get('hashtags', {})
    quantity = data.get('quantity', 100)
    
    app_instance = current_app._get_current_object()
    threading.Thread(
        target=run_scraper, 
        args=(app_instance, scrape.id, data['duration'], data['ttl'], data.get('platforms', 'all'), hashtags, quantity), 
        daemon=True
    ).start()
    
    return jsonify({'success': True, 'scrape_id': scrape.id})

@admin_bp.route('/api/scrape/<int:scrape_id>/videos')
@login_required
def get_scrape_videos(scrape_id):
    scrape = Scrape.query.get_or_404(scrape_id)
    return jsonify([{
        'id': v.id,
        'platform': v.platform,
        'url': v.url,
        'status': v.status,
        'filename': v.filename
    } for v in scrape.videos])

@admin_bp.route('/api/scrape-logs/<int:scrape_id>')
@login_required
def get_scrape_logs(scrape_id):
    owner_id = None if getattr(current_user, 'is_admin', False) else current_user.id
    scrape, error, code = safe_query_or_404(Scrape, scrape_id, owner_id)
    if error:
        return jsonify(error), code
    return jsonify({
        'logs': scrape.logs if hasattr(scrape, 'logs') else [],
        'status': scrape.status
    })

@admin_bp.route('/api/scrape/<int:scrape_id>/stop', methods=['POST'])
@login_required
def stop_scrape(scrape_id):
    owner_id = None if getattr(current_user, 'is_admin', False) else current_user.id
    scrape, error, code = safe_query_or_404(Scrape, scrape_id, owner_id)
    if error:
        return jsonify(error), code
        
    scrape.status = 'stopped'
    db.session.commit()
    
    # Create stop flag file to signal scraping threads
    stop_flag = f"stop_{scrape_id}.flag"
    open(stop_flag, 'w').close()
    return jsonify({'success': True})

@admin_bp.route('/api/scrape/<int:scrape_id>/delete', methods=['DELETE'])
@login_required
def delete_scrape(scrape_id):
    owner_id = None if getattr(current_user, 'is_admin', False) else current_user.id
    scrape, error, code = safe_query_or_404(Scrape, scrape_id, owner_id)
    if error:
        return jsonify(error), code
        
    # Delete video files before cascade database record deletion
    for video in scrape.videos:
        if video.filename:
            filepath = os.path.join(CACHE_FOLDER, video.filename)
            safe_file_operation(os.remove, filepath)
            
    db.session.delete(scrape)
    db.session.commit()
    return jsonify({'success': True})
