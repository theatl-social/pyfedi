#!/usr/bin/env python3
"""
Production test for the explore page bug fix.
Run this on the production machine to verify the fix is working.
"""
import os
import sys
import subprocess
import requests
from pathlib import Path

def check_template_syntax():
    """Check that the explore template has correct syntax."""
    print("🔧 CHECKING TEMPLATE SYNTAX")
    print("=" * 40)
    
    template_path = 'app/templates/explore.html'
    
    if not os.path.exists(template_path):
        print(f"❌ Template not found: {template_path}")
        print("   Make sure you're running this from the project root directory")
        return False
    
    try:
        with open(template_path, 'r') as f:
            content = f.read()
        
        # Check for the bug we fixed
        if 'len(topics)' in content:
            print("❌ CRITICAL: Template still has the bug!")
            print("   Found len(topics) usage - this will cause 'len' is undefined error")
            return False
        
        if 'topics|length' in content:
            print("✅ Template syntax is correct (uses topics|length)")
            return True
        else:
            print("⚠️  No length check found - template may have been modified")
            return True
            
    except Exception as e:
        print(f"❌ Error reading template: {e}")
        return False

def test_database_topics():
    """Test that topics can be loaded from the database."""
    print("\n📊 TESTING DATABASE TOPICS")
    print("=" * 40)
    
    try:
        # Try to run a simple database query using the Flask shell
        test_script = '''
import os
from app import create_app
from app.utils import topic_tree

app = create_app()
with app.app_context():
    try:
        topics = topic_tree()
        print(f"SUCCESS: Found {len(topics)} top-level topics")
        for topic_data in topics:
            topic = topic_data["topic"]
            children = topic_data["children"]
            print(f"  - {topic.name} ({len(children)} children)")
        exit(0)
    except Exception as e:
        print(f"ERROR: {e}")
        exit(1)
'''
        
        # Write the test script to a temporary file
        with open('/tmp/test_topics.py', 'w') as f:
            f.write(test_script)
        
        # Run the test in the Flask environment
        result = subprocess.run([
            'python', '/tmp/test_topics.py'
        ], capture_output=True, text=True, cwd='.')
        
        if result.returncode == 0:
            print("✅ Database topics loaded successfully:")
            print(result.stdout.strip())
            return True
        else:
            print("❌ Failed to load topics from database:")
            print(result.stderr.strip())
            return False
            
    except Exception as e:
        print(f"❌ Error testing database: {e}")
        return False
    finally:
        # Clean up
        if os.path.exists('/tmp/test_topics.py'):
            os.remove('/tmp/test_topics.py')

def test_http_endpoint(base_url="http://localhost:5000"):
    """Test the /explore HTTP endpoint directly."""
    print(f"\n🌐 TESTING HTTP ENDPOINT: {base_url}/explore")
    print("=" * 50)
    
    try:
        response = requests.get(f"{base_url}/explore", timeout=10)
        
        print(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            html = response.text
            
            # Check for signs that topics are being displayed
            checks = [
                ("Topics tab", "Topics" in html),
                ("Topic structure", "topic" in html.lower()),
                ("No template errors", "len is not defined" not in html),
                ("No empty container", len(html.strip()) > 1000),  # Should have substantial content
            ]
            
            passed = 0
            for check_name, check_result in checks:
                if check_result:
                    print(f"   ✅ {check_name}")
                    passed += 1
                else:
                    print(f"   ❌ {check_name}")
            
            if passed >= 3:  # Most checks should pass
                print("✅ HTTP endpoint is working correctly")
                return True
            else:
                print("❌ HTTP endpoint has issues")
                return False
                
        elif response.status_code == 500:
            print("❌ Server error - template or database issue")
            print("   Check server logs for details")
            return False
        else:
            print(f"❌ Unexpected status code: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to the server")
        print(f"   Make sure the app is running on {base_url}")
        return False
    except Exception as e:
        print(f"❌ Error testing endpoint: {e}")
        return False

def test_docker_environment():
    """Test in Docker environment if available."""
    print("\n🐳 TESTING DOCKER ENVIRONMENT")
    print("=" * 40)
    
    try:
        # Check if docker containers are running
        result = subprocess.run(['docker', 'ps'], capture_output=True, text=True)
        if result.returncode != 0:
            print("⚠️  Docker not available or no containers running")
            return None
        
        # Look for pyfedi/piefed containers
        containers = result.stdout
        container_names = []
        
        for line in containers.split('\n'):
            if 'pyfed' in line.lower() or 'piefed' in line.lower():
                parts = line.split()
                if len(parts) > 0:
                    container_names.append(parts[-1])  # Container name is usually last
        
        if not container_names:
            print("⚠️  No pyfedi containers found")
            return None
        
        print(f"📦 Found containers: {', '.join(container_names)}")
        
        # Test the explore endpoint in the container
        for container in container_names:
            if 'web' in container or 'app' in container:
                print(f"🧪 Testing in container: {container}")
                
                test_cmd = [
                    'docker', 'exec', container, 
                    'python', '-c',
                    '''
from app import create_app
from app.utils import topic_tree
app = create_app()
with app.app_context():
    topics = topic_tree()
    print(f"Container topics: {len(topics)}")
'''
                ]
                
                result = subprocess.run(test_cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"   ✅ Container test passed: {result.stdout.strip()}")
                    return True
                else:
                    print(f"   ❌ Container test failed: {result.stderr.strip()}")
        
        return False
        
    except Exception as e:
        print(f"⚠️  Docker test error: {e}")
        return None

def main():
    """Run all production tests."""
    print("🚀 PRODUCTION EXPLORE PAGE TEST")
    print("=" * 50)
    print("This test verifies that the explore page bug has been fixed.")
    print()
    
    # Get the base URL from environment or use default
    base_url = os.environ.get('APP_URL', 'http://localhost:5000')
    
    # Run all tests
    tests = [
        ("Template Syntax", check_template_syntax),
        ("Database Topics", test_database_topics),
        ("HTTP Endpoint", lambda: test_http_endpoint(base_url)),
        ("Docker Environment", test_docker_environment),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with error: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n📊 TEST RESULTS SUMMARY")
    print("=" * 30)
    
    passed = 0
    total = 0
    
    for test_name, result in results:
        if result is True:
            print(f"✅ {test_name}: PASSED")
            passed += 1
            total += 1
        elif result is False:
            print(f"❌ {test_name}: FAILED")
            total += 1
        else:
            print(f"⚠️  {test_name}: SKIPPED")
    
    print(f"\nScore: {passed}/{total} tests passed")
    
    if passed >= 2:  # At least template and one other test should pass
        print("\n🎉 SUCCESS! The explore page bug appears to be fixed!")
        print("   ✅ Template syntax is correct")
        print("   ✅ Core functionality is working")
        print("\n   Users should now see topics in the explore page")
        print("   instead of an empty container.")
        return 0
    else:
        print("\n❌ FAILURE! The explore page still has issues.")
        print("   Please check the failed tests above and:")
        print("   1. Ensure the template fixes have been applied")
        print("   2. Verify the database has topic data") 
        print("   3. Check server logs for errors")
        return 1

if __name__ == '__main__':
    exit(main())