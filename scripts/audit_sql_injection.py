#!/usr/bin/env python3
"""
SQL Injection Audit Script
Scans PyFedi codebase for potential SQL injection vulnerabilities
"""
import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Tuple
import argparse
from datetime import datetime


class SQLInjectionAuditor:
    """Audit codebase for SQL injection vulnerabilities"""
    
    DANGEROUS_PATTERNS = [
        # String formatting in execute
        (r'\.execute\s*\([^)]*%[sd]', 'String formatting in SQL execute', 'CRITICAL'),
        (r'\.execute\s*\(f["\']', 'F-string in SQL execute', 'CRITICAL'),
        (r'\.execute\s*\([^)]*\+\s*[^)]+\)', 'String concatenation in SQL execute', 'CRITICAL'),
        
        # format() in SQL
        (r'\.execute\s*\([^)]*\.format\s*\(', 'format() method in SQL execute', 'CRITICAL'),
        
        # Raw SQL construction
        (r'sql\s*=\s*["\'].*%[sd]', 'String formatting in SQL variable', 'HIGH'),
        (r'query\s*=\s*["\'].*%[sd]', 'String formatting in query variable', 'HIGH'),
        (r'sql\s*=\s*f["\']', 'F-string SQL construction', 'HIGH'),
        (r'query\s*=\s*f["\']', 'F-string query construction', 'HIGH'),
        (r'sql\s*\+=', 'SQL string concatenation', 'HIGH'),
        (r'query\s*\+=', 'Query string concatenation', 'HIGH'),
        
        # Potentially dangerous but might be safe with text()
        (r'text\s*\([^)]*%[sd]', 'String formatting in text()', 'MEDIUM'),
        (r'text\s*\(f["\']', 'F-string in text()', 'MEDIUM'),
        
        # Look for dynamic table/column names
        (r'(FROM|JOIN|UPDATE|INSERT INTO)\s+["\']?\s*\+', 'Dynamic table name', 'HIGH'),
        (r'SET\s+[^=]+=\s*[^,\s]+\s*\+', 'Dynamic column in SET', 'HIGH'),
    ]
    
    # Safe patterns that might trigger false positives
    SAFE_PATTERNS = [
        r'\.execute\s*\(\s*text\s*\([^)]+\)\s*,\s*{',  # Parameterized with text()
        r'\.execute\s*\([^)]+\)\s*#\s*safe',  # Marked as safe
    ]
    
    def __init__(self, root_dir: str = '.'):
        self.root_dir = Path(root_dir)
        self.vulnerabilities = []
        self.file_count = 0
        self.lines_scanned = 0
    
    def audit_file(self, filepath: Path) -> List[Dict]:
        """Audit a single Python file"""
        vulnerabilities = []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
                self.lines_scanned += len(lines)
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
            return vulnerabilities
        
        # Check each dangerous pattern
        for pattern, description, severity in self.DANGEROUS_PATTERNS:
            for match in re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE):
                line_no = content[:match.start()].count('\n') + 1
                line_content = lines[line_no - 1].strip()
                
                # Check if it's actually safe
                if self._is_safe_usage(lines, line_no - 1):
                    continue
                
                # Get context (3 lines before and after)
                context_start = max(0, line_no - 4)
                context_end = min(len(lines), line_no + 3)
                context = lines[context_start:context_end]
                
                vulnerabilities.append({
                    'file': str(filepath.relative_to(self.root_dir)),
                    'line': line_no,
                    'severity': severity,
                    'issue': description,
                    'code': line_content,
                    'context': context,
                    'pattern': pattern
                })
        
        return vulnerabilities
    
    def _is_safe_usage(self, lines: List[str], line_idx: int) -> bool:
        """Check if the suspicious pattern is actually safe"""
        if line_idx < 0 or line_idx >= len(lines):
            return False
        
        line = lines[line_idx]
        
        # Check for safe patterns
        for safe_pattern in self.SAFE_PATTERNS:
            if re.search(safe_pattern, line):
                return True
        
        # Check if it's using proper parameter binding
        if 'execute' in line and (':' in line or '%s' not in line):
            # Look for parameter dict on same or next line
            if '{' in line or (line_idx + 1 < len(lines) and '{' in lines[line_idx + 1]):
                return True
        
        # Check for ORM usage (likely safe)
        if any(orm in line for orm in ['.query.', '.filter(', '.filter_by(', 'db.session.add', 'db.session.merge']):
            return True
        
        return False
    
    def audit_directory(self, directory: Path) -> None:
        """Recursively audit directory"""
        for py_file in directory.rglob('*.py'):
            # Skip virtual environments and migrations
            if any(skip in str(py_file) for skip in ['venv/', 'env/', '__pycache__', 'migrations/versions/']):
                continue
            
            self.file_count += 1
            vulns = self.audit_file(py_file)
            self.vulnerabilities.extend(vulns)
    
    def generate_report(self) -> str:
        """Generate audit report"""
        if not self.vulnerabilities:
            return "✅ No SQL injection vulnerabilities found!"
        
        # Sort by severity
        severity_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
        self.vulnerabilities.sort(key=lambda x: (severity_order.get(x['severity'], 999), x['file'], x['line']))
        
        report = []
        report.append("=" * 80)
        report.append("SQL INJECTION VULNERABILITY AUDIT REPORT")
        report.append("=" * 80)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Files scanned: {self.file_count}")
        report.append(f"Lines scanned: {self.lines_scanned}")
        report.append(f"Vulnerabilities found: {len(self.vulnerabilities)}")
        report.append("")
        
        # Summary by severity
        by_severity = {}
        for vuln in self.vulnerabilities:
            by_severity[vuln['severity']] = by_severity.get(vuln['severity'], 0) + 1
        
        report.append("Summary by Severity:")
        for severity in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
            count = by_severity.get(severity, 0)
            if count > 0:
                report.append(f"  {severity}: {count}")
        report.append("")
        
        # Detailed findings
        current_severity = None
        for vuln in self.vulnerabilities:
            if vuln['severity'] != current_severity:
                current_severity = vuln['severity']
                report.append("-" * 80)
                report.append(f"{current_severity} SEVERITY ISSUES")
                report.append("-" * 80)
            
            report.append(f"\nFile: {vuln['file']}, Line {vuln['line']}")
            report.append(f"Issue: {vuln['issue']}")
            report.append(f"Code: {vuln['code']}")
            report.append(f"Pattern matched: {vuln['pattern']}")
            report.append("Context:")
            for i, ctx_line in enumerate(vuln['context']):
                line_no = vuln['line'] - 3 + i
                marker = ">>>" if line_no == vuln['line'] else "   "
                report.append(f"  {marker} {line_no}: {ctx_line}")
            report.append("")
        
        return "\n".join(report)
    
    def generate_fixes(self) -> str:
        """Generate suggested fixes for vulnerabilities"""
        fixes = []
        fixes.append("=" * 80)
        fixes.append("SUGGESTED FIXES")
        fixes.append("=" * 80)
        
        for vuln in self.vulnerabilities[:10]:  # Show fixes for first 10
            fixes.append(f"\nFile: {vuln['file']}, Line {vuln['line']}")
            fixes.append(f"Current: {vuln['code']}")
            
            # Suggest fix based on pattern
            if '%s' in vuln['code'] or '%d' in vuln['code']:
                fixes.append("Fix: Use parameterized queries")
                fixes.append("Example:")
                fixes.append("  # Instead of:")
                fixes.append("  db.session.execute('SELECT * FROM user WHERE id = %s' % user_id)")
                fixes.append("  # Use:")
                fixes.append("  db.session.execute(text('SELECT * FROM user WHERE id = :id'), {'id': user_id})")
            
            elif 'f"' in vuln['code'] or "f'" in vuln['code']:
                fixes.append("Fix: Use parameterized queries instead of f-strings")
                fixes.append("Example:")
                fixes.append("  # Instead of:")
                fixes.append('  db.session.execute(f"UPDATE user SET name = \'{name}\' WHERE id = {id}")')
                fixes.append("  # Use:")
                fixes.append("  db.session.execute(text('UPDATE user SET name = :name WHERE id = :id'), {'name': name, 'id': id})")
            
            elif '+' in vuln['code']:
                fixes.append("Fix: Use parameterized queries instead of string concatenation")
                fixes.append("Example:")
                fixes.append("  # Instead of:")
                fixes.append('  sql = "SELECT * FROM " + table_name')
                fixes.append("  # For dynamic table names, validate against whitelist:")
                fixes.append('  allowed_tables = ["user", "post", "comment"]')
                fixes.append('  if table_name in allowed_tables:')
                fixes.append('      sql = f"SELECT * FROM {table_name}"  # Safe after validation')
            
            fixes.append("")
        
        return "\n".join(fixes)


def main():
    parser = argparse.ArgumentParser(description='Audit PyFedi for SQL injection vulnerabilities')
    parser.add_argument('path', nargs='?', default='app', help='Path to audit (default: app)')
    parser.add_argument('--output', '-o', help='Output file for report')
    parser.add_argument('--fixes', '-f', action='store_true', help='Include suggested fixes')
    parser.add_argument('--severity', '-s', choices=['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'], 
                       help='Minimum severity to report')
    
    args = parser.parse_args()
    
    print(f"Auditing {args.path} for SQL injection vulnerabilities...")
    
    auditor = SQLInjectionAuditor()
    auditor.audit_directory(Path(args.path))
    
    # Filter by severity if requested
    if args.severity:
        severity_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
        min_severity = severity_order[args.severity]
        auditor.vulnerabilities = [
            v for v in auditor.vulnerabilities 
            if severity_order.get(v['severity'], 999) <= min_severity
        ]
    
    report = auditor.generate_report()
    
    if args.fixes and auditor.vulnerabilities:
        report += "\n\n" + auditor.generate_fixes()
    
    # Output report
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"Report written to {args.output}")
    else:
        print(report)
    
    # Exit with error code if vulnerabilities found
    if auditor.vulnerabilities:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()