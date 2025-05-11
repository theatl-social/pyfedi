import unittest
from app.utils import allowlist_html

class TestAllowlistHtml(unittest.TestCase):
    
    def test_basic_html(self):
        """Test basic HTML with allowed tags is preserved"""
        html = "<p>Basic paragraph</p>"
        result = allowlist_html(html)
        self.assertEqual(result, html)
        
    def test_disallowed_tags(self):
        """Test that disallowed tags are removed"""
        html = "<p>Paragraph with <script>alert('xss')</script> script</p>"
        result = allowlist_html(html)
        self.assertEqual(result, "<p>Paragraph with  script</p>")
        
    def test_nested_tags(self):
        """Test that allowed nested tags are preserved"""
        html = "<blockquote><p>Nested content</p></blockquote>"
        result = allowlist_html(html)
        self.assertEqual(result, html)
        
    def test_attributes(self):
        """Test that allowed attributes are preserved and others removed"""
        html = '<a href="https://example.com" onclick="alert(\'xss\')" style="color:red">Link</a>'
        result = allowlist_html(html)
        self.assertEqual(result, '<a href="https://example.com" rel="nofollow ugc" target="_blank">Link</a>')
        
    def test_empty_input(self):
        """Test empty input"""
        self.assertEqual(allowlist_html(""), "")
        self.assertEqual(allowlist_html(None), "")
        
    def test_plain_text_urls(self):
        """Test that plain text URLs are converted to links"""
        html = "<p>Visit https://example.com for more info.</p>"
        result = allowlist_html(html)
        self.assertEqual(result, '<p>Visit <a href="https://example.com" rel="nofollow ugc" target="_blank">https://example.com</a> for more info.</p>')
    
    def test_angle_brackets_in_text(self):
        """Test that angle brackets in plain text are escaped"""
        html = "<p>Text with <Book Title and Volume> needs escaping</p>"
        result = allowlist_html(html)
        print(f"Original: {html}")
        print(f"Result: {result}")
        self.assertTrue("&lt;Book Title and Volume&gt;" in result)
        
    def test_angle_brackets_in_blockquote(self):
        """Test that angle brackets in blockquote are escaped"""
        html = "<blockquote><p><Book Title and Volume> Review Goes Here [5/10]</p></blockquote>"
        result = allowlist_html(html)
        print(f"Original: {html}")
        print(f"Result: {result}")
        self.assertTrue("&lt;Book Title and Volume&gt;" in result)
        
if __name__ == '__main__':
    unittest.main()