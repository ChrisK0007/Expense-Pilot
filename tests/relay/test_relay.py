import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

source = Path(__file__).resolve().parents[2]/'deploy/push-relay/relay.py'
if not source.exists(): source = Path('/relay/relay.py')
spec = importlib.util.spec_from_file_location('relay', source); relay = importlib.util.module_from_spec(spec); spec.loader.exec_module(relay)

class RelayTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.env = patch.dict(os.environ, {'RELAY_DATA':self.directory.name,'PUSH_RELAY_CLIENTS':json.dumps({'test':'s'*40}),'APNS_TOPIC':'example.app','APNS_ENVIRONMENT':'production'})
        self.env.start(); self.addCleanup(self.env.stop)
        self.client = relay.app.test_client()
        self.payload = dict(token='a'*64,context='b'*64,key='invoice.2.2026-10-17T10:00:00+00:00',kind='invoicePaid',screen='invoice',item='2',sound=False)
        self.headers = {'Authorization':'Bearer '+'s'*40}
    def test_rejects_unauthenticated_arbitrary_payloads(self):
        self.assertEqual(self.client.post('/notify',json=self.payload).status_code,401)
        for changed in ({'screen':'https://evil.example'}, {'kind':'custom'}, {'token':'bad'}):
            self.assertEqual(self.client.post('/notify',json={**self.payload,**changed},headers=self.headers).status_code,400)
    def test_generic_payload_and_retry_dedup(self):
        with patch.object(relay,'jwt',return_value='fake'), patch.object(relay._client,'post',return_value=Mock(status_code=200)) as send:
            self.assertEqual(self.client.post('/notify',json=self.payload,headers=self.headers).status_code,200)
            self.assertEqual(self.client.post('/notify',json=self.payload,headers=self.headers).status_code,200)
            self.assertEqual(send.call_count,1)
            body = send.call_args.kwargs['json']
            self.assertNotIn('sound',body['aps']); self.assertEqual(body['kind'],'invoicePaid')
            self.assertLessEqual(len(send.call_args.kwargs['headers']['apns-collapse-id']),64)
            self.assertNotIn('token',body)
    def test_failed_delivery_remains_retryable(self):
        with patch.object(relay,'jwt',return_value='fake'), patch.object(relay._client,'post',return_value=Mock(status_code=503)) as send:
            self.assertEqual(self.client.post('/notify',json=self.payload,headers=self.headers).status_code,502)
            self.assertEqual(self.client.post('/notify',json=self.payload,headers=self.headers).status_code,502)
            self.assertEqual(send.call_count,2)
