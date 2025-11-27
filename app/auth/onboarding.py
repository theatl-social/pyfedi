from flask import redirect, url_for, flash, current_app, abort
from flask_babel import _
from flask_login import current_user, login_required

from app import db, cache
from app.activitypub.signature import send_post_request
from app.auth import bp
from app.auth.forms import ChooseTopicsForm, ChooseTrumpMuskForm
from app.constants import SUBSCRIPTION_NONMEMBER
from app.models import User, Topic, Community, CommunityJoinRequest, CommunityMember, Filter, InstanceChooser, Language
from app.utils import render_template, joined_communities, community_membership, get_setting, num_topics


@bp.route('/instance_chooser')
def onboarding_instance_chooser():
    if get_setting('enable_instance_chooser', False):
        instances = InstanceChooser.query.all()
        language_ids = set()
        for instance in instances:
            language_ids.add(instance.language_id)
        languages = Language.query.filter(Language.id.in_(language_ids)).all()
        return render_template('auth/instance_chooser.html', title=_('Which server do you want to join?'),
                               instances=instances, languages=languages)
    else:
        return redirect(url_for('auth.register'))


@bp.route('/trump_musk', methods=['GET', 'POST'])
@login_required
def trump_musk():
    if get_setting('filter_selection', True):
        form = ChooseTrumpMuskForm()
        if form.validate_on_submit():
            if form.trump_musk_level.data >= 0:
                content_filter = Filter(title='Trump & Musk', filter_home=True, filter_posts=True, filter_replies=False, hide_type=form.trump_musk_level.data, keywords='trump\nmusk', expire_after=None, user_id=current_user.id)
                db.session.add(content_filter)
                db.session.commit()
            return redirect(url_for('auth.choose_topics'))
        else:
            existing_filters = Filter.query.filter(Filter.user_id == current_user.id).first()
            if existing_filters is not None:
                return redirect(url_for('auth.choose_topics'))

            return render_template('auth/trump_musk.html', form=form,
                                   )
    else:
        return redirect(url_for('auth.choose_topics'))


@bp.route('/choose_topics', methods=['GET', 'POST'])
@login_required
def choose_topics():
    if get_setting('choose_topics', True) and num_topics() > 0:
        form = ChooseTopicsForm()
        form.chosen_topics.choices = topics_for_form()
        if form.validate_on_submit():
            if form.chosen_topics.data:
                for topic_id in form.chosen_topics.data:
                    join_topic(topic_id)
                flash(_('You have joined some communities relating to those interests. Find more on the Topics menu or browse the home page.'))
                cache.delete_memoized(joined_communities, current_user.id)
                return redirect(url_for('main.index'))
            else:
                flash(_('You did not choose any topics. Would you like to choose individual communities instead?'))
                return redirect(url_for('main.list_communities'))
        else:
            return render_template('auth/choose_topics.html', form=form,
                                   )
    else:
        flash(_('Please join some communities you\'re interested in and then go to the home page by clicking on the logo above.'))
        return redirect(url_for('main.list_communities'))


def join_topic(topic_id):
    communities = Community.query.filter_by(topic_id=topic_id, banned=False).all()
    for community in communities:
        if not community.user_is_banned(current_user) and community_membership(current_user, community) == SUBSCRIPTION_NONMEMBER:
            if not community.is_local():
                join_request = CommunityJoinRequest(user_id=current_user.id, community_id=community.id)
                db.session.add(join_request)
                db.session.commit()
                send_community_follow(community.id, join_request.uuid, current_user.id)

            existing_member = CommunityMember.query.filter(CommunityMember.community_id == community.id, CommunityMember.user_id == current_user.id).first()
            if not existing_member:
                member = CommunityMember(user_id=current_user.id, community_id=community.id)
                db.session.add(member)
                db.session.commit()
            cache.delete_memoized(community_membership, current_user, community)


def topics_for_form():
    topics = Topic.query.filter_by(parent_id=None).order_by(Topic.name).all()
    result = []
    for topic in topics:
        result.append((topic.id, topic.name))
        sub_topics = Topic.query.filter_by(parent_id=topic.id).order_by(Topic.name).all()
        for sub_topic in sub_topics:
            result.append((sub_topic.id, ' --- ' + sub_topic.name))
    return result


def send_community_follow(community_id: int, join_request_id: int, user_id: int):
    with current_app.app_context():
        user = User.query.get(user_id)
        community = Community.query.get(community_id)
        if not community.instance.gone_forever:
            follow = {
                "actor": user.public_url(),
                "to": [community.public_url()],
                "object": community.public_url(),
                "type": "Follow",
                "id": f"https://{current_app.config['SERVER_NAME']}/activities/follow/{join_request_id}"
            }
            send_post_request(community.ap_inbox_url, follow, user.private_key, user.public_url() + '#main-key')
