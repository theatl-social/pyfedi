# syntax=docker/dockerfile:1.4

# Stage 1: Builder
# Use a Debian "Bookworm" based Python image
FROM --platform=linux/x86_64 python:3.11-bookworm AS builder

# Set environment variables to prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies, including git
RUN apt-get update
RUN apt install cron -y
RUN apt-get install -y --no-install-recommends \
    # Add git to clone the repository
    git \
    # Utilities for adding PostgreSQL repo
    gnupg \
    lsb-release && \
    # Add PostgreSQL repository
    curl -sS https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/postgresql-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/postgresql-archive-keyring.gpg] http://apt.postgresql.org/pub/repos/apt/ $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list && \
    # Update again and install build tools
    apt-get update && \
    apt-get install -y --no-install-recommends \
    pkg-config \
    gcc \
    build-essential \
    tesseract-ocr \
    tesseract-ocr-eng \
    postgresql-client-16 \
    bash && \
    # Clean up apt cache to reduce image size
    rm -rf /var/lib/apt/lists/*


# add bash
RUN apt-get install -y --no-install-recommends bash

# Set up the application directory
WORKDIR /app

# # Clone the repository directly into the container, and then checkout the branch 
# RUN git clone --branch 20250717/theatl-fork-pyfed-nightly-2 --single-branch https://github.com/theatl-social/pyfedi .

COPY . .

# Install Python dependencies from the cloned requirements.txt
# This uses the requirements.txt from the repo, not from the local context
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install --no-cache-dir -r requirements.txt

# Install Gunicorn separately
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install --no-cache-dir gunicorn

FROM --platform=linux/x86_64 python:3.11-bookworm

# Add 'gosu' for privilege-dropping in the entrypoint
RUN apt-get update && \
    apt-get install -y --no-install-recommends cron gosu && \
    rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create a non-root user for security
RUN adduser --system --disabled-password --group python

# Copy build artifacts from the builder stage
WORKDIR /app
COPY --from=builder /app /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
# ... (rest of your COPY commands) ...

# Compile translation files
RUN pybabel compile -d app/translations || true

# Make the entrypoint scripts executable and ensure ownership is correct.
# The entrypoint will be run by root, so it needs the execute bit.
RUN chmod +x ./entrypoint.sh ./entrypoint_celery.sh ./entrypoint.test.sh && \
    chown -R python:python /app

# Add the crontab entries
RUN cat <<EOF > /etc/cron.d/my-cron-job
1 */6 * * * root /app/email_notifs.sh
5 4 * * 1 /app/remove_orphan_files.sh
5 2 * * * /app/daily.sh
*/5 * * * * /app/send_queue.sh
EOF

# DO NOT switch user here. The entrypoint script will handle it.
# USER python  <-- REMOVE OR COMMENT OUT THIS LINE

# Set the default command. This works because WORKDIR is /app.
ENTRYPOINT ["./entrypoint.sh"]