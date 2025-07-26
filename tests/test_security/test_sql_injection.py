"""
Test cases for SQL injection vulnerabilities
Tests the SQL injection audit script and verifies fixes prevent SQL injection
"""
import pytest
from unittest.mock import Mock, patch, mock_open
from pathlib import Path
import tempfile
import os
from scripts.audit_sql_injection import SQLInjectionAuditor


class TestSQLInjectionAuditor:
    """Test SQL injection detection capabilities"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.auditor = SQLInjectionAuditor()
    
    def test_detects_string_formatting_in_execute(self):
        """Test detection of string formatting in execute() calls"""
        vulnerable_code = '''
def get_user(user_id):
    result = db.session.execute("SELECT * FROM users WHERE id = %s" % user_id)
    return result
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(vulnerable_code)
            f.flush()
            
            vulns = self.auditor.audit_file(Path(f.name))
            
            assert len(vulns) > 0
            assert vulns[0]['severity'] == 'CRITICAL'
            assert 'String formatting in SQL execute' in vulns[0]['issue']
            
        os.unlink(f.name)
    
    def test_detects_fstring_in_execute(self):
        """Test detection of f-strings in execute() calls"""
        vulnerable_code = '''
def delete_post(post_id):
    db.session.execute(f"DELETE FROM posts WHERE id = {post_id}")
    db.session.commit()
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(vulnerable_code)
            f.flush()
            
            vulns = self.auditor.audit_file(Path(f.name))
            
            assert len(vulns) > 0
            assert vulns[0]['severity'] == 'CRITICAL'
            assert 'F-string in SQL execute' in vulns[0]['issue']
            
        os.unlink(f.name)
    
    def test_detects_string_concatenation(self):
        """Test detection of string concatenation in SQL"""
        vulnerable_code = '''
def search_users(name):
    query = "SELECT * FROM users WHERE name LIKE '%" + name + "%'"
    result = db.session.execute(query)
    return result
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(vulnerable_code)
            f.flush()
            
            vulns = self.auditor.audit_file(Path(f.name))
            
            assert len(vulns) >= 2  # Both variable assignment and execute
            assert any('concatenation' in v['issue'] for v in vulns)
            
        os.unlink(f.name)
    
    def test_detects_format_method(self):
        """Test detection of format() method in SQL"""
        vulnerable_code = '''
def update_user(user_id, new_name):
    sql = "UPDATE users SET name = '{}' WHERE id = {}".format(new_name, user_id)
    db.session.execute(sql)
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(vulnerable_code)
            f.flush()
            
            vulns = self.auditor.audit_file(Path(f.name))
            
            assert len(vulns) > 0
            assert any('format() method' in v['issue'] for v in vulns)
            
        os.unlink(f.name)
    
    def test_detects_dynamic_table_names(self):
        """Test detection of dynamic table names"""
        vulnerable_code = '''
def get_from_table(table_name, record_id):
    query = "SELECT * FROM " + table_name + " WHERE id = " + str(record_id)
    return db.session.execute(query)
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(vulnerable_code)
            f.flush()
            
            vulns = self.auditor.audit_file(Path(f.name))
            
            assert len(vulns) > 0
            assert any('Dynamic table name' in v['issue'] for v in vulns)
            
        os.unlink(f.name)
    
    def test_safe_parameterized_queries_not_flagged(self):
        """Test that safe parameterized queries are not flagged"""
        safe_code = '''
from sqlalchemy import text

def get_user_safe(user_id):
    # Using parameterized query with text()
    result = db.session.execute(
        text("SELECT * FROM users WHERE id = :user_id"),
        {"user_id": user_id}
    )
    return result

def update_user_safe(user_id, name):
    # Using ORM
    user = User.query.filter_by(id=user_id).first()
    if user:
        user.name = name
        db.session.commit()
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(safe_code)
            f.flush()
            
            vulns = self.auditor.audit_file(Path(f.name))
            
            assert len(vulns) == 0  # No vulnerabilities in safe code
            
        os.unlink(f.name)
    
    def test_orm_usage_not_flagged(self):
        """Test that ORM usage is not flagged as vulnerable"""
        orm_code = '''
def find_users(username):
    # Safe ORM usage
    users = User.query.filter(User.username.contains(username)).all()
    return users

def create_user(email, name):
    # Safe ORM object creation
    user = User(email=email, name=name)
    db.session.add(user)
    db.session.commit()
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(orm_code)
            f.flush()
            
            vulns = self.auditor.audit_file(Path(f.name))
            
            assert len(vulns) == 0
            
        os.unlink(f.name)
    
    def test_text_with_parameters_considered_safe(self):
        """Test text() with parameters is considered safe"""
        code = '''
from sqlalchemy import text

def complex_query(user_id, status):
    # This should be safe
    result = db.session.execute(
        text("SELECT * FROM posts WHERE user_id = :uid AND status = :status"),
        {"uid": user_id, "status": status}
    )
    return result
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            f.flush()
            
            vulns = self.auditor.audit_file(Path(f.name))
            
            assert len(vulns) == 0
            
        os.unlink(f.name)
    
    def test_severity_classification(self):
        """Test that vulnerabilities are classified with correct severity"""
        code_with_multiple_severities = '''
# Critical - direct execute with string formatting
db.session.execute("DELETE FROM users WHERE id = %s" % user_id)

# High - SQL variable construction
sql = "SELECT * FROM users WHERE name = '%s'" % username

# Medium - text() with formatting (might be mitigated)
query = text(f"SELECT * FROM {table_name}")
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code_with_multiple_severities)
            f.flush()
            
            vulns = self.auditor.audit_file(Path(f.name))
            
            severities = [v['severity'] for v in vulns]
            assert 'CRITICAL' in severities
            assert 'HIGH' in severities
            assert 'MEDIUM' in severities
            
        os.unlink(f.name)
    
    def test_context_extraction(self):
        """Test that vulnerability context is properly extracted"""
        code = '''
def vulnerable_function(user_input):
    # This function has SQL injection
    query = "SELECT * FROM users WHERE name = '" + user_input + "'"
    result = db.session.execute(query)
    return result
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            f.flush()
            
            vulns = self.auditor.audit_file(Path(f.name))
            
            assert len(vulns) > 0
            vuln = vulns[0]
            
            # Check context includes surrounding lines
            assert len(vuln['context']) >= 3
            assert any('This function has SQL injection' in line for line in vuln['context'])
            
        os.unlink(f.name)


class TestSQLInjectionPatterns:
    """Test specific SQL injection attack patterns"""
    
    def test_union_injection_pattern(self):
        """Test UNION injection attempts are detected"""
        vulnerable_code = '''
def search(term):
    # Vulnerable to UNION injection
    query = "SELECT id, name FROM users WHERE name = '" + term + "'"
    # Attacker could inject: ' UNION SELECT password, email FROM users--
    return db.session.execute(query)
'''
        
        auditor = SQLInjectionAuditor()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(vulnerable_code)
            f.flush()
            
            vulns = auditor.audit_file(Path(f.name))
            assert len(vulns) > 0
            
        os.unlink(f.name)
    
    def test_blind_injection_pattern(self):
        """Test blind SQL injection vulnerable patterns"""
        vulnerable_code = '''
def check_user_exists(username):
    # Vulnerable to blind injection
    query = f"SELECT COUNT(*) FROM users WHERE username = '{username}'"
    # Attacker could inject: admin' AND SLEEP(5)--
    count = db.session.execute(query).scalar()
    return count > 0
'''
        
        auditor = SQLInjectionAuditor()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(vulnerable_code)
            f.flush()
            
            vulns = auditor.audit_file(Path(f.name))
            assert len(vulns) > 0
            assert vulns[0]['severity'] in ['CRITICAL', 'HIGH']
            
        os.unlink(f.name)
    
    def test_second_order_injection(self):
        """Test second-order injection patterns"""
        vulnerable_code = '''
def store_user_preference(user_id, preference):
    # Store potentially malicious data
    pref = UserPreference(user_id=user_id, value=preference)
    db.session.add(pref)
    db.session.commit()

def use_preference(user_id):
    # Second-order injection - using stored data unsafely
    pref = UserPreference.query.filter_by(user_id=user_id).first()
    if pref:
        # Vulnerable if pref.value contains SQL
        query = f"SELECT * FROM data WHERE category = '{pref.value}'"
        return db.session.execute(query)
'''
        
        auditor = SQLInjectionAuditor()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(vulnerable_code)
            f.flush()
            
            vulns = auditor.audit_file(Path(f.name))
            
            # Should detect the f-string vulnerability in use_preference
            assert any('use_preference' in str(v) or v['line'] > 10 for v in vulns)
            
        os.unlink(f.name)


class TestSQLInjectionPrevention:
    """Test that our security fixes prevent SQL injection"""
    
    def test_parameterized_query_prevents_injection(self):
        """Test parameterized queries prevent injection"""
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        
        # Create in-memory SQLite for testing
        engine = create_engine('sqlite:///:memory:')
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Create test table
        session.execute(text('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                password TEXT
            )
        '''))
        
        # Insert test data
        session.execute(text(
            "INSERT INTO users (username, password) VALUES (:user, :pass)"
        ), {"user": "admin", "pass": "secret"})
        session.commit()
        
        # Attempt injection with parameterized query
        malicious_input = "admin' OR '1'='1"
        
        # Safe parameterized query
        result = session.execute(
            text("SELECT * FROM users WHERE username = :username"),
            {"username": malicious_input}
        ).fetchall()
        
        # Should return 0 results (injection prevented)
        assert len(result) == 0
        
        # Verify the admin user still exists
        result = session.execute(
            text("SELECT * FROM users WHERE username = :username"),
            {"username": "admin"}
        ).fetchall()
        
        assert len(result) == 1
        assert result[0][1] == "admin"
    
    def test_input_validation_for_dynamic_queries(self):
        """Test input validation for dynamic table/column names"""
        ALLOWED_TABLES = ["users", "posts", "comments"]
        ALLOWED_COLUMNS = ["id", "created_at", "updated_at", "status"]
        
        def safe_dynamic_query(table_name, column_name, value):
            # Validate table name
            if table_name not in ALLOWED_TABLES:
                raise ValueError(f"Invalid table name: {table_name}")
            
            # Validate column name
            if column_name not in ALLOWED_COLUMNS:
                raise ValueError(f"Invalid column name: {column_name}")
            
            # Now safe to use in query
            query = f"SELECT * FROM {table_name} WHERE {column_name} = :value"
            return text(query), {"value": value}
        
        # Test valid inputs
        query, params = safe_dynamic_query("users", "id", 123)
        assert "FROM users WHERE id = :value" in str(query)
        assert params["value"] == 123
        
        # Test invalid table name
        with pytest.raises(ValueError, match="Invalid table name"):
            safe_dynamic_query("passwords", "id", 123)
        
        # Test invalid column name  
        with pytest.raises(ValueError, match="Invalid column name"):
            safe_dynamic_query("users", "password", "test")
    
    def test_escape_like_wildcards(self):
        """Test proper escaping of LIKE wildcards"""
        def safe_search(search_term):
            # Escape SQL wildcards
            escaped = search_term.replace("%", "\\%").replace("_", "\\_")
            
            # Use parameterized query with escaped input
            query = text("SELECT * FROM posts WHERE title LIKE :pattern ESCAPE '\\\\'")
            pattern = f"%{escaped}%"
            
            return query, {"pattern": pattern}
        
        # Test with potential SQL wildcard injection
        malicious_input = "test%' OR '1'='1"
        query, params = safe_search(malicious_input)
        
        # The % should be escaped
        assert "\\%" in params["pattern"]
        assert "test\\%" in params["pattern"]


class TestRealWorldSQLInjectionScenarios:
    """Test real-world SQL injection scenarios specific to PyFedi"""
    
    def test_activitypub_actor_search_injection(self):
        """Test ActivityPub actor search is safe from injection"""
        vulnerable_pattern = '''
def search_remote_actors(domain, username):
    # Vulnerable pattern
    query = f"SELECT * FROM users WHERE ap_profile_id LIKE '%{domain}%' AND username LIKE '%{username}%'"
    return db.session.execute(query)
'''
        
        safe_pattern = '''
from sqlalchemy import text

def search_remote_actors_safe(domain, username):
    # Safe pattern
    query = text("""
        SELECT * FROM users 
        WHERE ap_profile_id LIKE :domain_pattern 
        AND username LIKE :username_pattern
    """)
    return db.session.execute(query, {
        "domain_pattern": f"%{domain}%",
        "username_pattern": f"%{username}%"
    })
'''
        
        auditor = SQLInjectionAuditor()
        
        # Test vulnerable pattern
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(vulnerable_pattern)
            f.flush()
            vulns = auditor.audit_file(Path(f.name))
            assert len(vulns) > 0
        os.unlink(f.name)
        
        # Test safe pattern
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(safe_pattern)
            f.flush()
            vulns = auditor.audit_file(Path(f.name))
            assert len(vulns) == 0
        os.unlink(f.name)
    
    def test_federation_stats_aggregation(self):
        """Test federation statistics queries are safe"""
        vulnerable_pattern = '''
def get_instance_stats(instance_domain):
    # Vulnerable to injection via instance_domain
    query = f"""
        SELECT COUNT(*) as user_count,
               SUM(post_count) as total_posts
        FROM users
        WHERE ap_profile_id LIKE '%@{instance_domain}'
    """
    return db.session.execute(query).first()
'''
        
        safe_pattern = '''
def get_instance_stats_safe(instance_domain):
    # Safe parameterized version
    query = text("""
        SELECT COUNT(*) as user_count,
               SUM(post_count) as total_posts
        FROM users
        WHERE ap_profile_id LIKE :domain_pattern
    """)
    domain_pattern = f"%@{instance_domain}"
    return db.session.execute(query, {"domain_pattern": domain_pattern}).first()
'''
        
        auditor = SQLInjectionAuditor()
        
        # Vulnerable should be detected
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(vulnerable_pattern)
            f.flush()
            vulns = auditor.audit_file(Path(f.name))
            assert len(vulns) > 0
            assert any("f-string" in v['issue'].lower() or "f\"\"\"" in str(v) for v in vulns)
        os.unlink(f.name)


class TestSQLInjectionReporting:
    """Test SQL injection audit reporting functionality"""
    
    def test_report_generation(self):
        """Test audit report generation"""
        auditor = SQLInjectionAuditor()
        
        # Add some fake vulnerabilities
        auditor.vulnerabilities = [
            {
                'file': 'app/routes.py',
                'line': 100,
                'severity': 'CRITICAL',
                'issue': 'String formatting in SQL execute',
                'code': 'db.session.execute("SELECT * FROM users WHERE id = %s" % user_id)',
                'context': ['line 98', 'line 99', 'line 100', 'line 101'],
                'pattern': r'\.execute\s*\([^)]*%[sd]'
            },
            {
                'file': 'app/models.py',
                'line': 50,
                'severity': 'HIGH',
                'issue': 'F-string in query variable',
                'code': 'query = f"SELECT * FROM {table_name}"',
                'context': ['line 49', 'line 50', 'line 51'],
                'pattern': r'query\s*=\s*f["\']'
            }
        ]
        
        auditor.file_count = 10
        auditor.lines_scanned = 5000
        
        report = auditor.generate_report()
        
        # Verify report contents
        assert "SQL INJECTION VULNERABILITY AUDIT REPORT" in report
        assert "Files scanned: 10" in report
        assert "Lines scanned: 5000" in report
        assert "Vulnerabilities found: 2" in report
        assert "CRITICAL: 1" in report
        assert "HIGH: 1" in report
        assert "app/routes.py" in report
        assert "app/models.py" in report
    
    def test_fix_suggestions(self):
        """Test fix suggestion generation"""
        auditor = SQLInjectionAuditor()
        
        auditor.vulnerabilities = [
            {
                'file': 'app/routes.py',
                'line': 100,
                'severity': 'CRITICAL',
                'issue': 'String formatting in SQL execute',
                'code': 'db.session.execute("SELECT * FROM users WHERE id = %s" % user_id)',
                'context': [],
                'pattern': ''
            }
        ]
        
        fixes = auditor.generate_fixes()
        
        # Verify fix suggestions
        assert "SUGGESTED FIXES" in fixes
        assert "Use parameterized queries" in fixes
        assert "text(" in fixes  # Should suggest text() usage
        assert "{'id': user_id}" in fixes  # Should show parameter dict