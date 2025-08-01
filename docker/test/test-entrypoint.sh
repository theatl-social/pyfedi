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

# Celery no longer used - removed configuration step

# Set up Flask environment
cd /app
export FLASK_APP=pyfedi.py
export FLASK_ENV=testing

# Initialize database
echo -e "${YELLOW}Running database migrations...${NC}"
flask db upgrade
echo -e "${GREEN}Migrations complete!${NC}"

# Initialize database with test data
echo -e "${YELLOW}Initializing database with test data...${NC}"
flask init-db
echo -e "${GREEN}Database initialized!${NC}"

# Verify configuration
echo -e "${YELLOW}Verifying configuration...${NC}"
flask config_check || true  # Don't fail if config_check has warnings

# Handle test execution based on command or RUN_TESTS
if [ "$1" = "pytest" ]; then
  # If pytest command provided, run it with remaining args
  shift
  exec pytest "$@"
elif [ "${RUN_TESTS:-true}" = "true" ]; then
  # Default: run all tests or specific test if provided
  echo -e "${GREEN}Running tests...${NC}"
  cd /app
  
  if [ $# -gt 0 ]; then
    # Run specific test(s) passed as arguments
    exec pytest "$@"
  else
    # Run all tests
    pytest tests/ \
      -v \
      --tb=short \
      --cov=app \
      --cov-report=html:coverage-reports \
      --cov-report=term \
      --cov-report=xml:test-reports/coverage.xml \
      --junit-xml=test-reports/junit.xml
    
    # Exit with pytest's exit code
    exit $?
  fi
else
  echo -e "${GREEN}Test environment ready!${NC}"
  echo -e "${YELLOW}Container will stay running. You can exec into it to run tests manually.${NC}"
  echo -e "${YELLOW}To run tests: pytest tests/ -v${NC}"
  
  # Keep container running
  tail -f /dev/null
fi