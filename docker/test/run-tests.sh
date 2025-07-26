#!/bin/bash
# Convenience script to run tests using Docker Compose

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Default to security tests
TEST_TYPE="${1:-security}"

echo -e "${GREEN}PyFedi Docker Test Runner${NC}"
echo "=========================="

# Function to cleanup
cleanup() {
    echo -e "\n${YELLOW}Cleaning up...${NC}"
    docker-compose -f docker/test/docker-compose.yml down -v
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Change to project root
cd "$(dirname "$0")/../.."

case "$TEST_TYPE" in
    "security")
        echo -e "${GREEN}Running security tests...${NC}"
        docker-compose -f docker/test/docker-compose.yml up --build test-runner
        ;;
        
    "all")
        echo -e "${GREEN}Running all tests...${NC}"
        docker-compose -f docker/test/docker-compose.yml --profile all up --build
        ;;
        
    "watch")
        echo -e "${GREEN}Starting test watcher...${NC}"
        docker-compose -f docker/test/docker-compose.yml --profile watch up --build
        ;;
        
    "shell")
        echo -e "${GREEN}Starting debug shell...${NC}"
        docker-compose -f docker/test/docker-compose.yml --profile debug run --rm test-shell
        ;;
        
    "lint")
        echo -e "${GREEN}Running linters...${NC}"
        docker-compose -f docker/test/docker-compose.yml --profile lint up --build
        ;;
        
    "scan")
        echo -e "${GREEN}Running security scan...${NC}"
        docker-compose -f docker/test/docker-compose.yml --profile scan up --build
        ;;
        
    "clean")
        echo -e "${YELLOW}Cleaning up test environment...${NC}"
        docker-compose -f docker/test/docker-compose.yml down -v --remove-orphans
        rm -rf docker/test/test-reports docker/test/coverage-reports
        echo -e "${GREEN}Cleanup complete!${NC}"
        exit 0
        ;;
        
    *)
        echo -e "${RED}Unknown command: $TEST_TYPE${NC}"
        echo "Usage: $0 [security|all|watch|shell|lint|scan|clean]"
        echo ""
        echo "Commands:"
        echo "  security - Run security tests only (default)"
        echo "  all      - Run all tests"
        echo "  watch    - Run tests in watch mode"
        echo "  shell    - Start interactive shell"
        echo "  lint     - Run code linters"
        echo "  scan     - Run security scanners"
        echo "  clean    - Clean up containers and test outputs"
        exit 1
        ;;
esac

# Check if tests passed
if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}Tests passed!${NC}"
    
    # Show coverage report location
    if [ -d "docker/test/coverage-reports" ]; then
        echo -e "${GREEN}Coverage report available at: docker/test/coverage-reports/index.html${NC}"
    fi
else
    echo -e "\n${RED}Tests failed!${NC}"
    exit 1
fi