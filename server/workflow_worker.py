"""Successful sign-in notifications, guarded across application workers."""
import fcntl
import threading


def tick():
    from app import DATA, db
    import signin_alerts
    with open(DATA/'.signin-worker.lock', 'a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        try: signin_alerts.process()
        except Exception:
            db().rollback()
            from flask import current_app
            current_app.logger.exception('Sign-in notification service failed')


def start(app):
    def loop():
        while True:
            with app.app_context(): tick()
            threading.Event().wait(60)
    threading.Thread(target=loop, daemon=True, name='expense-pilot-signins').start()
