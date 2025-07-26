#!/usr/bin/env python3
"""
Security test runner for PyFedi
Runs all security tests and generates a report
"""
import sys
import os
import subprocess
import json
from datetime import datetime
from pathlib import Path


class SecurityTestRunner:
    """Run security tests and generate reports"""
    
    def __init__(self, root_dir=None):
        self.root_dir = root_dir or Path(__file__).parent.parent.parent
        self.test_dir = Path(__file__).parent
        self.results = {}
        self.start_time = None
        self.end_time = None
    
    def run_all_tests(self):
        """Run all security tests"""
        self.start_time = datetime.now()
        print(f"Starting security test suite at {self.start_time}")
        print("=" * 80)
        
        test_modules = [
            ("JSON Validator Tests", "test_json_validator.py"),
            ("Signature Validator Tests", "test_signature_validator.py"),
            ("URI Validator Tests", "test_uri_validator.py"),
            ("SQL Injection Tests", "test_sql_injection.py"),
            ("Secure Routes Tests", "test_secure_routes.py"),
            ("ActivityPub Integration Tests", "test_activitypub_integration.py")
        ]
        
        total_passed = 0
        total_failed = 0
        
        for test_name, test_file in test_modules:
            print(f"\nRunning {test_name}...")
            print("-" * 40)
            
            result = self.run_test_module(test_file)
            self.results[test_name] = result
            
            if result['success']:
                print(f"✅ {test_name}: PASSED ({result['tests_run']} tests)")
                total_passed += result['tests_run']
            else:
                print(f"❌ {test_name}: FAILED")
                total_failed += result.get('failures', 0)
        
        self.end_time = datetime.now()
        duration = (self.end_time - self.start_time).total_seconds()
        
        print("\n" + "=" * 80)
        print("SECURITY TEST SUMMARY")
        print("=" * 80)
        print(f"Total tests run: {total_passed + total_failed}")
        print(f"Passed: {total_passed}")
        print(f"Failed: {total_failed}")
        print(f"Duration: {duration:.2f} seconds")
        
        return total_failed == 0
    
    def run_test_module(self, test_file):
        """Run a single test module"""
        test_path = self.test_dir / test_file
        
        cmd = [
            sys.executable, "-m", "pytest",
            str(test_path),
            "-v",
            "--tb=short",
            "--json-report",
            f"--json-report-file=/tmp/{test_file}.json"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.root_dir)
            )
            
            # Parse JSON report if available
            json_report_path = f"/tmp/{test_file}.json"
            if os.path.exists(json_report_path):
                with open(json_report_path, 'r') as f:
                    report = json.load(f)
                
                return {
                    'success': result.returncode == 0,
                    'tests_run': report['summary'].get('total', 0),
                    'passed': report['summary'].get('passed', 0),
                    'failed': report['summary'].get('failed', 0),
                    'errors': report['summary'].get('error', 0),
                    'duration': report['duration']
                }
            else:
                # Fallback to parsing output
                return {
                    'success': result.returncode == 0,
                    'tests_run': self._parse_test_count(result.stdout),
                    'output': result.stdout,
                    'errors': result.stderr
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'tests_run': 0
            }
    
    def _parse_test_count(self, output):
        """Parse test count from pytest output"""
        import re
        match = re.search(r'(\d+) passed', output)
        if match:
            return int(match.group(1))
        return 0
    
    def run_security_audit(self):
        """Run SQL injection audit"""
        print("\nRunning SQL injection audit...")
        print("-" * 40)
        
        audit_script = self.root_dir / "scripts" / "audit_sql_injection.py"
        if not audit_script.exists():
            print("⚠️  SQL injection audit script not found")
            return False
        
        cmd = [sys.executable, str(audit_script), str(self.root_dir / "app")]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print("✅ No SQL injection vulnerabilities found")
            else:
                print("❌ SQL injection vulnerabilities detected:")
                print(result.stdout)
            
            return result.returncode == 0
            
        except Exception as e:
            print(f"❌ Error running SQL audit: {e}")
            return False
    
    def generate_report(self, output_file=None):
        """Generate detailed test report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'duration': (self.end_time - self.start_time).total_seconds() if self.end_time else 0,
            'results': self.results,
            'summary': {
                'total_modules': len(self.results),
                'passed_modules': sum(1 for r in self.results.values() if r.get('success')),
                'total_tests': sum(r.get('tests_run', 0) for r in self.results.values()),
                'total_passed': sum(r.get('passed', 0) for r in self.results.values()),
                'total_failed': sum(r.get('failed', 0) for r in self.results.values())
            }
        }
        
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2)
            print(f"\nDetailed report saved to: {output_file}")
        
        return report
    
    def check_coverage(self):
        """Check test coverage for security modules"""
        print("\nChecking test coverage...")
        print("-" * 40)
        
        security_modules = [
            "app/security/json_validator.py",
            "app/security/signature_validator.py", 
            "app/security/uri_validator.py",
            "app/security/secure_routes.py"
        ]
        
        cmd = [
            sys.executable, "-m", "pytest",
            str(self.test_dir),
            f"--cov={self.root_dir}/app/security",
            "--cov-report=term-missing",
            "--cov-report=html",
            "-q"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.root_dir)
            )
            
            print(result.stdout)
            
            if "htmlcov/index.html" in result.stdout:
                print("\n📊 Coverage report generated at: htmlcov/index.html")
                
        except Exception as e:
            print(f"⚠️  Could not generate coverage report: {e}")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run PyFedi security tests')
    parser.add_argument('--audit', action='store_true', help='Run SQL injection audit')
    parser.add_argument('--coverage', action='store_true', help='Generate coverage report')
    parser.add_argument('--report', help='Output JSON report to file')
    parser.add_argument('--module', help='Run specific test module')
    
    args = parser.parse_args()
    
    runner = SecurityTestRunner()
    
    if args.module:
        # Run single module
        result = runner.run_test_module(args.module)
        success = result.get('success', False)
    else:
        # Run all tests
        success = runner.run_all_tests()
        
        if args.audit:
            audit_success = runner.run_security_audit()
            success = success and audit_success
        
        if args.coverage:
            runner.check_coverage()
        
        if args.report:
            runner.generate_report(args.report)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()