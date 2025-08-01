# Contents

* [Choose your path - easy way or hard way](#choose-path)
* [Setup Database](#setup-database)
* [Install Python Libraries](#install-python-libraries)
* [Install additional requirements](#install-additional-requirements)      
* [Setup pyfedi](#setup-pyfedi)
* [Setup .env file](#setup-env-file)
* [Initialise Database and Setup Admin account](#initialise-database-and-setup-admin-account)
* [Run the app](#run-the-app)
* [Database Management](#database-management)
* [Keeping your local instance up to date](#keeping-your-local-instance-up-to=date)
* [Running PieFed in production](#running-piefed-in-production)
* [Accepting donations through Stripe](#stripe)
* [Testing and debugging](#testing)
* [Pre-requisites for Mac OS](#pre-requisites-for-mac-os)
* [Notes for Windows (WSL2)](#notes-for-windows-wsl2)        
* [Notes for Pip Package Management](#notes-for-pip-package-management)

<div id="choose-path"></div>

## Do you want this the easy way or the hard way?

### Easy way: docker

Docker can be used to create an isolated environment that is separate from the host server and starts from a consistent
configuration. While it is quicker and easier, it's not to everyone's taste.

[DOCKER INSTRUCTIONS ARE HERE](https://codeberg.org/rimu/pyfedi/src/branch/main/INSTALL-docker.md)


### Hard way: bare metal

Doing things this way will give you the ultimate customization that larger instances need. You will need to be more careful about
whether your OS is compatible with what PieFed needs:

#### Software requirements

 - Python 3.9+
 - PostgreSQL 13+
 - Redis 6.x

#### Hardware requirements

It really depends on how many communities you will be subscribing to and how many users you have.

Minimum:
 - 2 CPU cores
 - 3 GB of RAM

Recommended:
 - 4 CPU cores
 - 5+ GB of RAM

PieFed is quite frugal with storage usage but it will grow over time. After 18 months of operation PieFed.social uses 100 GB of space, for example.

<div id="setup-database"></div>

## Setup Database

#### Install postgresql

PieFed should work on version 13.x or newer. If you have errors running `flask init-db`, check your postrgesql version.

##### Install postgresql 16:

For installation environments that use `apt` as a package manager:

```bash
sudo apt install ca-certificates pkg-config
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt/ $(lsb_release -cs)-pgdg main" >> /etc/apt/sources.list.d/pgdg.list'
sudo apt update
sudo apt install libpq-dev postgresql
```

#### Create new DB user

Choose a username and password. To use 'pyfedi' for both:     
```bash
sudo -iu postgres psql -c "CREATE USER pyfedi WITH PASSWORD 'pyfedi';"
```

#### Create new database

Choose a database name, owned by your new user. For a database called and owned by 'pyfedi':      
```bash
sudo -iu postgres psql -c "CREATE DATABASE pyfedi WITH OWNER pyfedi;"
```

<div id="install-python-libraries"></div>

## Install Python Libraries

[Pre-requisites for Mac OS](#pre-requisites-for-mac-os)         
[Notes for Windows (WSL2)](#notes-for-windows-wsl2)        

For installation environments that use `apt` as a package manager:   
```bash
sudo apt install python3-pip python3-venv python3-dev python3-psycopg2
``` 


<div id="install-additional-requirements"></div>

## Install additional requirements

For installation environments that use 'apt' as a package manager:   

```bash
sudo apt install redis-server
sudo apt install git
sudo apt install tesseract-ocr
```

Developers might want to use `ruff` as a pre-commit linter. Install it with `pip install ruff` then use `ruff check` to analyze code.
We have supplied a ruff.toml config file in the root of the project.

<div id="setup-pyfedi"></div>

## Setup PyFedi

* Clone PieFed

```bash
git clone https://codeberg.org/rimu/pyfedi.git
```

* cd into pyfedi, set up and enter virtual environment

```bash
cd pyfedi
python3 -m venv ./venv
source venv/bin/activate
```

* Use pip to install requirements           

```bash
pip install wheel
pip install -r requirements.txt
```
(see [Notes for Windows (WSL2)](#windows-wsl2) if appropriate)        

<div id="setup-env-file"></div>

## Setup .env file

* Copy `env.sample` to `.env`
* Edit `.env` to suit your server.
* Using the same username, password, and database name as used when setting up database, set the connection up, something like this:
    ```
    DATABASE_URL=postgresql+psycopg2://username:password@localhost/database_name
    ```
    * Also change `SECRET_KEY` to some random sequence of numbers and letters.
    

### Extra info

* `SERVER_NAME` should be the domain of the site/instance. Use `127.0.0.1:5000` during development unless using ngrok. Just use the bare
domain name, without https:// on the front or a slash on the end.
* `CACHE_TYPE` can be `FileSystemCache` or `RedisCache`. `FileSystemCache` is fine during development (set `CACHE_DIR` to `/tmp/piefed` or `/dev/shm/piefed`)
while `RedisCache` **should** be used in production. If using `RedisCache`, set `CACHE_REDIS_URL` to `redis://localhost:6379/1` or `unix:///var/run/redis/redis.sock?db=1`. Visit https://yourdomain/testredis to check if your redis url is working.

* `CELERY_BROKER_URL` is similar to `CACHE_REDIS_URL` but with a different number on the end: `redis://localhost:6379/0`.
 If using unix socket, try something like `CELERY_BROKER_URL='redis+socket:///var/run/redis/redis.sock?virtual_host=0'`

* `MAIL_*` is for sending email using a SMTP server. Leave `MAIL_SERVER` empty to send email using AWS SES instead. Set MAIL_FROM to a no-reply inbox.

* Set ERRORS_TO to an email address that will receive error reports. Only do this if debugging problems and you have MAIL_* set.

* `AWS_REGION` is the name of the AWS region where you chose to set up SES, if using SES. [SES credentials are stored in `~/.aws/credentials`](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html). That file has a format like

    ```
    [default]
    aws_access_key_id = JKJHER*#KJFFF
    aws_secret_access_key = /jkhejhkrejhkre
    region=ap-southeast-2
    ```
    You can also [use environment variables](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html#environment-variables) if you prefer.

* Test email sending by going to https://yourdomain/test_email. (after setting the FLASK_DEBUG environment variable to 1). It will try to send an email to the current user's email address.
If it does not work check the log file at logs/pyfedi.log for clues.

* BOUNCE_ADDRESS is where email bounces will go to. If BOUNCE_* is configured then all emails in that inbox
will be treated as bounces and deleted after extracting the email addresses in them. Use a dedicated inbox
for bounces, not a inbox you also use for other purposes.

* Set FLAG_THROWAWAY_EMAILS = 1 to see a warning on throwaway email addresses during registration approvals - https://piefed.social/post/758768

* Enable [image blocking](https://piefed.social/post/751901) by setting IMAGE_HASHING_ENDPOINT to the url of [a PDQ hashing instance](https://piefed.social/post/759065).

* If the home page is loading slowly, set PAGE_LENGTH to a lower number.

### Development mode

Setting `FLASK_DEBUG=1` in the `.env` file will enable the `<your-site>/dev/tools` page. It will expose some various testing routes as well. See the [testing section](#testing).

That page can be accessed from the `Admin` navigation drop down, or nav bar as `Dev Tools`. That page has buttons that can create/delete communities and topics. The communities and topics will all begin with "dev_".

Note that SSL is not a hard requirement for local testing or development. By including `HTTP_PROTOCOL='http'` in the `.env` file, some features will play a little nicer without SSL. This is not a teribly well-vetted workflow, so there might still be cases in which SSL is expected/required (such as S3 usage). This is primarily intended to ease development of basic features or UI changes.

<div id="initialise-database-and-setup-admin-account"></div>

## Initialise database, and set up admin account

```bash
export FLASK_APP=pyfedi.py
flask db upgrade
flask init-db
```

(choose a new username, email address, and password for your PyFedi admin account)

If you see an error message `ModuleNotFoundError: No module named 'flask_babel'` then use `venv/bin/flask` instead of `flask`
for all flask commands.

### Verify your configuration

After setting up your .env file and your database, you can verify your configuration is correct by running:

```bash
export FLASK_APP=pyfedi.py
source venv/bin/activate
flask config_check
```

This command will check your environment variables for proper format, test database and Redis connections, verify directory
permissions, and identify common configuration issues. Fix any errors reported before proceeding. For warnings you'll need to use
your judgement.

<div id="run-the-app"></div>

## Run the app    

```bash
flask run
```
(open web browser at http://127.0.0.1:5000)          
(log in with username and password from admin account)

For development purposes, that should be enough - see ./dev_notes.txt for a few more bits and pieces. Most of what follows is for running PieFed in production.

<div id="database-management"></div>

## Database Management

In future if you use git pull and notice some new files in `migrations/versions/*`, you need to do:    

```bash
source venv/bin/activate #if not already in virtual environment
flask db upgrade
```

#### For Database changes:

create a migration based on recent changes to `app/models.py`:

```bash
flask db migrate -m "users table"
```
     
run migrations:         
```bash
flask db upgrade
```

<div id="keeping-your-local-instance-up-to=date"></div>

## Keeping your local instance up to date

In a development environment, all you need to do is

```bash
git pull
flask db upgrade
```

In production, celery and flask run as background services so they need to be restarted manually. Run the `./deploy.sh` script
to easily restart services at the same time as pulling down changes from git, etc.

<div id="federation-during-development"></div>

## Federation during development

Federation doesn't work without SSL, without a domain name or without your server being accessible from outside your network. So, when running on http://127.0.0.1:5000 you have none of those.

The site will still run without federation. You can create local communities and post in them...

My way around this is to use ngrok.com, which is a quick and simple way to create a temporary VPN with a domain and SSL. The free plan comes with ephermeral domain names that change every few days, which will break federation, or one randomly-named static domain that will need re-launching every few days. $10 per month will get you https://yourwhatever.ngrok.app which won't change. 

Once you have ngrok working, edit the `.env` file and change the `SERVER_NAME` variable to your new domain name (all lower case).

<div id="running-piefed-in-production"></div>

## Running PieFed in production

Running PieFed in production relies on several additional packages that need to be installed.

```bash
source venv/bin/activate #if not already in virtual environment
pip3 install gunicorn celery
```

Copy `celery_worker.default.py` to `celery_worker.py`. Edit `DATABASE_URL` and `SERVER_NAME` to have the same values as in `.env`.

Edit `gunicorn.conf.py` and change `worker_tmp_dir` if needed.

You will want to [tune PostgreSQL](https://pgtune.leopard.in.ua/). [More on this](https://www.enterprisedb.com/postgres-tutorials/how-tune-postgresql-memory).
If you have more than 4 GB of RAM, consider [turning on 'huge pages'](https://www.percona.com/blog/why-linux-hugepages-are-super-important-for-database-servers-a-case-with-postgresql/)
also [see this](https://pganalyze.com/blog/5mins-postgres-tuning-huge-pages).

[PgBouncer](https://www.pgbouncer.org) can be helpful for instances with > 800 MAU.

To assess whether to accept a registration application it can be helpful to know the country of the applicant. If you are using
CloudFlare then add COUNTRY_SOURCE_HEADER='CF-IPCountry' to your .env. Otherwise, use [the ipinfo service](https://ipinfo.io/) - register with them to get an API token
and put it into your .env file (IPINFO_TOKEN).

If the search function is not returning any results, you need to [add some database triggers](https://codeberg.org/rimu/pyfedi/issues/358#issuecomment-2475019).

Enable the API for use by mobile apps by setting the ENABLE_ALPHA_API environment variable to 'true' (a string, with quotes).

To limit which domains can access the API, set the CORS_ALLOW_ORIGIN environment variable. This defaults to '*' (allowing requests from any origin) but can be set to a specific domain like 'https://example.com' for security.

<div id="background-services"></div>

### Background services

In production, Gunicorn and Celery need to run as background services:

#### Gunicorn

Create a new file:

```bash
sudo nano /etc/systemd/system/pyfedi.service
```

Add the following to the new file, altering paths as appropriate for your install location

```
[Unit]
Description=Gunicorn instance to serve PieFed application
After=network.target

[Service]
User=rimu
Group=rimu
WorkingDirectory=/home/rimu/pyfedi/
Environment="PATH=/home/rimu/pyfedi/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin"
ExecStart=/home/rimu/pyfedi/venv/bin/gunicorn --config gunicorn.conf.py --preload pyfedi:app
ExecReload=/bin/kill -HUP $MAINPID
Restart=always


[Install]
WantedBy=multi-user.target
```
    

#### Celery

Create another file:

```bash
sudo nano /etc/systemd/system/celery.service
```

Add the following, altering as appropriate

```
[Unit]
Description=Celery Service
After=network.target

[Service]
Type=forking
User=rimu
Group=rimu
EnvironmentFile=/etc/default/celeryd
WorkingDirectory=/home/rimu/pyfedi
ExecStart=/bin/sh -c '${CELERY_BIN} multi start -A ${CELERY_APP} ${CELERYD_NODES} --pidfile=${CELERYD_PID_FILE} \
  --logfile=${CELERYD_LOG_FILE} ${CELERYD_OPTS}'
ExecStop=/bin/sh -c '${CELERY_BIN} multi stopwait ${CELERYD_NODES} --pidfile=${CELERYD_PID_FILE}'
ExecReload=/bin/sh -c '${CELERY_BIN} multi restart -A ${CELERY_APP} ${CELERYD_NODES} --pidfile=${CELERYD_PID_FILE} \
  --logfile=${CELERYD_LOG_FILE} ${CELERYD_OPTS}'

[Install]
WantedBy=multi-user.target
```

Create another file:

```
sudo nano /etc/default/celeryd
```

Contents (change paths to suit):

```
# The names of the workers. This example creates one workers
CELERYD_NODES="worker1"

# The name of the Celery App, should be the same as the python file
# where the Celery tasks are defined
CELERY_APP="celery_worker.celery"

# Log and PID directories
CELERYD_LOG_FILE="/var/log/celery/%n%I.log"
CELERYD_PID_FILE="/dev/shm/celery/%n.pid"

# Log level
CELERYD_LOG_LEVEL=INFO

# Path to celery binary, that is in your virtual environment
CELERY_BIN=/home/rimu/pyfedi/venv/bin/celery
CELERYD_OPTS="--autoscale=5,1 --queues=celery,background,send"
```

#### Enable and start background services

```bash
sudo systemctl enable pyfedi.service
sudo systemctl enable celery.service

sudo systemctl start pyfedi.service
sudo systemctl start celery.service
```

Check status of services:

```bash
sudo systemctl status pyfedi.service
sudo systemctl status celery.service
```

Inspect log files at:

* `/var/log/celery/*`
* `/var/log/nginx/*`
* `/your_piefed_installation/logs/pyfedi.log`

### Reverse Proxies

#### Nginx

You need a reverse proxy that sends all traffic to port 5000. Something like:

```
upstream app_server {
    # fail_timeout=0 means we always retry an upstream even if it failed
    # to return a good HTTP response

    # for UNIX domain socket setups
    # server unix:/tmp/gunicorn.sock fail_timeout=0;

    # for a TCP configuration
    server 127.0.0.1:5000 fail_timeout=0;
    keepalive 2;
}

server {
    server_name piefed.social
    root /whatever

    keepalive_timeout 30;
    ssi off;

    location / {
        # Proxy all requests to Gunicorn
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Host $http_host;
        proxy_redirect off;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_pass http://app_server;
        ssi off;
    }

    # Serve static files directly with nginx
    location /static/ {
        alias /whatever/app/static/;
        expires max;
        access_log off;
    }

}
```

**_The above is not a complete configuration_** - you will want to add more settings for SSL, etc. See also
https://codeberg.org/rimu/pyfedi/issues/136#issuecomment-1726739

#### Caddy

```
piefed.social {
        # Serve static files directly with caddy
        handle_path /static/* {
                root * /whatever/app/static/
                file_server
                header Cache-Control "max-age=31536000"
        }

        reverse_proxy :5000
}
```

### Cron tasks


To send email reminders about unread notifications, put this in a new file under `/etc/cron.d`

```
1 */6 * * * rimu cd /home/rimu/pyfedi && /home/rimu/pyfedi/email_notifs.sh
```

Change `/home/rimu/pyfedi` to the location of your installation and change `rimu` to the user that piefed runs as.

Once a week or so it's good to run `remove_orphan_files.sh` to save disk space:

```
5 4 * * 1 rimu cd /home/rimu/pyfedi && /home/rimu/pyfedi/remove_orphan_files.sh
```

One per day there are some maintenance tasks that PieFed needs to do (run it at a time of low usage):

```
5 2 * * * rimu cd /home/rimu/pyfedi && /home/rimu/pyfedi/daily.sh
```

Every few minutes PieFed will retry federation sending attempts that failed previously:

```
*/5 * * * * rimu cd /home/rimu/pyfedi && /home/rimu/pyfedi/send_queue.sh
```

The send_queue cron job is also needed to make scheduled posts publish themselves.


### Email

Email can be sent either through SMTP or Amazon web services (SES). SES is faster but PieFed does not send much
email so it probably doesn't matter which method you choose.

#### AWS SES

PieFed uses Amazon's `boto3` module to connect to SES. Boto3 needs to log into AWS and that can be set up using a file
at `~/.aws/credentials` or environment variables. Details at https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html.

In your `.env` you need to set the AWS region you're using for SES. Something like `AWS_REGION = 'ap-southeast-2'`.

#### CDN

A CDN like Cloudflare is recommended for instances with more than a handful of users. [Recommended caching settings](https://join.piefed.social/2024/02/20/how-much-difference-does-a-cdn-make-to-a-fediverse-instance/).

Some Cloudflare tips:

- Ensure you exclude the URL "/inbox" from the Cloudflare WAF [as shown here](https://join.piefed.social/wp-content/uploads/2024/10/disable-waf-on-inbox.png). If you don't do this there will be federation issues.
- Under Speed -> Optimization -> Content Optimization, turn everything off especially "Rocket Loader" to avoid JavaScript problems.
- Under Speed -> Optimization -> Protocol Optimization, turn off HTTP/3 to avoid problems with Firefox.
- Paying careful attention to the caching settings can sharply reduce the load on your server - see [these Cloudflare caching tips](https://join.piefed.social/2024/02/20/how-much-difference-does-a-cdn-make-to-a-fediverse-instance/).
- Cloudflare's bot protection / AI scraper blocker tends to play havoc with the API, you'll have a much better time if you turn this off entirely.

PieFed has the capability to automatically remove file copies from the Cloudflare cache whenever
 those files are deleted from the server. To enable this, set these variables in your `.env` file:

- `CLOUDFLARE_API_TOKEN` - go to https://dash.cloudflare.com/profile/api-tokens and create a "Zone.Cache Purge" token.
- `CLOUDFLARE_ZONE_ID` - this can be found in the right hand column of your Cloudflare dashboard in the API section.

#### S3 (object storage)

Over time images for user profile photos, image posts and link thumbnails will consume quite a lot of storage space so it is a good idea
to use a cheaper form of storage such as AWS S3 or Cloudflare R2. The S3 API is widely implemented by many providers and PieFed can
store media in any of them. Cloudflare does not charge egress fees so they are pretty good value. Wasabi is cheaper than Cloudflare
and AWS - see the [Wasabi setup tips](https://codeberg.org/rimu/pyfedi/src/branch/main/docs/Using%20Wasabi%20S3%20with%20Piefed.md).

To enable S3 storage you need to set these environment variables in your .env file:

 - S3_REGION = 'auto'
 - S3_BUCKET = 'piefed-media'
 - S3_ENDPOINT = 'https://something_something.r2.cloudflarestorage.com'
 - S3_PUBLIC_URL = 'media.piefed.social'
 - S3_ACCESS_KEY = 'xyz'
 - S3_ACCESS_SECRET = 'xyzxyz'

Cloudflare does not care about S3_REGION so it can be 'auto' but for AWS you should use something like us-east-1. All the
other values are shown to you during the setup of the space (often called the "bucket") on your S3 provider.

Test your S3 connection by going to https://yourinstance.tld/test_s3. If it crashes, something is wrong. If you see 'Ok' all is well.



#### SMTP

To use SMTP you need to set all the `MAIL_*` environment variables in you `.env` file. See `env.sample` for a list of them.

#### Testing email

You need to set `MAIL_FROM` in `.env` to some email address.

Also set an environment variable `FLASK_DEBUG` to '1' ( `export FLASK_DEBUG="1"` ).

Log into Piefed then go to https://yourdomain/test_email to trigger a test email. It will use SES or SMTP depending on
which environment variables you defined in .env. If `MAIL_SERVER` is empty it will try SES. Then if `AWS_REGION` is empty it'll
silently do nothing.


#### Log in with Google (OAuth)

You need to set these two environment variables:

 - GOOGLE_OAUTH_CLIENT_ID
 - GOOGLE_OAUTH_SECRET

The values for them are found by registering your instance with Google as 'an app'. Go to https://console.cloud.google.com/
to begin. Create a new project, enable the People API, go to APIs & Services > Credentials and create a new OAuth client ID.
Under "Authorized Redirect URIs", use `https://yourdomain.tld/auth/google_authorize`.

#### CMS

At /admin/pages there is a markdown-based CMS which you can use to add pages to your instance. Create one with the url
'privacy' to override the default privacy policy. Create one with the url 'about' and it will be appended to the existing about page.

All other urls have no special behaviour and will just display the page.

---

<div id="stripe"></div>

## Accepting donations through Stripe

In env.sample there are all the environment variables you need to add to your .env for Stripe to work.

STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY can be found on the Stripe dashboard.

STRIPE_MONTHLY_SMALL and STRIPE_MONTHLY_BIG are the Price IDs of two **monthly recurring** products. Find the price ID by editing
a product you've made and then clicking on the 3 dot button to the right of the price.

Change STRIPE_MONTHLY_SMALL_TEXT and STRIPE_MONTHLY_BIG_TEXT to be the amounts of your product prices.

To get a WEBHOOK_SIGNING_SECRET you need to set up a webhook to send data to https://yourinstance/stripe_webhook, sending the
checkout.session.completed and customer.subscription.deleted events.

---

<div id="testing"></div>

## Testing and debugging

### Logs

Check these locations for interesting error messages:

 - logs/pyfedi.log
 - /var/log/celery/*.log

There are a few urls you can go to which will test things out and report a result or log an error. You need the FLASK_DEBUG environment
variable set to 1 for these to work.

 - https://yourinstance.tld/test_s3 - tests your S3 config
 - https://yourinstance.tld/test_email - tests email sending
 - https://yourinstance.tld/test_redis - tests the connection to redis

You can also run `flask config_check` to validate your configuration and identify potential issues with environment variables, database connections, and file permissions.

---

<div id="pre-requisites-for-mac-os"></div>

## Pre-requisites for Mac OS

#### Install Python Version Manager (pyenv)
see this site: https://opensource.com/article/19/5/python-3-default-mac
    
```bash
brew install pyenv
```

#### Install Python3 version and set as default (with pyenv) 

```bash
pyenv install 3.8.6
pyenv global 3.7.3
```

Note..
You may see this error when running `pip install -r requirements.txt` in regards to psycopg2:
    
    ld: library not found for -lssl
    clang: error: linker command failed with exit code 1 (use -v to see invocation)
    error: command 'clang' failed with exit status 1

If this happens try installing openssl...
Install openssl with brew install openssl if you don't have it already.
    
`brew install openssl`
    
Add openssl path to LIBRARY_PATH :
    
    export LIBRARY_PATH=$LIBRARY_PATH:/usr/local/opt/openssl/lib/
    
---

<div id="notes-for-windows-wsl2"></div>

## Notes for Windows (WSL 2 - Ubuntu 22.04 LTS - Python 3.9.16)

**Important:**
    Python 3.10+ or 3.11+ may cause some package or compatibility errors. If you are having issues installing packages from
    `requirements.txt`, try using Python 3.8 or 3.9 instead with `pyenv` (https://github.com/pyenv/pyenv).
    Follow all the setup instructions in the pyenv documentation and setup any version of either Python 3.8 or 3.9.
    If you are getting installation errors or missing packages with pyenv, run 

```bash
sudo apt-update
sudo apt install build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev curl libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev llvm
```
---

#### Install Python 3, pip, and venv

```bash
sudo apt-get update
sudo apt-get upgrade
sudo apt-get install python3 python3-pip ipython3 libpq-dev python3-psycopg2 python3-dev build-essential redis-server
sudo apt-get install python3-venv
```

#### Setup venv first before installing other packages
**Note: **
    (Replace <3.9> with your version number if you are using another version of Python, 
    e.g. 'sudo apt-get install python3.10-venv' for Python 3.10. Repeat for the rest of the instructions below.)

```bash
python3.9 -m venv ./venv
source venv/bin/activate
```

Make sure that your venv is also running the correct version of pyenv. You may need to re-setup venv if you setup venv before pyenv.

Follow the package installation instructions above to get the packages

```bash
python3.9 -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

<div id="notes-for-pip-package-management"></div>

---

## Notes for Pip Package Management:

make sure you have `wheel` installed:
```bash
pip install wheel
```
    
install packages from a file:
```bash
pip install -r requirements.txt
```

dump currently installed packages to file:
```bash
pip freeze > requirements.txt
```

upgrade a package:
```bash
pip install --upgrade <package_name>
```

## Developers

See dev_notes.txt and https://join.piefed.social/docs/developers/
