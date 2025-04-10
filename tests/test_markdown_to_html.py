import unittest
from app.utils import markdown_to_html

class TestMarkdownToHtml(unittest.TestCase):
    
    def test_basic_markdown(self):
        """Test basic markdown formatting"""
        markdown = "**Bold** and *italic* text"
        result = markdown_to_html(markdown)
        self.assertEqual(result, "<p><strong>Bold</strong> and <em>italic</em> text</p>\n")
        
    def test_paragraphs(self):
        """Test paragraph formatting"""
        markdown = "First paragraph\n\nSecond paragraph"
        result = markdown_to_html(markdown)
        self.assertEqual(result, "<p>First paragraph</p>\n<p>Second paragraph</p>\n")
        
    def test_links(self):
        """Test links formatting"""
        markdown = "[Link text](https://example.com)"
        result = markdown_to_html(markdown)
        self.assertEqual(result, '<p><a href="https://example.com" rel="nofollow ugc" target="_blank">Link text</a></p>\n')
        
    def test_code_blocks(self):
        """Test code blocks formatting"""
        markdown = "```\ncode block\n```"
        result = markdown_to_html(markdown)
        self.assertTrue("<pre><code>code block" in result)
        
    def test_blockquote(self):
        """Test blockquote formatting"""
        markdown = "> This is a quote"
        result = markdown_to_html(markdown)
        self.assertTrue("<blockquote>\n<p>This is a quote</p>\n</blockquote>" in result)
        
    def test_lists(self):
        """Test unordered and ordered lists"""
        markdown = "* Item 1\n* Item 2\n\n1. First\n2. Second"
        result = markdown_to_html(markdown)
        self.assertTrue("<ul>\n<li>Item 1</li>\n<li>Item 2</li>\n</ul>" in result)
        self.assertTrue("<ol>\n<li>First</li>\n<li>Second</li>\n</ol>" in result)
        
    def test_angle_brackets(self):
        """Test that angle brackets are properly escaped"""
        markdown = "Text with <tags> should be escaped"
        result = markdown_to_html(markdown)
        self.assertTrue("&lt;tags&gt;" in result)
        
    def test_angle_brackets_in_blockquote(self):
        """Test that angle brackets in blockquotes are properly escaped"""
        markdown = "> <Book Title and Volume> Review Goes Here [5/10]"
        result = markdown_to_html(markdown)
        self.assertTrue("&lt;Book Title and Volume&gt;" in result)
        
    def test_complex_markdown_with_angle_brackets(self):
        """Test a more complex markdown sample with angle brackets"""
        markdown = """What light novels have you read in the past week? Something good? Bad? Let us know about it.

And if you want to add your score to the database to help your fellow Bookworms find new reading materials you can use the following template:

><Book Title and Volume> Review Goes Here [5/10]
"""
        result = markdown_to_html(markdown)
        print("Result: " + result)
        self.assertTrue("&lt;Book Title and Volume&gt;" in result)
        self.assertTrue("<blockquote>" in result)
        
if __name__ == '__main__':
    unittest.main()