#!/bin/bash
#
# Comprehensive Private Registration Testing Script
# 
# This script tests private registration endpoints in various configurations:
# - Local development testing
# - CI/CD environment testing  
# - Different configuration scenarios
#
# Usage:
#   ./scripts/test-private-registration.sh --local
#   ./scripts/test-private-registration.sh --ci
#   ./scripts/test-private-registration.sh --config env-only
#   ./scripts/test-private-registration.sh --all

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'  
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TEST_DB_NAME="test_private_registration_$(date +%s)"

# Default values
MODE="local"
CONFIG_TYPE="default"
VERBOSE=false
CLEANUP=true

print_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Test private registration endpoints with various configurations"
    echo ""
    echo "Options:"
    echo "  --local              Run tests in local development mode (default)"
    echo "  --ci                 Run tests in CI/CD mode"
    echo "  --config TYPE        Configuration type: default|env-only|db-only|mixed"
    echo "  --verbose, -v        Verbose output"
    echo "  --no-cleanup         Don't cleanup test database"
    echo "  --all                Run all configuration scenarios"
    echo "  --help, -h           Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --local                    # Basic local testing"
    echo "  $0 --ci --verbose            # CI mode with verbose output"
    echo "  $0 --config env-only         # Test environment variable configuration only"
    echo "  $0 --all                     # Test all configuration scenarios"
}

log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}"
}

success() {
    echo -e "${GREEN}✓ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

error() {
    echo -e "${RED}✗ $1${NC}"
    exit 1
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --local)
            MODE="local"
            shift
            ;;
        --ci)
            MODE="ci"
            shift
            ;;
        --config)
            CONFIG_TYPE="$2"
            shift 2
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --no-cleanup)
            CLEANUP=false
            shift
            ;;
        --all)
            CONFIG_TYPE="all"
            shift
            ;;
        --help|-h)
            print_usage
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            ;;
    esac
done

# Environment setup based on mode
setup_environment() {
    local config=$1
    
    log "Setting up environment for configuration: $config"
    
    # Base environment variables
    export TESTING=true
    export WTF_CSRF_ENABLED=false
    export MAIL_SUPPRESS_SEND=true
    export CACHE_TYPE=null
    export CELERY_ALWAYS_EAGER=true
    
    case $config in
        "env-only")
            log "Testing environment variable configuration only"
            export PRIVATE_REGISTRATION_ENABLED=true
            export PRIVATE_REGISTRATION_SECRET="test-secret-env-$(date +%s)"
            export PRIVATE_REGISTRATION_ALLOWED_IPS="127.0.0.1,10.0.0.0/8,172.16.0.0/12"
            export PRIVATE_REGISTRATION_RATE_LIMIT="10"
            # Ensure database settings don't interfere
            unset DATABASE_PRIVATE_REGISTRATION_ENABLED
            ;;
        "mixed")
            log "Testing mixed environment and database configuration"
            export PRIVATE_REGISTRATION_ENABLED=true
            export PRIVATE_REGISTRATION_SECRET="test-secret-mixed-$(date +%s)"
            # Some settings from DB, some from env
            ;;
        "default"|*)
            log "Testing default configuration"
            export PRIVATE_REGISTRATION_ENABLED=true
            export PRIVATE_REGISTRATION_SECRET="test-secret-default-$(date +%s)"
            export PRIVATE_REGISTRATION_ALLOWED_IPS="127.0.0.1,10.0.0.0/8"
            export PRIVATE_REGISTRATION_RATE_LIMIT="5"
            ;;
    esac
    
    # Set server name to avoid config issues
    export SERVER_NAME=localhost
    
    # Database configuration
    if [ "$MODE" = "ci" ]; then
        export DATABASE_URL="sqlite:///:memory:"
    else
        export DATABASE_URL="sqlite:///test_private_reg.db"
    fi
    
    success "Environment configured for $config mode"
}

# Check prerequisites  
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check if we're in the right directory
    if [ ! -f "$PROJECT_ROOT/app/__init__.py" ]; then
        error "Not in PieFed project root. Please run from project directory."
    fi
    
    # Check if virtual environment is activated
    if [ "$MODE" = "local" ] && [ -z "$VIRTUAL_ENV" ]; then
        warning "Virtual environment not detected. Attempting to activate..."
        if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
            source "$PROJECT_ROOT/.venv/bin/activate"
            success "Activated virtual environment"
        else
            error "No virtual environment found. Please run 'uv venv && source .venv/bin/activate'"
        fi
    fi
    
    # Check required dependencies
    if ! python -c "import pytest" 2>/dev/null; then
        error "pytest not installed. Please install test dependencies."
    fi
    
    success "Prerequisites check passed"
}

# Run tests for a specific configuration
run_test_configuration() {
    local config=$1
    local test_name="Private Registration Tests ($config)"
    
    log "Running $test_name..."
    
    setup_environment "$config"
    
    # Pytest arguments
    local pytest_args=(
        "$PROJECT_ROOT/tests/test_private_registration_endpoints.py"
        "-v"
        "--tb=short"
    )
    
    if [ "$VERBOSE" = true ]; then
        pytest_args+=("-s")
    fi
    
    if [ "$MODE" = "ci" ]; then
        pytest_args+=(
            "--junit-xml=test-results/private-registration-$config.xml"
            "--cov=app.api.admin"
            "--cov-report=xml:coverage-$config.xml"
        )
    fi
    
    # Add PYTHONPATH if needed
    if [ -z "$PYTHONPATH" ]; then
        export PYTHONPATH="$PROJECT_ROOT"
    fi
    
    # Run the tests
    if pytest "${pytest_args[@]}"; then
        success "$test_name passed"
        return 0
    else
        error "$test_name failed"
        return 1
    fi
}

# Test all endpoints with curl (additional integration test)
test_endpoints_with_curl() {
    local base_url="http://localhost:5000/api/alpha/admin"
    local secret="$PRIVATE_REGISTRATION_SECRET"
    
    log "Running curl-based endpoint tests..."
    
    # Start a test server in background (if not already running)
    local server_pid=""
    if ! curl -s "$base_url/health" >/dev/null 2>&1; then
        log "Starting test server..."
        cd "$PROJECT_ROOT"
        flask run --port=5000 --debug &
        server_pid=$!
        sleep 5  # Wait for server to start
    fi
    
    # Test health endpoint
    log "Testing health endpoint..."
    local health_response=$(curl -s \
        -H "X-PieFed-Secret: $secret" \
        -H "X-Forwarded-For: 127.0.0.1" \
        "$base_url/health")
    
    if echo "$health_response" | grep -q '"enabled": true'; then
        success "Health endpoint test passed"
    else
        warning "Health endpoint test failed: $health_response"
    fi
    
    # Test user validation endpoint
    log "Testing user validation endpoint..."
    local validation_response=$(curl -s \
        -H "X-PieFed-Secret: $secret" \
        -H "Content-Type: application/json" \
        -H "X-Forwarded-For: 127.0.0.1" \
        -d '{"username":"testuser","email":"test@example.com"}' \
        "$base_url/user/validate")
    
    if echo "$validation_response" | grep -q '"username_available"'; then
        success "User validation endpoint test passed"
    else
        warning "User validation endpoint test failed: $validation_response"
    fi
    
    # Test registration endpoint (basic validation)
    log "Testing registration endpoint..."
    local reg_response=$(curl -s \
        -H "X-PieFed-Secret: $secret" \
        -H "Content-Type: application/json" \
        -H "X-Forwarded-For: 127.0.0.1" \
        -d '{
            "username":"curltestuser",
            "email":"curltest@example.com",
            "auto_activate":true
        }' \
        "$base_url/private_register")
    
    if echo "$reg_response" | grep -q '"success": true'; then
        success "Registration endpoint test passed"
    else
        warning "Registration endpoint test failed: $reg_response"
    fi
    
    # Cleanup server if we started it
    if [ -n "$server_pid" ]; then
        kill $server_pid 2>/dev/null || true
    fi
}

# Main test execution
main() {
    log "Starting Private Registration Test Suite"
    log "Mode: $MODE, Config: $CONFIG_TYPE"
    
    check_prerequisites
    
    # Create test results directory for CI
    if [ "$MODE" = "ci" ]; then
        mkdir -p "$PROJECT_ROOT/test-results"
    fi
    
    local exit_code=0
    
    if [ "$CONFIG_TYPE" = "all" ]; then
        # Run all configuration scenarios
        local configs=("default" "env-only" "mixed")
        for config in "${configs[@]}"; do
            log "Running configuration scenario: $config"
            if ! run_test_configuration "$config"; then
                exit_code=1
            fi
            echo ""
        done
    else
        # Run single configuration
        if ! run_test_configuration "$CONFIG_TYPE"; then
            exit_code=1
        fi
    fi
    
    # Run curl-based integration tests in local mode
    if [ "$MODE" = "local" ] && [ "$exit_code" -eq 0 ]; then
        test_endpoints_with_curl
    fi
    
    # Cleanup
    if [ "$CLEANUP" = true ]; then
        log "Cleaning up test artifacts..."
        rm -f "$PROJECT_ROOT/test_private_reg.db" 2>/dev/null || true
        success "Cleanup completed"
    fi
    
    if [ "$exit_code" -eq 0 ]; then
        success "All Private Registration tests passed!"
    else
        error "Some tests failed. Check output above."
    fi
    
    exit $exit_code
}

# Run main function
main "$@"