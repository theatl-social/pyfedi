"""Test that all form fields referenced in templates exist in their form classes.

This test prevents a class of bug where:
1. A template references a form field (e.g., {{ render_field(form.privacy_url) }})
2. But the corresponding form class doesn't define that field
3. Resulting in a 500 error at runtime

This was introduced after fork feature `privacy_url` was lost during upstream merge.
"""

import re
from pathlib import Path

import pytest

# Form class imports - only import forms we're actually testing
from app.admin.forms import SiteProfileForm, SiteMiscForm, FederationForm
from app.auth.forms import LoginForm, RegistrationForm
from app.community.forms import AddCommunityForm


# Mapping of templates to their form classes
# Add new mappings as needed when templates/forms are added
TEMPLATE_FORM_MAP = {
    "admin/site.html": SiteProfileForm,
    "admin/misc.html": SiteMiscForm,
    "admin/federation.html": FederationForm,
    "auth/login.html": LoginForm,
    "auth/register.html": RegistrationForm,
    "community/add_community.html": AddCommunityForm,
}


def extract_form_field_references(template_content: str) -> set[str]:
    """Extract all form field references from template content.

    Matches patterns like:
    - render_field(form.field_name)
    - form.field_name()
    - form.field_name.data
    - form.field_name.label
    - form.field_name.errors
    """
    # Match form.XXX where XXX is a word character sequence
    pattern = r"form\.(\w+)"
    matches = set(re.findall(pattern, template_content))

    # Filter out method calls that aren't field references
    non_field_attrs = {"hidden_tag", "csrf_token", "validate_on_submit", "errors"}

    return matches - non_field_attrs


def get_form_field_names(form_class) -> set[str]:
    """Get all field names from a form class instance."""
    form = form_class()
    # Get field names from the form instance
    field_names = {field.name for field in form}
    # Also add csrf_token which is always present
    field_names.add("csrf_token")
    return field_names


class TestTemplateFormFields:
    """Test suite for validating template/form field consistency."""

    @pytest.mark.parametrize(
        "template_rel,form_class",
        list(TEMPLATE_FORM_MAP.items()),
        ids=list(TEMPLATE_FORM_MAP.keys()),
    )
    def test_template_form_fields_exist(self, template_rel: str, form_class):
        """Verify all form fields referenced in a template exist in the form class."""
        template_path = Path("app/templates") / template_rel

        if not template_path.exists():
            pytest.skip(f"Template {template_rel} not found")

        template_content = template_path.read_text()
        referenced_fields = extract_form_field_references(template_content)
        form_fields = get_form_field_names(form_class)

        missing_fields = referenced_fields - form_fields

        assert not missing_fields, (
            f"Template '{template_rel}' references fields not in {form_class.__name__}:\n"
            + "\n".join(f"  - form.{field}" for field in sorted(missing_fields))
        )

    def test_admin_site_form_completeness(self):
        """Specific test for admin/site.html - the template that triggered this test suite."""
        template_path = Path("app/templates/admin/site.html")
        template_content = template_path.read_text()

        # Extract fields specifically from render_field() calls
        render_field_pattern = r"render_field\(form\.(\w+)\)"
        rendered_fields = set(re.findall(render_field_pattern, template_content))

        form = SiteProfileForm()
        form_fields = {field.name for field in form}

        missing_fields = rendered_fields - form_fields

        assert not missing_fields, (
            f"admin/site.html render_field() calls reference missing SiteProfileForm fields:\n"
            + "\n".join(f"  - form.{field}" for field in sorted(missing_fields))
        )
