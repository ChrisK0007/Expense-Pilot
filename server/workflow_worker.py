"""One bounded background pass across workers, guarded by an advisory lock."""
import fcntl
import threading


def tick(security_only=False):
    from app import DATA, db
    import signin_alerts, mail_intake, offsite_backup
    with open(DATA/('.signin-worker.lock' if security_only else '.workflow-worker.lock'),'a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return
        for work in ((signin_alerts.process,) if security_only else (mail_intake.poll,offsite_backup.tick)):
            try: work()
            except Exception:
                db().rollback()
                from flask import current_app
                current_app.logger.exception('Background review service failed: %s',work.__module__)


def start(app):
    def loop(security_only):
        while True:
            with app.app_context(): tick(security_only)
            threading.Event().wait(60)
    for security_only in (True,False):
        threading.Thread(target=loop,args=(security_only,),daemon=True,name='expense-pilot-signins' if security_only else 'expense-pilot-workflows').start()
