from unittest.mock import Mock


class _EmptyPostModels:
    def all(self):
        return []


def test_anonymous_post_list_returns_empty_response_without_language_filters(
    monkeypatch,
):
    """Anonymous post lists must not require a per-user language preference."""
    from app import create_app
    from app.api.alpha.utils import post as post_utils
    from tests.conftest import TestConfig

    empty_result = Mock()
    empty_result.scalars.return_value.all.return_value = []
    monkeypatch.setattr(
        post_utils.db.session, "execute", Mock(return_value=empty_result)
    )
    monkeypatch.setattr(
        post_utils, "post_ids_to_models", lambda *args: _EmptyPostModels()
    )

    app = create_app(TestConfig)
    with app.test_request_context("/api/alpha/post/list"):
        response = post_utils.get_post_list(None, {})

    assert response == {"posts": [], "next_page": None}
