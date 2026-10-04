import multiprocessing
import os

cpu_cores = multiprocessing.cpu_count()

if num_workers := os.environ.get('GUNICORN_WORKERS'):
    workers = int(num_workers)
else:
    workers = max(4, cpu_cores // 2)
threads = 2

worker_tmp_dir = '/dev/shm'

bind = '0.0.0.0:5000'
umask = 0o007
reload = False

worker_class = 'gthread'

#logging
accesslog = '-'
errorlog = '-'

if gunicorn_max_requests := os.environ.get('GUNICORN_MAX_REQUESTS'):
    max_requests = int(gunicorn_max_requests)
else:
    max_requests = 2000

max_requests_jitter = 50

keepalive = 20
