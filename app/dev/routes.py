from flask import request, flash, json, url_for, current_app, redirect, g, abort
from flask_login import login_required, current_user
from flask_babel import _
from sqlalchemy import desc, or_, and_, text

from app.activitypub.signature import RsaKeys
from app import db, celery, cache
from app.dev.forms import AddTestCommunities
# from app.chat.forms import AddReply, ReportConversationForm
# from app.chat.util import send_message
from app.models import Site, User, Community, CommunityMember, Language
# from app.user.forms import ReportUserForm
from app.utils import render_template, community_membership, moderating_communities, joined_communities, menu_topics, markdown_to_html
from app.dev import bp


# use this to populate communities in the database
@bp.route('/dev/tools', methods=['GET', 'POST'])
@login_required
def populate_communities():
    form = AddTestCommunities()
    if form.validate_on_submit():
        # do a for loop for a range up to 30 or so
        # build the community title from that and then submit it 
        # to the db
        for n in range(30):
            # generate a keypair
            private_key, public_key = RsaKeys.generate_keypair()
            # generate a Title, name, description, rules, as strings, all the same with num from loop
            # add local_only, ap_profile_id, ap_public_url. ap_followers_url, ap_domain, subscriptions_count
            # instance_id, and low_quality='memes' in form.url.data  bits as in the community thing
            loop_num = "{:02d}".format(n)
            title = "dev_Community_" + loop_num
            name = "dev_Community_" + loop_num
            description = "dev_Community_" + loop_num
            rules = "dev_Community_" + loop_num + "Rules"
            community = Community(title=title, name=name, description=description,
                                  rules=rules, nsfw=False, private_key=private_key,
                                  public_key=public_key, description_html=markdown_to_html(description),
                                  rules_html=markdown_to_html(rules), local_only=True,
                                  ap_profile_id='https://' + current_app.config['SERVER_NAME'] + '/c/' + name.lower(),
                                  ap_public_url='https://' + current_app.config['SERVER_NAME'] + '/c/' + name.lower(),
                                  ap_followers_url='https://' + current_app.config['SERVER_NAME'] + '/c/' + name.lower() + '/followers',
                                  ap_domain=current_app.config['SERVER_NAME'],
                                  subscriptions_count=1, instance_id=1, low_quality='memes' in name)            
            #
            # add and commit to db
            db.session.add(community)
            db.session.commit()
            #
            # add community membership for current user
            # add to db
            membership = CommunityMember(user_id=current_user.id, community_id=community.id, is_moderator=True,
                                         is_owner=True)
            db.session.add(membership)
            # 
            # add english as language choice
            # commit to db
            # community.languages.append(Language.query.filter(Language.name.in_('English')))
            # db.session.commit()
            #
            # do the cache.dememoiz
            cache.delete_memoized(community_membership, current_user, community)
            cache.delete_memoized(joined_communities, current_user.id)
            cache.delete_memoized(moderating_communities, current_user.id)
        return redirect(url_for('main.list_communities'))
    else:
        return render_template('dev/tools.html', form=form)
