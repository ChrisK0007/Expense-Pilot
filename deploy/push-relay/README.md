# Optional iPhone push relay

Local driving notifications need no relay. Without this optional service, receipts,
invoices, budgets and bank alerts update when the iPhone app connects to the server.
The relay is not deployed or enabled by a normal Expense Pilot update.

Build this directory with Docker, expose port 8790 behind your HTTPS reverse proxy,
and mount a writable `/data` directory owned by UID 10001. Mount your Apple `.p8`
push key read-only and set `APNS_KEY_FILE` to its path. Keep all keys out of git.

Set these on the relay (not in public application images):

- `APNS_TEAM_ID`: your Apple developer team ID.
- `APNS_KEY_ID`: the Apple APNs key ID.
- `APNS_TOPIC`: the registered bundle ID used by the signed iPhone app.
- `APNS_ENVIRONMENT`: `production` for TestFlight/App Store, `development` for a development-signed Xcode app. Use separate relays if testing both.
- `PUSH_RELAY_CLIENTS`: a JSON object mapping container names to distinct random tokens of at least 32 characters. Generate tokens locally; never reuse a login password.

Set these on each Expense Pilot container:

- `PUSH_RELAY_URL=https://your-relay.example/notify`
- `PUSH_RELAY_TOKEN`: that container's token from the relay mapping.

Recreate the container after configuring these environment variables. In Xcode,
enable **Push Notifications** for the registered App ID/target and refresh signing.
No extra Background Mode is needed for visible push alerts. Leave Location Updates
on for driving. Archive/upload the app, then enable Notifications and “Push alerts
while the app is closed” on the phone. Push registration requires HTTPS to the
Expense Pilot server, including when accessed at home.

The relay receives a device token, opaque account reference, alert type and record
reference. It never receives names, amounts, addresses, receipt contents or custom
message text. It sends a fixed generic preview. Authenticate every relay caller,
use HTTPS, keep port 8790 private behind the proxy, and rotate/revoke individual
container tokens when needed. APNs keys stay only on the relay.

Delivery is best effort. The application retries failures with backoff and deduplicates
successful deliveries. The relay adds retry deduplication, a per-container hourly
limit, APNs collapse IDs and a one-hour expiry. Quiet hours use the last timezone
reported by the phone. Sign-out revokes the device's server login and registration;
remote alerts pause when that login expires. Beta.12 and iPhone 0.8.5 renew
remembered-device logins for 30 days from authenticated activity. Older/browser
logins still expire after 12 hours. Push delivery never renews a login. Local drive alerts continue independently of push delivery.
This conservative session binding avoids sending account alerts after access ends.

Apple signing, APNs delivery, your reverse proxy and real-device lock-screen behavior
must be checked with your own developer account before advertising public push support.
