# Configuration for production gunicorn server
# pylint: skip-file
import multiprocessing

workers = multiprocessing.cpu_count() * 2
worker_class = "uvicorn.workers.UvicornWorker"
max_requests = 100
max_requests_jitter = 10
threads = multiprocessing.cpu_count() * 2
bind = "0.0.0.0:8080"
certfile = "/persistent/letsencrypt/live/log-detective.com/cert.pem"
keyfile = "/persistent/letsencrypt/live/log-detective.com/privkey.pem"
ca_certs = "/persistent/letsencrypt/live/log-detective.com/fullchain.pem"
timeout = 1800
accesslog = "-"
