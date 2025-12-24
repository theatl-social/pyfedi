import unittest

import markdown2
from app.markdown_extras import apply_enhanced_image_attributes


def markdown_with_enhanced_images(text, extras_list=None):
    """Helper function to convert markdown with enhanced images support"""
    if extras_list is None:
        extras_list = ["enhanced-images"]
    extras_dict = {extra: True for extra in extras_list}
    md = markdown2.Markdown(extras=extras_dict)
    html = md.convert(text)
    # Apply enhanced image attributes
    html = apply_enhanced_image_attributes(html, md)
    return html


class TestEnhancedImages(unittest.TestCase):
    def test_image_with_align_left_and_width(self):
        """Test image with align-left and width attribute"""
        markdown = "![A cute cat :: align-left width=200px](cat.jpg)"
        result = markdown_with_enhanced_images(markdown)
        self.assertIn('align="left"', result)
        self.assertIn('width="200px"', result)
        self.assertIn('alt="A cute cat"', result)
        self.assertIn('src="cat.jpg"', result)

    def test_image_with_align_right_and_percentage_width(self):
        """Test image with align-right and percentage width"""
        markdown = "![Logo :: align-right width=50%](logo.png)"
        result = markdown_with_enhanced_images(markdown)
        self.assertIn('align="right"', result)
        self.assertIn('width="50%"', result)
        self.assertIn('alt="Logo"', result)
        self.assertIn('src="logo.png"', result)

    def test_image_with_align_center_width_and_height(self):
        """Test image with align-center, width, and height"""
        markdown = "![Banner :: align-center width=800px height=200px](banner.jpg)"
        result = markdown_with_enhanced_images(markdown)
        self.assertIn('align="center"', result)
        self.assertIn('width="800px"', result)
        self.assertIn('height="200px"', result)
        self.assertIn('alt="Banner"', result)
        self.assertIn('src="banner.jpg"', result)

    def test_regular_image_without_custom_attributes(self):
        """Test that regular markdown images still work"""
        markdown = "![Regular image](regular.jpg)"
        result = markdown_with_enhanced_images(markdown)
        self.assertIn('alt="Regular image"', result)
        self.assertIn('src="regular.jpg"', result)
        # Should not have any custom attributes
        self.assertNotIn("align=", result)
        self.assertNotIn("width=", result)
        self.assertNotIn("height=", result)

    def test_image_with_class_attribute(self):
        """Test image with CSS class attribute"""
        markdown = "![Styled :: align-left class=thumbnail](thumb.jpg)"
        result = markdown_with_enhanced_images(markdown)
        self.assertIn('align="left"', result)
        self.assertIn('class="thumbnail"', result)
        self.assertIn('alt="Styled"', result)
        self.assertIn('src="thumb.jpg"', result)

    def test_image_with_all_attributes(self):
        """Test image with all supported attributes"""
        markdown = "![Full example :: align-center width=300px height=200px class=fancy](example.jpg)"
        result = markdown_with_enhanced_images(markdown)
        self.assertIn('align="center"', result)
        self.assertIn('width="300px"', result)
        self.assertIn('height="200px"', result)
        self.assertIn('class="fancy"', result)
        self.assertIn('alt="Full example"', result)
        self.assertIn('src="example.jpg"', result)

    def test_image_without_enhanced_extras(self):
        """Test that :: delimiter in alt text works normally without the extras"""
        markdown = "![Alt text :: some data](image.jpg)"
        result = markdown2.markdown(markdown)
        # Without the extras, the :: should be preserved in alt text
        self.assertIn('alt="Alt text :: some data"', result)
        self.assertNotIn("align=", result)

    def test_image_with_title(self):
        """Test enhanced image with title attribute"""
        markdown = '![Cat :: align-left width=200px](cat.jpg "A cute cat")'
        result = markdown_with_enhanced_images(markdown)
        self.assertIn('align="left"', result)
        self.assertIn('width="200px"', result)
        self.assertIn('alt="Cat"', result)
        self.assertIn('title="A cute cat"', result)
        self.assertIn('src="cat.jpg"', result)

    def test_multiple_images_in_same_document(self):
        """Test multiple enhanced images in the same markdown"""
        markdown = """
![First :: align-left width=100px](first.jpg)

Some text here.

![Second :: align-right width=200px](second.jpg)
"""
        result = markdown_with_enhanced_images(markdown)
        # First image
        self.assertIn('alt="First"', result)
        self.assertIn('align="left"', result)
        self.assertIn('width="100px"', result)
        self.assertIn('src="first.jpg"', result)
        # Second image
        self.assertIn('alt="Second"', result)
        self.assertIn('align="right"', result)
        self.assertIn('width="200px"', result)
        self.assertIn('src="second.jpg"', result)

    def test_image_with_width_no_units(self):
        """Test image with width value without units"""
        markdown = "![Image :: width=500](image.jpg)"
        result = markdown_with_enhanced_images(markdown)
        self.assertIn('width="500"', result)
        self.assertIn('alt="Image"', result)

    def test_image_with_em_units(self):
        """Test image with em units for width"""
        markdown = "![Image :: width=20em height=15em](image.jpg)"
        result = markdown_with_enhanced_images(markdown)
        self.assertIn('width="20em"', result)
        self.assertIn('height="15em"', result)

    def test_thumbnail_with_fullsize(self):
        """Test thumbnail image linking to fullsize"""
        markdown = "![Cat :: width=200px](thumb.jpg, full.jpg)"
        result = markdown_with_enhanced_images(markdown)
        self.assertIn('<a href="full.jpg">', result)
        self.assertIn('src="thumb.jpg"', result)
        self.assertIn('width="200px"', result)
        self.assertIn('alt="Cat"', result)
        # Img should be inside anchor tag
        self.assertIn("</a>", result)

    def test_thumbnail_with_fullsize_and_attributes(self):
        """Test thumbnail with fullsize and multiple attributes"""
        markdown = (
            "![Cat :: align-left width=200px class=thumbnail](thumb.jpg, full.jpg)"
        )
        result = markdown_with_enhanced_images(markdown)
        self.assertIn('<a href="full.jpg">', result)
        self.assertIn('src="thumb.jpg"', result)
        self.assertIn('align="left"', result)
        self.assertIn('width="200px"', result)
        self.assertIn('class="thumbnail"', result)
        self.assertIn('alt="Cat"', result)

    def test_thumbnail_with_fullsize_and_title(self):
        """Test thumbnail with fullsize and title attribute"""
        markdown = '![Cat :: width=200px](thumb.jpg, full.jpg "A cute cat")'
        result = markdown_with_enhanced_images(markdown)
        self.assertIn('<a href="full.jpg">', result)
        self.assertIn('src="thumb.jpg"', result)
        self.assertIn('width="200px"', result)
        self.assertIn('title="A cute cat"', result)
        self.assertIn('alt="Cat"', result)

    def test_single_image_no_anchor_tag(self):
        """Test that single images don't get wrapped in anchor tag"""
        markdown = "![Cat :: width=200px](cat.jpg)"
        result = markdown_with_enhanced_images(markdown)
        self.assertIn("<img", result)
        self.assertIn('src="cat.jpg"', result)
        # Should NOT have anchor tag
        self.assertNotIn("<a href=", result)

    def test_integration_with_markdown_to_html(self):
        """Test integration with markdown_to_html function (full extras suite)"""
        from app.utils import markdown_to_html

        markdown = "Testing!\n\n![an image :: width=50](https://piefed.social/static/media/logo_8p7en.svg)\n\nthere we go"
        # Pass test_env to skip fediverse_domains() cache lookup which requires Flask app context
        result = markdown_to_html(markdown, test_env={"fn_string": "fn-test"})
        print(f"Result: {result}")
        # Should have proper width attribute
        self.assertIn('width="50"', result)
        # Should have proper src (without extra quotes)
        self.assertIn("src=", result)
        self.assertIn("https://piefed.social/static/media/logo_8p7en.svg", result)
        # Should have proper alt text
        self.assertIn("alt=", result)
        self.assertIn("an image", result)
        # Should NOT have data-enhanced-img in final output
        self.assertNotIn("data-enhanced-img", result)
        # Should NOT have broken quotes like src="'url'"
        self.assertNotIn("src=\"'", result)
        self.assertNotIn("alt=\"'", result)


if __name__ == "__main__":
    unittest.main()
