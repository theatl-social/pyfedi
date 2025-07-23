from datetime import datetime
from marshmallow import Schema, fields, validate, ValidationError, EXCLUDE


# Lists used in schema for validation
reg_mode_list = ["Closed", "RequireApplication", "Open"]
sort_list = ["Active", "Hot", "New", "TopHour", "TopSixHour", "TopTwelveHour", "TopDay", "TopWeek", "TopMonth",
             "TopThreeMonths", "TopSixMonths", "TopNineMonths", "TopYear", "TopAll", "Scaled"]
comment_sort_list = ["Hot", "Top", "New", "Old"]
listing_type_list = ["All", "Local", "Subscribed", "Popular", "Moderating"]


def validate_datetime_string(text):
    try:
        # Ensures that string matches timestamp format used by lemmy/piefed api
        datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ")
        return True
    except ValueError:
        raise ValidationError(f"Bad datetime string: {text}")


class DefaultError(Schema):
    message = fields.String()

class Person(Schema):
    class Meta:
        unknown = EXCLUDE
    
    about = fields.String()
    actor_id = fields.Url(required=True, metadata={"example": "https://piefed.social/u/rimu"})
    avatar = fields.Url(allow_none=True)
    banned = fields.Boolean(required=True)
    banner = fields.Url(allow_none=True)
    bot = fields.Boolean(required=True)
    deleted = fields.Boolean(required=True)
    flair = fields.String()
    id = fields.Integer(required=True)
    instance_id = fields.Integer(required=True)
    local = fields.Boolean(required=True)
    published = fields.String(validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z"})
    title = fields.String()
    user_name = fields.String(required=True)


class PersonAggregates(Schema):
    comment_count = fields.Integer(required=True)
    person_id = fields.Integer(required=True)
    post_count = fields.Integer(required=True)


class PersonView(Schema):
    class Meta:
        unknown = EXCLUDE
    
    activity_alert = fields.Boolean(required=True)
    counts = fields.Nested(PersonAggregates, required=True)
    is_admin = fields.Boolean(required=True)
    person = fields.Nested(Person, required=True)


class LanguageView(Schema):
    class Meta:
        unknown = EXCLUDE
    
    code = fields.String(metadata={"example": "en"})
    id = fields.Integer(metadata={"example": "2"})
    name = fields.String(metadata={"example": "English"})


class Site(Schema):
    class Meta:
        unknown = EXCLUDE
    
    actor_id = fields.Url(required=True, metadata={"example": "https://piefed.social"})
    all_languages = fields.List(fields.Nested(LanguageView))
    description = fields.String()
    enable_downvotes = fields.Boolean()
    icon = fields.Url(allow_none=True)
    name = fields.String(required=True)
    registration_mode = fields.String(validate=validate.OneOf(reg_mode_list))
    sidebar = fields.String()
    user_count = fields.Integer()


class Community(Schema):
    class Meta:
        unknown = EXCLUDE
    
    actor_id = fields.Url(required=True, metadata={"example": "https://piefed.social/c/piefed_meta"})
    ap_domain = fields.String(metadata={"example": "piefed.social"})
    banned = fields.Boolean()
    banner = fields.Url(allow_none=True)
    deleted = fields.Boolean(required=True)
    description = fields.String()
    hidden = fields.Boolean(required=True)
    icon = fields.Url(allow_none=True)
    id = fields.Integer(required=True)
    instance_id = fields.Integer(required=True)
    local = fields.Boolean(required=True)
    name = fields.String(required=True)
    nsfw = fields.Boolean(required=True)
    posting_warning = fields.String()
    published = fields.String(required=True, validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z"})
    removed = fields.Boolean(required=True)
    restricted_to_mods = fields.Boolean(required=True)
    title = fields.String(required=True)
    updated = fields.String(validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z"})


class CommunityBlockView(Schema):
    class Meta:
        unknown = EXCLUDE
    
    community = fields.Nested(Community)
    person = fields.Nested(Person)


class CommunityFollowerView(Schema):
    class Meta:
        unknown = EXCLUDE
    
    community = fields.Nested(Community, required=True)
    follower = fields.Nested(Person, required=True)


class Instance(Schema):
    class Meta:
        unknown = EXCLUDE
    
    domain = fields.String(required=True, metadata={"example": "piefed.social"})
    id = fields.Integer(required=True)
    published = fields.String(required=True, validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z"})
    software = fields.String()
    updated = fields.String(validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z"})
    version = fields.String()


class InstanceBlockView(Schema):
    class Meta:
        unknown = EXCLUDE
    
    instance = fields.Nested(Instance, required=True)
    person = fields.Nested(Person, required=True)
    site = fields.Nested(Site, required=True)


class LocalUser(Schema):
    default_comment_sort_type = fields.String(required=True, validate=validate.OneOf(comment_sort_list))
    default_listing_type = fields.String(required=True, validate=validate.OneOf(listing_type_list))
    default_sort_type = fields.String(required=True, validate=validate.OneOf(sort_list))
    show_bot_accounts = fields.Boolean(required=True)
    show_nsfl = fields.Boolean(required=True)
    show_nsfw = fields.Boolean(required=True)
    show_read_posts = fields.Boolean(required=True)
    show_scores = fields.Boolean(required=True)


class LocalUserView(Schema):
    class Meta:
        unknown = EXCLUDE
    
    counts = fields.Nested(PersonAggregates, required=True)
    local_user = fields.Nested(LocalUser, required=True)
    person = fields.Nested(Person, required=True)


class CommunityModeratorView(Schema):
    class Meta:
        unknown = EXCLUDE
    
    community = fields.Nested(Community, required=True)
    moderator = fields.Nested(Person, required=True)


class PersonBlockView(Schema):
    class Meta:
        unknown = EXCLUDE
    
    person = fields.Nested(Person, required=True)
    target = fields.Nested(Person, required=True)


class MyUserInfo(Schema):
    class Meta:
        unknown = EXCLUDE
    
    community_blocks = fields.List(fields.Nested(CommunityBlockView), required=True)
    discussion_languages = fields.List(fields.Nested(LanguageView), required=True)
    follows = fields.List(fields.Nested(CommunityFollowerView), required=True)
    instance_blocks = fields.List(fields.Nested(InstanceBlockView), required=True)
    local_user_view = fields.Nested(LocalUserView, required=True)
    moderates = fields.List(fields.Nested(CommunityModeratorView), required=True)
    person_blocks = fields.List(fields.Nested(PersonBlockView), required=True)


class GetSiteResponse(Schema):
    class Meta:
        unknown = EXCLUDE
    
    admins = fields.List(fields.Nested(PersonView), required=True)
    my_user = fields.Nested(MyUserInfo)
    site = fields.Nested(Site, required=True)
    version = fields.String(required=True, metadata={"title": "Software version"})