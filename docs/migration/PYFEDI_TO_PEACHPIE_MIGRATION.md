# PyFedi to PeachPie Migration Guide

This guide helps you migrate an existing PyFedi instance to PeachPie.

## Overview

PeachPie is a fork of PyFedi that maintains full federation compatibility while adding:
- Python 3.13 support with comprehensive type annotations
- Redis Streams replacing Celery for better performance
- Enhanced security features
- Improved database schema
- Modern development workflow

## Migration Steps

### 1. Backup Your Data

**CRITICAL**: Always backup your database before migration!

```bash
# PostgreSQL backup
pg_dump -U your_user -h localhost your_database > pyfedi_backup_$(date +%Y%m%d).sql

# Also backup your .env file and any uploaded media
cp .env .env.backup
tar -czf media_backup_$(date +%Y%m%d).tar.gz media/
```

### 2. Update Environment Variables

Add these new environment variables to your `.env` file:

```env
# Software branding (maintains PyFedi compatibility)
SOFTWARE_NAME=PeachPie
SOFTWARE_REPO=https://github.com/theatl-social/peachpie
SOFTWARE_VERSION=1.0.1  # Optional, defaults to version in constants.py

# Consolidated Redis URL (replaces CACHE_REDIS_URL, CELERY_BROKER_URL, RESULT_BACKEND)
REDIS_URL=redis://localhost:6379/0
```

### 3. Run Database Migration

The migration script will:
- Fix URL field lengths (critical for long ActivityPub URLs)
- Add performance indexes
- Create federation error tracking table
- Update software identification

```bash
# Pull latest code
git pull origin main

# Install dependencies
pip install -r requirements.txt

# Run migration
flask db upgrade 8272566919f0
```

### 4. Update Configuration

The software will now identify as "PeachPie" in:
- User-Agent headers for federation
- Instance software identification
- Admin interfaces

However, it maintains full PyFedi protocol compatibility.

### 5. Restart Services

```bash
# Stop old services
sudo systemctl stop pyfedi-web pyfedi-worker

# Start new services
sudo systemctl start peachpie-web peachpie-federation
```

## What Changes

### User-Facing Changes
- Software identifies as "PeachPie" instead of "PieFed"
- Improved performance from Redis Streams
- Better error handling and monitoring

### Technical Changes
- Database schema improvements (see migration script)
- Type-safe Python 3.13 codebase
- Redis Streams instead of Celery
- Enhanced security features

### Federation Compatibility
- Fully compatible with PyFedi/PieFed instances
- No changes to ActivityPub protocol implementation
- Existing federations remain intact

## Rollback Procedure

If you need to rollback:

```bash
# Restore database
psql -U your_user -h localhost your_database < pyfedi_backup_YYYYMMDD.sql

# Restore old code
git checkout your-previous-branch

# Restore environment
cp .env.backup .env

# Restart old services
sudo systemctl start pyfedi-web pyfedi-worker
```

## Environment Variables Reference

### Required Variables
- `SOFTWARE_NAME` - Software name shown in UI and federation (default: PeachPie)
- `SOFTWARE_REPO` - Repository URL for User-Agent (default: https://github.com/theatl-social/peachpie)
- `SOFTWARE_VERSION` - Software version (optional, defaults to version in constants.py)
- `REDIS_URL` - Single Redis connection URL (replaces CACHE_REDIS_URL, CELERY_BROKER_URL, etc)

### Optional Variables
All existing PyFedi environment variables are still supported.

## Monitoring the Migration

Check these after migration:
1. Federation is working: `/admin/federation`
2. No errors in logs: `journalctl -u peachpie-web -f`
3. Database queries are fast: Check slow query log
4. Redis is healthy: `redis-cli ping`

## Getting Help

- GitHub Issues: https://github.com/theatl-social/peachpie/issues
- Migration Support: See SUPPORT.md

## FAQ

**Q: Will this break federation with other instances?**
A: No, PeachPie maintains full PyFedi/PieFed protocol compatibility.

**Q: Can I keep using "PyFedi" as the software name?**
A: Yes, set `SOFTWARE_NAME=PyFedi` in your environment.

**Q: What if the migration fails?**
A: The migration is transactional. If it fails, your database remains unchanged. Fix the issue and retry.

**Q: Do I need to notify other instances?**
A: No, the federation protocol remains unchanged. Other instances will see the new software name but communication continues normally.