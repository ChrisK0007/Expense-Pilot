def post_worker_init(worker):
    from app import app
    from billing import start_scheduler
    start_scheduler(app)
    from pocketsmith import start_scheduler as start_bank_scheduler
    start_bank_scheduler(app)

    from notifications import start_scheduler as start_notification_scheduler
    start_notification_scheduler(app)
