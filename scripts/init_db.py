#!/usr/bin/env python3
"""
Modernized database initialization script for PeachPie.

This script handles proper sequencing of database operations:
1. Waits for PostgreSQL to be ready
2. Creates database if needed
3. Runs migrations
4. Seeds initial data

Can run in interactive or non-interactive mode for automation.
"""

import os
import sys
import time
import click
from urllib.parse import urlparse
import psycopg2
from psycopg2 import sql
import secrets
import string

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from flask_migrate import upgrade
from app.models import Site, Instance, Settings, BannedInstances, Domain, Language, Role, RolePermission, User
from app.activitypub.signature import RsaKeys
from app.utils import retrieve_block_list, retrieve_peertube_block_list


def wait_for_postgres(database_url: str, max_attempts: int = 30) -> bool:
    """
    Wait for PostgreSQL to be ready.
    
    Args:
        database_url: PostgreSQL connection URL
        max_attempts: Maximum number of connection attempts
        
    Returns:
        True if connection successful, False otherwise
    """
    parsed = urlparse(database_url)
    
    # Extract connection parameters
    host = parsed.hostname or 'localhost'
    port = parsed.port or 5432
    user = parsed.username or 'postgres'
    password = parsed.password or ''
    
    click.echo(f"Waiting for PostgreSQL at {host}:{port}...")
    
    for attempt in range(max_attempts):
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname='postgres',  # Connect to default db first
                connect_timeout=5
            )
            conn.close()
            click.echo("✓ PostgreSQL is ready")
            return True
        except psycopg2.OperationalError:
            if attempt < max_attempts - 1:
                time.sleep(1)
                sys.stdout.write('.')
                sys.stdout.flush()
            else:
                click.echo("\n✗ PostgreSQL connection failed")
                return False
    
    return False


def create_database_if_needed(database_url: str) -> bool:
    """
    Create the database if it doesn't exist.
    
    Args:
        database_url: PostgreSQL connection URL
        
    Returns:
        True if database exists or was created, False on error
    """
    parsed = urlparse(database_url)
    
    # Extract connection parameters
    host = parsed.hostname or 'localhost'
    port = parsed.port or 5432
    user = parsed.username or 'postgres'
    password = parsed.password or ''
    dbname = parsed.path.lstrip('/')
    
    if not dbname:
        click.echo("✗ No database name found in DATABASE_URL")
        return False
    
    try:
        # Connect to postgres database to check/create target db
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname='postgres'
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        # Check if database exists
        cur.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (dbname,)
        )
        
        if cur.fetchone():
            click.echo(f"✓ Database '{dbname}' already exists")
        else:
            click.echo(f"Creating database '{dbname}'...")
            cur.execute(sql.SQL("CREATE DATABASE {}").format(
                sql.Identifier(dbname)
            ))
            click.echo(f"✓ Database '{dbname}' created")
        
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        click.echo(f"✗ Database error: {e}")
        return False


def run_migrations(app) -> bool:
    """
    Run database migrations using Flask-Migrate.
    
    Args:
        app: Flask application instance
        
    Returns:
        True if successful, False otherwise
    """
    click.echo("Running database migrations...")
    
    try:
        with app.app_context():
            # Check if this is a fresh database
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            if 'alembic_version' not in tables:
                click.echo("Fresh database detected, initializing migration system...")
                
                # Drop any stray views that might interfere
                try:
                    db.session.execute(db.text('DROP VIEW IF EXISTS ap_request_combined CASCADE'))
                    db.session.execute(db.text('DROP VIEW IF EXISTS ap_request_summary CASCADE'))
                    db.session.execute(db.text('DROP VIEW IF EXISTS ap_request_status_incomplete CASCADE'))
                    db.session.execute(db.text('DROP VIEW IF EXISTS ap_request_status_last CASCADE'))
                    db.session.commit()
                except:
                    db.session.rollback()
            
            # Run migrations
            upgrade()
            click.echo("✓ Database migrations completed")
            return True
            
    except Exception as e:
        click.echo(f"✗ Migration error: {e}")
        return False


def validate_environment():
    """
    Validate required environment variables.
    
    Returns:
        Tuple of (is_valid, missing_vars)
    """
    required_vars = ['DATABASE_URL', 'SECRET_KEY', 'SERVER_NAME']
    missing = [var for var in required_vars if not os.environ.get(var)]
    
    return len(missing) == 0, missing


def generate_secure_password(length: int = 16) -> str:
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits + string.punctuation
    # Remove problematic characters
    alphabet = alphabet.replace("'", "").replace('"', "").replace("\\", "")
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def seed_initial_data(app, admin_username: str, admin_email: str, admin_password: str,
                     site_name: str, site_description: str, skip_blocklists: bool = False):
    """
    Seed the database with initial data.
    
    Args:
        app: Flask application instance
        admin_username: Admin username
        admin_email: Admin email
        admin_password: Admin password
        site_name: Name of the site
        site_description: Site description
        skip_blocklists: Whether to skip loading blocklists
    """
    with app.app_context():
        click.echo("Seeding initial data...")
        
        # Check if already initialized
        if Site.query.first():
            click.echo("✓ Database already initialized, skipping seed data")
            return
        
        # Generate site keys
        private_key, public_key = RsaKeys.generate_keypair()
        
        # Create site
        site = Site(
            name=site_name,
            description=site_description,
            public_key=public_key,
            private_key=private_key,
            language_id=2  # English
        )
        db.session.add(site)
        
        # Create local instance
        instance = Instance(
            domain=app.config['SERVER_NAME'],
            software=os.environ.get('SOFTWARE_NAME', 'PeachPie')
        )
        db.session.add(instance)
        
        # Add settings
        settings_data = [
            ('allow_nsfw', False),
            ('allow_nsfl', False),
            ('allow_dislike', True),
            ('allow_local_image_posts', True),
            ('allow_remote_image_posts', True),
            ('federation', True)
        ]
        
        for name, value in settings_data:
            db.session.add(Settings(name=name, value=json.dumps(value)))
        
        # Add languages
        languages = [
            ('und', 'Undetermined'),
            ('en', 'English'),
            ('de', 'Deutsch'),
            ('es', 'Español'),
            ('fr', 'Français'),
            ('hi', 'हिन्दी'),
            ('ja', '日本語'),
            ('zh', '中文')
        ]
        
        for code, name in languages:
            db.session.add(Language(code=code, name=name))
        
        # Create roles
        roles_data = [
            ('Anonymous user', 0, []),
            ('Authenticated user', 1, []),
            ('Staff', 2, [
                'approve registrations',
                'ban users',
                'administer all communities',
                'administer all users'
            ]),
            ('Admin', 3, [
                'approve registrations',
                'change user roles',
                'ban users',
                'manage users',
                'change instance settings',
                'administer all communities',
                'administer all users',
                'edit cms pages'
            ])
        ]
        
        roles = {}
        for name, weight, permissions in roles_data:
            role = Role(name=name, weight=weight)
            for perm in permissions:
                role.permissions.append(RolePermission(permission=perm))
            db.session.add(role)
            roles[name] = role
        
        # Load blocklists unless skipped
        if not skip_blocklists:
            click.echo("Loading blocklists...")
            
            # Default banned instances
            default_banned = [
                'anonib.al', 'lemmygrad.ml', 'gab.com', 'rqd2.net', 
                'exploding-heads.com', 'hexbear.net', 'threads.net',
                'noauthority.social', 'pieville.net', 'links.hackliberty.org',
                'poa.st', 'freespeechextremist.com', 'bae.st', 
                'nicecrew.digital', 'detroitriotcity.com', 'pawoo.net',
                'shitposter.club', 'spinster.xyz', 'catgirl.life',
                'gameliberty.club', 'yggdrasil.social', 'beefyboys.win',
                'brighteon.social', 'cum.salon', 'wizard.casa'
            ]
            
            for domain in default_banned:
                db.session.add(BannedInstances(domain=domain))
            
            # Load external blocklists
            try:
                block_list = retrieve_block_list()
                if block_list:
                    for domain in block_list.split('\n'):
                        domain = domain.strip()
                        if domain:
                            db.session.add(Domain(name=domain, banned=True))
                    click.echo("✓ Loaded 'No-QAnon' blocklist")
            except:
                click.echo("⚠ Could not load 'No-QAnon' blocklist")
            
            try:
                block_list = retrieve_peertube_block_list()
                if block_list:
                    for domain in block_list.split('\n'):
                        domain = domain.strip()
                        if domain:
                            db.session.add(Domain(name=domain, banned=True))
                            db.session.add(BannedInstances(domain=domain))
                    click.echo("✓ Loaded 'Peertube Isolation' blocklist")
            except:
                click.echo("⚠ Could not load 'Peertube Isolation' blocklist")
        
        # Create admin user
        click.echo(f"Creating admin user '{admin_username}'...")
        
        private_key, public_key = RsaKeys.generate_keypair()
        admin_user = User(
            user_name=admin_username,
            title=admin_username,
            email=admin_email,
            verification_token=secrets.token_urlsafe(16),
            instance_id=1,
            email_unread_sent=False,
            private_key=private_key,
            public_key=public_key,
            verified=True,
            ap_profile_id=f"https://{app.config['SERVER_NAME']}/u/{admin_username.lower()}",
            ap_public_url=f"https://{app.config['SERVER_NAME']}/u/{admin_username}",
            ap_inbox_url=f"https://{app.config['SERVER_NAME']}/u/{admin_username.lower()}/inbox"
        )
        admin_user.set_password(admin_password)
        admin_user.roles.append(roles['Admin'])
        admin_user.last_seen = datetime.now(timezone.utc)
        
        db.session.add(admin_user)
        
        # Commit all changes
        db.session.commit()
        
        click.echo("✓ Initial data seeded successfully")


@click.command()
@click.option('--non-interactive', is_flag=True, help='Run in non-interactive mode (requires env vars)')
@click.option('--skip-blocklists', is_flag=True, help='Skip loading external blocklists')
@click.option('--force', is_flag=True, help='Force recreation of existing data')
def init_db(non_interactive, skip_blocklists, force):
    """Initialize the database with proper sequencing."""
    
    click.echo(f"{os.environ.get('SOFTWARE_NAME', 'PeachPie')} Database Initialization")
    click.echo("=" * 40)
    
    # Validate environment
    valid, missing = validate_environment()
    if not valid:
        click.echo(f"✗ Missing required environment variables: {', '.join(missing)}")
        click.echo("\nRequired variables:")
        click.echo("  DATABASE_URL - PostgreSQL connection string")
        click.echo("  SECRET_KEY - Secret key for sessions")
        click.echo("  SERVER_NAME - Domain name of this instance")
        sys.exit(1)
    
    # Get database URL
    database_url = os.environ.get('DATABASE_URL')
    
    # Wait for PostgreSQL
    if not wait_for_postgres(database_url):
        click.echo("✗ Could not connect to PostgreSQL")
        sys.exit(1)
    
    # Create database if needed
    if not create_database_if_needed(database_url):
        click.echo("✗ Could not create database")
        sys.exit(1)
    
    # Create Flask app
    app = create_app()
    
    # Run migrations
    if not run_migrations(app):
        click.echo("✗ Database migration failed")
        sys.exit(1)
    
    # Get initialization parameters
    if non_interactive:
        # Non-interactive mode - require all env vars
        admin_username = os.environ.get('ADMIN_USERNAME')
        admin_email = os.environ.get('ADMIN_EMAIL')
        admin_password = os.environ.get('ADMIN_PASSWORD')
        site_name = os.environ.get('SITE_NAME', os.environ.get('SOFTWARE_NAME', 'PeachPie'))
        site_description = os.environ.get('SITE_DESCRIPTION', 'Explore Anything, Discuss Everything.')
        
        if not all([admin_username, admin_email, admin_password]):
            click.echo("✗ Non-interactive mode requires ADMIN_USERNAME, ADMIN_EMAIL, and ADMIN_PASSWORD")
            sys.exit(1)
    else:
        # Interactive mode
        click.echo("\nAdmin User Configuration")
        click.echo("-" * 40)
        click.echo("Create an admin user for instance administration.")
        click.echo("This should not be your primary daily account.\n")
        
        admin_username = click.prompt('Admin username', default='admin')
        admin_email = click.prompt('Admin email')
        
        # Validate email
        while '@' not in admin_email or len(admin_email) > 320:
            click.echo("Invalid email address")
            admin_email = click.prompt('Admin email')
        
        # Validate username
        while '@' in admin_username or ' ' in admin_username:
            click.echo("Username cannot contain @ or spaces")
            admin_username = click.prompt('Admin username', default='admin')
        
        # Password prompt with generation option
        if click.confirm('Generate secure password?', default=True):
            admin_password = generate_secure_password()
            click.echo(f"\nGenerated password: {admin_password}")
            click.echo("⚠️  Save this password now - it won't be shown again!\n")
            click.pause('Press any key to continue...')
        else:
            admin_password = click.prompt('Admin password', hide_input=True,
                                        confirmation_prompt=True)
        
        # Site configuration
        click.echo("\nSite Configuration")
        click.echo("-" * 40)
        site_name = click.prompt('Site name', default=os.environ.get('SOFTWARE_NAME', 'PeachPie'))
        site_description = click.prompt('Site description', 
                                       default='Explore Anything, Discuss Everything.')
    
    # Seed initial data
    try:
        seed_initial_data(
            app,
            admin_username=admin_username,
            admin_email=admin_email,
            admin_password=admin_password,
            site_name=site_name,
            site_description=site_description,
            skip_blocklists=skip_blocklists
        )
    except Exception as e:
        click.echo(f"✗ Error seeding data: {e}")
        sys.exit(1)
    
    # Success!
    click.echo("\n" + "=" * 40)
    click.echo("✓ Database initialization complete!")
    click.echo("=" * 40)
    click.echo(f"\nYour PeachPie instance is ready at: https://{app.config['SERVER_NAME']}")
    click.echo(f"Admin login: {admin_username}")
    if non_interactive:
        click.echo("\nAdmin password was set from ADMIN_PASSWORD environment variable")
    click.echo("\nNext steps:")
    click.echo("1. Start the web server")
    click.echo("2. Start the federation worker")
    click.echo("3. Visit /admin to configure your instance")


if __name__ == '__main__':
    # Add missing imports when run as script
    import json
    from datetime import datetime, timezone
    
    init_db()