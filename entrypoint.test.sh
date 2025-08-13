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
python3 -m flask init-test-db 2>/dev/null || {
    echo "⚠️  init-test-db command not found, using standard init-db"
    python3 -m flask init-db
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