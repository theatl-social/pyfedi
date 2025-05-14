# if commands in this file are not working (e.g. 'flask translate') make sure you set the FLASK_APP environment variable.
# e.g. export FLASK_APP=pyfedi.py
import imaplib
import re
from datetime import datetime, timedelta
from random import randint
from time import sleep

import flask
from flask import json, current_app
from flask_babel import _
from sqlalchemy import or_, desc, text

from app import db
import click
import os

from app.activitypub.signature import RsaKeys, send_post_request
from app.activitypub.util import find_actor_or_create, extract_domain_and_actor, notify_about_post
from app.auth.util import random_token
from app.constants import NOTIF_COMMUNITY, NOTIF_POST, NOTIF_REPLY, POST_STATUS_SCHEDULED, POST_STATUS_PUBLISHED
from app.email import send_email
from app.models import Settings, BannedInstances, Role, User, RolePermission, Domain, ActivityPubLog, \
    utcnow, Site, Instance, File, Notification, Post, CommunityMember, NotificationSubscription, PostReply, Language, \
    Tag, InstanceRole, Community, DefederationSubscription, SendQueue
from app.post.routes import post_delete_post
from app.shared.post import edit_post
from app.shared.tasks import task_selector
from app.utils import retrieve_block_list, blocked_domains, retrieve_peertube_block_list, \
    shorten_string, get_request, blocked_communities, gibberish, get_request_instance, \
    instance_banned, recently_upvoted_post_replies, recently_upvoted_posts, jaccard_similarity, download_defeds, \
    get_setting, set_setting, get_redis_connection, instance_online, instance_gone_forever, find_next_occurrence, \
    guess_mime_type


def register(app):
    @app.cli.group()
    def translate():
        """Translation and localization commands."""
        pass

    @translate.command()
    @click.argument('lang')
    def init(lang):
        """Initialize a new language."""
        if os.system('pybabel extract -F babel.cfg -k _l -o messages.pot .'):
            raise RuntimeError('extract command failed')
        if os.system(
                'pybabel init -i messages.pot -d app/translations -l ' + lang):
            raise RuntimeError('init command failed')
        os.remove('messages.pot')

    @translate.command()
    def update():
        """Update all languages."""
        if os.system('pybabel extract -F babel.cfg -k _l -o messages.pot .'):
            raise RuntimeError('extract command failed')
        if os.system('pybabel update -i messages.pot -d app/translations'):
            raise RuntimeError('update command failed')
        os.remove('messages.pot')

    @translate.command()
    def compile():
        """Compile all languages."""
        if os.system('pybabel compile -d app/translations'):
            raise RuntimeError('compile command failed')

    @app.cli.command("keys")
    def keys():
        private_key, public_key = RsaKeys.generate_keypair()
        print(private_key)
        print(public_key)

    @app.cli.command("admin-keys")
    def admin_keys():
        private_key, public_key = RsaKeys.generate_keypair()
        u: User = User.query.get(1)
        u.private_key = private_key
        u.public_key = public_key
        db.session.commit()
        print('Admin keys have been reset')

    @app.cli.command("init-db")
    def init_db():
        with app.app_context():
            db.drop_all()
            db.configure_mappers()
            db.create_all()
            private_key, public_key = RsaKeys.generate_keypair()
            db.session.add(Site(name="PieFed", description='Explore Anything, Discuss Everything.', public_key=public_key, private_key=private_key))
            db.session.add(Instance(domain=app.config['SERVER_NAME'], software='PieFed'))   # Instance 1 is always the local instance
            db.session.add(Settings(name='allow_nsfw', value=json.dumps(False)))
            db.session.add(Settings(name='allow_nsfl', value=json.dumps(False)))
            db.session.add(Settings(name='allow_dislike', value=json.dumps(True)))
            db.session.add(Settings(name='allow_local_image_posts', value=json.dumps(True)))
            db.session.add(Settings(name='allow_remote_image_posts', value=json.dumps(True)))
            db.session.add(Settings(name='federation', value=json.dumps(True)))
            db.session.add(Language(name='Undetermined', code='und'))
            db.session.add(Language(name='English', code='en'))
            banned_instances = ['anonib.al','lemmygrad.ml', 'gab.com', 'rqd2.net', 'exploding-heads.com', 'hexbear.net',
                                'threads.net', 'noauthority.social', 'pieville.net', 'links.hackliberty.org',
                                'poa.st', 'freespeechextremist.com', 'bae.st', 'nicecrew.digital', 'detroitriotcity.com',
                                'pawoo.net', 'shitposter.club', 'spinster.xyz', 'catgirl.life', 'gameliberty.club',
                                'yggdrasil.social', 'beefyboys.win', 'brighteon.social', 'cum.salon', 'wizard.casa']
            for bi in banned_instances:
                db.session.add(BannedInstances(domain=bi))
                print("Added banned instance", bi)

            # Load initial domain block list
            block_list = retrieve_block_list()
            if block_list:
                for domain in block_list.split('\n'):
                    db.session.add(Domain(name=domain.strip(), banned=True))
                print("Added 'No-QAnon' blocklist, see https://github.com/rimu/no-qanon")

            # Load peertube domain block list
            block_list = retrieve_peertube_block_list()
            if block_list:
                for domain in block_list.split('\n'):
                    db.session.add(Domain(name=domain.strip(), banned=True))
                    db.session.add(BannedInstances(domain=domain.strip()))
                print("Added 'Peertube Isolation' blocklist, see https://peertube_isolation.frama.io/")

            # Initial roles
            # These roles will create rows in the 'role' table with IDs of 1,2,3,4. There are some constants (ROLE_*) in
            # constants.py that will need to be updated if the role IDs ever change.
            anon_role = Role(name='Anonymous user', weight=0)
            anon_role.permissions.append(RolePermission(permission='register'))
            db.session.add(anon_role)

            auth_role = Role(name='Authenticated user', weight=1)
            db.session.add(auth_role)

            staff_role = Role(name='Staff', weight=2)
            staff_role.permissions.append(RolePermission(permission='approve registrations'))
            staff_role.permissions.append(RolePermission(permission='ban users'))
            staff_role.permissions.append(RolePermission(permission='administer all communities'))
            staff_role.permissions.append(RolePermission(permission='administer all users'))
            db.session.add(staff_role)

            admin_role = Role(name='Admin', weight=3)
            admin_role.permissions.append(RolePermission(permission='approve registrations'))
            admin_role.permissions.append(RolePermission(permission='change user roles'))
            admin_role.permissions.append(RolePermission(permission='ban users'))
            admin_role.permissions.append(RolePermission(permission='manage users'))
            admin_role.permissions.append(RolePermission(permission='change instance settings'))
            admin_role.permissions.append(RolePermission(permission='administer all communities'))
            admin_role.permissions.append(RolePermission(permission='administer all users'))
            db.session.add(admin_role)

            # Admin user
            user_name = input("Admin user name (ideally not 'admin'): ")
            email = input("Admin email address: ")
            password = input("Admin password: ")
            while '@' in user_name or ' ' in user_name:
                print('User name cannot be an email address or have spaces.')
                user_name = input("Admin user name (ideally not 'admin'): ")
            verification_token = random_token(16)
            private_key, public_key = RsaKeys.generate_keypair()
            admin_user = User(user_name=user_name, title=user_name,
                              email=email, verification_token=verification_token,
                              instance_id=1, email_unread_sent=False,
                              private_key=private_key, public_key=public_key,
                              alt_user_name=gibberish(randint(8, 20)))
            admin_user.set_password(password)
            admin_user.roles.append(admin_role)
            admin_user.verified = True
            admin_user.last_seen = utcnow()
            admin_user.ap_profile_id = f"https://{current_app.config['SERVER_NAME']}/u/{admin_user.user_name.lower()}"
            admin_user.ap_public_url = f"https://{current_app.config['SERVER_NAME']}/u/{admin_user.user_name}"
            admin_user.ap_inbox_url = f"https://{current_app.config['SERVER_NAME']}/u/{admin_user.user_name.lower()}/inbox"
            db.session.add(admin_user)

            db.session.commit()
            print("Initial setup is finished.")

    @app.cli.command('daily-maintenance')
    def daily_maintenance():
        with app.app_context():
            # Remove notifications older than 90 days
            db.session.query(Notification).filter(Notification.created_at < utcnow() - timedelta(days=90)).delete()
            db.session.commit()

            # Remove SendQueue older than 7 days
            db.session.query(SendQueue).filter(SendQueue.created < utcnow() - timedelta(days=7)).delete()
            db.session.commit()

            # Remove old content from communities
            print(f'Start removing old content from communities {datetime.now()}')
            communities = Community.query.filter(Community.content_retention > 0).all()
            for community in communities:
                cut_off = utcnow() - timedelta(days=community.content_retention)
                old_posts = Post.query.filter_by(deleted=False, sticky=False, community_id=community.id).filter(Post.posted_at < cut_off).all()
                for post in old_posts:
                    post_delete_post(community, post, post.user_id, federate_all_communities=False)
                    community.post_count -= 1
            db.session.commit()

            # Ensure accurate count of posts associated with each hashtag
            print(f'Ensure accurate count of posts associated with each hashtag {datetime.now()}')
            db.session.execute(text('''
                UPDATE tag 
                SET post_count = (
                    SELECT COUNT(post_tag.post_id)
                    FROM post_tag 
                    WHERE post_tag.tag_id = tag.id
                )
            '''))
            db.session.commit()

            # Delete soft-deleted content after 7 days
            print(f'Delete soft-deleted content {datetime.now()}')
            for post_reply in PostReply.query.filter(PostReply.deleted == True,
                                                     PostReply.posted_at < utcnow() - timedelta(days=7)).all():
                post_reply.delete_dependencies()
                if not post_reply.has_replies():
                    db.session.delete(post_reply)
            db.session.commit()

            for post in Post.query.filter(Post.deleted == True,
                                          Post.posted_at < utcnow() - timedelta(days=7)).all():
                post.delete_dependencies()
                db.session.delete(post)
            db.session.commit()

            # Ensure accurate community stats
            print(f'Ensure accurate community stats {datetime.now()}')
            for community in Community.query.filter(Community.banned == False, Community.last_active > utcnow() - timedelta(days=3)).all():
                community.subscriptions_count = db.session.execute(text('SELECT COUNT(user_id) as c FROM community_member WHERE community_id = :community_id AND is_banned = false'),
                                                          {'community_id': community.id}).scalar()
                community.post_count = db.session.execute(text('SELECT COUNT(id) as c FROM post WHERE deleted is false and community_id = :community_id'),
                                                          {'community_id': community.id}).scalar()
                community.post_reply_count = db.session.execute(text('SELECT COUNT(id) as c FROM post_reply WHERE deleted is false and community_id = :community_id'),
                                                                {'community_id': community.id}).scalar()
                db.session.commit()

            # Delete voting data after 6 months
            print(f'Delete old voting data {datetime.now()}')
            db.session.execute(text('DELETE FROM "post_vote" WHERE created_at < :cutoff'), {'cutoff': utcnow() - timedelta(days=28 * 6)})
            db.session.execute(text('DELETE FROM "post_reply_vote" WHERE created_at < :cutoff'), {'cutoff': utcnow() - timedelta(days=28 * 6)})
            db.session.commit()

            # Un-ban after ban expires
            print(f'Un-ban after ban expires {datetime.now()}')
            db.session.execute(text('UPDATE "user" SET banned = false WHERE banned is true AND banned_until < :cutoff AND banned_until is not null'),
                               {'cutoff': utcnow()})
            db.session.commit()

            # update and sync defederation subscriptions
            print(f'update and sync defederation subscriptions {datetime.now()}')
            db.session.execute(text('DELETE FROM banned_instances WHERE subscription_id is not null'))
            for defederation_sub in DefederationSubscription.query.all():
                download_defeds(defederation_sub.id, defederation_sub.domain)

            # Check for dormant or dead instances
            print(f'Check for dormant or dead instances {datetime.now()}')
            HEADERS = {'Accept': 'application/activity+json'}
            try:
                # Check for instances that have been dormant for 5+ days and mark them as gone_forever
                five_days_ago = utcnow() - timedelta(days=5)
                dormant_instances = Instance.query.filter(Instance.dormant == True, Instance.start_trying_again < five_days_ago).all()
                
                for instance in dormant_instances:
                    instance.gone_forever = True
                db.session.commit()
                
                # Re-check dormant instances that are not gone_forever
                dormant_to_recheck = Instance.query.filter(Instance.dormant == True, Instance.gone_forever == False, Instance.id != 1).all()
                
                for instance in dormant_to_recheck:
                    if instance_banned(instance.domain) or instance.domain == 'flipboard.com':
                        continue
                    
                    try:
                        # Try the nodeinfo endpoint first
                        if instance.nodeinfo_href:
                            node = get_request_instance(instance.nodeinfo_href, headers=HEADERS, instance=instance)
                            if node.status_code == 200:
                                try:
                                    node_json = node.json()
                                    if 'software' in node_json:
                                        instance.software = node_json['software']['name'].lower()[:50]
                                        instance.version = node_json['software']['version'][:50]
                                        instance.failures = 0
                                        instance.dormant = False
                                        current_app.logger.info(f"Dormant instance {instance.domain} is back online")
                                finally:
                                    node.close()
                        else:
                            # If no nodeinfo_href, try to discover it
                            nodeinfo = get_request_instance(f"https://{instance.domain}/.well-known/nodeinfo",
                                                          headers=HEADERS, instance=instance)
                            if nodeinfo.status_code == 200:
                                try:
                                    nodeinfo_json = nodeinfo.json()
                                    for links in nodeinfo_json['links']:
                                        if isinstance(links, dict) and 'rel' in links and links['rel'] in [
                                            'http://nodeinfo.diaspora.software/ns/schema/2.0',
                                            'https://nodeinfo.diaspora.software/ns/schema/2.0',
                                            'http://nodeinfo.diaspora.software/ns/schema/2.1']:
                                            instance.nodeinfo_href = links['href']
                                            instance.failures = 0
                                            instance.dormant = False
                                            current_app.logger.info(f"Dormant instance {instance.domain} is back online")
                                            break
                                finally:
                                    nodeinfo.close()
                    except Exception as e:
                        db.session.rollback()
                        instance.failures += 1
                        current_app.logger.error(f"Error rechecking dormant instance {instance.domain}: {e}")
                
                db.session.commit()

                # Check healthy instances to see if still healthy
                instances = Instance.query.filter(Instance.gone_forever == False, Instance.dormant == False, Instance.id != 1).all()

                for instance in instances:
                    if instance_banned(instance.domain) or instance.domain == 'flipboard.com':
                        continue
                    nodeinfo_href = instance.nodeinfo_href
                    if instance.software == 'lemmy' and instance.version is not None and instance.version >= '0.19.4' and \
                            instance.nodeinfo_href and instance.nodeinfo_href.endswith('nodeinfo/2.0.json'):
                        nodeinfo_href = None

                    if not nodeinfo_href:
                        try:
                            nodeinfo = get_request_instance(f"https://{instance.domain}/.well-known/nodeinfo",
                                                            headers=HEADERS, instance=instance)

                            if nodeinfo.status_code == 200:
                                nodeinfo_json = nodeinfo.json()
                                for links in nodeinfo_json['links']:
                                    if isinstance(links, dict) and 'rel' in links and links['rel'] in [
                                        'http://nodeinfo.diaspora.software/ns/schema/2.0',
                                        'https://nodeinfo.diaspora.software/ns/schema/2.0',
                                        'http://nodeinfo.diaspora.software/ns/schema/2.1']:
                                        instance.nodeinfo_href = links['href']
                                        instance.failures = 0
                                        instance.dormant = False
                                        instance.gone_forever = False
                                        break
                                    else:
                                        instance.failures += 1
                            elif nodeinfo.status_code >= 300:
                                current_app.logger.info(f"{instance.domain} has no well-known/nodeinfo response")
                                instance.failures += 1
                        except Exception:
                            db.session.rollback()
                            instance.failures += 1
                        finally:
                            nodeinfo.close()
                        db.session.commit()

                    if instance.nodeinfo_href:
                        try:
                            node = get_request_instance(instance.nodeinfo_href, headers=HEADERS, instance=instance)
                            if node.status_code == 200:
                                node_json = node.json()
                                if 'software' in node_json:
                                    instance.software = node_json['software']['name'].lower()[:50]
                                    instance.version = node_json['software']['version'][:50]
                                    instance.failures = 0
                                    instance.dormant = False
                                    instance.gone_forever = False
                            elif node.status_code >= 300:
                                instance.nodeinfo_href = None
                                instance.failures += 1
                                instance.most_recent_attempt = utcnow()
                                if instance.failures > 5:
                                    instance.dormant = True
                                    instance.start_trying_again = utcnow() + timedelta(days=5)
                        except Exception:
                            db.session.rollback()
                            instance.failures += 1
                            instance.most_recent_attempt = utcnow()
                            if instance.failures > 5:
                                instance.dormant = True
                                instance.start_trying_again = utcnow() + timedelta(days=5)
                            if instance.failures > 12:
                                instance.gone_forever = True
                        finally:
                            node.close()

                        db.session.commit()
                    else:
                        instance.failures += 1
                        instance.most_recent_attempt = utcnow()
                        if instance.failures > 5:
                            instance.dormant = True
                            instance.start_trying_again = utcnow() + timedelta(days=5)
                        if instance.failures > 12:
                            instance.gone_forever = True
                        db.session.commit()

                    # Handle admin roles
                    if instance.online() and (instance.software == 'lemmy' or instance.software == 'piefed'):
                        try:
                            response = get_request(f'https://{instance.domain}/api/v3/site')
                            if response and response.status_code == 200:
                                instance_data = response.json()
                                admin_profile_ids = []
                                for admin in instance_data['admins']:
                                    profile_id = admin['person']['actor_id']
                                    if profile_id.startswith('https://'):
                                        admin_profile_ids.append(profile_id.lower())
                                        user = find_actor_or_create(profile_id)
                                        if user and not instance.user_is_admin(user.id):
                                            new_instance_role = InstanceRole(instance_id=instance.id, user_id=user.id,
                                                                             role='admin')
                                            db.session.add(new_instance_role)
                                # remove any InstanceRoles that are no longer part of instance-data['admins']
                                for instance_admin in InstanceRole.query.filter_by(instance_id=instance.id):
                                   if instance_admin.user.profile_id() not in admin_profile_ids:
                                       db.session.query(InstanceRole).filter(
                                           InstanceRole.user_id == instance_admin.user.id,
                                           InstanceRole.instance_id == instance.id,
                                           InstanceRole.role == 'admin').delete()
                        except Exception:
                            db.session.rollback()
                            instance.failures += 1
                        finally:
                            if response:
                                response.close()
                        db.session.commit()

            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error in daily maintenance: {e}")

            print(f'Done {datetime.now()}')

    @app.cli.command('send-queue')
    def send_queue():
        with app.app_context():
            # Semaphore to avoid parallel runs of this task
            if get_setting('send-queue-running', False):
                print('Send queue is still running - stopping this process to avoid duplication.')
                return
            set_setting('send-queue-running', True)

            # Check size of redis memory. Abort if > 200 MB used
            try:
                redis = get_redis_connection()
                try:
                    if redis and redis.memory_stats()['total.allocated'] > 200000000:
                        print('Redis memory is quite full - stopping send queue to avoid making it worse.')
                        set_setting('send-queue-running', False)
                        return
                except: # retrieving memory stats fails on recent versions of redis. Once the redis package is fixed this problem should go away.
                    ...
            except:
                print('Could not connect to redis')
                set_setting('send-queue-running', False)
                return

            to_be_deleted = []
            try:
                # Send all waiting Activities that are due to be sent
                for to_send in SendQueue.query.filter(SendQueue.send_after < utcnow()):
                    if instance_online(to_send.destination_domain):
                        if to_send.retries <= to_send.max_retries:
                            send_post_request(to_send.destination, json.loads(to_send.payload), to_send.private_key, to_send.actor,
                                              retries=to_send.retries + 1)
                        to_be_deleted.append(to_send.id)
                    elif instance_gone_forever(to_send.destination_domain):
                        to_be_deleted.append(to_send.id)
                # Remove them once sent - send_post_request will have re-queued them if they failed
                if len(to_be_deleted):
                    db.session.execute(text('DELETE FROM "send_queue" WHERE id IN :to_be_deleted'), {'to_be_deleted': tuple(to_be_deleted)})
                    db.session.commit()

                publish_scheduled_posts()

            except Exception as e:
                set_setting('send-queue-running', False)
                raise e
            finally:
                set_setting('send-queue-running', False)

    @app.cli.command('publish-scheduled-posts')
    def publish_scheduled_posts_command():
        # for dev/debug purposes this is it's own separate cli command but once it's finished we'll want to remove the @app.cli.command decorator
        # so that instance admins don't need to set up another cron job
        publish_scheduled_posts()

    def publish_scheduled_posts():
        with app.app_context():
            for post in Post.query.filter(Post.status == POST_STATUS_SCHEDULED, Post.scheduled_for < utcnow(),
                                          Post.deleted == False):
                post.status = POST_STATUS_PUBLISHED
                if post.repeat and post.repeat != 'none':
                    next_occurrence = post.scheduled_for + find_next_occurrence(post)
                else:
                    next_occurrence = None
                post.scheduled_for = None
                post.posted_at = utcnow()
                post.edited_at = None
                db.session.commit()

                # Federate post
                task_selector('make_post', post_id=post.id)

                # create Notification()s for all the people subscribed to this post.community, post.author, post.topic_id and feed
                notify_about_post(post)

                if next_occurrence:
                    # create new post with new_post.scheduled_for = next_occurrence and new_post.repeat = post.repeat. Call Post.new()
                    ...

    @app.cli.command('move-files-to-s3')
    def move_files_to_s3():
        with app.app_context():
            from app.utils import move_file_to_s3
            import boto3

            print('This will run for a long time, you should run it in a tmux session. Hit Ctrl+C now if not using tmux.')
            sleep(5.0)
            boto3_session = boto3.session.Session()
            s3 = boto3_session.client(
                service_name='s3',
                region_name=current_app.config['S3_REGION'],
                endpoint_url=current_app.config['S3_ENDPOINT'],
                aws_access_key_id=current_app.config['S3_ACCESS_KEY'],
                aws_secret_access_key=current_app.config['S3_ACCESS_SECRET'],
            )
            for community in Community.query.filter(Community.banned == False):
                did_something = False
                if community.icon_id:
                    did_something = True
                    move_file_to_s3(community.icon_id, s3)
                if community.image_id:
                    did_something = True
                    move_file_to_s3(community.image_id, s3)
                if did_something:
                    print(f'Moved image for community {community.link()}')

            for user in User.query.filter(User.deleted == False, User.banned == False, User.last_seen > utcnow() - timedelta(days=180)):
                did_something = False
                if user.avatar_id:
                    did_something = True
                    move_file_to_s3(user.avatar_id, s3)
                if user.cover_id:
                    did_something = True
                    move_file_to_s3(user.cover_id, s3)
                if did_something:
                    print(f'Moved image for user {user.link()}')
            s3.close()
            print('Done')

    @app.cli.command('move-post-images-to-s3')
    def move_post_images_to_s3():
        with app.app_context():
            from app.utils import move_file_to_s3
            import boto3
            processed = 0
            print(f'Beginning move of post images... this could take a long time. Use tmux.')
            local_post_image_ids = list(db.session.execute(text('SELECT image_id FROM "post" WHERE deleted is false and image_id is not null and instance_id = 1 ORDER BY id DESC')).scalars())
            remote_post_image_ids = list(db.session.execute(text('SELECT image_id FROM "post" WHERE deleted is false and image_id is not null and instance_id != 1 ORDER BY id DESC')).scalars())
            boto3_session = boto3.session.Session()
            s3 = boto3_session.client(
                service_name='s3',
                region_name=current_app.config['S3_REGION'],
                endpoint_url=current_app.config['S3_ENDPOINT'],
                aws_access_key_id=current_app.config['S3_ACCESS_KEY'],
                aws_secret_access_key=current_app.config['S3_ACCESS_SECRET'],
            )
            for post_image_id in local_post_image_ids:
                move_file_to_s3(post_image_id, s3)
                processed += 1
                if processed % 5:
                    print(processed)

            print('Finished moving local post images, doing remote ones now...')
            for post_image_id in remote_post_image_ids:
                move_file_to_s3(post_image_id, s3)
                processed += 1
                if processed % 5:
                    print(processed)
            s3.close()
            print('Done')

    @app.cli.command('move-more-post-images-to-s3')
    def move_more_post_images_to_s3():
        with app.app_context():
            import boto3
            server_name = current_app.config['SERVER_NAME']
            boto3_session = boto3.session.Session()
            s3 = boto3_session.client(
                service_name='s3',
                region_name=current_app.config['S3_REGION'],
                endpoint_url=current_app.config['S3_ENDPOINT'],
                aws_access_key_id=current_app.config['S3_ACCESS_KEY'],
                aws_secret_access_key=current_app.config['S3_ACCESS_SECRET'],
            )

            file_ids = list(db.session.execute(text(f'select id from "file" where source_url like \'https://{server_name}/static%\'')).scalars())
            for file_id in file_ids:
                file = File.query.get(file_id)
                content_type = guess_mime_type(file.source_url)
                new_path = file.source_url.replace('/static/media/', f"/")
                s3_path = new_path.replace(f'https://{server_name}/', '')
                new_path = new_path.replace(server_name, current_app.config['S3_PUBLIC_URL'])
                local_file = file.source_url.replace(f'https://{server_name}/static/media/', 'app/static/media/')
                if os.path.isfile(local_file):
                    try:
                        s3.upload_file(local_file, current_app.config['S3_BUCKET'], s3_path,
                                       ExtraArgs={'ContentType': content_type})
                    except Exception as e:
                        print(f"Error uploading {local_file}: {e}")
                    os.unlink(local_file)
                    file.source_url = new_path
                    print(new_path)
                else:
                    print('Could not find ' + local_file)

                db.session.commit()
        print('Done')

    @app.cli.command("spaceusage")
    def spaceusage():
        with app.app_context():
            for user in User.query.all():
                filesize = user.filesize()
                num_content = user.num_content()
                if filesize > 0 and num_content > 0:
                    print(f'{user.id},"{user.ap_id}",{filesize},{num_content}')

    def list_files(directory):
        for root, dirs, files in os.walk(directory):
            for file in files:
                yield os.path.join(root, file)

    @app.cli.command("remove_orphan_files")
    def remove_orphan_files():
        """ Any user-uploaded file that does not have a corresponding entry in the File table should be deleted """
        with app.app_context():
            for file_path in list_files('app/static/media/users'):
                if 'thumbnail' in file_path:
                    f = File.query.filter(File.thumbnail_path == file_path).first()
                else:
                    f = File.query.filter(File.file_path == file_path).first()
                if f is None:
                    os.unlink(file_path)

    @app.cli.command("send_missed_notifs")
    def send_missed_notifs():
        with app.app_context():
            site = Site.query.get(1)
            users_to_notify = User.query.join(Notification, User.id == Notification.user_id).filter(
                User.ap_id == None,
                Notification.created_at > User.last_seen,
                Notification.read == False,
                User.email_unread_sent == False,  # they have not been emailed since last activity
                User.email_unread == True  # they want to be emailed
            ).all()

            for user in users_to_notify:
                notifications = Notification.query.filter(Notification.user_id == user.id, Notification.read == False,
                                                          Notification.created_at > user.last_seen).all()
                if notifications:
                    # Also get the top 20 posts since their last login
                    posts = Post.query.join(CommunityMember, Post.community_id == CommunityMember.community_id).filter(
                        CommunityMember.is_banned == False)
                    posts = posts.filter(CommunityMember.user_id == user.id)
                    if user.ignore_bots == 1:
                        posts = posts.filter(Post.from_bot == False)
                    if user.hide_nsfl == 1:
                        posts = posts.filter(Post.nsfl == False)
                    if user.hide_nsfw == 1:
                        posts = posts.filter(Post.nsfw == False)
                    domains_ids = blocked_domains(user.id)
                    if domains_ids:
                        posts = posts.filter(or_(Post.domain_id.not_in(domains_ids), Post.domain_id == None))
                    community_ids = blocked_communities(user.id)
                    if community_ids:
                        posts = posts.filter(Post.community_id.not_in(community_ids))
                    posts = posts.filter(Post.posted_at > user.last_seen).order_by(desc(Post.score))
                    posts = posts.limit(20).all()

                    # Send email!
                    send_email(_('[PieFed] You have unread notifications'),
                               sender=f'{site.name} <{current_app.config["MAIL_FROM"]}>',
                               recipients=[user.email],
                               text_body=flask.render_template('email/unread_notifications.txt', user=user,
                                                               notifications=notifications),
                               html_body=flask.render_template('email/unread_notifications.html', user=user,
                                                               notifications=notifications,
                                                               posts=posts,
                                                               domain=current_app.config['SERVER_NAME']))
                    user.email_unread_sent = True
                    db.session.commit()

    @app.cli.command("process_email_bounces")
    def process_email_bounces():
        with app.app_context():
            import email

            imap_host = current_app.config['BOUNCE_HOST']
            imap_user = current_app.config['BOUNCE_USERNAME']
            imap_pass = current_app.config['BOUNCE_PASSWORD']
            something_deleted = False

            if imap_host:

                # connect to host using SSL
                imap = imaplib.IMAP4_SSL(imap_host, port=993)

                ## login to server
                imap.login(imap_user, imap_pass)

                imap.select('Inbox')

                tmp, data = imap.search(None, 'ALL')
                rgx = r'[\w\.-]+@[\w\.-]+'

                emails = set()

                for num in data[0].split():
                    tmp, data = imap.fetch(num, '(RFC822)')
                    email_message = email.message_from_bytes(data[0][1])
                    match = []
                    if not isinstance(email_message._payload, str):
                        if isinstance(email_message._payload[0]._payload, str):
                            payload = email_message._payload[0]._payload.replace("\n", " ").replace("\r", " ")
                            match = re.findall(rgx, payload)
                        elif isinstance(email_message._payload[0]._payload, list):
                            if isinstance(email_message._payload[0]._payload[0]._payload, str):
                                payload = email_message._payload[0]._payload[0]._payload.replace("\n", " ").replace("\r", " ")
                                match = re.findall(rgx, payload)

                        for m in match:
                            if current_app.config['SERVER_NAME'] not in m and current_app.config['SERVER_NAME'].upper() not in m:
                                emails.add(m)
                                print(str(num) + ' ' + m)

                    imap.store(num, '+FLAGS', '\\Deleted')
                    something_deleted = True

                if something_deleted:
                    imap.expunge()
                    pass

                imap.close()

                # Keep track of how many times email to an account has bounced. After 2 bounces, disable email sending to them
                for bounced_email in emails:
                    bounced_accounts = User.query.filter_by(email=bounced_email).all()
                    for account in bounced_accounts:
                        if account.bounces is None:
                            account.bounces = 0
                        if account.bounces > 2:
                            account.newsletter = False
                            account.email_unread = False
                        else:
                            account.bounces += 1
                    db.session.commit()

    @app.cli.command("clean_up_old_activities")
    def clean_up_old_activities():
        with app.app_context():
            db.session.query(ActivityPubLog).filter(ActivityPubLog.created_at < utcnow() - timedelta(days=3)).delete()
            db.session.commit()

    @app.cli.command("detect_vote_manipulation")
    def detect_vote_manipulation():
        with app.app_context():
            print('Getting user ids...')
            all_user_ids = [user.id for user in User.query.filter(User.last_seen > datetime.utcnow() - timedelta(days=7))]
            print('Checking...')
            for i, first_user_id in enumerate(all_user_ids):
                current_user_upvoted_posts = ['post/' + str(id) for id in recently_upvoted_posts(first_user_id)]
                current_user_upvoted_replies = ['reply/' + str(id) for id in recently_upvoted_post_replies(first_user_id)]

                current_user_upvotes = set(current_user_upvoted_posts + current_user_upvoted_replies)
                if len(current_user_upvotes) > 12:
                    print(i)
                    for j in range(i + 1, len(all_user_ids)):
                        other_user_id = all_user_ids[j]
                        if jaccard_similarity(current_user_upvotes, other_user_id) >= 95:
                            first_user = User.query.get(first_user_id)
                            other_user = User.query.get(other_user_id)
                            print(f'{first_user.link()} votes the same as {other_user.link()}')

    @app.cli.command("migrate_community_notifs")
    def migrate_community_notifs():
        with app.app_context():
            member_infos = CommunityMember.query.filter(CommunityMember.notify_new_posts == True,
                                                       CommunityMember.is_banned == False).all()
            for member_info in member_infos:
                new_notification = NotificationSubscription(user_id=member_info.user_id, entity_id=member_info.community_id,
                                                            type=NOTIF_COMMUNITY)
                db.session.add(new_notification)
            db.session.commit()
            print('Done')

    @app.cli.command("migrate_post_notifs")
    def migrate_post_notifs():
        with app.app_context():
            posts = Post.query.filter(Post.notify_author == True).all()
            for post in posts:
                new_notification = NotificationSubscription(name=shorten_string(_('Replies to my post %(post_title)s',
                                                                              post_title=post.title)),
                                                            user_id=post.user_id, entity_id=post.id,
                                                            type=NOTIF_POST)
                db.session.add(new_notification)
            db.session.commit()

            post_replies = PostReply.query.filter(PostReply.notify_author == True).all()
            for reply in post_replies:
                new_notification = NotificationSubscription(name=shorten_string(_('Replies to my comment on %(post_title)s',
                                                                              post_title=reply.post.title)),
                                                            user_id=post.user_id, entity_id=reply.id,
                                                            type=NOTIF_REPLY)
                db.session.add(new_notification)
            db.session.commit()

            print('Done')

    @app.cli.command("populate_community_search")
    def populate_community_search():
        with app.app_context():
            # pull down the community.full.json
            print('Pulling in the lemmyverse data ...')
            resp = get_request('https://data.lemmyverse.net/data/community.full.json')
            community_json = resp.json()
            resp.close()

            # get the banned urls list
            print('Getting the banned domains list ...')
            banned_urls = list(db.session.execute(text('SELECT domain FROM "banned_instances"')).scalars())
                        
            # iterate over the entries and get out the url and the nsfw status in a new list
            print('Generating the communities lists ...')
            all_communities = []
            all_sfw_communities = []
            for c in community_json:
                # skip if the domain is banned
                if c['baseurl'] in banned_urls:
                    continue

                # sort out any that have less than 50 posts
                elif c['counts']['posts'] < 50:
                    continue

                # sort out any that do not have greater than 10 active users over the past week
                elif c['counts']['users_active_week'] < 10:
                    continue

                # sort out the 'seven things you can't say on tv' names (cursewords), plus some
                # "low effort" communities
                seven_things_plus = [
                    'shit', 'piss', 'fuck',
                    'cunt', 'cocksucker', 'motherfucker', 'tits',
                    'piracy', '196', 'greentext', 'usauthoritarianism',
                    'enoughmuskspam', 'political_weirdos', '4chan'
                    ]
                if any(badword in c['name'].lower() for badword in seven_things_plus):
                    continue
        
                # convert the url to server, community
                server, community = extract_domain_and_actor(c['url'])
                
                # if the community is nsfw append to the all_communites only, if sfw, append to both
                if c['nsfw']:
                    all_communities.append(f'{community}@{server}')
                else:
                    all_communities.append(f'{community}@{server}')
                    all_sfw_communities.append(f'{community}@{server}')
            
            # add those lists to dicts
            all_communities_json = {}
            all_sfw_communities_json = {}
            all_communities_json['all_communities'] = all_communities
            all_sfw_communities_json['all_sfw_communities'] = all_sfw_communities

            # write those files to disk as json
            print('Saving the communities lists to app/static/ ...')
            with open('app/static/all_communities.json','w') as acj:
                json.dump(all_communities_json, acj)

            with open('app/static/all_sfw_communities.json','w') as asfwcj:
                json.dump(all_sfw_communities_json, asfwcj)

            print('Done!')

    @app.cli.command("populate_post_reply_for_api")
    def populate_post_reply_for_api():
        with app.app_context():
            sql = '''WITH RECURSIVE reply_path AS (
                        -- Base case: each reply starts with its own ID
                        SELECT
                            id,
                            parent_id,
                            ARRAY[0, id] AS path
                        FROM post_reply
                        WHERE parent_id IS NULL  -- Top-level replies
                    
                        UNION ALL
                    
                        -- Recursive case: build the path from parent replies
                        SELECT
                            pr.id,
                            pr.parent_id,
                            rp.path || pr.id  -- Append current reply ID to the parent's path
                        FROM post_reply pr
                        JOIN reply_path rp ON pr.parent_id = rp.id
                    )
                    UPDATE post_reply
                    SET path = reply_path.path
                    FROM reply_path
                    WHERE post_reply.id = reply_path.id;
                    '''
            db.session.execute(text(sql))
            db.session.commit()

            db.session.execute(text('update post_reply set child_count = 0'))

            sql = '''WITH unnested_paths AS (
                        SELECT
                            UNNEST(path[2:array_length(path, 1) - 1]) AS parent_id  -- Exclude the last element (self)
                        FROM post_reply
                        WHERE array_length(path, 1) > 2  -- Ensure the path contains at least one parent
                    ),
                    child_counts AS (
                        SELECT
                            parent_id,
                            COUNT(*) AS child_count
                        FROM unnested_paths
                        GROUP BY parent_id
                    )
                    UPDATE post_reply
                    SET child_count = COALESCE(child_counts.child_count, 0)
                    FROM child_counts
                    WHERE post_reply.id = child_counts.parent_id;'''
            db.session.execute(text(sql))
            db.session.commit()

            sql = 'UPDATE post_reply SET root_id = path[1] WHERE path IS NOT NULL;'
            db.session.execute(text(sql))
            db.session.commit()

            print('Done!')


def parse_communities(interests_source, segment):
    lines = interests_source.split("\n")
    include_in_output = False
    output = []

    for line in lines:
        line = line.strip()
        if line == segment:
            include_in_output = True
            continue
        elif line == '':
            include_in_output = False
        if include_in_output:
            output.append(line)

    return "\n".join(output)
