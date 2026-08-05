import os
import random
from flask import Blueprint, request, jsonify, send_from_directory, current_app
from flask_login import login_required, current_user
from sqlalchemy import func
from backend.database import db
from backend.models import User, Scrape, Video, Comment, Like, SavedVideo, WatchHistory
from config import CACHE_FOLDER
from backend.utils import safe_file_operation
from backend.scraper import download_video_task

videos_bp = Blueprint('videos', __name__)

@videos_bp.route('/api/videos')
@login_required
def get_videos():
    limit = request.args.get('limit', default=30, type=int)
    offset = request.args.get('offset', default=0, type=int)
    exclude_ids = request.args.get('exclude', default='', type=str)
    
    excluded = set()
    if exclude_ids:
        try:
            excluded = set(map(int, exclude_ids.split(',')))
        except:
            pass
            
    watched_filenames = {h.filename for h in WatchHistory.query.filter_by(user_id=current_user.id).all()}
    
    query = Video.query.filter(
        Video.status == 'completed'
    ).order_by(Video.created_at.desc())
    
    if excluded:
        query = query.filter(Video.id.notin_(excluded))
        
    videos = query.all()
    valid_videos = videos
    
    user_likes = {like.filename for like in Like.query.filter_by(user_id=current_user.id).all()}
    user_saved = {saved.filename for saved in SavedVideo.query.filter_by(user_id=current_user.id).all()}
    
    likes_count = dict(db.session.query(Like.filename, func.count(Like.id)).group_by(Like.filename).all())
    comments_count = dict(db.session.query(Comment.filename, func.count(Comment.id)).group_by(Comment.filename).all())
    
    unwatched = []
    watched = []
    for v in valid_videos:
        video_data = {
            'id': v.id,
            'platform': v.platform,
            'filename': v.filename,
            'url': v.url,
            'likes': likes_count.get(v.filename, 0),
            'liked': v.filename in user_likes,
            'saved': v.filename in user_saved,
            'comment_count': comments_count.get(v.filename, 0),
            'scrape_id': v.scrape_id,
            'watched': v.filename in watched_filenames
        }
        if v.filename in watched_filenames:
            watched.append(video_data)
        else:
            unwatched.append(video_data)
            
    random.shuffle(unwatched)
    random.shuffle(watched)
    
    result = unwatched[:limit]
    if len(result) < limit:
        result.extend(watched[:limit - len(result)])
    return jsonify(result)

@videos_bp.route('/api/video/<int:video_id>/download_request', methods=['POST'])
@login_required
def download_request(video_id):
    video = Video.query.get_or_404(video_id)
    scrape = Scrape.query.get(video.scrape_id)
    try:
        app_instance = current_app._get_current_object()
        download_video_task(video.id, video.url, scrape.id, app_instance, db, Video, Scrape, CACHE_FOLDER)
        db.session.refresh(video)
        if video.status in ['completed', 'ready']:
            return jsonify({
                'success': True,
                'filename': video.filename,
                'status': video.status
            })
        else:
            return jsonify({
                'success': False,
                'message': f"Download failed: status is {video.status}"
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

@videos_bp.route('/api/video/<int:video_id>/cleanup_server_file', methods=['POST'])
@login_required
def cleanup_server_file(video_id):
    video = Video.query.get_or_404(video_id)
    if video.filename:
        filepath = os.path.join(CACHE_FOLDER, video.filename)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                return jsonify({'success': True, 'message': 'Server file deleted successfully'})
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)})
    return jsonify({'success': True, 'message': 'No file to delete'})

@videos_bp.route('/api/video/<path:filename>/like', methods=['POST'])
@login_required
def like_video(filename):
    like = Like.query.filter_by(filename=filename, user_id=current_user.id).first()
    if like:
        db.session.delete(like)
        liked = False
    else:
        new_like = Like(filename=filename, user_id=current_user.id)
        db.session.add(new_like)
        liked = True
    db.session.commit()
    total_likes = Like.query.filter_by(filename=filename).count()
    return jsonify({'likes': total_likes, 'liked': liked})

@videos_bp.route('/api/video/<path:filename>/comment', methods=['POST'])
@login_required
def add_comment(filename):
    data = request.json
    comment = Comment(filename=filename, user_id=current_user.id, text=data['text'])
    db.session.add(comment)
    db.session.commit()
    total_comments = Comment.query.filter_by(filename=filename).count()
    return jsonify({'success': True, 'comment_count': total_comments})

@videos_bp.route('/api/video/<path:filename>/comments')
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
                'name': user.name if user else None,
                'avatar': user.avatar if user else None
            }
        result.append({
            'id': c.id,
            'username': user_cache[c.user_id]['username'],
            'name': user_cache[c.user_id]['name'],
            'avatar': user_cache[c.user_id]['avatar'],
            'text': c.text,
            'created_at': c.created_at.isoformat()
        })
    return jsonify(result)

@videos_bp.route('/api/comment/<int:comment_id>', methods=['PUT'])
@login_required
def edit_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    comment.text = data['text']
    db.session.commit()
    return jsonify({'success': True})

@videos_bp.route('/api/comment/<int:comment_id>', methods=['DELETE'])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    db.session.delete(comment)
    db.session.commit()
    return jsonify({'success': True})

@videos_bp.route('/api/video/<path:filename>/save', methods=['POST'])
@login_required
def save_video(filename):
    existing = SavedVideo.query.filter_by(filename=filename, user_id=current_user.id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'saved': False})
    else:
        video = Video.query.filter_by(filename=filename).first()
        platform = video.platform if video else filename.split('_')[0]
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

@videos_bp.route('/api/saved-videos')
@login_required
def get_saved_videos():
    limit = request.args.get('limit', type=int)
    query = SavedVideo.query.filter_by(user_id=current_user.id).order_by(SavedVideo.created_at.desc())
    if limit:
        query = query.limit(limit)
    saved = query.all()
    
    user_likes = {like.filename for like in Like.query.filter_by(user_id=current_user.id).all()}
    likes_count = dict(db.session.query(Like.filename, func.count(Like.id)).group_by(Like.filename).all())
    comments_count = dict(db.session.query(Comment.filename, func.count(Comment.id)).group_by(Comment.filename).all())
    result = []
    for s in saved:
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

@videos_bp.route('/api/saved-video/<int:saved_id>', methods=['DELETE'])
@login_required
def delete_saved_video(saved_id):
    saved = SavedVideo.query.get_or_404(saved_id)
    if saved.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    filepath = os.path.join(CACHE_FOLDER, saved.filename)
    safe_file_operation(os.remove, filepath)
    db.session.delete(saved)
    db.session.commit()
    return jsonify({'success': True})

@videos_bp.route('/cache/<path:filename>')
@login_required
def serve_video(filename):
    return send_from_directory(CACHE_FOLDER, filename)

@videos_bp.route('/api/video/<path:filename>/watch', methods=['POST'])
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

@videos_bp.route('/api/history-videos')
@login_required
def get_history_videos():
    limit = request.args.get('limit', type=int)
    query = WatchHistory.query.filter_by(user_id=current_user.id).order_by(WatchHistory.watched_at.desc())
    if limit:
        query = query.limit(limit)
    history = query.all()
    user_likes = {like.filename for like in Like.query.filter_by(user_id=current_user.id).all()}
    
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
            
    for h in orphaned:
        db.session.delete(h)
    if orphaned:
        db.session.commit()
    return jsonify(result)

@videos_bp.route('/api/history/<int:history_id>', methods=['DELETE'])
@login_required
def delete_history(history_id):
    history = WatchHistory.query.get_or_404(history_id)
    if history.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    db.session.delete(history)
    db.session.commit()
    return jsonify({'success': True})
