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
until redis-cli -h "$REDIS_HOST" ping 2>/dev/null; do
  >&2 echo "Redis is unavailable - sleeping"
  sleep 2
done
echo -e "${GREEN}Redis is ready!${NC}"

# Initialize database if needed
if [ "$1" != "shell" ]; then
  echo -e "${YELLOW}Initializing database...${NC}"
  flask db upgrade
  echo -e "${GREEN}Database ready!${NC}"
fi

# Handle different test modes
case "$1" in
  "security")
    echo -e "${GREEN}Running security tests...${NC}"
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
    pytest tests/ \
      -v \
      --tb=short \
      --cov=app \
      --cov-report=html:coverage-reports/all \
      --cov-report=term
    ;;
    
  "specific")
    echo -e "${GREEN}Running specific tests: ${2}${NC}"
    pytest tests/test_security/${2} -v --tb=short
    ;;
    
  "watch")
    echo -e "${GREEN}Running tests in watch mode...${NC}"
    ptw tests/test_security/ -- -v --tb=short
    ;;
    
  "shell")
    echo -e "${GREEN}Starting interactive shell...${NC}"
    exec /bin/bash
    ;;
    
  "lint")
    echo -e "${GREEN}Running linters...${NC}"
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