from flask import request, flash, json, url_for, current_app, redirect, g, abort
from flask_login import login_required, current_user
from flask_babel import _
from sqlalchemy import desc, or_, and_, text

from app.activitypub.signature import RsaKeys
from app import db, celery, cache
from app.dev.forms import AddTestCommunities, AddTestTopics
from app.models import Site, User, Community, CommunityMember, Language, Topic
from app.utils import render_template, community_membership, moderating_communities, joined_communities, menu_topics, markdown_to_html
from app.dev import bp
import random


# use this to populate communities in the database
@bp.route('/dev/tools', methods=['GET', 'POST'])
@login_required
def tools():
    communities_form = AddTestCommunities()
    topics_form = AddTestTopics()
    if communities_form.communities_submit.data and communities_form.validate():
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
    elif topics_form.topics_submit.data and topics_form.validate():
        # get the list of communities in the db
        communities = Community.query.filter_by(banned=False)
        
        # pick 10 random communities from the communities list
        rand_communities = []
        for c in range(10):
            rand_communities.append(random.choice(communities.all()))
        
        # get those community_ids
        # rand_community_ids = []
        # for c in rand_communities:
            # rand_community_ids.append(c.id)
        
        # generate new topics
        # for n in range(10):
        #     # generate strings for name, machine_name, and default to 0 communities
        #     loop_num = "{:02d}".format(n)
        #     name = "dev_Topic_" + loop_num
        #     machine_name = "dev-topic-" + loop_num
        #     num_communities = 0
        #     # make the topic
        #     topic = Topic(name=name, machine_name=machine_name, num_communities=num_communities)
        #     # add the new topic to the db
        #     db.session.add(topic)
        #     db.session.commit()
        #     # refresh the topic menu
        #     cache.delete_memoized(menu_topics)

        # get the list of topics in the db
        topics = Topic.query.filter_by()

        # pick 10 random topics from the topics list
        rand_topics = []
        for t in range(10):
            rand_topics.append(random.choice(topics.all()))

        # get those topic_ids
        rand_topic_ids = []
        for t in rand_topics:
            rand_topic_ids.append(t.id)

        # loop 10 times
        # get the community
        # add the topic_id to the community
        # save the db
        # update the num_communities for the topic
        # save the db again
        for i in range(10): 

            community = rand_communities[i]
            community.topic_id = rand_topic_ids[i]
            db.session.commit()
            community.topic.num_communities = community.topic.communities.count()
            db.session.commit()

        
        # flash(_(f'rand_topic_ids: {rand_topic_ids}'))
        # return redirect(url_for('dev.tools'))
        return redirect(url_for('main.list_topics'))
    else:
        return render_template('dev/tools.html', communities_form=communities_form, topics_form=topics_form)
