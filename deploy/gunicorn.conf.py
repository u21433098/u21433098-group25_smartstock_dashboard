"""Gunicorn settings for the Linux server (Gunicorn does not run on Windows; use Waitress there).

Started by deploy/smartstock.service as:  gunicorn -c deploy/gunicorn.conf.py wsgi:app
"""
bind = "127.0.0.1:8000"      # only Nginx on the same server can reach it
workers = 3                  # 2 x CPU cores + 1 is the usual rule; 3 suits a small 1-core server
timeout = 30                 # restart a worker stuck for 30 seconds
accesslog = "-"              # request log to stdout -> systemd journal
errorlog = "-"
