// Run the actual scripts embedded in the app, including unavailable-network cases.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../ExpensePilot/ReceiptBridge.swift'), 'utf8');
function script(name) {
  const match = source.match(new RegExp(`static let ${name} = """\\n([\\s\\S]*?)\\n    """`));
  assert.ok(match, `Missing ${name} bridge`);
  return match[1];
}
const owner = {id: 7, role: 'owner', must_change_password: 0};
const session = user => ({user, csrf: 'current-csrf', mfa_required: false});
const response = (body, ok = true) => ({ok, json: async () => body});
async function run(name, values = {}) {
  const context = vm.createContext({
    S: session(owner), expectedUser: owner.id, encoded: Buffer.from('%PDF-test').toString('base64'), filename: 'receipt.pdf',
    AbortController, setTimeout, clearTimeout, atob, Uint8Array, FormData, Blob,
    fetch: async () => { throw new TypeError('Network unavailable'); }, ...values
  });
  return JSON.parse(JSON.stringify(await new vm.Script(`(async () => {${script(name)}})()`).runInContext(context)));
}
(async () => {
  let networkCalls = 0;
  const allowed = await run('scanContext', {fetch: async () => { networkCalls++; throw Error('offline'); }});
  assert.deepEqual(allowed, {ok: true, userID: owner.id});
  assert.equal(networkCalls, 0, 'Starting the camera must not depend on a network request');
  assert.equal((await run('scanContext', {S: session({...owner, role:'tax_agent', permission:'read_write'})})).ok, true);
  for (const S of [undefined, {}, session(null), {...session(owner), mfa_required:true}, session({...owner,must_change_password:1}), session({...owner,role:'employee'}), session({...owner,role:'tax_agent',permission:'read_only'}), session({...owner,id:'7'})]) {
    assert.equal((await run('scanContext', {S})).ok, false, 'Invalid/local unauthenticated state must not start the scanner');
  }
  const offline = await run('uploadScan');
  assert.equal(offline.ok, false);
  assert.match(offline.error, /Keep the app open.*Retry upload/);
  assert.doesNotMatch(offline.error, /JavaScript|exception/);

  // Retry the exact same PDF after the transport reconnects.
  let uploaded = false;
  const connected = async (url, options) => {
    if (url === '/api/session') return response(session(owner));
    assert.equal(url, '/api/receipts');
    assert.equal(options.method, 'POST');
    assert.equal(options.headers['X-CSRF-Token'], 'current-csrf');
    assert.equal(await options.body.get('file').text(), '%PDF-test');
    uploaded = true;
    return response({id:'receipt-1'});
  };
  assert.equal((await run('uploadScan', {fetch: connected})).ok, true);
  assert.equal(uploaded, true);

  // Fresh server authority overrides the loaded page (expired session, account
  // switching, pending 2FA/password change, permission downgrade or retired role).
  for (const current of [session(null), session({...owner,id:8}), {...session(owner),mfa_required:true}, session({...owner,must_change_password:1}), session({...owner,role:'tax_agent',permission:'read_only'}), session({...owner,role:'employee'})]) {
    let posts = 0;
    const result = await run('uploadScan', {fetch: async (url) => {
      if (url === '/api/session') return response(current);
      posts++; return response({id:'must-not-upload'});
    }});
    assert.equal(result.ok, false);
    assert.equal(posts, 0, 'Permission/session failures must not transmit the receipt');
  }
  const readonly = {...owner,role:'tax_agent',permission:'read_write'};
  assert.equal((await run('uploadScan', {fetch: async url => response(url === '/api/session' ? session(readonly) : {id:'write-agent'})})).ok, true);
  assert.equal((await run('uploadScan', {fetch: async () => response({}, false)})).ok, false);
  assert.equal((await run('uploadScan', {fetch: async () => ({ok:true,json:async () => {throw Error('HTML proxy page');}})})).ok, false);
  const rejection = await run('uploadScan', {fetch: async url => url === '/api/session' ? response(session(owner)) : response({error:'Too large'},false)});
  assert.equal(rejection.error, 'Too large');
  const droppedUpload = await run('uploadScan', {fetch: async url => {
    if (url === '/api/session') return response(session(owner));
    throw Error('Connection lost after capture');
  }});
  assert.equal(droppedUpload.ok, false);
  const timeout = await run('uploadScan', {
    setTimeout: callback => { callback(); return 1; }, clearTimeout: () => {},
    fetch: async (_, options) => { assert.equal(options.signal.aborted, true); throw Error('aborted'); }
  });
  assert.equal(timeout.ok, false);
  // A lost acknowledgement can be retried safely using server fingerprint dedupe.
  assert.deepEqual(await run('uploadScan', {fetch: async url => response(url === '/api/session' ? session(owner) : {duplicate:true})}), {ok:true,duplicate:true});
  assert.equal((await run('uploadScan', {fetch:connected,page:'dashboard',render:() => {throw Error('UI refresh failed');}})).ok, true);
  console.log('PASS: offline scanner startup, first-login/2FA/role gates, reconnect retry, live account checks, CSRF, transport/proxy failures, timeout and duplicate acknowledgement');
})().catch(error => { console.error(error); process.exitCode = 1; });
