import os
from flask import Blueprint, render_template, redirect, url_for, send_from_directory, current_app
from flask_login import login_required, current_user
from config import CACHE_FOLDER

views_bp = Blueprint('views', __name__)

@views_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('views.dashboard'))
    return redirect(url_for('views.auth'))

@views_bp.route('/auth')
def auth():
    if current_user.is_authenticated:
        return redirect(url_for('views.dashboard'))
    return render_template('auth.html')

@views_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@views_bp.route('/scrapp')
@login_required
def scrapp():
    return render_template('scrapp.html')

@views_bp.route('/play')
@login_required
def play():
    return render_template('play.html')

@views_bp.route('/saved')
@login_required
def saved():
    return render_template('saved.html')

@views_bp.route('/polling')
@login_required
def polling():
    if not getattr(current_user, 'is_admin', False):
        return redirect(url_for('views.dashboard'))
    return render_template('polling.html')

@views_bp.route('/admin')
@login_required
def admin():
    if not getattr(current_user, 'is_admin', False):
        return redirect(url_for('views.dashboard'))
    return render_template('admin.html')

@views_bp.route('/about')
@login_required
def about():
    return render_template('about.html')

@views_bp.route('/contact')
@login_required
def contact():
    return render_template('contact.html')

@views_bp.route('/history')
@login_required
def history():
    return render_template('history.html')

# PWA serving endpoints
@views_bp.route('/sw.js')
def serve_sw():
    return send_from_directory(os.path.join(current_app.root_path, 'static'), 'sw.js', mimetype='application/javascript')

@views_bp.route('/manifest.json')
def serve_manifest():
    return send_from_directory(os.path.join(current_app.root_path, 'static'), 'manifest.json', mimetype='application/json')

@views_bp.route('/icon.svg')
def serve_icon():
    return send_from_directory(os.path.join(current_app.root_path, 'static'), 'icon.svg', mimetype='image/svg+xml')
