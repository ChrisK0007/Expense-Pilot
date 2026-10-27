"""Disposable browser-test server. NOT copied into production images.

Only the CI container mounts tests/. SMTP is replaced with an in-memory capture,
so browser tests exercise invitations without sending any messages.
"""
import os
import sys
from pathlib import Path
source = Path(__file__).resolve().parents[2] / 'server'
sys.path.insert(0, str(source if source.is_dir() else Path(__file__).resolve().parents[1]))
from flask import jsonify
from app import app, db
import billing

invitations={}
def fake_delivery(recipient,subject,message,*args,**kwargs):
    if not recipient.endswith('@example.test'):
        raise ValueError('Browser tests may only use example.test recipients.')
    invitations[recipient]=message
    return 'sent',''
billing.deliver=fake_delivery
with app.app_context():
    billing.save_settings('email',{**billing.DEFAULT_MAIL,'host':'smtp.example.test','from_email':'owner@example.test'})
    billing.save_settings('access',{'login_url':'http://127.0.0.1:8788'})
    db().commit()

@app.get('/test/invitations')
def captured_invitations():
    return jsonify(invitations)

import pocketsmith
from pocketsmith_fixture import BrowserClient
pocketsmith.Client=BrowserClient

# Keep synthetic payroll documents off every real provider during browser tests.
import ai_providers
def unavailable_ai(*args, **kwargs):
    raise ai_providers.AIError('Ollama did not finish reading this synthetic document.')
ai_providers.extract=unavailable_ai

app.run(host='0.0.0.0',port=int(os.environ.get('PORT','8788')),threaded=True)
