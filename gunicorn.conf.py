import multiprocessing

workers = 1
threads = multiprocessing.cpu_count() * 4 + 1

worker_tmp_dir = '/dev/shm'

bind = '0.0.0.0:5000'
umask = 0o007
reload = False

worker_class = 'gthread'

#logging
accesslog = '-'
errorlog = '-'

max_requests = 500
max_requests_jitter = 50
