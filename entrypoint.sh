# #!/usr/bin/env sh
# set -e

# export FLASK_APP=pyfedi.py

# echo "Starting cron daemon..."
# cron

# echo "Running database migrations..."
# python3 -m flask db upgrade

# python3 -m flask populate_community_search

# if [ "${FLASK_DEBUG:-}" = "1" ] && [ "${FLASK_ENV:-}" = "development" ]; then
#   export FLASK_RUN_EXTRA_FILES=$(find app/templates app/static -type f | tr '\n' ':')
#   echo "Starting flask development server..."
#   python3 -m flask run -h 0.0.0.0 -p 5000
# else
#   echo "Starting Gunicorn..."
#   python3 -m gunicorn --config gunicorn.conf.py --preload pyfedi:app
# fi

#!/usr/bin/env sh
set -e

# This script now runs as ROOT

export FLASK_APP=pyfedi.py

# 1. Start cron daemon in the background (as root)
echo "Starting cron daemon..."
cron

# 2. Run setup tasks (as root)
echo "Running database migrations..."
python3 -m flask db upgrade

echo "Populating community search..."
python3 -m flask populate_community_search

# 3. Drop privileges and run the main application as the 'python' user
if [ "${FLASK_DEBUG:-}" = "1" ] && [ "${FLASK_ENV:-}" = "development" ]; then
  export FLASK_RUN_EXTRA_FILES=$(find app/templates app/static -type f | tr '\n' ':')
  echo "Starting flask development server as user 'python'..."
  # Use 'exec' to replace the shell process with the Flask process
  # Use 'gosu' to switch from root to the 'python' user
  exec gosu python python3 -m flask run -h 0.0.0.0 -p 5000
else
  echo "Starting Gunicorn as user 'python'..."
  # Use 'exec' to replace the shell process with the Gunicorn process
  # Use 'gosu' to switch from root to the 'python' user
  exec gosu python python3 -m gunicorn --config gunicorn.conf.py --preload pyfedi:app
fi