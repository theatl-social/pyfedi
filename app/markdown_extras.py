"""
Custom markdown2 extras for PieFed
"""
import re
from markdown2 import Extra, Stage


class EnhancedImages(Extra):
    """
    Enhances markdown image syntax to support additional attributes like alignment and dimensions.

    Syntax: ![alt text :: align-left width=200px height=150px](image_url)
    Or with thumbnail: ![alt text :: align-left width=200px](thumbnail.jpg, fullsize.jpg)

    Supported attributes:
    - align-left, align-right, align-center: Sets align attribute
    - width=VALUE: Sets width attribute (supports px, %, em, etc.)
    - height=VALUE: Sets height attribute (supports px, %, em, etc.)
    - class=VALUE: Adds CSS class(es)

    Examples:
        ![A cat :: align-left width=200px](cat.jpg)
        -> <img src="cat.jpg" alt="A cat" align="left" width="200px" />

        ![Logo :: align-center width=50%](logo.png)
        -> <img src="logo.png" alt="Logo" align="center" width="50%" />

        ![Cat :: width=200px](thumb.jpg, full.jpg)
        -> <a href="full.jpg"><img src="thumb.jpg" alt="Cat" width="200px" /></a>
    """

    name = 'enhanced-images'
    # Run BEFORE LINKS stage to process markdown syntax
    order = (Stage.LINKS,), ()

    # Regex to find markdown image syntax with :: separated attributes
    # Matches: ![alt text :: attributes](url) or ![alt text :: attributes](url "title")
    _md_img_with_attrs_re = re.compile(
        r'!\[([^\]]*?)\s*::\s*([^\]]+?)\]'  # ![alt text :: attributes]
        r'\(([^\)]+?)\)',  # (url) or (url "title")
        re.MULTILINE
    )

    def test(self, text):
        """Only run if there are markdown images with :: delimiter"""
        return '![' in text and '::' in text

    def run(self, text):
        """
        Process markdown image syntax and convert to temporary placeholder that
        will be converted to proper HTML by markdown2's link processing.
        """
        return self._md_img_with_attrs_re.sub(self._process_markdown_image, text)

    def _process_markdown_image(self, match: re.Match) -> str:
        """Process a single markdown image and extract custom attributes"""
        alt_text = match.group(1).strip()
        attrs_string = match.group(2).strip()
        url_and_title = match.group(3).strip()

        # Check if there are two URLs (thumbnail, fullsize)
        # Split by comma, but be careful about titles with commas
        full_url = None
        if ',' in url_and_title:
            # Check if there's a quoted title
            title_match = re.search(r'"([^"]*)"', url_and_title)
            if title_match:
                # Extract the title and remove it temporarily
                title = title_match.group(0)
                url_part = url_and_title.replace(title, '').strip()
                if ',' in url_part:
                    # Two URLs present
                    urls = [u.strip() for u in url_part.split(',', 1)]
                    url_and_title = f"{urls[0]} {title}"
                    full_url = urls[1]
            else:
                # No title, just split by comma
                urls = [u.strip() for u in url_and_title.split(',', 1)]
                if len(urls) == 2:
                    url_and_title = urls[0]
                    full_url = urls[1]

        # Parse custom attributes
        custom_attrs = {}

        # Process alignment
        if 'align-left' in attrs_string:
            custom_attrs['align'] = 'left'
        elif 'align-right' in attrs_string:
            custom_attrs['align'] = 'right'
        elif 'align-center' in attrs_string:
            custom_attrs['align'] = 'center'

        # Process width attribute: width=200px, width=50%, etc.
        width_match = re.search(r'width\s*=\s*([^\s]+)', attrs_string)
        if width_match:
            custom_attrs['width'] = width_match.group(1)

        # Process height attribute
        height_match = re.search(r'height\s*=\s*([^\s]+)', attrs_string)
        if height_match:
            custom_attrs['height'] = height_match.group(1)

        # Process class attribute
        class_match = re.search(r'class\s*=\s*["\']?([^"\'\s]+)["\']?', attrs_string)
        if class_match:
            custom_attrs['class'] = class_match.group(1)

        # Store the attributes in the Markdown instance for later retrieval
        # Create a unique marker using a counter to ensure uniqueness
        if not hasattr(self.md, '_enhanced_images_counter'):
            self.md._enhanced_images_counter = 0
        self.md._enhanced_images_counter += 1
        marker_id = f"enhanced-img-{self.md._enhanced_images_counter}"

        # Store in markdown instance
        if not hasattr(self.md, '_enhanced_images_attrs'):
            self.md._enhanced_images_attrs = {}
        self.md._enhanced_images_attrs[marker_id] = {
            'attrs': custom_attrs,
            'full_url': full_url
        }

        # Return raw HTML instead of markdown so we can control the output exactly
        # Parse title if present
        title_match = re.search(r'"([^"]*)"', url_and_title)
        title_attr = f' title="{title_match.group(1)}"' if title_match else ''

        # Get the URL (first part before any title)
        url = url_and_title.split('"')[0].strip() if '"' in url_and_title else url_and_title.split()[0]

        # Create the HTML and hash it to protect from smarty-pants and other processing
        # Use double quotes since the HTML is protected by hashing
        html = f'<img src="{url}" alt="{alt_text}"{title_attr} data-enhanced-img="{marker_id}" />'
        # Use markdown2's hashing to protect the HTML from further processing (especially smarty-pants)
        return self.md._hash_span(html)


# Post-process function to be called manually after markdown2.markdown()
# This is needed because hashed HTML doesn't get processed by extras after unhashing
def apply_enhanced_image_attributes(html: str, md_instance) -> str:
    """
    Apply stored enhanced image attributes to HTML output.
    Call this after markdown2.markdown() to add custom attributes to enhanced images.
    """
    if not hasattr(md_instance, '_enhanced_images_attrs'):
        return html

    # Match img tags with data-enhanced-img attribute
    img_pattern = re.compile(r'<img\s+([^>]*?data-enhanced-img=[^>]*?)(/?>)', re.IGNORECASE)

    def add_attrs(match):
        attrs_str = match.group(1)
        closing = match.group(2)

        # Extract marker ID
        marker_match = re.search(r'data-enhanced-img="([^"]+)"', attrs_str)
        if not marker_match:
            return match.group(0)

        marker_id = marker_match.group(1)
        stored_data = md_instance._enhanced_images_attrs.get(marker_id, {})
        custom_attrs = stored_data.get('attrs', {})
        full_url = stored_data.get('full_url')

        # Remove data-enhanced-img attribute
        new_attrs = re.sub(r'\s*data-enhanced-img="[^"]+"', '', attrs_str)

        # Add custom attributes
        for attr_name, attr_value in custom_attrs.items():
            new_attrs += f' {attr_name}="{attr_value}"'

        img_tag = f'<img {new_attrs}{closing}'

        # Wrap in anchor if needed
        if full_url:
            return f'<a href="{full_url}">{img_tag}</a>'
        return img_tag

    return img_pattern.sub(add_attrs, html)


# Register the extra for markdown2
EnhancedImages.register()
