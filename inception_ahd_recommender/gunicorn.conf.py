import os

workers = os.environ.get("RECOMMENDER_WORKERS", "2")
bind = os.environ.get("RECOMMENDER_ADDRESS", ":5000")
log_level = 'info'
wsgi_app = "main:app"