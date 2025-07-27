# PeachPie Quick Start Guide

This guide will help you get a PeachPie instance running quickly for development or testing.

## Prerequisites

- Python 3.13+
- PostgreSQL 15+
- Redis 7+
- Docker & Docker Compose (optional, recommended)

## Quick Start (Docker)

The fastest way to get started is using our quick start script:

```bash
# Make the script executable
chmod +x scripts/quickstart.sh

# Run the quick start
./scripts/quickstart.sh
```

This will:
1. Start PostgreSQL and Redis using Docker
2. Initialize the database with schema and seed data
3. Create an admin user
4. Generate secure passwords
5. Save configuration to `.env.dev`

## Manual Setup

### 1. Start Dependencies

If using Docker:
```bash
docker-compose -f docker-compose.dev.yml up -d db redis
```

Or install PostgreSQL and Redis locally.

### 2. Configure Environment

Create a `.env` file:
```env
# Required
SERVER_NAME=localhost:5000
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgresql://peachpie:peachpie@localhost:5432/peachpie
REDIS_URL=redis://localhost:6379/0

# Admin credentials (for non-interactive setup)
ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=secure-password

# Optional
SITE_NAME=PeachPie
SITE_DESCRIPTION=A modern ActivityPub platform
```

### 3. Initialize Database

Interactive mode (prompts for admin credentials):
```bash
python scripts/init_db.py
```

Non-interactive mode (uses environment variables):
```bash
python scripts/init_db.py --non-interactive
```

Skip blocklists for faster setup:
```bash
python scripts/init_db.py --skip-blocklists
```

### 4. Run Migrations

The init script handles migrations, but you can also run them manually:
```bash
flask db upgrade
```

### 5. Start the Application

Terminal 1 - Web Server:
```bash
flask run
```

Terminal 2 - Federation Worker:
```bash
python -m app.federation.processor
```

### 6. Access Your Instance

- Web interface: http://localhost:5000
- Admin panel: http://localhost:5000/admin
- Monitoring: http://localhost:5000/monitoring/ (admin only)

## Docker Compose Profiles

The development docker-compose includes optional tools:

```bash
# Start with monitoring tools
docker-compose -f docker-compose.dev.yml --profile tools up -d

# Access tools
# Redis Commander: http://localhost:8081
# pgAdmin: http://localhost:8082
```

## Production Setup

For production deployment:

1. Use environment variables instead of `.env` files
2. Set `FLASK_ENV=production` and `FLASK_DEBUG=0`
3. Use proper domain name in `SERVER_NAME`
4. Generate strong `SECRET_KEY` (at least 32 characters)
5. Set up proper PostgreSQL credentials
6. Configure email settings
7. Set up reverse proxy (nginx/caddy)
8. Enable HTTPS

## Troubleshooting

### Database Connection Failed
- Ensure PostgreSQL is running
- Check DATABASE_URL format
- Verify credentials

### Redis Connection Failed
- Ensure Redis is running
- Check REDIS_URL format
- Verify Redis is accessible

### Migration Errors
- Drop and recreate database if needed
- Check for pending migrations: `flask db current`
- Review migration files in `migrations/versions/`

### Federation Issues
- Ensure federation worker is running
- Check `/monitoring/` dashboard
- Verify SERVER_NAME matches your domain

## Next Steps

1. Configure your instance settings at `/admin`
2. Create communities
3. Invite users or open registration
4. Monitor federation at `/monitoring/`
5. Read the full documentation