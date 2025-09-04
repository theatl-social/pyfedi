from flask import current_app, jsonify, request
from flask_smorest import abort
from flask_limiter import RateLimitExceeded
from sqlalchemy.orm.exc import NoResultFound

from app import limiter
from app.api.alpha import bp, site_bp, misc_bp, comm_bp, feed_bp, topic_bp, user_bp, reply_bp
from app.api.alpha.utils.community import get_community, get_community_list, post_community_follow, \
    post_community_block, post_community, put_community, put_community_subscribe, post_community_delete, \
    get_community_moderate_bans, put_community_moderate_unban, post_community_moderate_ban, \
    post_community_moderate_post_nsfw, post_community_mod
from app.api.alpha.utils.feed import get_feed_list
from app.api.alpha.utils.misc import get_search, get_resolve_object
from app.api.alpha.utils.post import get_post_list, get_post, post_post_like, put_post_save, put_post_subscribe, \
    post_post, put_post, post_post_delete, post_post_report, post_post_lock, post_post_feature, post_post_remove, \
    post_post_mark_as_read, get_post_replies
from app.api.alpha.utils.private_message import get_private_message_list, post_private_message, \
    post_private_message_mark_as_read, get_private_message_conversation, put_private_message, post_private_message_delete, \
    post_private_message_report
from app.api.alpha.utils.reply import get_reply_list, post_reply_like, put_reply_save, put_reply_subscribe, post_reply, \
    put_reply, post_reply_delete, post_reply_report, post_reply_remove, post_reply_mark_as_read, get_reply
from app.api.alpha.utils.site import get_site, post_site_block, get_federated_instances, get_site_instance_chooser, \
    get_site_instance_chooser_search, get_site_version
from app.api.alpha.utils.topic import get_topic_list
from app.api.alpha.utils.upload import post_upload_image, post_upload_community_image, post_upload_user_image
from app.api.alpha.utils.user import get_user, post_user_block, get_user_unread_count, get_user_replies, \
    post_user_mark_all_as_read, put_user_subscribe, put_user_save_user_settings, \
    get_user_notifications, put_user_notification_state, get_user_notifications_count, \
    put_user_mark_all_notifications_read, post_user_verify_credentials, post_user_set_flair
from app.constants import *
from app.utils import orjson_response, get_setting
from app.api.alpha.schema import *


def enable_api():
    return True if current_app.debug or current_app.config['ENABLE_ALPHA_API'] == 'true' else False


def is_trusted_request():
    if current_app.debug:
        return True
    if request.remote_addr in current_app.config['SKIP_RATE_LIMIT_IPS']:
        return True
    return False


# Site
@site_bp.route('/site', methods=['GET'])
@site_bp.doc(summary="Gets the site, and your user data.")
@site_bp.response(200, GetSiteResponse)
@site_bp.alt_response(400, schema=DefaultError)
def get_alpha_site():
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = get_site(auth)
        return GetSiteResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@site_bp.route('/site/version', methods=['GET'])
@site_bp.doc(summary="Gets version of PieFed.")
@site_bp.response(200, GetSiteVersionResponse)
@site_bp.alt_response(400, schema=DefaultError)
def get_alpha_site_version():
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = get_site_version(auth)
        return GetSiteVersionResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@site_bp.route('/site/block', methods=['POST'])
@site_bp.doc(summary="Block an instance.")
@site_bp.arguments(BlockInstanceRequest)
@site_bp.response(200, BlockInstanceResponse)
@site_bp.alt_response(400, schema=DefaultError)
def post_alpha_site_block(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = post_site_block(auth, data)
        return BlockInstanceResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


# Site instance chooser
@site_bp.route('/site/instance_chooser', methods=['GET'])
@site_bp.doc(summary="Gets the site info for use by other instances in the Instance Chooser functionality.")
@site_bp.response(200, GetSiteInstanceChooserResponse)
@site_bp.alt_response(400, schema=DefaultError)
def get_alpha_site_instance_chooser():
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    if get_setting('enable_instance_chooser', False):
        auth = request.headers.get('Authorization')
        resp = get_site_instance_chooser(auth)
        return GetSiteInstanceChooserResponse().load(resp)
    else:
        return abort(404)


@site_bp.route('/site/instance_chooser_search', methods=['GET'])
@site_bp.doc(summary="Search for other instances.")
@site_bp.arguments(SearchInstanceChooser, location="query")
@site_bp.response(200, GetSiteInstanceChooserSearchResponse)
@site_bp.alt_response(400, schema=DefaultError)
def get_alpha_site_instance_chooser_search(data):
    try:
        if get_setting('enable_instance_chooser', False):
            resp = get_site_instance_chooser_search(data)
            return GetSiteInstanceChooserSearchResponse().load(resp)
        else:
            return abort(404)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


# Misc
@misc_bp.route('/search', methods=["GET"])
@misc_bp.doc(summary="Search PieFed.")
@misc_bp.arguments(SearchRequest, location="query")
@misc_bp.response(200, SearchResponse)
@misc_bp.alt_response(400, schema=DefaultError)
def get_alpha_search(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = get_search(auth, data)
        return SearchResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@misc_bp.route('/resolve_object', methods=['GET'])
@misc_bp.doc(summary="Fetch a non-local / federated object.")
@misc_bp.arguments(ResolveObjectRequest, location="query")
@misc_bp.response(200, ResolveObjectResponse)
@misc_bp.alt_response(400, schema=DefaultError)
def get_alpha_resolve_object(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = get_resolve_object(auth, data)
        return ResolveObjectResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))



@misc_bp.route('/federated_instances', methods=['GET'])
@misc_bp.doc(summary="Fetch federated instances.")
@misc_bp.response(200, GetFederatedInstancesResponse)
@misc_bp.alt_response(400, schema=DefaultError)
def get_alpha_federated_instances():
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        data = {"include_federation_state": False}
        resp = get_federated_instances(data)
        return GetFederatedInstancesResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


# Community
@comm_bp.route("/community", methods=["GET"])
@comm_bp.doc(summary="Get / fetch a community.")
@comm_bp.arguments(GetCommunityRequest, location="query")
@comm_bp.response(200, GetCommunityResponse)
@comm_bp.alt_response(400, schema=DefaultError)
def get_alpha_community(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = get_community(auth, data)
        return GetCommunityResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@comm_bp.route("/community/list", methods=["GET"])
@comm_bp.doc(summary="List communities, with various filters.")
@comm_bp.arguments(ListCommunitiesRequest, location="query")
@comm_bp.response(200, ListCommunitiesResponse)
@comm_bp.alt_response(400, schema=DefaultError)
def get_alpha_community_list(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = get_community_list(auth, data)
        return ListCommunitiesResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@comm_bp.route("/community/follow", methods=["POST"])
@comm_bp.doc(summary="Follow / subscribe to a community.")
@comm_bp.arguments(FollowCommunityRequest)
@comm_bp.response(200, CommunityResponse)
@comm_bp.alt_response(400, schema=DefaultError)
def post_alpha_community_follow(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = post_community_follow(auth, data)
        return CommunityResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@comm_bp.route("/community/block", methods=["POST"])
@comm_bp.doc(summary="Block a community.")
@comm_bp.arguments(BlockCommunityRequest)
@comm_bp.response(200, BlockCommunityResponse)
@comm_bp.alt_response(400, schema=DefaultError)
def post_alpha_community_block(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = post_community_block(auth, data)
        return BlockCommunityResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@comm_bp.route("/community", methods=["POST"])
@comm_bp.doc(summary="Create a new community.")
@comm_bp.arguments(CreateCommunityRequest)
@comm_bp.response(200, CommunityResponse)
@comm_bp.alt_response(400, schema=DefaultError)
@comm_bp.alt_response(429, schema=DefaultError)
def post_alpha_community(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        with limiter.limit('10/day'):
            auth = request.headers.get('Authorization')
            resp = post_community(auth, data)
            return CommunityResponse().load(resp)
    except RateLimitExceeded as ex:
        return abort(429, message=str(ex))
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@comm_bp.route("/community", methods=["PUT"])
@comm_bp.doc(summary="Edit community.")
@comm_bp.arguments(EditCommunityRequest)
@comm_bp.response(200, CommunityResponse)
@comm_bp.alt_response(400, schema=DefaultError)
def put_alpha_community(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = put_community(auth, data)
        return CommunityResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@comm_bp.route("/community/subscribe", methods=["PUT"])
@comm_bp.doc(summary="Subscribe to activities in a community.")
@comm_bp.arguments(SubscribeCommunityRequest)
@comm_bp.response(200, CommunityResponse)
@comm_bp.alt_response(400, schema=DefaultError)
def put_alpha_community_subscribe(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = put_community_subscribe(auth, data)
        return CommunityResponse().load(resp)
    except NoResultFound:
        return abort(400, message="Community not found")
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@comm_bp.route("/community/delete", methods=["POST"])
@comm_bp.doc(summary="Delete a community.")
@comm_bp.arguments(DeleteCommunityRequest)
@comm_bp.response(200, CommunityResponse)
@comm_bp.alt_response(400, schema=DefaultError)
def post_alpha_community_delete(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = post_community_delete(auth, data)
        return CommunityResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@comm_bp.route('/community/mod', methods=['POST'])
@comm_bp.doc(summary="Add or remove a moderator for your community.")
@comm_bp.arguments(ModCommunityRequest)
@comm_bp.response(200, ModCommunityResponse)
@comm_bp.alt_response(400, schema=DefaultError)
def post_alpha_community_mod(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = post_community_mod(auth, data)
        return ModCommunityResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@comm_bp.route('/community/moderate/bans', methods=['GET'])
@comm_bp.doc(summary="Get the list of banned users for a community.")
@comm_bp.arguments(CommunityModerationBansListRequest, location="query")
@comm_bp.response(200, CommunityModerationBansListResponse)
@comm_bp.alt_response(400, schema=DefaultError)
def get_alpha_community_moderate_bans(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = get_community_moderate_bans(auth, data)
        return CommunityModerationBansListResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@comm_bp.route('/community/moderate/unban', methods=['PUT'])
@comm_bp.doc(summary="Unban a user from a community.")
@comm_bp.arguments(CommunityModerationUnbanRequest)
@comm_bp.response(200, CommunityModerationBanItem)
@comm_bp.alt_response(400, schema=DefaultError)
def put_alpha_community_moderate_unban(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = put_community_moderate_unban(auth, data)
        return CommunityModerationBanItem().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@comm_bp.route('/community/moderate/ban', methods=['POST'])
@comm_bp.doc(summary="Ban a user from a community.")
@comm_bp.arguments(CommunityModerationBanRequest)
@comm_bp.response(200, CommunityModerationBanItem)
@comm_bp.alt_response(400, schema=DefaultError)
def post_alpha_community_moderate_ban(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = post_community_moderate_ban(auth, data)
        return CommunityModerationBanItem().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@comm_bp.route('/community/moderate/post/nsfw', methods=['POST'])
@comm_bp.doc(summary="Mark or unmark a post as NSFW.")
@comm_bp.arguments(CommunityModerationNsfwRequest)
@comm_bp.response(200, PostView)
@comm_bp.alt_response(400, schema=DefaultError)
def post_alpha_community_moderate_post_nsfw(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = post_community_moderate_post_nsfw(auth, data)
        return PostView().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


# Feed
@feed_bp.route('/feed/list', methods=["GET"])
@feed_bp.doc(summary="Get list of feeds")
@feed_bp.arguments(FeedListRequest, location="query")
@feed_bp.response(200, FeedListResponse)
@feed_bp.alt_response(400, schema=DefaultError)
def get_alpha_feed_list(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = get_feed_list(auth, data)
        validated = FeedListResponse().load(resp)
        return orjson_response(validated)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


# Post
@bp.route('/api/alpha/post/list', methods=['GET'])
def get_alpha_post_list():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.args.to_dict() or None
        return orjson_response(get_post_list(auth, data))
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/post', methods=['GET'])
def get_alpha_post():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.args.to_dict() or None
        return jsonify(get_post(auth, data))
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/post/replies', methods=['GET'])
def get_alpha_post_replies():
    if not enable_api():
        return jsonify({'error': 'api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.args.to_dict() or None
        return orjson_response(get_post_replies(auth, data))
    except NoResultFound:
        return jsonify({"error": "Post not found"}), 400
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/post/like', methods=['POST'])
def post_alpha_post_like():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.get_json(force=True) or {}
        return jsonify(post_post_like(auth, data))
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/post/save', methods=['PUT'])
def put_alpha_post_save():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.get_json(force=True) or {}
        return jsonify(put_post_save(auth, data))
    except NoResultFound:
        return jsonify({"error": "Post not found"}), 400
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/post/subscribe', methods=['PUT'])
def put_alpha_post_subscribe():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.get_json(force=True) or {}
        return jsonify(put_post_subscribe(auth, data))
    except NoResultFound:
        return jsonify({"error": "Post not found"}), 400
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/post', methods=['POST'])
def post_alpha_post():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        with limiter.limit('3/minute'):
            auth = request.headers.get('Authorization')
            data = request.get_json(force=True) or {}
            return jsonify(post_post(auth, data))
    except RateLimitExceeded as ex:
        return jsonify({"error": str(ex)}), 429
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/post', methods=['PUT'])
def put_alpha_post():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.get_json(force=True) or {}
        return jsonify(put_post(auth, data))
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/post/delete', methods=['POST'])
def post_alpha_post_delete():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.get_json(force=True) or {}
        return jsonify(post_post_delete(auth, data))
    except Exception as ex:
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/post/report', methods=['POST'])
def post_alpha_post_report():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.get_json(force=True) or {}
        return jsonify(post_post_report(auth, data))
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/post/lock', methods=['POST'])
def post_alpha_post_lock():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.get_json(force=True) or {}
        return jsonify(post_post_lock(auth, data))
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/post/feature', methods=['POST'])
def post_alpha_post_feature():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.get_json(force=True) or {}
        return jsonify(post_post_feature(auth, data))
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/post/remove', methods=['POST'])
def post_alpha_post_remove():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.get_json(force=True) or {}
        return jsonify(post_post_remove(auth, data))
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/post/mark_as_read', methods=['POST'])
def post_alpha_post_mark_as_read():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.get_json(force=True) or {}
        return jsonify(post_post_mark_as_read(auth, data))
    except NoResultFound:
        return jsonify({"error": "Post not found"}), 400
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


# Reply
@reply_bp.route('/comment/list', methods=['GET'])
@reply_bp.doc(summary="List comments, with various filters.")
@reply_bp.arguments(ListCommentsRequest, location="query")
@reply_bp.response(200, ListCommentsResponse)
@reply_bp.alt_response(400, schema=DefaultError)
def get_alpha_comment_list(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = get_reply_list(auth, data)
        validated = ListCommentsResponse().load(resp)
        return orjson_response(validated)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@reply_bp.route('/comment/like', methods=['POST'])
@reply_bp.doc(summary="Like / vote on a comment.")
@reply_bp.arguments(LikeCommentRequest)
@reply_bp.response(200, GetCommentResponse)
@reply_bp.alt_response(400, schema=DefaultError)
def post_alpha_comment_like(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = post_reply_like(auth, data)
        return GetCommentResponse().load(resp)
    except NoResultFound:
        return abort(400, message="Comment not found")
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@reply_bp.route('/comment/save', methods=['PUT'])
@reply_bp.doc(summary="Save a comment.")
@reply_bp.arguments(SaveCommentRequest)
@reply_bp.response(200, GetCommentResponse)
@reply_bp.alt_response(400, schema=DefaultError)
def put_alpha_comment_save(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = put_reply_save(auth, data)
        return GetCommentResponse().load(resp)
    except NoResultFound:
        return abort(400, message="Comment not found")
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@reply_bp.route('/comment/subscribe', methods=['PUT'])
@reply_bp.doc(summary="Subscribe to a comment.")
@reply_bp.arguments(SubscribeCommentRequest)
@reply_bp.response(200, GetCommentResponse)
@reply_bp.alt_response(400, schema=DefaultError)
def put_alpha_comment_subscribe(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = put_reply_subscribe(auth, data)
        return GetCommentResponse().load(resp)
    except NoResultFound:
        return abort(400, message="Comment not found")
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@reply_bp.route('/comment', methods=['POST'])
@reply_bp.doc(summary="Create a comment.")
@reply_bp.arguments(CreateCommentRequest)
@reply_bp.response(200, GetCommentResponse)
@reply_bp.alt_response(400, schema=DefaultError)
@reply_bp.alt_response(429, schema=DefaultError)
def post_alpha_comment(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        with limiter.limit('3/minute'):
            auth = request.headers.get('Authorization')
            resp = post_reply(auth, data)
            return GetCommentResponse().load(resp)
    except RateLimitExceeded as ex:
        return abort(429, message=str(ex))
    except NoResultFound:
        return abort(400, message="Post / Parent Comment not found")
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@reply_bp.route('/comment', methods=['PUT'])
@reply_bp.doc(summary="Edit a comment.")
@reply_bp.arguments(EditCommentRequest)
@reply_bp.response(200, GetCommentResponse)
@reply_bp.alt_response(400, schema=DefaultError)
def put_alpha_comment(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = put_reply(auth, data)
        return GetCommentResponse().load(resp)
    except NoResultFound:
        return abort(400, message="Comment not found")
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@reply_bp.route('/comment/delete', methods=['POST'])
@reply_bp.doc(summary="Delete a comment.")
@reply_bp.arguments(DeleteCommentRequest)
@reply_bp.response(200, GetCommentResponse)
@reply_bp.alt_response(400, schema=DefaultError)
def post_alpha_comment_delete(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = post_reply_delete(auth, data)
        return GetCommentResponse().load(resp)
    except NoResultFound:
        return abort(400, message="Comment not found")
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@reply_bp.route('/comment/report', methods=['POST'])
@reply_bp.doc(summary="Report a comment.")
@reply_bp.arguments(ReportCommentRequest)
@reply_bp.response(200, GetCommentReportResponse)
@reply_bp.alt_response(400, schema=DefaultError)
def post_alpha_comment_report(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = post_reply_report(auth, data)
        return GetCommentReportResponse().load(resp)
    except NoResultFound:
        return abort(400, message="Comment not found")
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@bp.route('/api/alpha/comment/remove', methods=['POST'])
def post_alpha_comment_remove():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.get_json(force=True) or {}
        return jsonify(post_reply_remove(auth, data))
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/comment/mark_as_read', methods=['POST'])
def post_alpha_comment_mark_as_read():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.get_json(force=True) or {}
        return jsonify(post_reply_mark_as_read(auth, data))
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@reply_bp.route("/comment", methods=["GET"])
@reply_bp.doc(summary="Get / fetch a comment.")
@reply_bp.arguments(GetCommentRequest, location="query")
@reply_bp.response(200, GetCommentResponse)
@reply_bp.alt_response(400, schema=DefaultError)
def get_alpha_comment(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = get_reply(auth, data)
        return GetCommentResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


# Private Message
@bp.route('/api/alpha/private_message/list', methods=['GET'])
def get_alpha_private_message_list():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.args.to_dict() or None
        return jsonify(get_private_message_list(auth, data))
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/private_message/conversation', methods=['GET'])
def get_alpha_private_message_conversation():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.args.to_dict() or None
        return jsonify(get_private_message_conversation(auth, data))
    except NoResultFound:
        return jsonify({"error": "Person not found"}), 400
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/private_message', methods=['POST'])
def post_alpha_private_message():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        with limiter.limit('3/minute'):
            auth = request.headers.get('Authorization')
            data = request.get_json(force=True) or {}
            return jsonify(post_private_message(auth, data))
    except NoResultFound:
        return jsonify({"error": "Recipient not found"}), 400
    except RateLimitExceeded as ex:
        return jsonify({"error": str(ex)}), 429
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/private_message', methods=['PUT'])
def put_alpha_private_message():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.get_json(force=True) or {}
        return jsonify(put_private_message(auth, data))
    except NoResultFound:
        return jsonify({"error": "Message not found"}), 400
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/private_message/mark_as_read', methods=['POST'])
def post_alpha_private_message_mark_as_read():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.get_json(force=True) or {}
        return jsonify(post_private_message_mark_as_read(auth, data))
    except NoResultFound:
        return jsonify({"error": "Message not found"}), 400
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/private_message/delete', methods=['POST'])
def post_alpha_private_message_delete():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.get_json(force=True) or {}
        return jsonify(post_private_message_delete(auth, data))
    except NoResultFound:
        return jsonify({"error": "Message not found"}), 400
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/private_message/report', methods=['POST'])
def post_alpha_private_message_report():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        auth = request.headers.get('Authorization')
        data = request.get_json(force=True) or {}
        return jsonify(post_private_message_report(auth, data))
    except NoResultFound:
        return jsonify({"error": "Message not found"}), 400
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


# Topic
@topic_bp.route('/topic/list', methods=["GET"])
@topic_bp.doc(summary="Get list of topics")
@topic_bp.arguments(TopicListRequest, location="query")
@topic_bp.response(200, TopicListResponse)
@topic_bp.alt_response(400, schema=DefaultError)
def get_alpha_topic_list(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = get_topic_list(auth, data)
        validated = TopicListResponse().load(resp)
        return orjson_response(validated)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


# User
@user_bp.route("/user", methods=["GET"])
@user_bp.doc(summary="Get the details for a person")
@user_bp.arguments(GetUserRequest, location="query")
@user_bp.response(200, GetUserResponse)
@user_bp.alt_response(400, schema=DefaultError)
def get_alpha_user(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = get_user(auth, data)
        validated = GetUserResponse().load(resp)
        return orjson_response(validated)
    except NoResultFound:
        return abort(400, message="User not found")
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@user_bp.route("/user/login", methods=["POST"])
@user_bp.doc(summary="Log into PieFed")
@user_bp.arguments(UserLoginRequest)
@user_bp.response(200, UserLoginResponse)
@user_bp.alt_response(400, schema=DefaultError)
@user_bp.alt_response(429, schema=DefaultError)
def post_alpha_user_login(data):
    from app.shared.auth import log_user_in
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        with limiter.limit('20/hour', exempt_when=is_trusted_request):
            resp = log_user_in(data, SRC_API)
            return UserLoginResponse().load(resp)
    except RateLimitExceeded as ex:
        return abort(429, message=str(ex))
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@user_bp.route('/user/unread_count', methods=['GET'])
@user_bp.doc(summary="Get your unread counts")
@user_bp.response(200, UserUnreadCountsResponse)
@user_bp.alt_response(400, schema=DefaultError)
def get_alpha_user_unread_count():
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = get_user_unread_count(auth)
        return UserUnreadCountsResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@user_bp.route('/user/replies', methods=['GET'])
@user_bp.doc(summary="Get comment replies")
@user_bp.arguments(UserRepliesRequest, location="query")
@user_bp.response(200, UserRepliesResponse)
@user_bp.alt_response(400, schema=DefaultError)
def get_alpha_user_replies(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = get_user_replies(auth, data)
        return UserRepliesResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@user_bp.route('/user/mentions', methods=['GET'])
@user_bp.doc(summary="Get mentions of your account made in comments")
@user_bp.arguments(UserMentionsRequest, location="query")
@user_bp.response(200, UserMentionsResponse)
@user_bp.alt_response(400, schema=DefaultError)
def get_alpha_user_mentions(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = get_user_replies(auth, data, mentions=True)
        return UserMentionsResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@user_bp.route('/user/block', methods=['POST'])
@user_bp.doc(summary="Block or unblock a person")
@user_bp.arguments(UserBlockRequest)
@user_bp.response(200, UserBlockResponse)
@user_bp.alt_response(400, schema=DefaultError)
def post_alpha_user_block(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = post_user_block(auth, data)
        return UserBlockResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@user_bp.route('/user/mark_all_as_read', methods=['POST'])
@user_bp.doc(summary="Mark all notifications and messages as read")
@user_bp.response(200, UserMarkAllReadResponse)
@user_bp.alt_response(400, schema=DefaultError)
def post_alpha_user_mark_all_as_read():
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = post_user_mark_all_as_read(auth)
        return UserMarkAllReadResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@user_bp.route('/user/subscribe', methods=['PUT'])
@user_bp.doc(summary="Subscribe or unsubscribe to activites of another user")
@user_bp.arguments(UserSubscribeRequest)
@user_bp.response(200, UserSubscribeResponse)
@user_bp.alt_response(400, schema=DefaultError)
def put_alpha_user_subscribe(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = put_user_subscribe(auth, data)
        return UserSubscribeResponse().load(resp)
    except NoResultFound:
        return abort(400, message="User not found")
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


# not all settings implemented yet, nor all choices for settings (eg. blur nsfw)
@user_bp.route('/user/save_user_settings', methods=['PUT'])
@user_bp.doc(summary="Save your user settings")
@user_bp.arguments(UserSaveSettingsRequest)
@user_bp.response(200, UserSaveSettingsResponse)
@user_bp.alt_response(400, schema=DefaultError)
def put_alpha_user_save_user_settings(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = put_user_save_user_settings(auth, data)
        return UserSaveSettingsResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@user_bp.route('/user/notifications', methods=['GET'])
@user_bp.doc(summary="Get your user notifications (not all notification types supported yet)")
@user_bp.arguments(UserNotificationsRequest, location="query")
@user_bp.response(200, UserNotificationsResponse)
@user_bp.alt_response(400, schema=DefaultError)
def get_alpha_user_notifications(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = get_user_notifications(auth, data)
        return UserNotificationsResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@user_bp.route('/user/notification_state', methods=['PUT'])
@user_bp.doc(summary="Set the read status of a given notification (not all notification types supported yet)")
@user_bp.arguments(UserNotificationStateRequest)
@user_bp.response(200, UserNotificationItemView)
@user_bp.alt_response(400, schema=DefaultError)
def put_alpha_user_notification_state(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = put_user_notification_state(auth, data)
        return UserNotificationItemView().load(resp)
    except NoResultFound:
        return abort(400, message="Notification not found")
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@user_bp.route('/user/notifications_count', methods=['GET'])
@user_bp.doc(summary="Get user unread notifications count")
@user_bp.response(200, UserNotificationsCountResponse)
@user_bp.alt_response(400, schema=DefaultError)
def get_alpha_user_notifications_count():
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = get_user_notifications_count(auth)
        return UserNotificationsCountResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@user_bp.route('/user/mark_all_notifications_read', methods=['PUT'])
@user_bp.doc(summary="Mark all notifications as read")
@user_bp.response(200, UserMarkAllNotifsReadResponse)
@user_bp.alt_response(400, schema=DefaultError)
def put_alpha_user_notifications_read():
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = put_user_mark_all_notifications_read(auth)
        return UserMarkAllNotifsReadResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@user_bp.route('/user/verify_credentials', methods=['POST'])
@user_bp.doc(summary="Verify username/password credentials")
@user_bp.arguments(UserLoginRequest)
@user_bp.response(200)
@user_bp.alt_response(400, schema=DefaultError)
def post_alpha_user_verify_credentials(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        with limiter.limit('6/hour', exempt_when=is_trusted_request):
            post_user_verify_credentials(data)
    except RateLimitExceeded as ex:
        return abort(429, message=str(ex))
    except NoResultFound:
        return abort(400, message="Bad credentials")
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


@user_bp.route('/user/set_flair', methods=['POST'])
@user_bp.doc(summary="Set your flair for a community")
@user_bp.arguments(UserSetFlairRequest)
@user_bp.response(200, UserSetFlairResponse)
@user_bp.alt_response(400, schema=DefaultError)
def post_alpha_user_set_flair(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    try:
        auth = request.headers.get('Authorization')
        resp = post_user_set_flair(auth, data)
        return UserSetFlairResponse().load(resp)
    except Exception as ex:
        current_app.logger.error(str(ex))
        return abort(400, message=str(ex))


# Upload
@bp.route('/api/alpha/upload/image', methods=['POST'])
def post_alpha_upload_image():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        with limiter.limit('15/hour'):
            auth = request.headers.get('Authorization')
            image_file = request.files['file']
            return jsonify(post_upload_image(auth, image_file))
    except RateLimitExceeded as ex:
        return jsonify({"error": str(ex)}), 429
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/upload/community_image', methods=['POST'])
def post_alpha_upload_community_image():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        with limiter.limit('20/day'):
            auth = request.headers.get('Authorization')
            image_file = request.files['file']
            return jsonify(post_upload_community_image(auth, image_file))
    except RateLimitExceeded as ex:
        return jsonify({"error": str(ex)}), 429
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


@bp.route('/api/alpha/upload/user_image', methods=['POST'])
def post_alpha_upload_user_image():
    if not enable_api():
        return jsonify({'error': 'alpha api is not enabled'}), 400
    try:
        with limiter.limit('20/day'):
            auth = request.headers.get('Authorization')
            image_file = request.files['file']
            return jsonify(post_upload_user_image(auth, image_file))
    except RateLimitExceeded as ex:
        return jsonify({"error": str(ex)}), 429
    except Exception as ex:
        current_app.logger.error(str(ex))
        return jsonify({"error": str(ex)}), 400


# Not yet implemented. Copied from lemmy's V3 api, so some aren't needed, and some need changing

# Site - not yet implemented
@bp.route('/api/alpha/site', methods=['POST'])  # Create New Site. No plans to implement
@bp.route('/api/alpha/site', methods=['PUT'])  # Edit Site. Not available in app
def alpha_site():
    return jsonify({"error": "not_yet_implemented"}), 400


# Miscellaneous - not yet implemented
@bp.route('/api/alpha/modlog', methods=['GET'])  # Get Modlog. Not usually public
def alpha_miscellaneous():
    return jsonify({"error": "not_yet_implemented"}), 400


# Community - not yet implemented
# @bp.route('/api/alpha/community', methods=['POST'])                               # (none
# @bp.route('/api/alpha/community', methods=['PUT'])                                #  of
@bp.route('/api/alpha/community/hide', methods=['PUT'])  # these
# @bp.route('/api/alpha/community/delete', methods=['POST'])                        #  are
@bp.route('/api/alpha/community/remove', methods=['POST'])  # available
@bp.route('/api/alpha/community/transfer', methods=['POST'])  # in
@bp.route('/api/alpha/community/ban_user', methods=['POST'])  # the app)
def alpha_community():
    return jsonify({"error": "not_yet_implemented"}), 400


# Post - not yet implemented
@bp.route('/api/alpha/post/report/resolve', methods=['PUT'])  # Stage 2
@bp.route('/api/alpha/post/report/list', methods=['GET'])  # Stage 2
@bp.route('/api/alpha/post/site_metadata', methods=['GET'])  # Not available in app
def alpha_post():
    return jsonify({"error": "not_yet_implemented"}), 400


# Reply - not yet implemented
@bp.route('/api/alpha/comment/distinguish', methods=['POST'])  # Not really used
@bp.route('/api/alpha/comment/report/resolve', methods=['PUT'])  # Stage 2
@bp.route('/api/alpha/comment/report/list', methods=['GET'])  # Stage 2
def alpha_reply():
    return jsonify({"error": "not_yet_implemented"}), 400


# Chat
@bp.route('/api/alpha/private_message/report/resolve', methods=['PUT'])  # Stage 2
@bp.route('/api/alpha/private_message/report/list', methods=['GET'])  # Stage 2
def alpha_chat():
    return jsonify({"error": "not_yet_implemented"}), 400


# User - not yet implemented
@bp.route('/api/alpha/user/register', methods=['POST'])  # Not available in app
@bp.route('/api/alpha/user/get_captcha', methods=['GET'])  # Not available in app
@bp.route('/api/alpha/user/mention/mark_as_read',
          methods=['POST'])  # No DB support / Not available in app (using mark_all instead)
@bp.route('/api/alpha/user/ban', methods=['POST'])  # Admin function. No plans to implement
@bp.route('/api/alpha/user/banned', methods=['GET'])  # Admin function. No plans to implement
@bp.route('/api/alpha/user/delete_account', methods=['POST'])  # Not available in app
@bp.route('/api/alpha/user/password_reset', methods=['POST'])  # Not available in app
@bp.route('/api/alpha/user/password_change', methods=['POST'])  # Not available in app
@bp.route('/api/alpha/user/change_password', methods=['PUT'])  # Stage 2
@bp.route('/api/alpha/user/report_count', methods=['GET'])  # Stage 2
@bp.route('/api/alpha/user/verify_email', methods=['POST'])  # Admin function. No plans to implement
@bp.route('/api/alpha/user/leave_admin', methods=['POST'])  # Admin function. No plans to implement
@bp.route('/api/alpha/user/totp/generate', methods=['POST'])  # Not available in app
@bp.route('/api/alpha/user/totp/update', methods=['POST'])  # Not available in app
@bp.route('/api/alpha/user/export_settings', methods=['GET'])  # Not available in app
@bp.route('/api/alpha/user/import_settings', methods=['POST'])  # Not available in app
@bp.route('/api/alpha/user/list_logins', methods=['GET'])  # Not available in app
@bp.route('/api/alpha/user/validate_auth', methods=['GET'])  # Not available in app
@bp.route('/api/alpha/user/logout', methods=['POST'])  # Stage 2
def alpha_user():
    return jsonify({"error": "not_yet_implemented"}), 400

@bp.route('/api/alpha/user/mention', methods=['GET'])
def alpha_user_mention():
    return jsonify({"error": "renamed to user/mentions"}), 400


# Admin - not yet implemented
@bp.route('/api/alpha/admin/add', methods=['POST'])
@bp.route('/api/alpha/admin/registration_application/count', methods=['GET'])  # (no
@bp.route('/api/alpha/admin/registration_application/list', methods=['GET'])  # plans
@bp.route('/api/alpha/admin/registration_application/approve', methods=['PUT'])  # to
@bp.route('/api/alpha/admin/purge/person', methods=['POST'])  # implement
@bp.route('/api/alpha/admin/purge/community', methods=['POST'])  # any
@bp.route('/api/alpha/admin/purge/post', methods=['POST'])  # endpoints
@bp.route('/api/alpha/admin/purge/comment', methods=['POST'])  # for
@bp.route('/api/alpha/post/like/list', methods=['GET'])  # admin
@bp.route('/api/alpha/comment/like/list', methods=['GET'])  # use)
def alpha_admin():
    return jsonify({"error": "not_yet_implemented"}), 400


# CustomEmoji - not yet implemented
@bp.route('/api/alpha/custom_emoji', methods=['PUT'])  # (doesn't
@bp.route('/api/alpha/custom_emoji', methods=['POST'])  # seem
@bp.route('/api/alpha/custom_emoji/delete', methods=['POST'])  # important)
def alpha_emoji():
    return jsonify({"error": "not_yet_implemented"}), 400
