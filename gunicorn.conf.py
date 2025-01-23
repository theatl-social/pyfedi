import multiprocessing

workers = 2
threads = multiprocessing.cpu_count() * 3 + 1

worker_tmp_dir = '/dev/shm'

bind = '0.0.0.0:5000'
umask = 0o007
reload = False

worker_class = 'gthread'

#logging
accesslog = '-'
errorlog = '-'

max_requests = 2000
max_requests_jitter = 50
