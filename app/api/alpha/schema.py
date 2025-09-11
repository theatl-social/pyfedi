import re

from datetime import datetime
from marshmallow import Schema, fields, validate, ValidationError, EXCLUDE, validates_schema


# Lists used in schema for validation
reg_mode_list = ["Closed", "RequireApplication", "Open"]
sort_list = ["Active", "Hot", "New", "TopHour", "TopSixHour", "TopTwelveHour", "TopDay", "TopWeek", "TopMonth",
             "TopThreeMonths", "TopSixMonths", "TopNineMonths", "TopYear", "TopAll", "Scaled"]
default_sorts_list = ["Hot", "Top", "New", "Active", "Old", "Scaled"]
default_comment_sorts_list = ["Hot", "Top", "New", "Old"]
comment_sort_list = ["Hot", "Top", "New", "Old"]
community_sort_list = ["Hot", "Top", "New"]
listing_type_list = ["All", "Local", "Subscribed", "Popular", "Moderating"]
community_listing_type_list = ["All", "Local", "Subscribed"]
content_type_list = ["Communities", "Posts", "Users", "Url"]
subscribed_type_list = ["Subscribed", "NotSubscribed", "Pending"]
notification_status_list = ["All", "Unread", "Read"]


def validate_datetime_string(text):
    try:
        # Ensures that string matches timestamp format used by lemmy/piefed api
        datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ")
        return True
    except ValueError:
        raise ValidationError(f"Bad datetime string: {text}")


def validate_color_code(text):
    try:
        # Ensures that hex color code strings have the correct format
        color_pattern = re.compile(r'^#([a-fA-F0-9]{6}|[a-fA-F0-9]{3})$')
        return bool(re.match(color_pattern, text))
    except:
        raise ValidationError(f"Bad hex color code string: {text}")


class DefaultError(Schema):
    message = fields.String()


class DefaultSchema(Schema):
    class Meta:
        unknown = EXCLUDE
        datetimeformat = "%Y-%m-%dT%H:%M:%S.%fZ"


class Person(DefaultSchema):
    actor_id = fields.Url(required=True, metadata={"example": "https://piefed.social/u/rimu"})
    banned = fields.Boolean(required=True)
    bot = fields.Boolean(required=True)
    deleted = fields.Boolean(required=True)
    id = fields.Integer(required=True)
    instance_id = fields.Integer(required=True)
    local = fields.Boolean(required=True)
    user_name = fields.String(required=True)
    about = fields.String(metadata={"format": "markdown"})
    about_html = fields.String(metadata={"format": "html"})
    avatar = fields.Url(allow_none=True)
    banner = fields.Url(allow_none=True)
    flair = fields.String()
    published = fields.String(validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})
    title = fields.String(allow_none=True)


class PersonAggregates(DefaultSchema):
    comment_count = fields.Integer(required=True)
    person_id = fields.Integer(required=True)
    post_count = fields.Integer(required=True)


class PersonView(DefaultSchema):
    activity_alert = fields.Boolean(required=True)
    counts = fields.Nested(PersonAggregates, required=True)
    is_admin = fields.Boolean(required=True)
    person = fields.Nested(Person, required=True)


class LanguageView(DefaultSchema):
    code = fields.String(metadata={"example": "en"})
    id = fields.Integer(metadata={"example": "2"})
    name = fields.String(metadata={"example": "English"})


class Site(DefaultSchema):
    actor_id = fields.Url(required=True, metadata={"example": "https://piefed.social"})
    name = fields.String(required=True)
    all_languages = fields.List(fields.Nested(LanguageView))
    description = fields.String()
    enable_downvotes = fields.Boolean()
    icon = fields.Url(allow_none=True)
    registration_mode = fields.String(validate=validate.OneOf(reg_mode_list))
    sidebar = fields.String(metadata={"format": "html"})
    sidebar_md = fields.String(metadata={"format": "markdown"})
    user_count = fields.Integer()


class Community(DefaultSchema):
    actor_id = fields.Url(required=True, metadata={"example": "https://piefed.social/c/piefed_meta"})
    ap_domain = fields.String(metadata={"example": "piefed.social"})
    deleted = fields.Boolean(required=True)
    hidden = fields.Boolean(required=True)
    id = fields.Integer(required=True)
    instance_id = fields.Integer(required=True)
    local = fields.Boolean(required=True)
    name = fields.String(required=True)
    nsfw = fields.Boolean(required=True)
    published = fields.String(required=True, validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})
    removed = fields.Boolean(required=True)
    restricted_to_mods = fields.Boolean(required=True)
    title = fields.String(required=True)
    banned = fields.Boolean()
    banner = fields.Url(allow_none=True)
    description = fields.String(metadata={"format": "markdown"})
    icon = fields.Url(allow_none=True)
    posting_warning = fields.String(allow_none=True)
    updated = fields.String(validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})


class CommunityBlockView(DefaultSchema):
    community = fields.Nested(Community)
    person = fields.Nested(Person)


class CommunityFollowerView(DefaultSchema):
    community = fields.Nested(Community, required=True)
    follower = fields.Nested(Person, required=True)


class Instance(DefaultSchema):
    domain = fields.String(required=True, metadata={"example": "piefed.social"})
    id = fields.Integer(required=True)
    published = fields.String(required=True, validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})
    software = fields.String()
    updated = fields.String(validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})
    version = fields.String()


class InstanceBlockView(DefaultSchema):
    instance = fields.Nested(Instance, required=True)
    person = fields.Nested(Person, required=True)


class LocalUser(DefaultSchema):
    default_comment_sort_type = fields.String(required=True, validate=validate.OneOf(comment_sort_list))
    default_listing_type = fields.String(required=True, validate=validate.OneOf(listing_type_list))
    default_sort_type = fields.String(required=True, validate=validate.OneOf(sort_list))
    show_bot_accounts = fields.Boolean(required=True)
    show_nsfl = fields.Boolean(required=True)
    show_nsfw = fields.Boolean(required=True)
    show_read_posts = fields.Boolean(required=True)
    show_scores = fields.Boolean(required=True)


class LocalUserView(DefaultSchema):
    counts = fields.Nested(PersonAggregates, required=True)
    local_user = fields.Nested(LocalUser, required=True)
    person = fields.Nested(Person, required=True)


class CommunityModeratorView(DefaultSchema):
    community = fields.Nested(Community, required=True)
    moderator = fields.Nested(Person, required=True)


class PersonBlockView(DefaultSchema):
    person = fields.Nested(Person, required=True)
    target = fields.Nested(Person, required=True)


class MyUserInfo(DefaultSchema):
    community_blocks = fields.List(fields.Nested(CommunityBlockView), required=True)
    discussion_languages = fields.List(fields.Nested(LanguageView), required=True)
    follows = fields.List(fields.Nested(CommunityFollowerView), required=True)
    instance_blocks = fields.List(fields.Nested(InstanceBlockView), required=True)
    local_user_view = fields.Nested(LocalUserView, required=True)
    moderates = fields.List(fields.Nested(CommunityModeratorView), required=True)
    person_blocks = fields.List(fields.Nested(PersonBlockView), required=True)


class GetSiteResponse(DefaultSchema):
    admins = fields.List(fields.Nested(PersonView), required=True)
    site = fields.Nested(Site, required=True)
    version = fields.String(required=True, metadata={"title": "Software version"})
    my_user = fields.Nested(MyUserInfo)


class GetSiteVersionResponse(DefaultSchema):
    version = fields.String(required=True)


class GetSiteInstanceChooserResponse(DefaultSchema):
    language = fields.Nested(LanguageView, required=True)
    nsfw = fields.Boolean(required=True)
    newbie_friendly = fields.Boolean(required=True)
    name = fields.String(required=True)
    elevator_pitch = fields.String(required=True)
    description = fields.String(required=True)
    about = fields.String(required=True)
    sidebar = fields.String(required=True)
    logo_url = fields.String(required=True)
    maturity = fields.String(required=True)
    tos_url = fields.String(required=True)
    mau = fields.Integer(required=True)
    can_make_communities = fields.Boolean(required=True)
    defederation = fields.List(fields.String(), required=True)
    trusts = fields.List(fields.String(), required=True)
    registration_mode = fields.String(required=True)


class GetSiteInstanceChooserSearchResponseItem(DefaultSchema):
    id = fields.Integer(required=True)
    name = fields.String(required=True)
    domain = fields.String(required=True)
    elevator_pitch = fields.String(required=True)
    description = fields.String(required=True)
    about = fields.String(required=True)
    sidebar = fields.String(required=True)
    logo_url = fields.String(required=True)
    maturity = fields.String(required=True)
    tos_url = fields.String(required=True)
    uptime = fields.String(required=True)
    mau = fields.Integer(required=True)
    can_make_communities = fields.Boolean(required=True)
    newbie_friendly = fields.Boolean(required=True)
    defederation = fields.List(fields.String(), required=True)
    trusts = fields.List(fields.String(), required=True)
    registration_mode = fields.String(required=True)
    language = fields.String(required=True)
    monthsmonitored = fields.Integer(required=True)



class GetSiteInstanceChooserSearchResponse(DefaultSchema):
    result = fields.List(fields.Nested(GetSiteInstanceChooserSearchResponseItem), required=True)


class BlockInstanceRequest(DefaultSchema):
    block = fields.Boolean(required=True)
    instance_id = fields.Integer(required=True)


class BlockInstanceResponse(DefaultSchema):
    blocked = fields.Boolean(required=True)


class SearchRequest(DefaultSchema):
    q = fields.String(required=True)
    type_ = fields.String(required=True, validate=validate.OneOf(content_type_list))
    limit = fields.Integer()
    listing_type = fields.String(validate=validate.OneOf(listing_type_list))
    page = fields.Integer()
    sort = fields.String(validate=validate.OneOf(sort_list))
    community_name = fields.String()
    community_id = fields.Integer()


class SearchInstanceChooser(DefaultSchema):
    q = fields.String()
    nsfw = fields.String()
    language = fields.String()
    newbie = fields.String()


class Post(DefaultSchema):
    ap_id = fields.Url(required=True)
    community_id = fields.Integer(required=True)
    deleted = fields.Boolean(required=True)
    id = fields.Integer(required=True)
    language_id = fields.Integer(required=True)
    local = fields.Boolean(required=True)
    locked = fields.Boolean(required=True)
    nsfw = fields.Boolean(required=True)
    published = fields.String(required=True, validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})
    removed = fields.Boolean(required=True)
    sticky = fields.Boolean(required=True)
    title = fields.String(required=True)
    user_id = fields.Integer(required=True)
    alt_text = fields.String()
    body = fields.String(metadata={"format": "markdown"})
    small_thumbnail_url = fields.Url()
    thumbnail_url = fields.Url()
    updated = fields.String(validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})
    url = fields.Url()


class PostAggregates(DefaultSchema):
    comments = fields.Integer(required=True)
    downvotes = fields.Integer(required=True)
    newest_comment_time = fields.String(required=True, validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})
    post_id = fields.Integer(required=True)
    published = fields.String(required=True, validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})
    score = fields.Integer(required=True)
    upvotes = fields.Integer(required=True)


class CommunityFlair(DefaultSchema):
    id = fields.Integer(required=True)
    community_id = fields.Integer(required=True)
    flair_title = fields.String(required=True)
    text_color = fields.String(required=True, validate=validate_color_code,
                               metadata={"example": "#000000", "description": "Hex color code for the text of the flair"})
    background_color = fields.String(required=True, validate=validate_color_code,
                                     metadata={"example": "#DEDDDA", "description": "Hex color code for the background of the flair"})
    blur_images = fields.Boolean(required=True)
    ap_id = fields.Url(required=True, allow_none=True,
                       metadata={"description": "Legacy tags that existed prior to 1.2 and some tags for remote communities might not have a defined ap_id"})


class PostView(DefaultSchema):
    banned_from_community = fields.Boolean(required=True)
    community = fields.Nested(Community, required=True)
    counts = fields.Nested(PostAggregates, required=True)
    creator = fields.Nested(Person, required=True)
    creator_banned_from_community = fields.Boolean(required=True)
    creator_is_admin = fields.Boolean(required=True)
    creator_is_moderator = fields.Boolean(required=True)
    hidden = fields.Boolean(required=True)
    post = fields.Nested(Post, required=True)
    read = fields.Boolean(required=True)
    saved = fields.Boolean(required=True)
    subscribed = fields.String(required=True, validate=validate.OneOf(subscribed_type_list))
    unread_comments = fields.Integer(required=True)
    activity_alert = fields.Boolean()
    my_vote = fields.Integer()
    flair = fields.List(fields.Nested(CommunityFlair))


class CommunityAggregates(DefaultSchema):
    id = fields.Integer(required=True)
    post_count = fields.Integer(required=True)
    post_reply_count = fields.Integer(required=True)
    published = fields.String(required=True)
    subscriptions_count = fields.Integer(required=True)
    total_subscriptions_count = fields.Integer(required=True)
    active_daily = fields.Integer()
    active_weekly = fields.Integer()
    active_monthly = fields.Integer()
    active_6monthly = fields.Integer()


class CommunityView(DefaultSchema):
    activity_alert = fields.Boolean(required=True)
    blocked = fields.Boolean(required=True)
    community = fields.Nested(Community, required=True)
    counts = fields.Nested(CommunityAggregates, required=True)
    subscribed = fields.String(required=True, validate=validate.OneOf(subscribed_type_list))
    flair_list = fields.List(fields.Nested(CommunityFlair))


class CommunityFlairCreateRequest(DefaultSchema):
    community_id = fields.Integer(required=True)
    flair_title = fields.String(required=True)
    text_color = fields.String(
        validate=validate_color_code,
        metadata={
            "example": "#000 or #000000",
            "default": "#000000",
            "description": "Hex color code for the text of the flair."})
    background_color = fields.String(
        validate=validate_color_code,
        metadata={
            "example": "#fff or #FFFFFF",
            "default": "#DEDDDA",
            "description": "Hex color code for the background of the flair."})
    blur_images = fields.Boolean(metadata={"default": False})


class CommunityFlairCreateResponse(CommunityFlair):
    pass


class CommunityFlairEditRequest(DefaultSchema):
    flair_id = fields.Integer(required=True)
    flair_title = fields.String()
    text_color = fields.String(
        validate=validate_color_code,
        metadata={
            "example": "#000 or #000000",
            "description": "Hex color code for the text of the flair."})
    background_color = fields.String(
        validate=validate_color_code,
        metadata={
            "example": "#fff or #FFFFFF",
            "description": "Hex color code for the background of the flair."})
    blur_images = fields.Boolean()


class CommunityFlairEditResponse(CommunityFlair):
    pass


class Comment(DefaultSchema):
    ap_id = fields.Url(required=True)
    body = fields.String(required=True, metadata={"format": "markdown"})
    deleted = fields.Boolean(required=True)
    id = fields.Integer(required=True)
    language_id = fields.Integer(required=True)
    local = fields.Boolean(required=True)
    path = fields.String(required=True)
    post_id = fields.Integer(required=True)
    published = fields.String(required=True, validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})
    removed = fields.Boolean(required=True)
    user_id = fields.Integer(required=True)
    distinguished = fields.Boolean()
    updated = fields.String(validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})
    locked = fields.Boolean()


class CommentReport(DefaultSchema):
    id = fields.Integer(required=True)
    creator_id = fields.Integer(required=True)
    comment_id = fields.Integer(required=True)
    original_comment_text = fields.String()
    reason = fields.String()
    resolved = fields.Boolean(required=True)
    # TODO: resolver_id = fields.Integer(required=True)
    published = fields.String(required=True, validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})
    updated = fields.String(validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})


class CommentAggregates(DefaultSchema):
    child_count = fields.Integer(required=True)
    comment_id = fields.Integer(required=True)
    downvotes = fields.Integer(required=True)
    published = fields.String(required=True, validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})
    score = fields.Integer(required=True)
    upvotes = fields.Integer(required=True)


class CommentView(DefaultSchema):
    activity_alert = fields.Boolean(required=True)
    banned_from_community = fields.Boolean(required=True)
    comment = fields.Nested(Comment, required=True)
    community = fields.Nested(Community, required=True)
    counts = fields.Nested(CommentAggregates, required=True)
    creator = fields.Nested(Person, required=True)
    creator_banned_from_community = fields.Boolean(required=True)
    creator_blocked = fields.Boolean(required=True)
    creator_is_admin = fields.Boolean(required=True)
    creator_is_moderator = fields.Boolean(required=True) 
    post = fields.Nested(Post, required=True)
    saved = fields.Boolean(required=True)
    subscribed = fields.String(required=True)
    my_vote = fields.Integer()
    can_auth_user_moderate = fields.Boolean()


class CommentReportView(CommentView):
    comment_report = fields.Nested(CommentReport, required=True)
    comment_creator = fields.Nested(Person, required=True)
    # TODO: resolver = fields.Nested(Person, required=True)


class SearchResponse(DefaultSchema):
    type_ = fields.String(required=True, validate=validate.OneOf(content_type_list))
    communities = fields.List(fields.Nested(CommunityView), required=True)
    posts = fields.List(fields.Nested(PostView), required=True)
    users = fields.List(fields.Nested(PersonView), required=True)
    comments = fields.List(fields.Nested(CommentView), required=True)


class ResolveObjectRequest(DefaultSchema):
    q = fields.String(required=True)


class ResolveObjectResponse(DefaultSchema):
    comment = fields.Nested(CommentView)
    post = fields.Nested(PostView)
    community = fields.Nested(CommunityView)
    person = fields.Nested(PersonView)


class InstanceWithoutFederationState(DefaultSchema):
    domain = fields.String(required=True)
    id = fields.Integer(required=True)
    published = fields.String(required=True, validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})
    software = fields.String()
    updated = fields.String(validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})
    version = fields.String()


class FederatedInstancesView(DefaultSchema):
    allowed = fields.List(fields.Nested(InstanceWithoutFederationState), required=True)
    blocked = fields.List(fields.Nested(InstanceWithoutFederationState), required=True)
    linked = fields.List(fields.Nested(InstanceWithoutFederationState), required=True)


class GetFederatedInstancesResponse(DefaultSchema):
    federated_instances = fields.Nested(FederatedInstancesView)


class GetCommunityRequest(DefaultSchema):
    id = fields.Integer()
    name = fields.String()


class GetCommunityResponse(DefaultSchema):
    community_view = fields.Nested(CommunityView, required=True)
    discussion_languages = fields.List(fields.Integer(), required=True)
    moderators = fields.List(fields.Nested(CommunityModeratorView), required=True)
    site = fields.Nested(Site)


class CommunityFlairDeleteRequest(DefaultSchema):
    flair_id = fields.Integer(required=True)


class CommunityFlairDeleteResponse(GetCommunityResponse):
    pass


class CreateCommunityRequest(DefaultSchema):
    name = fields.String(required=True)
    title = fields.String(required=True)
    banner_url = fields.Url(allow_none=True)
    description = fields.String(metadata={"format": "markdown"})
    discussion_languages = fields.List(fields.Integer())
    icon_url = fields.Url(allow_none=True)
    local_only = fields.Boolean()
    nsfw = fields.Boolean()
    restricted_to_mods = fields.Boolean()
    rules = fields.String()


class CommunityResponse(DefaultSchema):
    community_view = fields.Nested(CommunityView, required=True)
    discussion_languages = fields.List(fields.Integer(), required=True)


class EditCommunityRequest(DefaultSchema):
    community_id = fields.Integer(required=True)
    title = fields.String(required=True)
    banner_url = fields.Url(allow_none=True)
    description = fields.String(metadata={"format": "markdown"})
    discussion_languages = fields.List(fields.Integer())
    icon_url = fields.Url(allow_none=True)
    local_only = fields.Boolean()
    nsfw = fields.Boolean()
    restricted_to_mods = fields.Boolean()
    rules = fields.String()


class DeleteCommunityRequest(DefaultSchema):
    community_id = fields.Integer(required=True)
    deleted = fields.Boolean(required=True)


class ListCommunitiesRequest(DefaultSchema):
    limit = fields.Integer()
    page = fields.Integer()
    show_nsfw = fields.Boolean()
    sort = fields.String(validate=validate.OneOf(community_sort_list))
    type_ = fields.String(validate=validate.OneOf(community_listing_type_list))


class ListCommunitiesResponse(DefaultSchema):
    communities = fields.List(fields.Nested(CommunityView), required=True)
    next_page = fields.String(allow_none=True)


class FollowCommunityRequest(DefaultSchema):
    community_id = fields.Integer(required=True)
    follow = fields.Boolean(required=True)


class BlockCommunityRequest(DefaultSchema):
    block = fields.Boolean(required=True)
    community_id = fields.Integer(required=True)


class BlockCommunityResponse(DefaultSchema):
    community_view = fields.Nested(CommunityView, required=True)
    blocked = fields.Boolean(required=True)


class ModCommunityRequest(DefaultSchema):
    added = fields.Boolean(required=True)
    community_id = fields.Integer(required=True)
    person_id = fields.Integer(required=True)


class ModCommunityResponse(DefaultSchema):
    moderators = fields.List(fields.Nested(CommunityModeratorView), required=True)


class SubscribeCommunityRequest(DefaultSchema):
    community_id = fields.Integer(required=True)
    subscribe = fields.Boolean(required=True)


class CommunityModerationBansListRequest(DefaultSchema):
    community_id = fields.Integer(required=True)
    limit = fields.Integer(metadata={"default": 10})
    page = fields.Integer(metadata={"default": 1})


class CommunityModerationBanItem(DefaultSchema):
    banned_by = fields.Nested(Person)
    banned_user = fields.Nested(Person)
    community = fields.Nested(Community)
    expired = fields.Boolean()
    expired_at = fields.String(allow_none=True, validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z, null=permanent ban", "format": "datetime"})
    expires_at = fields.String(allow_none=True, validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z, null=permanent ban", "format": "datetime"})
    reason = fields.String()


class CommunityModerationBansListResponse(DefaultSchema):
    items = fields.List(fields.Nested(CommunityModerationBanItem))
    next_page = fields.String(allow_none=True)


class CommunityModerationBanRequest(DefaultSchema):
    community_id = fields.Integer(required=True)
    reason = fields.String(required=True)
    user_id = fields.Integer(required=True)
    expires_at = fields.String(validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})
    permanent = fields.Boolean()


class CommunityModerationUnbanRequest(DefaultSchema):
    community_id = fields.Integer(required=True)
    user_id = fields.Integer(required=True)


class CommunityModerationNsfwRequest(DefaultSchema):
    post_id = fields.Integer(required=True)
    nsfw_status = fields.Boolean(required=True)


class FeedView(DefaultSchema):
    actor_id = fields.Url(required=True)
    ap_domain = fields.String(required=True)
    children = fields.List(fields.Nested(lambda: FeedView()), required=True)
    communities = fields.List(fields.Nested(Community), required=True)
    communities_count = fields.Integer(required=True)
    id = fields.Integer(required=True)
    is_instance_feed = fields.Boolean(required=True)
    local = fields.Boolean(required=True)
    name = fields.String(required=True)
    nsfl = fields.Boolean(required=True)
    nsfw = fields.Boolean(required=True)
    owner = fields.Boolean(required=True, metadata={"description": "Is the authorized user the creator of the feed?"})
    public = fields.Boolean(required=True)
    published = fields.String(required=True, validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})
    show_posts_from_children = fields.Boolean(required=True)
    subscribed = fields.Boolean(required=True)
    subscriptions_count = fields.Integer(required=True)
    title = fields.String(required=True)
    updated = fields.String(required=True, validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})
    user_id = fields.Integer(required=True, metadata={"description": "user_id of the feed creator/owner"}) 
    banner = fields.Url(allow_none=True)
    description = fields.String(allow_none=True, metadata={"format": "markdown"})
    description_html = fields.String(allow_none=True, metadata={"format": "html"})
    icon = fields.Url(allow_none=True)
    parent_feed_id = fields.Integer(allow_none=True)


class FeedListRequest(DefaultSchema):
    include_communities = fields.Boolean(metadata={"description": "include list of communities in each feed with result", "default": True})
    mine_only = fields.Boolean(metadata={"description": "only return feeds created by the authorized user", "default": False})


class FeedListResponse(DefaultSchema):
    feeds = fields.List(fields.Nested(FeedView), required=True)


class TopicView(DefaultSchema):
    children = fields.List(fields.Nested(lambda: TopicView()), required=True)
    communities = fields.List(fields.Nested(Community), required=True)
    communities_count = fields.Integer(required=True)
    id = fields.Integer(required=True)
    name = fields.String(required=True)
    show_posts_from_children = fields.Boolean(required=True)
    title = fields.String(required=True)
    parent_topic_id = fields.Integer(allow_none=True)


class TopicListRequest(DefaultSchema):
    include_communities = fields.Boolean(metadata={"description": "include list of communities in each topic with result", "default": True})


class TopicListResponse(DefaultSchema):
    topics = fields.List(fields.Nested(TopicView), required=True)


class GetUserRequest(DefaultSchema):
    person_id = fields.Integer(metadata={"description": "One of either person_id or username must be specified"})
    username = fields.String(metadata={"description": "One of either person_id or username must be specified"})
    sort = fields.String(validate=validate.OneOf(sort_list))
    page = fields.Integer(metadata={"default": 1})
    limit = fields.Integer(metadata={"default": 20})  # Previous defaults were 50 for posts, 10 for comments
    community_id = fields.Integer(metadata={"description": "Limit posts/comments to just a single community"})
    saved_only = fields.Boolean(metadata={"default": False})
    include_content = fields.Boolean(metadata={"default": False})

    @validates_schema
    def validate_input(self, data, **kwargs):
        if "person_id" not in data and "username" not in data:
            raise ValidationError("One of either person_id or username must be specified")


class GetUserResponse(DefaultSchema):
    comments = fields.List(fields.Nested(CommentView), required=True)
    moderates = fields.List(fields.Nested(CommunityModeratorView), required=True)
    person_view = fields.Nested(PersonView, required=True)
    posts = fields.List(fields.Nested(PostView), required=True)
    site = fields.Nested(Site)


class UserLoginRequest(DefaultSchema):
    username = fields.String(required=True)
    password = fields.String(required=True)


class UserLoginResponse(DefaultSchema):
    jwt = fields.String(required=True)


class UserUnreadCountsResponse(DefaultSchema):
    mentions = fields.Integer(required=True, metadata={"description": "Post and comment mentions"})
    private_messages = fields.Integer(required=True)
    replies = fields.Integer(required=True, metadata={"description": "Replies to posts and comments"})
    other = fields.Integer(required=True, metadata={"description": "Any other type of notification (reports, activity alerts, etc.)"})


class UserRepliesRequest(DefaultSchema):
    limit = fields.Integer(metadata={"default": 10})
    page = fields.Integer(metadata={"default": 1})
    sort = fields.String(validate=validate.OneOf(comment_sort_list), metadata={"default": "New"})
    unread_only = fields.Boolean(metadata={"default": True})


class CommentReply(DefaultSchema):
    id = fields.Integer(required=True)  # redundant with comment_id
    comment_id = fields.Integer(required=True)  # redundant with id
    published = fields.String(required=True, validate=validate_datetime_string, metadata={"example": "2025-06-07T02:29:07.980084Z", "format": "datetime"})
    read = fields.Boolean(required=True)
    recipient_id = fields.Integer(required=True)


class CommentReplyView(DefaultSchema):
    activity_alert = fields.Boolean(required=True)
    comment = fields.Nested(Comment, required=True)
    comment_reply = fields.Nested(CommentReply, required=True)
    community = fields.Nested(Community, required=True)
    counts = fields.Nested(CommentAggregates, required=True)
    creator = fields.Nested(Person, required=True)
    creator_banned_from_community = fields.Boolean(required=True)
    creator_blocked = fields.Boolean(required=True)
    creator_is_admin = fields.Boolean(required=True)
    creator_is_moderator = fields.Boolean(required=True)
    my_vote = fields.Integer(required=True)
    post = fields.Nested(Post, required=True)
    recipient = fields.Nested(Person, required=True)
    saved = fields.Boolean(required=True)
    subscribed = fields.String(required=True, validate=validate.OneOf(subscribed_type_list))


class UserRepliesResponse(DefaultSchema):
    next_page = fields.Integer(required=True, allow_none=True)
    replies = fields.List(fields.Nested(CommentReplyView), required=True)


class UserMentionsRequest(DefaultSchema):
    limit = fields.Integer(metadata={"default": 10})
    page = fields.Integer(metadata={"default": 1})
    sort = fields.String(validate=validate.OneOf(comment_sort_list), metadata={"default": "New"})
    unread_only = fields.Boolean(metadata={"default": True})


class UserMentionsResponse(DefaultSchema):
    next_page = fields.Integer(required=True, allow_none=True)
    replies = fields.List(fields.Nested(CommentReplyView), required=True)


class UserBlockRequest(DefaultSchema):
    block = fields.Boolean(required=True)
    person_id = fields.Integer(required=True)


class UserBlockResponse(DefaultSchema):
    blocked = fields.Boolean(required=True)
    person_view = fields.Nested(PersonView, required=True)


class UserMarkAllReadResponse(DefaultSchema):
    replies = fields.List(fields.Nested(CommentReplyView), required=True, metadata={"description": "Should be empty list"})


class UserSubscribeRequest(DefaultSchema):
    person_id = fields.Integer(required=True)
    subscribe = fields.Boolean(required=True)


class UserSubscribeResponse(DefaultSchema):
    person_view = fields.Nested(PersonView, required=True)
    subscribed = fields.Boolean(required=True)  # Added field


class UserSetFlairRequest(DefaultSchema):
    community_id = fields.Integer(required=True)
    flair_text = fields.String(allow_none=True, metadata={"description": "Either omit or set to null to remove existing flair"})


class UserSetFlairResponse(DefaultSchema):
    person_view = fields.Nested(PersonView)


class UserSaveSettingsRequest(DefaultSchema):
    avatar = fields.String(allow_none=True, metadata={"format": "url", "description": "Pass a null value to remove the image"})
    bio = fields.String(metadata={"format": "markdown"})
    cover = fields.String(allow_none=True, metadata={"format": "url", "description": "Pass a null value to remove the image"})
    default_comment_sort_type = fields.String(validate=validate.OneOf(default_comment_sorts_list))
    default_sort_type = fields.String(validate=validate.OneOf(default_sorts_list))
    show_nsfw = fields.Boolean()
    show_nsfl = fields.Boolean()
    show_read_posts = fields.Boolean()


class UserSaveSettingsResponse(DefaultSchema):
    my_user = fields.Nested(MyUserInfo)


class UserNotificationsRequest(DefaultSchema):
    status = fields.String(required=True, validate=validate.OneOf(notification_status_list))
    limit = fields.Integer(metadata={"default": 10})
    page = fields.Integer(metadata={"default": 1})


class UserNotificationItemView(DefaultSchema):
    author = fields.Nested(Person, required=True, metadata={"description": "returned for all notif types"})
    notif_body = fields.String(required=True, metadata={"description": "returned for all notif types"})
    notif_id = fields.Integer(required=True, metadata={"description": "returned for all notif types"})
    notif_subtype = fields.String(required=True, metadata={"description": "returned for all notif types"})
    notif_type = fields.Integer(required=True, metadata={"description": "returned for all notif types"})
    status = fields.String(validate=validate.OneOf(["Unread", "Read"]), required=True, metadata={"description": "returned for all notif types"})
    comment = fields.Nested(Comment, metadata={"description": "returned for notif_types: 3, 4, 6 (comment_mention subtype)"})
    comment_id = fields.Integer(metadata={"description": "returned for notif_types: 3, 4, 6 (comment_mention subtype)"})
    community = fields.Nested(Community, metadata={"description": "returned for notif_type 1"})
    post = fields.Nested(PostView, metadata={"description": "returned for notif_types: 0, 1, 2, 3, 4, 5, 6 (post_mention subtype)"})
    post_id = fields.Integer(metadata={"description": "returned for notif_types: 0, 1, 2, 3, 4, 5, 6 (post_mention subtype)"})

class UserNotificationsCounts(DefaultSchema):
    unread = fields.Integer(required=True)
    read = fields.Integer(required=True)
    total = fields.Integer(required=True)


class UserNotificationsResponse(DefaultSchema):
    counts = fields.Nested(UserNotificationsCounts, required=True)
    items = fields.List(fields.Nested(UserNotificationItemView), required=True)
    status = fields.String(required=True, validate=validate.OneOf(notification_status_list))
    username = fields.String(required=True)
    next_page = fields.Integer(required=True, allow_none=True)


class UserNotificationStateRequest(DefaultSchema):
    notif_id = fields.Integer(required=True)
    read_state = fields.Boolean(required=True, metadata={"description": "true sets notification as read, false marks it unread"})


class UserNotificationsCountResponse(DefaultSchema):
    count = fields.Integer(required=True)


class UserMarkAllNotifsReadResponse(DefaultSchema):
    mark_all_notifications_as_read = fields.String(required=True, metadata={"example": "complete"})


# Upstream API Schemas - Added from merge
class ListCommentsRequest(DefaultSchema):
    limit = fields.Integer(metadata={"default": 10})
    page = fields.Integer(metadata={"default": 1})
    sort = fields.String(validate=validate.OneOf(comment_sort_list), metadata={"default": "New"})
    liked_only = fields.Boolean()
    saved_only = fields.Boolean()
    person_id = fields.Integer()
    community_id = fields.Integer()
    post_id = fields.Integer()
    parent_id = fields.Integer()
    max_depth = fields.Integer()
    depth_first = fields.Boolean(metadata={"description": "guarantee parent comments are on the same page as any fetched comments"})


class ListCommentsResponse(DefaultSchema):
    comments = fields.List(fields.Nested(CommentView), required=True)
    next_page = fields.String(allow_none=True)


class GetCommentRequest(DefaultSchema):
    id = fields.Integer(required=True)


class GetCommentResponse(DefaultSchema):
    comment_view = fields.Nested(CommentView, required=True)


class LikeCommentRequest(DefaultSchema):
    comment_id = fields.Integer(required=True)
    score = fields.Integer(required=True, metadata={"example": 1, "description": "-1 to downvote, 1 to upvote, 0 to revert previous vote"})
    private = fields.Boolean(metadata={"description": "private votes are not federated to other instances", "default": False})


class SaveCommentRequest(DefaultSchema):
    comment_id = fields.Integer(required=True)
    save = fields.Boolean(required=True)


class SubscribeCommentRequest(DefaultSchema):
    comment_id = fields.Integer(required=True)
    subscribe = fields.Boolean(required=True)


class CreateCommentRequest(DefaultSchema):
    body = fields.String(required=True)
    post_id = fields.Integer(required=True)
    parent_id = fields.Integer()
    language_id = fields.Integer()


class EditCommentRequest(DefaultSchema):
    body = fields.String(required=True)
    comment_id = fields.Integer(required=True)
    language_id = fields.Integer()
    distinguished = fields.Boolean(metadata={"default": False, "description": "Visibly mark reply as from a moderator in the web UI"})


class DeleteCommentRequest(DefaultSchema):
    comment_id = fields.Integer(required=True)
    deleted = fields.Boolean(required=True)


class ReportCommentRequest(DefaultSchema):
    comment_id = fields.Integer(required=True)
    reason = fields.String(required=True)
    description = fields.String()
    report_remote = fields.Boolean(metadata={"default": True, "description": "Also send report to originating instance"})


class GetCommentReportResponse(DefaultSchema):
    comment_report_view = fields.Nested(CommentReportView, required=True)


class RemoveCommentRequest(DefaultSchema):
    comment_id = fields.Integer(required=True)
    removed = fields.Boolean(required=True)
    reason = fields.String()


class MarkCommentAsReadRequest(DefaultSchema):
    comment_reply_id = fields.Integer(required=True)
    read = fields.Boolean(required=True)


class GetCommentReplyResponse(DefaultSchema):
    comment_reply_view = fields.Nested(CommentReplyView, required=True)


class LockCommentRequest(DefaultSchema):
    comment_id = fields.Integer(required=True)
    locked = fields.Boolean(required=True)


class ListCommentLikesRequest(DefaultSchema):
    comment_id = fields.Integer(required=True)
    page = fields.Integer(metadata={"default": 1})
    limit = fields.Integer(metadata={"default": 50})


class CommentLikeView(DefaultSchema):
    score = fields.Integer(required=True)
    creator_banned_from_community = fields.Boolean(required=True)
    creator_banned = fields.Boolean(required=True)
    creator = fields.Nested(Person, required=True)


class ListCommentLikesResponse(DefaultSchema):
    comment_likes = fields.List(fields.Nested(CommentLikeView, required=True))
    next_page = fields.String(allow_none=True)


class ListPostLikesRequest(DefaultSchema):
    post_id = fields.Integer(required=True)
    page = fields.Integer(metadata={"default": 1})
    limit = fields.Integer(metadata={"default": 50})


class PostLikeView(CommentLikeView):
    pass


class ListPostLikesResponse(DefaultSchema):
    post_likes = fields.List(fields.Nested(PostLikeView, required=True))
    next_page = fields.String(allow_none=True)


# Admin API Schemas
class AdminPrivateRegistrationRequest(DefaultSchema):
    username = fields.String(required=True, validate=validate.Length(min=3, max=50), 
                             metadata={"description": "Username (3-50 characters, alphanumeric + underscore)"})
    email = fields.Email(required=True, metadata={"description": "Valid email address"})
    display_name = fields.String(validate=validate.Length(min=1, max=100),
                                metadata={"description": "Display name (1-100 characters)"})
    password = fields.String(validate=validate.Length(min=8, max=128),
                            metadata={"description": "Password (8-128 characters). If omitted, a secure password will be generated"})
    auto_activate = fields.Boolean(metadata={"description": "Skip email verification", "default": True})
    send_welcome_email = fields.Boolean(metadata={"description": "Send welcome email to user", "default": False})
    bio = fields.String(validate=validate.Length(max=5000), 
                       metadata={"description": "User biography (max 5000 characters)"})
    timezone = fields.String(metadata={"description": "User timezone", "default": "UTC"})


class AdminPrivateRegistrationResponse(DefaultSchema):
    success = fields.Boolean(required=True, metadata={"description": "Registration success status"})
    user_id = fields.Integer(required=True, metadata={"description": "Created user ID"})
    username = fields.String(required=True, metadata={"description": "Created username"})
    email = fields.String(required=True, metadata={"description": "User email address"})
    display_name = fields.String(metadata={"description": "User display name"})
    generated_password = fields.String(metadata={"description": "Generated password (only if password was not provided)"})
    activation_required = fields.Boolean(required=True, metadata={"description": "Whether email verification is required"})
    message = fields.String(required=True, metadata={"description": "Success message"})


class AdminPrivateRegistrationError(DefaultSchema):
    success = fields.Boolean(required=True, metadata={"description": "Always false for errors"})
    error = fields.String(required=True, metadata={"description": "Error type", 
                          "enum": ["invalid_secret", "rate_limited", "validation_failed", "user_exists", "feature_disabled", "ip_unauthorized"]})
    message = fields.String(required=True, metadata={"description": "Human readable error message"})
    details = fields.Dict(metadata={"description": "Additional error details including field-specific errors"})


class AdminUserValidationRequest(DefaultSchema):
    username = fields.String(required=True, validate=validate.Length(min=3, max=50))
    email = fields.Email(required=True)


class AdminUserValidationResponse(DefaultSchema):
    username_available = fields.Boolean(required=True)
    email_available = fields.Boolean(required=True)
    username_suggestions = fields.List(fields.String(), metadata={"description": "Alternative username suggestions if taken"})
    validation_errors = fields.Dict(metadata={"description": "Field-specific validation errors"})


class AdminUserListRequest(DefaultSchema):
    local_only = fields.Boolean(metadata={"description": "Filter to local users only", "default": True})
    verified = fields.Boolean(metadata={"description": "Filter by verification status"})
    active = fields.Boolean(metadata={"description": "Filter by active/banned status"})
    search = fields.String(validate=validate.Length(max=100), metadata={"description": "Search username or email"})
    sort = fields.String(validate=validate.OneOf(["created_desc", "created_asc", "username_asc", "username_desc", 
                                                  "last_seen_desc", "last_seen_asc", "post_count_desc"]),
                        metadata={"description": "Sort order", "default": "created_desc"})
    page = fields.Integer(validate=validate.Range(min=1), metadata={"default": 1})
    limit = fields.Integer(validate=validate.Range(min=1, max=100), metadata={"default": 50})
    last_seen_days = fields.Integer(validate=validate.Range(min=1), metadata={"description": "Users active within N days"})


class AdminUserInfo(DefaultSchema):
    id = fields.Integer(required=True)
    username = fields.String(required=True)
    email = fields.String(required=True)
    display_name = fields.String()
    created_at = fields.DateTime(required=True, format='iso')
    last_seen = fields.DateTime(format='iso')
    is_verified = fields.Boolean(required=True)
    is_banned = fields.Boolean(required=True)
    is_local = fields.Boolean(required=True)
    post_count = fields.Integer(required=True)
    comment_count = fields.Integer()
    reputation = fields.Integer()
    bio = fields.String()


class AdminUserListPagination(DefaultSchema):
    page = fields.Integer(required=True)
    limit = fields.Integer(required=True)
    total = fields.Integer(required=True)
    total_pages = fields.Integer(required=True)
    has_next = fields.Boolean(required=True)
    has_prev = fields.Boolean(required=True)


class AdminUserListResponse(DefaultSchema):
    users = fields.List(fields.Nested(AdminUserInfo), required=True)
    pagination = fields.Nested(AdminUserListPagination, required=True)


class AdminUserLookupRequest(DefaultSchema):
    username = fields.String(validate=validate.Length(min=1, max=50))
    email = fields.Email()
    id = fields.Integer(validate=validate.Range(min=1))
    
    @validates_schema
    def validate_at_least_one_field(self, data, **kwargs):
        if not any([data.get('username'), data.get('email'), data.get('id')]):
            raise ValidationError("At least one of username, email, or id must be provided")


class AdminUserLookupResponse(DefaultSchema):
    found = fields.Boolean(required=True)
    user = fields.Nested(AdminUserInfo)


class AdminHealthResponse(DefaultSchema):
    private_registration = fields.Dict(required=True)
    database = fields.String(required=True)
    timestamp = fields.DateTime(required=True, format='iso')


# Phase 2: User Management Schemas

class AdminUserUpdateRequest(DefaultSchema):
    display_name = fields.String(validate=validate.Length(min=1, max=100))
    bio = fields.String(validate=validate.Length(max=2000))
    timezone = fields.String(validate=validate.Length(max=50))
    email = fields.Email()
    verified = fields.Boolean()
    newsletter = fields.Boolean()
    searchable = fields.Boolean()


class AdminUserUpdateResponse(DefaultSchema):
    success = fields.Boolean(required=True)
    user_id = fields.Integer(required=True)
    message = fields.String(required=True)
    updated_fields = fields.List(fields.String())


class AdminUserActionRequest(DefaultSchema):
    reason = fields.String(validate=validate.Length(min=1, max=500), 
                          metadata={"description": "Reason for action (required for ban/disable)"})
    expires_at = fields.DateTime(format='iso', 
                                metadata={"description": "Optional expiry date for temporary actions"})
    notify_user = fields.Boolean(metadata={"description": "Send notification email to user", "default": False})


class AdminUserActionResponse(DefaultSchema):
    success = fields.Boolean(required=True)
    user_id = fields.Integer(required=True)
    action = fields.String(required=True, 
                          validate=validate.OneOf(["disabled", "enabled", "banned", "unbanned", "deleted"]))
    message = fields.String(required=True)
    performed_by = fields.String(metadata={"description": "Admin who performed action"})
    timestamp = fields.DateTime(required=True, format='iso')


class AdminBulkUserRequest(DefaultSchema):
    operation = fields.String(required=True, 
                             validate=validate.OneOf(["disable", "enable", "ban", "unban", "delete"]))
    user_ids = fields.List(fields.Integer(validate=validate.Range(min=1)), required=True,
                          validate=validate.Length(min=1, max=100))
    reason = fields.String(validate=validate.Length(min=1, max=500))
    notify_users = fields.Boolean(metadata={"default": False})


class AdminBulkUserResponse(DefaultSchema):
    success = fields.Boolean(required=True)
    operation = fields.String(required=True)
    total_requested = fields.Integer(required=True)
    successful = fields.Integer(required=True)
    failed = fields.Integer(required=True)
    results = fields.List(fields.Dict(), metadata={"description": "Per-user results"})
    message = fields.String(required=True)


class AdminUserStatsResponse(DefaultSchema):
    total_users = fields.Integer(required=True)
    local_users = fields.Integer(required=True)
    remote_users = fields.Integer(required=True)
    verified_users = fields.Integer(required=True)
    banned_users = fields.Integer(required=True)
    active_24h = fields.Integer(required=True)
    active_7d = fields.Integer(required=True)
    active_30d = fields.Integer(required=True)
    registrations_today = fields.Integer(required=True)
    registrations_7d = fields.Integer(required=True)
    registrations_30d = fields.Integer(required=True)
    timestamp = fields.DateTime(required=True, format='iso')


class AdminRegistrationStatsRequest(DefaultSchema):
    days = fields.Integer(validate=validate.Range(min=1, max=365), 
                         metadata={"description": "Number of days to analyze", "default": 30})
    include_hourly = fields.Boolean(metadata={"description": "Include hourly breakdown", "default": False})


class AdminRegistrationStatsResponse(DefaultSchema):
    period_days = fields.Integer(required=True)
    total_registrations = fields.Integer(required=True)
    private_registrations = fields.Integer(required=True)
    public_registrations = fields.Integer(required=True)
    daily_breakdown = fields.List(fields.Dict(), 
                                 metadata={"description": "Daily registration counts"})
    hourly_breakdown = fields.List(fields.Dict(), 
                                  metadata={"description": "Hourly breakdown (if requested)"})
    timestamp = fields.DateTime(required=True, format='iso')


class AdminUserExportRequest(DefaultSchema):
    format = fields.String(validate=validate.OneOf(["csv", "json"]), 
                          metadata={"description": "Export format", "default": "csv"})
    export_fields = fields.List(fields.String(), 
                        metadata={"description": "Fields to include in export"})
    filters = fields.Dict(metadata={"description": "Same filters as user list endpoint"})


class AdminUserExportResponse(DefaultSchema):
    success = fields.Boolean(required=True)
    format = fields.String(required=True)
    total_records = fields.Integer(required=True)
    download_url = fields.String(metadata={"description": "Temporary download URL"})
    expires_at = fields.DateTime(format='iso')
    message = fields.String(required=True)


class GetPostRequest(DefaultSchema):
    id = fields.Integer(required=True)


class GetPostResponse(DefaultSchema):
    post_view = fields.Nested(PostView, required=True)
    community_view = fields.Nested(CommunityView, required=True)
    moderators = fields.List(fields.Nested(CommunityModeratorView), required=True)
    cross_posts = fields.List(fields.Nested(PostView), required=True)


class PostSetFlairRequest(DefaultSchema):
    post_id = fields.Integer(required=True)
    flair_id_list = fields.List(
        fields.Integer(),
        allow_none=True,
        metadata={"description": "A list of all the flair id to assign to the post. Either pass an empty list or null to remove flair"})


class PostSetFlairResponse(PostView):
    pass
