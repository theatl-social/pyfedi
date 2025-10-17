#!/bin/bash
set -e

# Full Production Mirror Test Runner
# Purpose: Validate current operations with PostgreSQL 17 before substantial changes
# This creates a complete production-like environment for comprehensive validation

echo "🚀 PieFed Full Production Mirror Test Environment"
echo "📋 Validating current operations before substantial changes"
echo "🐘 Using PostgreSQL 17 for maximum production compatibility"
echo ""

# Configuration
COMPOSE_FILE="compose.test.yml"
TEST_NETWORK="pyfedi_test_network"
TEST_TIMEOUT="300"  # 5 minutes max for full test suite

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to cleanup containers
cleanup() {
    print_status "🧹 Cleaning up test environment..."
    docker compose -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
    docker network rm "$TEST_NETWORK" 2>/dev/null || true
    print_success "✅ Cleanup completed"
}

# Set up cleanup on script exit
trap cleanup EXIT

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    print_error "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Check if compose file exists
if [ ! -f "$COMPOSE_FILE" ]; then
    print_error "❌ Test compose file not found: $COMPOSE_FILE"
    print_error "   Please ensure you're running this from the project root directory."
    exit 1
fi

print_status "🔧 Building test environment..."

# Build the containers
if ! docker compose -f "$COMPOSE_FILE" build --no-cache; then
    print_error "❌ Failed to build test containers"
    exit 1
fi

print_success "✅ Test containers built successfully"

print_status "🚀 Starting test services..."
print_status "   - PostgreSQL 17 database"
print_status "   - Redis cache"
print_status "   - Celery worker"
print_status "   - Web application"

# Start services in background
if ! docker compose -f "$COMPOSE_FILE" up -d test-db test-redis test-celery test-web; then
    print_error "❌ Failed to start test services"
    exit 1
fi

print_status "⏳ Waiting for services to be healthy..."

# Wait for database to be ready
print_status "   Checking PostgreSQL 17..."
timeout=60
while [ $timeout -gt 0 ]; do
    if docker compose -f "$COMPOSE_FILE" exec -T test-db pg_isready -U pyfedi_test -d pyfedi_test >/dev/null 2>&1; then
        print_success "   ✅ PostgreSQL 17 is ready"
        break
    fi
    sleep 2
    timeout=$((timeout - 2))
done

if [ $timeout -le 0 ]; then
    print_error "❌ PostgreSQL 17 failed to start within 60 seconds"
    print_error "   Check logs: docker compose -f $COMPOSE_FILE logs test-db"
    exit 1
fi

# Wait for Redis to be ready
print_status "   Checking Redis..."
if docker compose -f "$COMPOSE_FILE" exec -T test-redis redis-cli ping >/dev/null 2>&1; then
    print_success "   ✅ Redis is ready"
else
    print_error "❌ Redis is not responding"
    exit 1
fi

# Wait for web application to be healthy
print_status "   Checking web application..."
timeout=120
while [ $timeout -gt 0 ]; do
    if docker compose -f "$COMPOSE_FILE" exec -T test-web curl -f http://localhost:5000/ >/dev/null 2>&1; then
        print_success "   ✅ Web application is ready"
        break
    fi
    sleep 3
    timeout=$((timeout - 3))
done

if [ $timeout -le 0 ]; then
    print_warning "⚠️  Web application health check timed out, but continuing..."
    print_warning "   You can check logs: docker compose -f $COMPOSE_FILE logs test-web"
fi

print_success "🎉 Full production mirror environment is ready!"
print_status "🔍 Environment details:"
print_status "   - Database: PostgreSQL 17 at localhost:5432 (internal)"
print_status "   - Cache: Redis 7 at localhost:6379 (internal)"
print_status "   - Web: http://localhost:8031 (external)"
print_status "   - Network: $TEST_NETWORK (isolated)"

print_status "🧪 Running comprehensive validation tests..."

# Run the test suite
if docker compose -f "$COMPOSE_FILE" run --rm test-runner; then
    print_success "🎉 All validation tests passed!"
    print_success "✅ Current operations verified successfully"
    print_success "🚀 Safe to proceed with substantial changes"
    TEST_RESULT=0
else
    print_error "❌ Some validation tests failed"
    print_error "🛑 Current operations have issues that need to be addressed"
    print_error "   Check test output above for details"
    TEST_RESULT=1
fi

print_status "📊 Test environment summary:"
print_status "   - PostgreSQL 17: Production-grade database engine"
print_status "   - Complete stack: All production services running"
print_status "   - Isolated network: No interference with development"
print_status "   - Clean state: Fresh database for each test run"

if [ $TEST_RESULT -eq 0 ]; then
    print_success "🏁 Production mirror validation completed successfully!"
    echo ""
    print_status "🔄 Next steps:"
    print_status "   1. Current operations are validated ✅"
    print_status "   2. Safe to make substantial changes"
    print_status "   3. Re-run this test after changes to verify nothing broke"
    print_status "   4. Use lightweight tests for rapid development feedback"
else
    print_error "🔧 Issues found that need attention before making changes"
    echo ""
    print_status "🔄 Recommended actions:"
    print_status "   1. Fix the failing tests first"
    print_status "   2. Re-run this validation"
    print_status "   3. Only proceed with changes after all tests pass"
fi

echo ""
print_status "📚 For more information:"
print_status "   - Logs: docker compose -f $COMPOSE_FILE logs"
print_status "   - Interactive: ./scripts/test-shell.sh"
print_status "   - Lightweight tests: ./scripts/run-unit-tests.sh"

exit $TEST_RESULT
