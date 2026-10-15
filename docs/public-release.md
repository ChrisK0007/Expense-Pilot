# Public-release preparation — beta 1.0.2-beta.7

Expense Pilot is a free self-hosted application with a separately versioned native iPhone client. The backend remains a Docker service on Unraid, Windows/macOS Docker Desktop, Linux or another Docker host. Keep the server running for remote access; the phone retains local drafts during outages. This beta prepares public distribution; it is not an App Store submission.

## New portable installation

1. Install Docker (Docker Desktop using Linux containers on Windows/macOS). Download `compose.public.yaml` from this repository into a dedicated folder.
2. Create `.env` in that folder with `SETUP_TOKEN=` followed by a unique random value of at least 24 characters. Generate it with a password manager. Do not publish this file. Optionally set `IMAGE=ghcr.io/chrisk0007/expense-pilot:1.0.2-beta.7` to pin this beta.
3. Run `docker compose -f compose.public.yaml up -d`.
4. Open `http://localhost:8788`. Enter the setup token, your name, email and a password of at least 12 characters. Sign in, then open **Settings → Workspace setup**. Create the owner account before exposing the server remotely.
5. Set business details if you issue invoices, choose AI or manual entry, and download a private backup. Configure email, bank feeds and other features only when needed.

The portable file uses a Docker named volume, avoiding host-path permissions on Windows/macOS. The existing Unraid templates and `compose.yaml`/`compose.registry.yaml` keep their existing mounts and configuration; do not switch an existing installation to an empty volume. Multiple installations need separate data volumes, ports and setup tokens. Never share the same data volume between stable and beta.

The published server image is currently Linux AMD64. This Compose file selects that platform explicitly; Apple silicon and other ARM Docker hosts need AMD64 emulation. Native ARM images and host-specific installation tests remain release follow-up work. Ollama's companion image chooses its own available native platform.

The default port binds only to the host's loopback interface. For trusted LAN access, set `BIND_ADDRESS=0.0.0.0` and configure the host firewall. For access from a phone away from home use a VPN or a properly configured HTTPS reverse proxy. Do not expose unencrypted HTTP to the internet. Set `COOKIE_SECURE=true` when using HTTPS. The native app requires a direct Expense Pilot endpoint and does not bypass an external SSO wall or invalid TLS certificate.

## Receipt AI modes

**No AI** is the default when no legacy Ollama environment is present. Manual entry, receipt storage, invoices and tracking continue to work. Existing `OLLAMA_URL`/`OLLAMA_MODEL` settings are preserved until the owner explicitly saves settings in the application.

**Local Ollama:** start the optional companion with `docker compose -f compose.public.yaml --profile local-ai up -d`. Download a vision model explicitly, for example `docker compose -f compose.public.yaml exec ollama ollama pull gemma3:4b`. Choose Local Ollama and that model in Settings. The companion is reachable inside the Docker network at `http://ollama:11434`; it has no public host port. This generic profile uses CPU by default. Existing Intel/NVIDIA/Apple hardware setups can instead use the existing/remote mode. Model downloads need internet and adequate storage/memory. Choosing a model in Expense Pilot does not download it.

**Existing / remote Ollama:** enter the base URL of the existing service and an installed vision model. Your `ollama-intel-gpu` container remains supported. An optional bearer key supports authenticated proxies; use a direct endpoint without redirects. Public endpoints require HTTPS; trusted LAN/Docker endpoints can use HTTP.

**Cloud AI:** choose OpenAI or Anthropic, enter your API key and exact vision-capable model ID, and explicitly agree to provider processing and charges. Keys are encrypted server-side and never returned to the client. Changing destination clears the saved key. API usage is billed by the provider; a consumer chat subscription is separate. No automatic provider fallback is performed. **Test saved connection & load models** lists available models without sending a receipt or generating a response; it does not prove image support. All AI output stays a draft for review. OpenAI requests disable response storage; the provider's other retention policies still apply.

## Email copies

In **Settings → Email delivery**, enable **Send me a copy of client emails** and choose the destination (initially your owner email). The same message and PDF attachments are BCC'd for invoices, quotes, automatic/manual reminders, payment receipts and statements. Clients do not see the BCC address. Invitations and test messages are excluded. A rejected copy is recorded as a warning without retrying an already-delivered client email. Issuing an invoice without sending an email produces no email copy.

## Backup and restore

**Settings → Privacy & data → Download full backup / restore guide** creates a consistent database snapshot plus receipt originals and the key needed to decrypt saved credentials. It requires your current password and authenticator/recovery code when enabled. The ZIP is not encrypted: store it privately. Host `.env`, reverse-proxy configuration and earlier archives are separate. The existing `backup.sh` full host backup remains available and is useful for regular scheduled host backups. Large backups that exceed the container's temporary storage should use that host helper.

Restore a downloaded ZIP into a **new empty data volume** with the application stopped. Keep the old volume as rollback. For example, create `expense-pilot-restored` using `docker volume create expense-pilot-restored`, then run:

```
docker run --rm --mount type=volume,source=expense-pilot-restored,target=/data --mount type=bind,source=/absolute/path/expense-pilot-backup.zip,target=/backup.zip,readonly --entrypoint python ghcr.io/chrisk0007/expense-pilot:1.0.2-beta.7 restore_backup.py /backup.zip
```

Use the full host path to your downloaded file (Docker Desktop may ask to share that folder). The restore command validates the manifest, checksums, allowed paths, database integrity, migration checksums and complete receipt inventory before installing the data. It refuses a nonempty destination. Use this version or a compatible newer image, then configure the service to mount the restored volume, supply the original deployment settings and start it. Sign in again; restored login sessions are revoked. Never restore while another container writes to the target volume. Host-helper `.tar.gz` archives use the separate restore process in `architecture.md`.

Before upgrading, back up and retain the previous image version. Then run `docker compose -f compose.public.yaml pull` and `docker compose -f compose.public.yaml up -d`, or update the selected Unraid container. Numbered migrations run transactionally. An older image refuses a database with newer migrations; roll back using the matching older backup and image together. Stable remains on its own release channel.

## Privacy and account lifecycle

The `/privacy` page explains storage, optional AI/email/bank services, GPS/address lookup, phone permissions and deletion. It is available before login and linked from Settings. The operator must review this information against their own hosting and backup practices.

Account deletion requires a current password, 2FA when enabled and an exact confirmation phrase. An owner deletes the **entire shared workspace**, including other accounts, settings, receipts and financial records. A tax agent deletes their own login while the owner's records remain. Earlier exports, messages, backups and other devices are separate. Export anything you need first. Deletion is never performed by an update.

## Mobile protocol and release preparation

`GET /api/server-info` identifies the application, API version, minimum client API and installation identity without credentials. `/api/session` retains existing fields and includes feature capabilities. Clients must check capabilities before using newer features. API version 1 remains backward compatible; server and iOS app versions are independent.

New mobile expense and receipt uploads accept a UUID `client_ref`. Exact retries return a matching `id`, `client_ref` and `stored: true`. Changed payloads conflict; deleted records retain a tombstone so delayed retries cannot recreate them. Clients must keep local copies until the matching acknowledgement is received. Trips retain their existing route-preserving acknowledgement contract.

Before App Store submission: enrol the Apple developer account, choose final app identifiers and support/privacy URLs, verify privacy disclosures against the actual shipped app, provide a reachable review/demo server with synthetic records, collect screenshots, test on physical devices through TestFlight, and submit via App Store Connect. Use a separate disposable server for review; never provide your personal workspace or financial records. CarPlay requires a separate Driving Task entitlement approval and signing; ordinary free development builds remain usable without it.
