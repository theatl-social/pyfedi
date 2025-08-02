#!/usr/bin/env python
"""Simple test runner to catch errors"""
import subprocess
import sys

try:
    result = subprocess.run(
        ["pytest", "tests/test_api_get_site.py", "-x", "--tb=short", "-q"],
        capture_output=True,
        text=True,
        timeout=30
    )
    print("STDOUT:")
    print(result.stdout)
    print("\nSTDERR:")
    print(result.stderr)
    
    # Look for programming errors
    if "ProgrammingError" in result.stderr:
        lines = result.stderr.split('\n')
        for i, line in enumerate(lines):
            if "ProgrammingError" in line:
                # Print context around the error
                start = max(0, i - 5)
                end = min(len(lines), i + 10)
                print("\nError context:")
                print('\n'.join(lines[start:end]))
                break
    
except subprocess.TimeoutExpired:
    print("Test timed out after 30 seconds")
    sys.exit(1)