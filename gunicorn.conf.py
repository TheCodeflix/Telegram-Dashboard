from config import PORT as _app_port

workers = 2
worker_class = "sync"
bind = "0.0.0.0:" + str(_app_port)
timeout = 120
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
