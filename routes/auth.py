from flask import Blueprint, request, jsonify, redirect, url_for, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash #type:ignore
from backend.database import db
from backend.models import User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data['username']).first()
    if user and check_password_hash(user.password, data['password']):
        login_user(user, remember=True)
        session.permanent = True
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Invalid credentials'})

@auth_bp.route('/api/register', methods=['POST'])
def register():
    data = request.json
    if User.query.filter_by(username=data.get('username', '')).first():
        return jsonify({'success': False, 'message': 'Username exists'})
    if User.query.filter_by(email=data.get('email', '')).first():
        return jsonify({'success': False, 'message': 'Email exists'})
    is_admin = False
    if data.get('username', '').lower() == 'admin':
        is_admin = True
    user = User(
        username=data['username'],
        email=data.get('email'),
        name=data.get('name'),
        password=generate_password_hash(data['password']),
        is_admin=is_admin
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({'success': True})

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('views.auth'))

@auth_bp.route('/api/user')
@login_required
def get_user():
    return jsonify({
        'username': current_user.username,
        'name': current_user.name or current_user.username,
        'email': current_user.email,
        'phone': current_user.phone,
        'avatar': current_user.avatar,
        'is_admin': getattr(current_user, 'is_admin', False)
    })

@auth_bp.route('/api/user/update', methods=['POST'])
@login_required
def update_user():
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
