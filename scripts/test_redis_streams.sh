#!/bin/bash
# Test Redis Streams implementation

echo "Testing Redis Streams Federation Implementation"
echo "============================================="

# Check if Redis is running
if ! redis-cli ping > /dev/null 2>&1; then
    echo "❌ Redis is not running. Please start Redis first."
    exit 1
fi

# Set test environment
export FLASK_ENV=testing
export REDIS_URL=redis://localhost:6379/15  # Use separate DB for tests

# Clean test Redis DB
echo "Cleaning test Redis database..."
redis-cli -n 15 FLUSHDB

# Run unit tests
echo -e "\n1. Running unit tests..."
python -m pytest tests/test_redis_streams.py::TestRedisStreamsBasics -v

# Run integration tests
echo -e "\n2. Running integration tests..."
python -m pytest tests/test_redis_streams.py::TestRedisStreamsIntegration -v

# Run monitoring tests
echo -e "\n3. Running monitoring tests..."
python -m pytest tests/test_redis_streams.py::TestMonitoring -v

# Run performance tests
echo -e "\n4. Running performance tests..."
python -m pytest tests/test_redis_streams.py::test_redis_streams_performance -v

# Test worker process
echo -e "\n5. Testing worker process..."
timeout 5 python worker.py --processes 1 --name test-worker &
WORKER_PID=$!
sleep 2

# Check if worker is running
if ps -p $WORKER_PID > /dev/null; then
    echo "✅ Worker process started successfully"
    kill $WORKER_PID
else
    echo "❌ Worker process failed to start"
fi

# Test concurrent workers
echo -e "\n6. Testing concurrent workers..."
timeout 5 python worker.py --processes 3 --name test-concurrent &
CONCURRENT_PID=$!
sleep 2

if ps -p $CONCURRENT_PID > /dev/null; then
    echo "✅ Concurrent workers started successfully"
    kill $CONCURRENT_PID
else
    echo "❌ Concurrent workers failed to start"
fi

# Check Redis Streams state
echo -e "\n7. Checking Redis Streams state..."
echo "Active streams:"
redis-cli -n 15 KEYS "federation:stream:*" | while read stream; do
    if [ ! -z "$stream" ]; then
        length=$(redis-cli -n 15 XLEN "$stream")
        echo "  - $stream: $length messages"
    fi
done

# Summary
echo -e "\n============================================="
echo "Redis Streams Testing Complete"
echo "============================================="