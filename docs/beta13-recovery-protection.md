# Beta.13 recovery, passive protection and fuel reading sources

## Password recovery

Use **Forgot password?** on the sign-in page. Web recovery requires an active account whose current mailbox was verified through Settings → Security, configured SMTP, and the owner's configured invitation/login address. Public login addresses must use HTTPS; HTTP is accepted only for loopback development. The request response does not disclose whether an account exists, is verified or can receive mail. SMTP is queued through a bounded in-memory worker pool so delivery latency does not disclose eligibility. A server restart or full queue can lose pending delivery; request another link later. Requests are limited to three per account and ten per resolved source address per hour.

Links contain 32 random bytes, expire in 15 minutes and work once. Only a SHA-256 verifier is stored. The fragment is removed from the browser address before rendering the reset form; it is never stored in localStorage. A new request replaces the earlier link. Changing the account's email/version, disabling the account or removing its mailbox proof prevents use. Failed or uncertain SMTP delivery invalidates that link. Password strength rules are the same as normal password changes.

If MFA is enabled, the user must also provide their authenticator or an unused recovery code. Resetting a password never disables MFA or changes roles, sharing or permissions. Successful recovery increments the account version, deletes its login sessions and notification devices and requires a fresh login. It records account IDs and action names in the audit log, not passwords or reset tokens.

The owner can use **Settings → Tax agent access → Send password reset** after entering their current password and MFA code when enabled. This queues a link to the agent's verified mailbox. It does not reveal a password to the owner, bypass the agent's MFA or revoke sessions before completion.

The existing `server/reset_password.py` terminal fallback remains available to an operator with access to the data directory. It is necessary when SMTP, verified mailbox access or MFA recovery is unavailable. Existing users are not automatically marked verified or locked out by this release. No real SMTP provider or live mailbox is exercised by automated tests; test SMTP is captured locally.

## Passive intrusion monitoring

**Settings → Security → Intrusion monitoring** defaults to **Monitor only**. Off clears stored events/source counters and stops this feature. It watches only fixed, unused decoy paths (`/.env`, `/.git/config`, `/wp-login.php`, `/xmlrpc.php`); it does not classify general 404s, ordinary navigation, form text or query strings as suspicious. Decoys return no file content. There is no scanning, retaliation, credential guessing or outward action.

The optional **Temporary source blocks** mode blocks anonymous API/quote/decoy traffic for 15 minutes after five decoy requests within ten minutes. Sign-in, setup and recovery entry points, static pages and authenticated users remain accessible. Normal authentication/request limits still apply. Mode changes clear prior thresholds and blocks. The owner dashboard lists events and temporary blocks and allows reauthenticated unblocking.

Source identity uses the existing trusted-proxy resolver; arbitrary forwarded headers do not select an address unless the immediate peer is explicitly trusted. Configure `TRUSTED_PROXIES` only for infrastructure you control. Shared NAT/proxy addresses can group unrelated visitors, so monitor before enabling blocks. This is not a firewall, WAF or comprehensive attack detector; unseen paths are not detected and authenticated requests remain governed by normal permissions.

Stored events contain a keyed source fingerprint, timestamp, fixed decoy label and action. They do not contain raw IP addresses, request bodies, headers or query strings. Events are capped at 500 and pruned after seven days on feature access; source state is capped at 1,000 entries, with expired state pruned on decoy access. Capacity eviction can shorten older blocks. Proxy/Gunicorn logs and external retention remain separate operator responsibilities.

## Fuel odometer provenance

Fuel records now retain **Estimated from synced drives**, **Confirmed dashboard reading**, or **Unknown / not confirmed** through drafts, save/reopen, reports and CSV. Editing an estimate does not confirm it; select confirmed dashboard explicitly after checking the actual reading. Unknown readings may be blank. Only confirmed dashboard values contribute to measured-distance and fuel-economy calculations; estimated/unknown fill-ups interrupt fuel-economy intervals. Expenses and fuel amounts are retained.

Migration m041 keeps all legacy odometer numbers and labels their source unknown because earlier records did not store evidence of confirmation. Older clients omitting a source keep an existing source only when the numeric reading is unchanged; new or changed unlabelled readings become unknown. No odometer-log baseline is created from a fuel estimate. No FY26–27 tax-rate or deduction-forecast logic changes are included.

Migrations m039–m041 add recovery and monitoring storage and fuel provenance. Back up before upgrading; rollback requires the matching pre-upgrade database backup and image. Stable, iOS and live deployments are outside this release.
