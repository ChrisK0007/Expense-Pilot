def post_worker_init(worker):
    from app import app
    from billing import start_scheduler
    start_scheduler(app)
