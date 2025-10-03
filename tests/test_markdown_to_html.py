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
        self.assertEqual(result,
                         '<p><a href="https://example.com" rel="nofollow ugc" target="_blank">Link text</a></p>\n')

    def test_links_w_periods(self):
        """Test links formatting with a period on the end"""
        markdown = "This is a test link https://pizza.com. Will it work?"
        result = markdown_to_html(markdown)
        self.assertEqual(result,
                         '<p>This is a test link <a href="https://pizza.com" rel="nofollow ugc" target="_blank">https://pizza.com</a>. Will it work?</p>\n')

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

    def test_gt_lt_in_code(self):
        """Test usage of angle brackets in code block"""
        markdown = "Normal text `code block > something else` normal text again"
        result = markdown_to_html(markdown)
        self.assertEqual(result, "<p>Normal text <code>code block &gt; something else</code> normal text again</p>\n")

    def test_gt_lt_in_code_block(self):
        """Test usage of angle brackets in large code block"""
        markdown = "Normal text\n\n```\n<html>\n```\n\nnormal text again"
        result = markdown_to_html(markdown)
        self.assertEqual(result,
                         "<p>Normal text</p>\n<pre><code>&lt;html&gt;\n</code></pre>\n<p>normal text again</p>\n")

    def test_complex_markdown_with_angle_brackets(self):
        """Test a more complex markdown sample with angle brackets"""
        markdown = """What light novels have you read in the past week? Something good? Bad? Let us know about it.

And if you want to add your score to the database to help your fellow Bookworms find new reading materials you can use the following template:

><Book Title and Volume> Review Goes Here [5/10]
"""
        result = markdown_to_html(markdown)
        self.assertTrue("&lt;Book Title and Volume&gt;" in result)
        self.assertTrue("<blockquote>" in result)

    def test_disallowed_tags(self):
        """Test that disallowed tags are removed"""
        markdown = "Paragraph with <script>alert('xss')</script> script."
        result = markdown_to_html(markdown)
        self.assertEqual(result, "<p>Paragraph with &lt;script&gt;alert(’xss’)&lt;/script&gt; script.</p>\n")
    
    def test_double_bold(self):
        """Test a variety of cases where bold markdown has caused problems in the past"""
        markdown = "Two **bold** words in one **bold** sentence."
        result = markdown_to_html(markdown)
        correct_html = "<p>Two <strong>bold</strong> words in one <strong>bold</strong> sentence.</p>\n"
        self.assertEqual(result, correct_html)

        markdown = "Links with underscores still work: https://en.wikipedia.org/wiki/Rick_Astley"
        result = markdown_to_html(markdown)
        correct_html = (
            '<p>Links with underscores still work: <a href="https://en.wikipedia.org/wiki/Rick_Astley" '
            'rel="nofollow ugc" target="_blank">https://en.wikipedia.org/wiki/Rick_Astley</a></p>\n')
        self.assertEqual(result, correct_html)

        markdown = "Double **bold** and ***italics* words** in *one* sentence."
        result = markdown_to_html(markdown)
        correct_html = ('<p>Double <strong>bold</strong> and <strong><em>italics</em> words</strong> in '
            '<em>one</em> sentence.</p>\n')
        self.assertEqual(result, correct_html)

        markdown = "Ignore `**bold**` words in code block with **bold** markdown."
        result = markdown_to_html(markdown)
        correct_html = '<p>Ignore <code>**bold**</code> words in code block with <strong>bold</strong> markdown.</p>\n'
        self.assertEqual(result, correct_html)

        markdown = "What about ignoring **bold** words inside a\n\n```\nfenced **code** block?\n```"
        result = markdown_to_html(markdown)
        correct_html = (
            '<p>What about ignoring <strong>bold</strong> words inside a</p>\n<pre><code>fenced **code** block?\n'
            '</code></pre>\n')
        self.assertEqual(result, correct_html)

        markdown = "[Bold in **part of** a link](https://en.wikipedia.org/wiki/Rick_Astley)"
        result = markdown_to_html(markdown)
        correct_html = (
            '<p><a href="https://en.wikipedia.org/wiki/Rick_Astley" rel="nofollow ugc" target="_blank">Bold in '
            '<strong>part of</strong> a link</a></p>\n')
        self.assertEqual(result, correct_html)

    def test_strikethrough_in_inline_code(self):
        """Don't strikethrough text in inline code."""
        markdown = "`don't ~~strikethrough~~`"
        correct_html = "<p><code>don't ~~strikethrough~~</code></p>\n"
        result = markdown_to_html(markdown)
        self.assertEqual(result, correct_html)
    
    def test_strikethrough_in_fenced_code(self):
        """Don't strikethrough text in fenced code block."""
        markdown = "```\ndon't ~~strikethrough~~\n```"
        correct_html = "<pre><code>don't ~~strikethrough~~\n</code></pre>\n"
        result = markdown_to_html(markdown)
        self.assertEqual(result, correct_html)
    
    def test_spoiler_in_fenced_code(self):
        """Don't format spoiler block in fenced code block."""
        markdown = "```\n::: spoiler Spoiler Title\ndon't ~~strikethrough~~\n:::\n```"
        correct_html = "<pre><code>::: spoiler Spoiler Title\ndon't ~~strikethrough~~\n:::\n</code></pre>\n"
        result = markdown_to_html(markdown)
        self.assertEqual(result, correct_html)

    def test_code_block_link(self):
        """Test code blocks formatting containing a link"""

        markdown = "```\ncode block with link: https://example.com/ \n```"
        result = markdown_to_html(markdown)
        self.assertEqual("<pre><code>code block with link: https://example.com/ \n</code></pre>\n", result)
    
    def test_en_dash(self):
        """Test converting -- to an en dash"""

        markdown = "Using--an en dash."
        result = markdown_to_html(markdown)
        self.assertEqual("<p>Using–an en dash.</p>\n", result)
    
    def test_em_dash(self):
        """Test converting --- to an em dash"""

        markdown = "Em-dashes are fairly idiosyncratic---strange, really---to use regularly."
        result = markdown_to_html(markdown)
        self.assertEqual("<p>Em-dashes are fairly idiosyncratic—strange, really—to use regularly.</p>\n", result)
    
    def test_em_dash_hr(self):
        """Test converting --- to an em dash while also having a horizontal rule"""

        markdown = "Writing em---dashes is\n\n---\n\nkind of annoying"
        result = markdown_to_html(markdown)
        self.assertEqual('<p>Writing em—dashes is</p>\n<hr/>\n<p>kind of annoying</p>\n', result)
    
    def test_ellipsis(self):
        """Test converting ... to an ellipsis character"""

        markdown = "Thinking about an ellipsis..."
        result = markdown_to_html(markdown)
        self.assertEqual("<p>Thinking about an ellipsis…</p>\n", result)
    
    def test_ignore_smartypants_inline_code(self):
        """Test that checks en- and em-dashes as well as ellipses are not in inline code"""

        markdown = "No `en--dash`, nor `em---dash`, nor `ellipsis...` here."
        result = markdown_to_html(markdown)
        self.assertEqual(
            '<p>No <code>en--dash</code>, nor <code>em---dash</code>, nor <code>ellipsis...</code> here.</p>\n', result)
    
    def test_ignore_smartypants_code_block(self):
        """Test that checks en- and em-dashes as well as ellipses are not in code blocks"""

        markdown = "```\nNo en--dash, nor em---dash, nor ellipsis... here.\n```"
        result = markdown_to_html(markdown)
        self.assertEqual("<pre><code>No en--dash, nor em---dash, nor ellipsis... here.\n</code></pre>\n", result)
    
    def test_bracketed_links(self):
        """Test that urls in angle brackets are turned into links"""

        markdown = "<https://piefed.social>"
        result = markdown_to_html(markdown)
        self.assertEqual(
            '<p><a href="https://piefed.social" rel="nofollow ugc" target="_blank">https://piefed.social</a></p>\n',
            result)
    
    def test_bracketed_links_inline_code(self):
        """Test that bracketed links are ignored in inline code"""

        markdown = "`<https://piefed.social>`"
        result = markdown_to_html(markdown)
        self.assertEqual('<p><code>&lt;https://piefed.social&gt;</code></p>\n', result)
    
    def test_bracketed_links_code_block(self):
        """Test that bracketed links are ignored in code blocks"""

        markdown = "```\n<https://piefed.social>\n```"
        result = markdown_to_html(markdown)
        self.assertEqual('<pre><code>&lt;https://piefed.social&gt;\n</code></pre>\n', result)
    
    def test_lemmy_autocomplete_community(self):
        """Test that lemmy-formatted autocomplete community names drop the markdown link formatting"""

        markdown = "[!community@instance.tld](https://instance.tld/c/community)"
        result = markdown_to_html(markdown)
        self.assertEqual('<p>!community@instance.tld</p>\n', result)
    
    def test_lemmy_autocomplete_person(self):
        """Test that lemmy-formatted autocomplete person names drop the markdown link formatting"""

        markdown = "[@user@instance.tld](https://instance.tld/u/user)"
        result = markdown_to_html(markdown)
        self.assertEqual('<p>@user@instance.tld</p>\n', result)
    
    def test_lemmy_autocomplete_feed(self):
        """
        Test that lemmy-formatted autocomplete feed names drop the markdown link formatting. Note that lemmy does not
        currently have autocomplete for feeds, this is really just a means to keep formatting consistent with people
        and communities.
        """

        markdown = "[~feed@instance.tld](https://instance.tld/f/feed)"
        result = markdown_to_html(markdown)
        self.assertEqual('<p>~feed@instance.tld</p>\n', result)


if __name__ == '__main__':
    unittest.main()
