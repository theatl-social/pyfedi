import os
from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models import User
from werkzeug.security import generate_password_hash

internal_bp = Blueprint('internal', __name__)


# Allow running as a standalone service
if __name__ == "__main__":
    from flask import Flask
    from app import db
    from app.models import User
    import os

    app = Flask(__name__)
    # Load config if needed, or set config here
    # Example: app.config.from_object('config.Config')
    # If you have a config.py, you can load it as above

    # You may need to initialize db with app
    db.init_app(app)

    app.register_blueprint(internal_bp)

    # Optionally, set host/port from env or default
    port = int(os.environ.get("INTERNAL_API_PORT", 5932))
    app.run(host="0.0.0.0", port=port)

@internal_bp.route('/internal/add_user', methods=['POST'])
def add_user():
    # Check for a shared secret in header, value from env var INTERNAL_API_SECRET
    secret = os.environ.get('INTERNAL_API_SECRET') or current_app.config.get('INTERNAL_API_SECRET')
    if not secret or request.headers.get('X-Internal-Secret') != secret:
        return jsonify({'error': 'unauthorized'}), 403

    data = request.get_json(force=True)
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    if not username or not email or not password:
        return jsonify({'error': 'missing fields'}), 400

    if User.query.filter_by(user_name=username).first():
        return jsonify({'error': 'username exists'}), 409
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'email exists'}), 409

    user = User(user_name=username, email=email)
    user.password_hash = generate_password_hash(password)
    db.session.add(user)
    db.session.commit()
    return jsonify({'status': 'success', 'user_id': user.id})


# Internal endpoint to get user info by user.id
@internal_bp.route('/internal/health', methods=['GET'])
def health():
    """Health check endpoint, always returns 200."""
    return jsonify({'status': 'ok'}), 200


@internal_bp.route('/internal/verify_api_key', methods=['GET'])
def verify_api_key():
    """Returns 200 if X-Internal-Secret header is valid, 403 otherwise."""
    secret = os.environ.get('INTERNAL_API_SECRET') or current_app.config.get('INTERNAL_API_SECRET')
    if not secret or request.headers.get('X-Internal-Secret') != secret:
        return jsonify({'error': 'unauthorized'}), 403
    return jsonify({'status': 'ok'}), 200
@internal_bp.route('/internal/get_user', methods=['GET'])
def get_user():
    secret = os.environ.get('INTERNAL_API_SECRET') or current_app.config.get('INTERNAL_API_SECRET')
    if not secret or request.headers.get('X-Internal-Secret') != secret:
        return jsonify({'error': 'unauthorized'}), 403

    user_id = request.args.get('user_id', type=int)
    if not user_id:
        return jsonify({'error': 'missing user_id'}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'not found'}), 404

    # Return basic user info (do not expose sensitive fields)
    return jsonify({
        'id': user.id,
        'user_name': user.user_name,
        'email': user.email,
        'created_at': str(getattr(user, 'created_at', '')),
        'banned': getattr(user, 'banned', False),
        'deleted': getattr(user, 'deleted', False)
    })
