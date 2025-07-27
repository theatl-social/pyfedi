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
until PGPASSWORD=${POSTGRES_PASSWORD:-pyfedi} psql -h "${POSTGRES_HOST:-test-db}" -U "${POSTGRES_USER:-pyfedi}" -d "${POSTGRES_DB:-pyfedi}" -c '\q' 2>/dev/null; do
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

# Configure celery_worker.py
echo -e "${YELLOW}Configuring celery_worker.py...${NC}"
if [ -f /app/celery_worker.py ]; then
  sed -i "s|DATABASE_URL = .*|DATABASE_URL = '${DATABASE_URL:-postgresql://pyfedi:pyfedi@test-db:5432/pyfedi}'|" /app/celery_worker.py
  sed -i "s|SERVER_NAME = .*|SERVER_NAME = '${SERVER_NAME:-test.local}'|" /app/celery_worker.py
  echo -e "${GREEN}celery_worker.py configured${NC}"
else
  echo -e "${YELLOW}Warning: celery_worker.py not found${NC}"
fi

# Set up Flask environment
cd /app
export FLASK_APP=pyfedi.py
export FLASK_ENV=testing

# Initialize database
echo -e "${YELLOW}Running database migrations...${NC}"
flask db upgrade
echo -e "${GREEN}Migrations complete!${NC}"

# Skip database initialization - tests should work with empty database
echo -e "${YELLOW}Skipping database initialization for testing...${NC}"

# Verify configuration
echo -e "${YELLOW}Verifying configuration...${NC}"
flask config_check || true  # Don't fail if config_check has warnings

# Handle test execution based on RUN_TESTS
if [ "${RUN_TESTS:-true}" = "true" ]; then
  echo -e "${GREEN}Running security tests...${NC}"
  cd /app
  pytest tests/test_security/ \
    -v \
    --tb=short \
    --cov=app/security \
    --cov-report=html:coverage-reports/security \
    --cov-report=term \
    --cov-report=xml:test-reports/coverage.xml \
    --junit-xml=test-reports/junit.xml
  
  # Exit with pytest's exit code
  exit $?
else
  echo -e "${GREEN}Test environment ready!${NC}"
  echo -e "${YELLOW}Container will stay running. You can exec into it to run tests manually.${NC}"
  echo -e "${YELLOW}To run tests: pytest tests/test_security/ -v${NC}"
  
  # Keep container running
  tail -f /dev/null
fi