"""
Test fixtures and factories for PyFedi tests
Used to create consistent test data
"""
from datetime import datetime
import factory
from factory.alchemy import SQLAlchemyModelFactory
from app.models import User, Community, Post, Instance, CommunityMember
from app import db


class InstanceFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Instance
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = 'commit'
    
    domain = factory.Sequence(lambda n: f'instance{n}.example.com')
    software = factory.Faker('random_element', elements=['mastodon', 'lemmy', 'peertube'])
    created_at = factory.Faker('date_time_this_year')
    updated_at = factory.LazyAttribute(lambda obj: obj.created_at)
    blocked = False


class UserFactory(SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = 'commit'
    
    username = factory.Sequence(lambda n: f'user{n}')
    email = factory.LazyAttribute(lambda obj: f'{obj.username}@example.com')
    ap_profile_id = factory.LazyAttribute(lambda obj: f'https://example.com/users/{obj.username}')
    instance = factory.SubFactory(InstanceFactory)
    public_key = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0Z3VS5JJcds3xfn/yP3Z
-----END PUBLIC KEY-----"""
    private_key = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDRndVLkkl2zfF+
-----END PRIVATE KEY-----"""
    created_at = factory.Faker('date_time_this_year')
    banned = False
    is_site_admin = False


class CommunityFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Community
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = 'commit'
    
    name = factory.Sequence(lambda n: f'community{n}')
    title = factory.LazyAttribute(lambda obj: f'{obj.name.title()} Community')
    ap_profile_id = factory.LazyAttribute(lambda obj: f'https://example.com/c/{obj.name}')
    ap_inbox_url = factory.LazyAttribute(lambda obj: f'{obj.ap_profile_id}/inbox')
    ap_outbox_url = factory.LazyAttribute(lambda obj: f'{obj.ap_profile_id}/outbox')
    created_at = factory.Faker('date_time_this_year')
    allow_non_members_to_post = True


class PostFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Post
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = 'commit'
    
    title = factory.Faker('sentence', nb_words=6)
    body = factory.Faker('text', max_nb_chars=500)
    ap_id = factory.Sequence(lambda n: f'https://example.com/posts/{n}')
    author = factory.SubFactory(UserFactory)
    community = factory.SubFactory(CommunityFactory)
    created_at = factory.Faker('date_time_this_year')
    updated_at = factory.LazyAttribute(lambda obj: obj.created_at)


class CommunityMemberFactory(SQLAlchemyModelFactory):
    class Meta:
        model = CommunityMember
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = 'commit'
    
    user = factory.SubFactory(UserFactory)
    community = factory.SubFactory(CommunityFactory)
    is_admin = False
    is_moderator = False
    is_banned = False
    created_at = factory.Faker('date_time_this_year')


# Test data generators
def create_test_user(**kwargs):
    """Create a test user with optional overrides"""
    return UserFactory(**kwargs)


def create_test_community(**kwargs):
    """Create a test community with optional overrides"""
    return CommunityFactory(**kwargs)


def create_test_post(**kwargs):
    """Create a test post with optional overrides"""
    return PostFactory(**kwargs)


def create_relay_actor():
    """Create a relay actor for testing"""
    instance = InstanceFactory(
        domain='relay.example.com',
        software='activityrelay'
    )
    return UserFactory(
        username='relay',
        ap_profile_id='https://relay.example.com/actor',
        instance=instance,
        type='Service'
    )


def create_malicious_actor():
    """Create a potentially malicious actor for security testing"""
    instance = InstanceFactory(
        domain='evil.example.com',
        blocked=False  # Not yet blocked
    )
    return UserFactory(
        username='attacker',
        ap_profile_id='https://evil.example.com/users/attacker',
        instance=instance
    )