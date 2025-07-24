#!/usr/bin/env python3
"""
Test script to verify alembic migration fix
"""
import subprocess
import sys
from pathlib import Path

def run_command(cmd, check=True):
    """Run a command and return output"""
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            check=check, 
            capture_output=True, 
            text=True
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return e.returncode, e.stdout, e.stderr

def test_alembic_heads():
    """Test if alembic heads are properly resolved"""
    print("=== TESTING ALEMBIC MIGRATION FIX ===\n")
    
    # First run our debug script
    print("1. Running debug script...")
    code, stdout, stderr = run_command("python3 debug_alembic_heads.py")
    
    if code != 0:
        print(f"❌ Debug script failed with code {code}")
        print(f"Error: {stderr}")
        return False
    
    # Check for multiple heads
    if "MULTIPLE HEADS DETECTED" in stdout:
        print("❌ Multiple heads still detected!")
        print(stdout)
        return False
    else:
        print("✅ No multiple heads detected")
    
    # Check for conflicts
    if "CONFLICT:" in stdout:
        print("❌ Conflicts still exist!")
        print(stdout)
        return False
    else:
        print("✅ No conflicts found")
    
    # Try to get current alembic head
    print("\n2. Checking alembic current version...")
    code, stdout, stderr = run_command("cd /Users/michael/code/pyfedi && flask db current", check=False)
    
    if code == 0:
        print(f"✅ Current alembic version: {stdout.strip()}")
    else:
        print(f"⚠️  Could not get current version (this might be OK if DB is not set up)")
        print(f"   Error: {stderr}")
    
    # Try a dry run of upgrade
    print("\n3. Testing upgrade (dry run)...")
    code, stdout, stderr = run_command("cd /Users/michael/code/pyfedi && flask db show head", check=False)
    
    if code == 0 and "Multiple head revisions" not in stderr:
        print("✅ Alembic can identify single head")
        print(f"   Head: {stdout.strip()}")
    else:
        print("❌ Alembic still reports multiple heads")
        print(f"   Error: {stderr}")
        return False
    
    print("\n=== TEST SUMMARY ===")
    print("✅ All tests passed! The migration issue should be resolved.")
    print("\nNext steps:")
    print("1. Commit these changes")
    print("2. Run 'flask db upgrade' in your environment")
    
    return True

if __name__ == "__main__":
    success = test_alembic_heads()
    sys.exit(0 if success else 1)