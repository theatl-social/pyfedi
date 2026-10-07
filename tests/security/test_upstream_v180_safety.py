"""Behavioral regressions found while integrating the upstream 1.8 release."""

from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image
from flask import g
from flask_wtf.csrf import generate_csrf
from werkzeug.datastructures import FileStorage, MultiDict


@pytest.mark.parametrize("case", ["missing_csrf", "invalid_csrf", "short_title", "long_alt", "valid"])
def test_gallery_form_preserves_outer_validation(test_app, case):
    from app import db
    from app.community.forms import CreateGalleryForm
    from app.models import Community

    community = Community(name="gallery-test", title="Gallery test", instance_id=1)
    db.session.add(community)
    db.session.commit()
    test_app.config["WTF_CSRF_ENABLED"] = True
    with test_app.test_request_context(method="POST"):
        g.site = SimpleNamespace(enable_nsfw=True, enable_nsfl=True, allow_local_image_posts=True)
        data = {
            "communities": str(community.id), "language_id": "1",
            "title": "Gallery title", "timezone": "UTC", "repeat": "none",
            "images-0-alt_text": "Image description", "csrf_token": generate_csrf(),
        }
        if case == "missing_csrf":
            del data["csrf_token"]
        elif case == "invalid_csrf":
            data["csrf_token"] = "invalid"
        elif case == "short_title":
            data["title"] = "x"
        elif case == "long_alt":
            data["images-0-alt_text"] = "x" * 1501
        image = BytesIO()
        Image.new("RGB", (2, 2)).save(image, "PNG")
        image.seek(0)
        form = CreateGalleryForm(formdata=MultiDict(data))
        form.communities.choices = [(community.id, community.title)]
        form.language_id.choices = [(1, "English")]
        form.timezone.choices = [("UTC", "UTC")]
        form.images[0].image_file.data = FileStorage(image, filename="image.png", content_type="image/png")
        assert form.validate() is (case == "valid"), form.errors


@pytest.mark.parametrize("path", ["/tmp/private.png", "private.png", "file:///tmp/private.png"])
def test_federated_gallery_rejects_local_image_paths(test_app, path, monkeypatch):
    from app.shared.post import build_gallery_thumbnail

    monkeypatch.setattr("app.shared.post.get_request", lambda url: None)
    opened = []
    monkeypatch.setattr("app.shared.post.Image.open", lambda value: opened.append(value))
    with pytest.raises(ValueError, match="remote"):
        build_gallery_thumbnail([path, "https://public.example/image.png"], return_file_id=False)
    assert opened == []


@pytest.mark.parametrize("remote", [True, False])
@pytest.mark.parametrize("local_only", [True, False])
def test_self_identified_feed_bot_has_no_moderation_privilege(test_app, remote, local_only, monkeypatch):
    from app.models import User, Instance
    from app.utils import can_create_post

    user = User(id=123, user_name="feed_bot", bot=True, verified=True, private_key="test-key")
    user.ap_id = "feed_bot@evil.example" if remote else None
    user.ap_profile_id = "https://evil.example/u/feed_bot" if remote else None
    user.instance = Instance(domain="evil.example") if remote else None
    community = SimpleNamespace(id=1, instance_id=1, banned=False, restricted_to_mods=True,
                                local_only=local_only, is_moderator=lambda actor: False)
    monkeypatch.setattr(User, "is_admin", lambda actor: False)
    monkeypatch.setattr("app.utils.instance_banned", lambda domain: False)
    monkeypatch.setattr("app.utils.communities_banned_from", lambda user_id: [])
    monkeypatch.setattr("app.utils.banned_instances", lambda user_id: [])
    assert can_create_post(user, community) is False


@pytest.mark.parametrize("configured,banned,posting_ban,allowed", [
    (True, False, False, True), (False, False, False, False),
    (True, True, False, False), (True, False, True, False),
])
def test_provisioned_rss_bot_requires_feed_and_respects_bans(test_app, monkeypatch, configured, banned, posting_ban, allowed):
    from app import db
    from app.models import Community, RssFeed, User
    from app.utils import can_create_post

    community = Community(name="rss-test", title="RSS", restricted_to_mods=True, local_only=True, instance_id=1)
    user = User(user_name="feed_bot", bot=True, verified=True, private_key="key", ban_posts=posting_ban,
                admin_note="Automatically created bot to author RSS feed posts")
    db.session.add_all([community, user])
    db.session.commit()
    if configured:
        db.session.add(RssFeed(community_id=community.id, url="https://example.org/feed"))
        db.session.commit()
    monkeypatch.setattr(User, "is_admin", lambda actor: False)
    monkeypatch.setattr("app.utils.communities_banned_from", lambda user_id: [community.id] if banned else [])
    monkeypatch.setattr("app.utils.banned_instances", lambda user_id: [])
    assert can_create_post(user, community) is allowed


def test_rss_cli_refuses_squatted_account_before_token_issuance(test_app, monkeypatch):
    from app import db
    from app.models import User

    db.session.add(User(user_name="feed_bot", bot=True))
    db.session.commit()
    issued = []
    monkeypatch.setattr(User, "encode_jwt_token", lambda user: issued.append(user.id))
    from app.cli import register
    register(test_app)
    result = test_app.test_cli_runner().invoke(args=["rss-feeds"])
    assert result.exit_code != 0
    assert "not provisioned" in str(result.exception)
    assert issued == []


def test_recent_hashtags_include_only_published_public_content(test_app):
    from app import db
    from app.community.util import hashtags_recent
    from app.constants import POST_STATUS_DRAFT, POST_STATUS_PUBLISHED
    from app.models import Community, Post, Tag

    for name, private_post, private_community, status in [
        ("public", False, False, POST_STATUS_PUBLISHED),
        ("secret-post", True, False, POST_STATUS_PUBLISHED),
        ("secret-community", False, True, POST_STATUS_PUBLISHED),
        ("draft", False, False, POST_STATUS_DRAFT),
    ]:
        community = Community(name=name, title=name, private=private_community)
        tag = Tag(name=name, display_as=name)
        post = Post(title=name, community=community, private=private_post, status=status)
        post.tags.append(tag)
        db.session.add(post)
    db.session.commit()
    assert [tag["name"] for tag in hashtags_recent({})] == ["public"]


def _gallery_post(test_app, tmp_path):
    from app import db
    from app.constants import POST_TYPE_GALLERY
    from app.models import Community, File, Post, User

    user = User(user_name="gallery-author", verified=True, private_key="test-key")
    community = Community(name="gallery", title="Gallery", instance_id=1)
    post = Post(title="Original gallery", community=community, author=user,
                type=POST_TYPE_GALLERY, url="https://example.org/post/1", slug="/post/1")
    path = tmp_path / "original.png"
    Image.new("RGB", (2, 2), "red").save(path)
    original = File(source_url="https://example.org/original.png", file_path=str(path), alt_text="Original alt")
    post.gallery.append(original)
    db.session.add(post)
    db.session.commit()
    return user, post, original, path


def _edit_gallery(post, user, uploads, alts):
    from app.constants import POST_TYPE_GALLERY, SRC_API
    from app.shared.post import edit_post

    data = dict(title=post.title, body="", url=post.url, nsfw=False, ai_generated=False,
                notify_author=False, language_id=None, timezone="UTC")
    return edit_post(data, post, POST_TYPE_GALLERY, SRC_API, user=user,
                     uploaded_files=uploads, image_alt_texts=alts)


def test_gallery_edit_updates_alt_text_with_unchanged_url(test_app, tmp_path, monkeypatch):
    user, post, original, path = _gallery_post(test_app, tmp_path)
    monkeypatch.setattr("app.shared.post.build_gallery_thumbnail", lambda files: None)
    monkeypatch.setattr("app.shared.post.task_selector", lambda *args, **kwargs: None)
    _edit_gallery(post, user, [None], ["Updated alt"])
    assert original.alt_text == "Updated alt"
    assert path.exists()
    assert [file.id for file in post.gallery] == [original.id]


def test_valid_gallery_replacement_saves_new_image_before_retiring_original(test_app, tmp_path, monkeypatch):
    from app import db
    from app.models import File

    user, post, original, path = _gallery_post(test_app, tmp_path)
    original_id = original.id
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("app.shared.post.build_gallery_thumbnail", lambda files: None)
    monkeypatch.setattr("app.shared.post.make_image_sizes", lambda *args: None)
    monkeypatch.setattr("app.shared.post.task_selector", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.shared.post.store_files_in_s3", lambda: False)
    test_app.config["IMAGE_HASHING_ENDPOINT"] = ""
    image = BytesIO()
    Image.new("RGB", (3, 3), "blue").save(image, "PNG")
    image.seek(0)
    _edit_gallery(post, user, [FileStorage(image, filename="replacement.png")], ["New alt"])
    gallery = list(post.gallery)
    assert len(gallery) == 1 and gallery[0].id != original_id
    assert gallery[0].alt_text == "New alt"
    assert Image.open(gallery[0].file_path).size == (3, 3)
    assert not path.exists()
    assert db.session.get(File, original_id) is None


def test_gallery_rejects_failed_svg_sanitization(test_app, tmp_path, monkeypatch):
    user, post, original, path = _gallery_post(test_app, tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("app.shared.post.sanitize_svg", lambda path: False)
    monkeypatch.setattr("app.shared.post.build_gallery_thumbnail", lambda files: None)
    monkeypatch.setattr("app.shared.post.make_image_sizes", lambda *args: None)
    monkeypatch.setattr("app.shared.post.task_selector", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.shared.post.store_files_in_s3", lambda: False)
    svg = FileStorage(BytesIO(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'), filename="active.svg")
    with pytest.raises(ValueError, match="SVG"):
        _edit_gallery(post, user, [svg], ["SVG alt"])
    assert path.exists()
    assert [file.id for file in post.gallery] == [original.id]
    assert not list(tmp_path.rglob("*.svg"))


def test_gallery_thumbnail_failure_preserves_originals(test_app, tmp_path, monkeypatch):
    user, post, original, path = _gallery_post(test_app, tmp_path)
    monkeypatch.chdir(tmp_path)
    def fail_thumbnail(files):
        raise RuntimeError("thumbnail failed")
    monkeypatch.setattr("app.shared.post.build_gallery_thumbnail", fail_thumbnail)
    monkeypatch.setattr("app.shared.post.make_image_sizes", lambda *args: None)
    monkeypatch.setattr("app.shared.post.store_files_in_s3", lambda: False)
    test_app.config["IMAGE_HASHING_ENDPOINT"] = ""
    image = BytesIO()
    Image.new("RGB", (3, 3), "blue").save(image, "PNG")
    image.seek(0)
    with pytest.raises(RuntimeError, match="thumbnail failed"):
        _edit_gallery(post, user, [FileStorage(image, filename="replacement.png")], ["Replacement"])
    assert path.exists()
    assert [file.id for file in post.gallery] == [original.id]


@pytest.mark.parametrize("source", ["/static/media/../../../sentinel.txt", "/static/media/posts/victim.png"])
def test_remote_gallery_cleanup_does_not_delete_url_named_local_files(test_app, tmp_path, monkeypatch, source):
    from app import db
    from app.models import File

    user, post, original, path = _gallery_post(test_app, tmp_path)
    monkeypatch.chdir(tmp_path)
    test_app.config["SERVER_NAME"] = "test.localhost"
    test_app.config["SERVER_URL"] = "https://test.localhost"
    victim = tmp_path / ("sentinel.txt" if ".." in source else "app/static/media/posts/victim.png")
    victim.parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "app/static/media").mkdir(parents=True, exist_ok=True)
    victim.write_bytes(b"Other owner's file")
    post.gallery.append(File(source_url=test_app.config["SERVER_URL"] + source))
    db.session.commit()
    post.delete_dependencies()
    db.session.commit()
    assert victim.read_bytes() == b"Other owner's file"


def test_owned_original_and_resized_files_are_deleted_without_url_inference(test_app, tmp_path):
    from app.models import File

    original = tmp_path / "owned-original.png"
    resized = tmp_path / "owned-resized.png"
    original.write_bytes(b"original")
    resized.write_bytes(b"resized")
    file = File(source_url="https://example.org/remote-name.png",
                original_path=str(original), file_path=str(resized))
    file.delete_from_disk(purge_cdn=False)
    assert not original.exists() and not resized.exists()


def test_rejected_gallery_replacement_preserves_original(test_app, tmp_path, monkeypatch):
    user, post, original, path = _gallery_post(test_app, tmp_path)
    original_bytes = path.read_bytes()
    monkeypatch.chdir(tmp_path)
    # Force gallery processing in the unfixed upstream implementation as well.
    post.url = None
    from app.constants import POST_TYPE_GALLERY, SRC_API
    from app.shared.post import edit_post

    invalid = FileStorage(BytesIO(b"not an image"), filename="replacement.png")
    data = dict(title=post.title, body="", url="https://example.org/gallery", nsfw=False,
                ai_generated=False, notify_author=False, language_id=None)
    with pytest.raises(Exception):
        edit_post(data, post, POST_TYPE_GALLERY, SRC_API, user=user,
                  uploaded_files=[invalid], image_alt_texts=["Replacement alt"])
    assert path.read_bytes() == original_bytes
    assert [file.id for file in post.gallery] == [original.id]


def test_gallery_purge_deletes_owned_images_and_preserves_shared_images(test_app, tmp_path):
    from app import db
    from app.models import File, Post

    user, post, original, path = _gallery_post(test_app, tmp_path)
    shared_path = tmp_path / "shared.png"
    Image.new("RGB", (2, 2), "blue").save(shared_path)
    shared = File(source_url="https://example.org/shared.png", file_path=str(shared_path))
    second = Post(title="Other gallery", author=user, community=post.community, type=post.type)
    post.gallery.append(shared)
    second.gallery.append(shared)
    db.session.add(second)
    db.session.commit()
    original_id = original.id
    post.delete_dependencies()
    db.session.delete(post)
    db.session.commit()
    assert not path.exists()
    assert db.session.get(File, original_id) is None
    assert shared_path.exists()
    assert [file.id for file in second.gallery] == [shared.id]


def test_rss_ignores_invalid_categories_and_keeps_valid_tags(test_app, tmp_path):
    from xml.etree import ElementTree
    from app.models import Tag
    from app.rss_extras import RSSFeed

    user, post, original, path = _gallery_post(test_app, tmp_path)
    post.tags = [Tag(name="bad", display_as="bad\x0btag"), Tag(name="normal", display_as="Normal")]
    post.ap_id = "https://example.org/posts/1"
    feed = RSSFeed(title="Feed", link="https://example.org", description="Feed")
    xml = ElementTree.fromstring(feed.create_feed([post], "https://example.org"))
    assert "Normal" in [element.text for element in xml.findall(".//item/category")]
    assert len(xml.findall(".//item")) == 1


def test_federated_gallery_create_update_preserves_images_order_and_alt(test_app, monkeypatch):
    from contextlib import nullcontext
    from app import db
    from app.models import Community, Instance, Post, Site, User, utcnow
    from app.constants import POST_TYPE_GALLERY
    from app.activitypub.util import update_post_from_activity

    instance = Instance(domain="remote.example", software="piefed")
    user = User(user_name="photographer", ap_id="photographer@remote.example", instance=instance,
                ap_profile_id="https://remote.example/u/photographer")
    community = Community(name="photos", title="Photos", instance_id=1)
    site = Site(id=1, name="Test")
    db.session.add_all([user, community, site])
    db.session.commit()
    db.session.connection().connection.driver_connection.create_function("now", 0, lambda: utcnow().isoformat(" "))
    monkeypatch.setattr("app.utils.site_language_id", lambda: None)
    monkeypatch.setattr("app.utils.blocked_phrases", lambda: [])
    monkeypatch.setattr("app.utils.get_setting", lambda key, default=None: False)
    monkeypatch.setattr("app.activitypub.util.get_setting", lambda key, default=None: False)
    monkeypatch.setattr("app.redis_client", SimpleNamespace(lock=lambda *args, **kwargs: nullcontext()))
    activity = dict(id="https://remote.example/activities/1", type="Create", object={
        "id": "https://remote.example/posts/1", "type": "Page", "name": "Gallery",
        "content": "Original body", "image": {"url": "https://remote.example/composite.png"},
        "attachment": [
            dict(type="Document", url="https://remote.example/first.png", name="First alt"),
            dict(type="Document", url="https://remote.example/second.png", name="Second alt"),
            dict(type="Link", href="https://remote.example/posts/1"),
        ],
    })
    post = Post.new(user, community, activity)
    assert post.type == POST_TYPE_GALLERY
    activity["type"] = "Update"
    activity["object"]["content"] = "Updated body"
    activity["object"]["attachment"] = [
        dict(type="Document", url="https://remote.example/second.png", name="Updated second"),
        dict(type="Document", url="https://remote.example/first.png", name="Updated first"),
        dict(type="Link", href="https://remote.example/posts/1"),
    ]
    update_post_from_activity(post, activity)
    assert post.type == POST_TYPE_GALLERY
    assert "Updated body" in post.body
    assert [(image.source_url, image.alt_text) for image in post.gallery] == [
        ("https://remote.example/second.png", "Updated second"),
        ("https://remote.example/first.png", "Updated first"),
    ]
