#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}PyFedi Test Environment${NC}"
echo "========================="

# Wait for PostgreSQL
echo -e "${YELLOW}Waiting for PostgreSQL...${NC}"
until PGPASSWORD=$POSTGRES_PASSWORD psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\q' 2>/dev/null; do
  >&2 echo "PostgreSQL is unavailable - sleeping"
  sleep 2
done
echo -e "${GREEN}PostgreSQL is ready!${NC}"

# Wait for Redis
echo -e "${YELLOW}Waiting for Redis...${NC}"
until python -c "import redis; r = redis.Redis(host='${REDIS_HOST:-test-redis}', port=6379); r.ping()" 2>/dev/null; do
  >&2 echo "Redis is unavailable - sleeping"
  sleep 2
done
echo -e "${GREEN}Redis is ready!${NC}"

# Initialize database if needed
if [ "$1" != "shell" ]; then
  echo -e "${YELLOW}Initializing database...${NC}"
  cd /app
  
  # Copy test_env.py to app directory so it can be imported
  cp /app/docker/test/test_env.py /app/test_env.py
  
  # Create a test-specific pyfedi.py that uses TestConfig
  cat > /app/pyfedi_test.py << 'EOF'
import sys
import os
from test_env import TestConfig
from app import create_app, db, cli
app = create_app(TestConfig)
cli.register(app)
EOF
  
  export FLASK_APP=pyfedi_test.py
  echo -e "${YELLOW}Running database migrations...${NC}"
  python -m flask db upgrade
  
  echo -e "${YELLOW}Initializing database with required data...${NC}"
  # Create a non-interactive database initialization script
  cat > /app/init_test_db.py << 'EOF'
import sys
import os
sys.path.insert(0, '/app/docker/test')
from test_env import TestConfig
sys.path.insert(0, '/app')
from app import create_app, db
from app.activitypub.signature import RsaKeys
from app.models import Site, Instance, Settings, Language, Role, RolePermission, User
from flask import json
from datetime import datetime
import uuid

app = create_app(TestConfig)

with app.app_context():
    # Drop and recreate all tables
    db.drop_all()
    db.configure_mappers()
    db.create_all()
    
    # Generate site keys
    private_key, public_key = RsaKeys.generate_keypair()
    
    # Create site
    site = Site(
        name="PyFedi Test Instance",
        description='Test instance for security testing',
        public_key=public_key,
        private_key=private_key,
        language_id=2
    )
    db.session.add(site)
    
    # Create local instance
    db.session.add(Instance(
        domain=app.config['SERVER_NAME'],
        software='PieFed'
    ))
    
    # Add settings
    db.session.add(Settings(name='allow_nsfw', value=json.dumps(False)))
    db.session.add(Settings(name='allow_nsfl', value=json.dumps(False)))
    db.session.add(Settings(name='allow_dislike', value=json.dumps(True)))
    db.session.add(Settings(name='allow_local_image_posts', value=json.dumps(True)))
    db.session.add(Settings(name='allow_remote_image_posts', value=json.dumps(True)))
    db.session.add(Settings(name='federation', value=json.dumps(True)))
    
    # Initial languages
    db.session.add(Language(name='Undetermined', code='und'))
    db.session.add(Language(code='en', name='English'))
    
    # Initial roles
    anon_role = Role(name='Anonymous user', weight=0)
    db.session.add(anon_role)
    
    auth_role = Role(name='Authenticated user', weight=1)
    db.session.add(auth_role)
    
    staff_role = Role(name='Staff', weight=2)
    staff_role.permissions.append(RolePermission(permission='approve registrations'))
    staff_role.permissions.append(RolePermission(permission='ban users'))
    staff_role.permissions.append(RolePermission(permission='administer all communities'))
    staff_role.permissions.append(RolePermission(permission='administer all users'))
    db.session.add(staff_role)
    
    admin_role = Role(name='Admin', weight=3)
    admin_role.permissions.append(RolePermission(permission='approve registrations'))
    admin_role.permissions.append(RolePermission(permission='change user roles'))
    admin_role.permissions.append(RolePermission(permission='ban users'))
    admin_role.permissions.append(RolePermission(permission='manage users'))
    admin_role.permissions.append(RolePermission(permission='change instance settings'))
    admin_role.permissions.append(RolePermission(permission='administer all communities'))
    admin_role.permissions.append(RolePermission(permission='administer all users'))
    admin_role.permissions.append(RolePermission(permission='edit cms pages'))
    db.session.add(admin_role)
    
    # Create test admin user
    private_key, public_key = RsaKeys.generate_keypair()
    admin_user = User(
        user_name='admin',
        title='Test Admin',
        email='admin@test.instance',
        verification_token=str(uuid.uuid4()),
        instance_id=1,
        email_unread_sent=False,
        private_key=private_key,
        public_key=public_key,
        alt_user_name='admin_alt_' + str(uuid.uuid4())[:8]
    )
    admin_user.set_password('testpassword123')
    admin_user.roles.append(admin_role)
    admin_user.verified = True
    admin_user.last_seen = datetime.utcnow()
    admin_user.ap_profile_id = f"https://{app.config['SERVER_NAME']}/u/admin"
    admin_user.ap_public_url = f"https://{app.config['SERVER_NAME']}/u/admin"
    admin_user.ap_inbox_url = f"https://{app.config['SERVER_NAME']}/u/admin/inbox"
    db.session.add(admin_user)
    
    db.session.commit()
    print("Test database initialized successfully!")
EOF
  
  python /app/init_test_db.py
  
  echo -e "${GREEN}Database ready!${NC}"
fi

# Handle different test modes
case "$1" in
  "security")
    echo -e "${GREEN}Running security tests...${NC}"
    export FLASK_APP=pyfedi_test.py
    cd /app
    pytest tests/test_security/ \
      -v \
      --tb=short \
      --cov=app/security \
      --cov-report=html:coverage-reports/security \
      --cov-report=term \
      --cov-report=xml:test-reports/coverage.xml \
      --junit-xml=test-reports/junit.xml
    ;;
    
  "all")
    echo -e "${GREEN}Running all tests...${NC}"
    export FLASK_APP=pyfedi_test.py
    cd /app
    pytest tests/ \
      -v \
      --tb=short \
      --cov=app \
      --cov-report=html:coverage-reports/all \
      --cov-report=term
    ;;
    
  "specific")
    echo -e "${GREEN}Running specific tests: ${2}${NC}"
    export FLASK_APP=pyfedi_test.py
    cd /app
    pytest tests/test_security/${2} -v --tb=short
    ;;
    
  "watch")
    echo -e "${GREEN}Running tests in watch mode...${NC}"
    export FLASK_APP=pyfedi_test.py
    cd /app
    ptw tests/test_security/ -- -v --tb=short
    ;;
    
  "shell")
    echo -e "${GREEN}Starting interactive shell...${NC}"
    exec /bin/bash
    ;;
    
  "lint")
    echo -e "${GREEN}Running linters...${NC}"
    cd /app
    echo "Running flake8..."
    flake8 app/security/ --max-line-length=120 --ignore=E501,W293
    echo "Running black check..."
    black --check app/security/
    echo "Running isort check..."
    isort --check-only app/security/
    echo "Running mypy..."
    mypy app/security/
    ;;
    
  "security-scan")
    echo -e "${GREEN}Running security scan...${NC}"
    cd /app
    echo "Running bandit..."
    bandit -r app/security/ -f json -o test-reports/bandit.json
    echo "Running safety check..."
    safety check --json --output test-reports/safety.json
    echo "Running SQL injection audit..."
    python scripts/audit_sql_injection.py app/ -o test-reports/sql-audit.txt
    ;;
    
  *)
    echo -e "${RED}Unknown command: $1${NC}"
    echo "Available commands:"
    echo "  security      - Run security tests only"
    echo "  all          - Run all tests"
    echo "  specific <file> - Run specific test file"
    echo "  watch        - Run tests in watch mode"
    echo "  shell        - Interactive shell"
    echo "  lint         - Run code linters"
    echo "  security-scan - Run security scanners"
    exit 1
    ;;
esac