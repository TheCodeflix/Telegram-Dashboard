import os

workers = 2
worker_class = "sync"
bind = "0.0.0.0:" + os.environ.get("PORT", "8000")
timeout = 120
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
