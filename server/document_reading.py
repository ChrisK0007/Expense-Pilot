"""Bounded document-reading jobs for the application's single Gunicorn worker.

Only short start/status requests cross the reverse proxy. Originals and extracted
drafts remain in SQLite/files; an interrupted job can be retried after a restart.
"""
import secrets
import threading
import time
from flask import g
from werkzeug.exceptions import HTTPException

_lock = threading.Lock()
_jobs = {}
_active = {}
MAX_ACTIVE = 2
MAX_RETAINED = 128
RETENTION = 900


def _snapshot(job):
    return {key: job[key] for key in ('job_id', 'status', 'result', 'error', 'error_status') if key in job}


def _prune():
    finished = sorted((job for job in _jobs.values() if job['status'] != 'reading'), key=lambda job: job['finished'])
    for job in finished:
        if time.monotonic() - job['finished'] > RETENTION or len(_jobs) >= MAX_RETAINED:
            _jobs.pop(job['job_id'], None)


def require_actor(uid, version):
    from app import one, fail, can_write
    g.user = one('SELECT * FROM users WHERE id=?', (uid,))
    if not g.user or not g.user['active'] or g.user['version'] != version or g.user['must_change_password'] or not can_write():
        fail('Access changed while reading the document. Sign in again before retrying.', 403)


def _run(job):
    from app import app, db
    from receipt_routes import extract_document
    outcome = dict(status='failed', error='Document reading was interrupted. Retry from Document inbox.', error_status=503)
    with app.app_context():
        try:
            require_actor(job['uid'], job['version'])
            result = extract_document(job['rid'], job['unfiled_only'])
            outcome = dict(status='complete', result=result)
        except Exception as exc:
            if isinstance(exc, HTTPException):
                message, code = exc.description, exc.code
            else:
                app.logger.exception('Document reading failed: %s', job['rid'])
                message, code = 'Document reading failed. The original is saved. Retry from Document inbox or enter the figures manually.', 500
            try:
                db().rollback()
                db().execute("UPDATE receipt_details SET scan_status='failed',scan_error=? WHERE receipt_id=? AND scan_status='reading'", (message, job['rid']))
                db().commit()
            except Exception:
                app.logger.exception('Could not record document-reading failure: %s', job['rid'])
            outcome = dict(status='failed', error=message, error_status=code)
        finally:
            with _lock:
                job.update(outcome, finished=time.monotonic())
                _active.pop(job['rid'], None)


def start(rid, unfiled_only, background):
    from app import fail
    with _lock:
        _prune()
        if rid in _active:
            if not background:
                fail('This document is already being read. Check Document inbox shortly.', 409)
            return _snapshot(_jobs[_active[rid]])
        if len(_active) >= MAX_ACTIVE:
            fail('Document reading is busy. The original is saved; retry shortly.', 429)
        job = dict(job_id=secrets.token_hex(20), rid=rid, uid=g.user['id'], version=g.user['version'],
                   unfiled_only=unfiled_only, status='reading')
        _jobs[job['job_id']] = job
        _active[rid] = job['job_id']
    if background:
        try:
            threading.Thread(target=_run, args=(job,), name='document-reader', daemon=True).start()
        except Exception:
            with _lock:
                _active.pop(rid, None)
                _jobs.pop(job['job_id'], None)
            fail('Could not start document reading. The original is saved; retry shortly.', 503)
    else:
        _run(job)
    with _lock:
        return _snapshot(job)


def status(rid, job_id):
    from app import fail
    with _lock:
        _prune()
        job = _jobs.get(job_id)
        if not job or job['rid'] != rid:
            fail('Reading progress is no longer available. Check the saved draft in Document inbox before retrying.', 404)
        return _snapshot(job)
