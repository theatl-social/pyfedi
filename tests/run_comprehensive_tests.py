#!/usr/bin/env python3
"""
Comprehensive test runner for PeachPie.

This script runs all unit tests for the refactored framework,
providing detailed coverage reports and performance metrics.
"""
import sys
import os
import time
import subprocess
from pathlib import Path
import pytest
import coverage


class TestRunner:
    """Manages comprehensive test execution."""
    
    def __init__(self):
        self.start_time = time.time()
        self.test_dir = Path(__file__).parent
        self.project_root = self.test_dir.parent
        self.coverage_enabled = True
        self.failed_tests = []
        
    def setup_environment(self):
        """Set up test environment."""
        print("🔧 Setting up test environment...")
        
        # Set test configuration
        os.environ['FLASK_ENV'] = 'testing'
        os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
        os.environ['REDIS_URL'] = 'redis://localhost:6379/15'
        os.environ['SECRET_KEY'] = 'test-secret-key'
        os.environ['SERVER_NAME'] = 'test.instance'
        os.environ['SOFTWARE_NAME'] = 'PeachPie'
        os.environ['NON_INTERACTIVE'] = 'true'
        
        print("✅ Environment configured")
    
    def run_unit_tests(self):
        """Run all unit tests."""
        print("\n🧪 Running unit tests...")
        
        test_suites = [
            {
                'name': 'Federation Components',
                'pattern': 'test_federation_components.py',
                'description': 'Redis Streams, health monitoring, rate limiting, scheduler'
            },
            {
                'name': 'ActivityPub Routes',
                'pattern': 'test_activitypub_routes.py',
                'description': 'All 41 ActivityPub endpoints'
            },
            {
                'name': 'Database Management',
                'pattern': 'test_database_management.py',
                'description': 'Database initialization and migrations'
            },
            {
                'name': 'Security Mitigations',
                'pattern': 'test_security_mitigations.py',
                'description': 'SQL injection, SSRF, auth bypass prevention'
            },
            {
                'name': 'Redis Streams',
                'pattern': 'test_redis_streams.py',
                'description': 'Stream processing and federation tasks'
            },
            {
                'name': 'Model Typing',
                'pattern': 'test_model_typing_comprehensive.py',
                'description': 'Type annotations and model validation'
            }
        ]
        
        total_passed = 0
        total_failed = 0
        
        for suite in test_suites:
            print(f"\n📋 Running {suite['name']} tests...")
            print(f"   {suite['description']}")
            
            test_file = self.test_dir / suite['pattern']
            if not test_file.exists():
                print(f"   ⚠️  Test file not found: {suite['pattern']}")
                continue
            
            # Run pytest for this suite
            result = subprocess.run(
                [
                    sys.executable, '-m', 'pytest',
                    str(test_file),
                    '-v',
                    '--tb=short',
                    '--no-header'
                ],
                capture_output=True,
                text=True
            )
            
            # Parse results
            output_lines = result.stdout.split('\n')
            for line in output_lines:
                if 'passed' in line and 'failed' in line:
                    # Extract test counts
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if 'passed' in part and i > 0:
                            passed = int(parts[i-1])
                            total_passed += passed
                        if 'failed' in part and i > 0:
                            failed = int(parts[i-1])
                            total_failed += failed
                            self.failed_tests.append(suite['name'])
            
            if result.returncode == 0:
                print(f"   ✅ {suite['name']} tests passed")
            else:
                print(f"   ❌ {suite['name']} tests failed")
                if result.stderr:
                    print(f"   Error: {result.stderr}")
        
        return total_passed, total_failed
    
    def run_integration_tests(self):
        """Run integration tests."""
        print("\n🔗 Running integration tests...")
        
        # Run integration test suites
        integration_suites = [
            'test_activitypub_integration.py',
            'test_secure_routes.py'
        ]
        
        passed = 0
        failed = 0
        
        for suite in integration_suites:
            test_file = self.test_dir / 'test_security' / suite
            if test_file.exists():
                result = subprocess.run(
                    [sys.executable, '-m', 'pytest', str(test_file), '-q'],
                    capture_output=True
                )
                if result.returncode == 0:
                    passed += 1
                else:
                    failed += 1
        
        print(f"   Integration tests: {passed} passed, {failed} failed")
        return passed, failed
    
    def run_coverage_analysis(self):
        """Run test coverage analysis."""
        if not self.coverage_enabled:
            return
        
        print("\n📊 Running coverage analysis...")
        
        # Initialize coverage
        cov = coverage.Coverage(source=[str(self.project_root / 'app')])
        cov.start()
        
        # Run tests with coverage
        pytest.main([
            str(self.test_dir),
            '--cov=app',
            '--cov-report=term-missing',
            '--cov-report=html',
            '-q'
        ])
        
        cov.stop()
        cov.save()
        
        # Generate reports
        print("\n📈 Coverage Report:")
        cov.report()
        cov.html_report(directory=str(self.project_root / 'htmlcov'))
        print(f"\n   HTML report generated at: {self.project_root / 'htmlcov/index.html'}")
    
    def run_performance_tests(self):
        """Run performance benchmarks."""
        print("\n⚡ Running performance tests...")
        
        benchmarks = [
            {
                'name': 'Redis Streams Throughput',
                'module': 'test_redis_streams',
                'function': 'test_redis_streams_performance'
            }
        ]
        
        for benchmark in benchmarks:
            print(f"\n   Running {benchmark['name']}...")
            
            result = subprocess.run(
                [
                    sys.executable, '-m', 'pytest',
                    f"{self.test_dir}/{benchmark['module']}.py::{benchmark['function']}",
                    '-v'
                ],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print(f"   ✅ {benchmark['name']} passed")
            else:
                print(f"   ❌ {benchmark['name']} failed")
    
    def generate_report(self, unit_results, integration_results):
        """Generate final test report."""
        elapsed_time = time.time() - self.start_time
        
        print("\n" + "="*60)
        print("📋 TEST SUMMARY REPORT")
        print("="*60)
        
        unit_passed, unit_failed = unit_results
        int_passed, int_failed = integration_results
        
        total_tests = unit_passed + unit_failed + int_passed + int_failed
        total_passed = unit_passed + int_passed
        total_failed = unit_failed + int_failed
        
        print(f"\n🔢 Total Tests Run: {total_tests}")
        print(f"✅ Passed: {total_passed}")
        print(f"❌ Failed: {total_failed}")
        
        if total_tests > 0:
            success_rate = (total_passed / total_tests) * 100
            print(f"📊 Success Rate: {success_rate:.1f}%")
        
        print(f"\n⏱️  Total Time: {elapsed_time:.2f} seconds")
        
        if self.failed_tests:
            print("\n❌ Failed Test Suites:")
            for suite in self.failed_tests:
                print(f"   - {suite}")
        
        print("\n📁 Test Categories:")
        print(f"   - Unit Tests: {unit_passed} passed, {unit_failed} failed")
        print(f"   - Integration Tests: {int_passed} passed, {int_failed} failed")
        
        # Recommendations
        print("\n💡 Recommendations:")
        if total_failed > 0:
            print("   - Fix failing tests before deployment")
            print("   - Run tests locally with: pytest -xvs <test_file>")
        else:
            print("   - All tests passing! ✨")
            print("   - Consider adding more edge case tests")
        
        if self.coverage_enabled:
            print("   - Review coverage report for untested code")
        
        print("\n" + "="*60)
        
        # Exit code based on results
        return 0 if total_failed == 0 else 1
    
    def run(self):
        """Run all tests."""
        print("🚀 PeachPie Comprehensive Test Suite")
        print("="*60)
        
        try:
            # Setup
            self.setup_environment()
            
            # Run tests
            unit_results = self.run_unit_tests()
            integration_results = self.run_integration_tests()
            
            # Coverage (optional)
            if '--coverage' in sys.argv:
                self.run_coverage_analysis()
            
            # Performance tests (optional)
            if '--performance' in sys.argv:
                self.run_performance_tests()
            
            # Generate report
            exit_code = self.generate_report(unit_results, integration_results)
            
            return exit_code
            
        except Exception as e:
            print(f"\n❌ Test runner failed: {e}")
            return 1


def main():
    """Main entry point."""
    runner = TestRunner()
    
    # Check for help
    if '--help' in sys.argv or '-h' in sys.argv:
        print("Usage: python run_comprehensive_tests.py [options]")
        print("\nOptions:")
        print("  --coverage     Generate coverage report")
        print("  --performance  Run performance benchmarks")
        print("  --help, -h     Show this help message")
        return 0
    
    # Run tests
    exit_code = runner.run()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()