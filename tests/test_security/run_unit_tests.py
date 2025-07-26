#!/usr/bin/env python3
"""
Run security unit tests without full app context
"""
import sys
import os
import subprocess

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Set up minimal environment
os.environ['TESTING'] = '1'
os.environ['FLASK_ENV'] = 'testing'

# Run tests
if __name__ == '__main__':
    # Run pytest with coverage
    cmd = [
        sys.executable, '-m', 'pytest',
        '-v',
        '--tb=short',
        '--disable-warnings',
        'tests/test_security/',
        '-k', 'not Integration'  # Skip integration tests
    ]
    
    if len(sys.argv) > 1:
        cmd.extend(sys.argv[1:])
    
    sys.exit(subprocess.call(cmd))