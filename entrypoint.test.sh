#!/usr/bin/env sh
set -e

# Test Environment Entrypoint
# Purpose: Non-interactive initialization for test validation
# This mirrors the production entrypoint but with test-specific setup

echo "🧪 PieFed Test Environment Initialization"
echo "📋 Validating current operations before substantial changes"

export FLASK_APP=pyfedi.py

# 1. Start cron daemon (same as production)
echo "⏰ Starting cron daemon..."
cron

# 2. Database setup and migrations
echo "🗄️  Setting up test database..."
echo "Running database migrations..."
python3 -m flask db upgrade

# 3. Test-specific database initialization
echo "🔧 Initializing test database with baseline data..."
python3 -c "
from app import create_app, db
from app.models import Site, Instance, Settings, User, Role, RolePermission
from app.keys import RsaKeys
import json
import hashlib
import secrets

print('🧪 Creating minimal test setup (non-interactive)...')
app = create_app()
with app.app_context():
    # Check if already initialized
    if Site.query.count() > 0:
        print('✅ Database already initialized')
    else:
        print('🏗️  Creating site configuration...')
        private_key, public_key = RsaKeys.generate_keypair()
        db.session.add(Site(
            name='PieFed Test Instance', 
            description='Test instance for validating current operations', 
            public_key=public_key,
            private_key=private_key, 
            language_id=2
        ))
        
        print('🌐 Creating local instance...')
        db.session.add(Instance(
            domain='test.pyfedi.local',
            software='PieFed'
        ))
        
        print('⚙️  Adding basic settings...')
        db.session.add(Settings(name='allow_nsfw', value=json.dumps(False)))
        db.session.add(Settings(name='allow_nsfl', value=json.dumps(False)))
        db.session.add(Settings(name='allow_dislike', value=json.dumps(True)))
        
        print('👤 Creating test admin user...')
        # Create basic roles
        admin_role = Role(id=1, name='admin', title='Admin', color='#FF0000', permissions=0xFFFFFFFF)
        user_role = Role(id=2, name='user', title='User', color='#000000', permissions=0)
        db.session.add(admin_role)
        db.session.add(user_role)
        
        # Create test admin user with predictable credentials
        password = 'test_admin_password_123'
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        admin_user = User(
            id=1,
            user_name='test_admin',
            email='test_admin@test.local',
            password=password_hash,
            active=True,
            instance_id=1
        )
        db.session.add(admin_user)
        
        db.session.commit()
        print('✅ Test setup complete! Admin: test_admin / test_admin_password_123')
" 2>/dev/null || {
    echo "❌ Failed to initialize test database"
    exit 1
}

# 4. Load test fixtures if available
echo "📊 Loading test fixtures..."
python3 -m flask load-test-fixtures 2>/dev/null || {
    echo "ℹ️  No test fixtures to load, continuing with basic setup"
}

# 5. Verify test environment is ready
echo "🔍 Verifying test environment..."
python3 -c "
import os
from app import create_app, db
from app.models import Site, User, Community

print('Testing database connection...')
app = create_app()
with app.app_context():
    try:
        site = Site.query.first()
        user_count = User.query.count()
        comm_count = Community.query.count()
        print(f'✅ Database ready: Site={site.name if site else \"None\"}, Users={user_count}, Communities={comm_count}')
    except Exception as e:
        print(f'❌ Database verification failed: {e}')
        exit(1)
"

# 6. Start the application or run tests
if [ "${RUN_TESTS:-}" = "true" ]; then
    echo "🧪 Running test suite..."
    # This will be handled by the test-runner container
    exec "$@"
else
    echo "🚀 Starting test web server..."
    # Drop privileges and run the main application as the 'python' user
    if [ "${FLASK_DEBUG:-}" = "1" ] && [ "${FLASK_ENV:-}" = "development" ]; then
        export FLASK_RUN_EXTRA_FILES=$(find app/templates app/static -type f | tr '\n' ':')
        echo "Starting flask development server as user 'python'..."
        exec gosu python python3 -m flask run -h 0.0.0.0 -p 5000
    else
        echo "Starting Gunicorn as user 'python'..."
        exec gosu python python3 -m gunicorn --config gunicorn.conf.py --preload pyfedi:app
    fi
fi