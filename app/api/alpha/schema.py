from enum import Enum
from marshmallow import Schema, fields, EXCLUDE


# Enums used in other schema
reg_enum = Enum("RegistrationEnum", [("Closed", "Closed"),
                                     ("RequireApplication", "RequireApplication"),
                                     ("Open", "Open")])

sort_enum = Enum("SortEnum", [("Active", "Active"),
                              ("Hot", "Hot"),
                              ("New", "New"),
                              ("TopHour", "TopHour"),
                              ("TopSixHour", "TopSixHour"),
                              ("TopTwelveHour", "TopTwelveHour"),
                              ("TopDay", "TopDay"),
                              ("TopWeek", "TopWeek"),
                              ("TopMonth", "TopMonth"),
                              ("TopThreeMonths", "TopThreeMonths"),
                              ("TopSixMonths", "TopSixMonths"),
                              ("TopNineMonths", "TopNineMonths"),
                              ("TopYear", "TopYear"),
                              ("TopAll", "TopAll"),
                              ("Scaled", "Scaled")])

comment_sort_enum = Enum("CommentEnum", [("Hot", "Hot"), ("Top", "Top"), ("New", "New"), ("Old", "Old")])

listing_type_enum = Enum("ListingEnum", [("All", "All"),
                                         ("Local", "Local"),
                                         ("Subscribed", "Subscribed"),
                                         ("Popular", "Popular"),
                                         ("Moderating", "Moderating")])


class DefaultError(Schema):
    message = fields.String()

class Person(Schema):
    class Meta:
        unknown = EXCLUDE
    
    about = fields.String()
    actor_id = fields.Url(required=True)
    avatar = fields.Url()
    banned = fields.Boolean(required=True)
    banner = fields.Url()
    bot = fields.Boolean(required=True)
    deleted = fields.Boolean(required=True)
    flair = fields.String()
    id = fields.Integer(required=True)
    instance_id = fields.Integer(required=True)
    local = fields.Boolean(required=True)
    published = fields.String()
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
    
    code = fields.String()
    id = fields.Integer()
    name = fields.String()


class Site(Schema):
    class Meta:
        unknown = EXCLUDE
    
    actor_id = fields.Url(required=True)
    all_languages = fields.List(fields.Nested(LanguageView))
    description = fields.String()
    enable_downvotes = fields.Boolean()
    icon = fields.Url()
    name = fields.String(required=True)
    registration_mode = fields.Enum(reg_enum)
    # registration_mode = fields.String()
    sidebar = fields.String()
    user_count = fields.String()


class Community(Schema):
    class Meta:
        unknown = EXCLUDE
    
    actor_id = fields.Url(required=True)
    ap_domain = fields.String()
    banned = fields.Boolean()
    banner = fields.Url()
    deleted = fields.Boolean(required=True)
    description = fields.String()
    hidden = fields.Boolean(required=True)
    icon = fields.Url()
    id = fields.Integer(required=True)
    instance_id = fields.Integer(required=True)
    local = fields.Boolean(required=True)
    name = fields.String(required=True)
    nsfw = fields.Boolean(required=True)
    posting_warning = fields.String()
    published = fields.String(required=True)
    removed = fields.Boolean(required=True)
    restricted_to_mods = fields.Boolean(required=True)
    title = fields.String(required=True)
    updated = fields.String()


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
    
    domain = fields.String(required=True)
    id = fields.Integer(required=True)
    published = fields.String(required=True)
    software = fields.String()
    updated = fields.String()
    version = fields.String()


class InstanceBlockView(Schema):
    class Meta:
        unknown = EXCLUDE
    
    instance = fields.Nested(Instance, required=True)
    person = fields.Nested(Person, required=True)
    site = fields.Nested(Site, required=True)


class LocalUser(Schema):
    default_comment_sort_type = fields.Enum(comment_sort_enum, required=True)
    default_listing_type = fields.Enum(listing_type_enum, required=True)
    default_sort_type = fields.Enum(sort_enum, required=True)
    show_bot_accounts = fields.Boolean(required=True)
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
