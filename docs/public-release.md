# Beta installation and configuration — 1.0.4-beta.2

Expense Pilot is a free self-hosted application with a separately versioned native iPhone client. The backend remains a Docker service on Unraid, Windows/macOS Docker Desktop, Linux or another Docker host. Keep the server running for remote access; the phone retains local drafts during outages. This guide describes beta 1.0.4-beta.2. Stable v1.0.4 includes this feature set; use the [stable guide](https://github.com/ChrisK0007/Expense-Pilot/blob/main/docs/public-release.md) for stable image defaults. The iPhone app stays in testing; no App Store setup is needed to install the container.

## New portable installation

1. Install Docker (Docker Desktop using Linux containers on Windows/macOS). Download `compose.public.yaml` from this repository into a dedicated folder.
2. Optionally create `.env` to customise the installation. Set `SETUP_TOKEN=` to a unique random value of at least 24 characters if you want protected first-run owner creation, or leave it blank/unset for token-free setup. Optionally set `IMAGE=ghcr.io/chrisk0007/expense-pilot:1.0.4-beta.2` to pin this beta release.
3. Run `docker compose -f compose.public.yaml up -d`.
4. Open `http://localhost:8788`. Enter your name, email and a password of at least 12 characters. The setup token field appears only when a token is configured. Sign in, then open **Settings → Workspace → Workspace setup**. Create the owner account before exposing the server remotely.
5. Set business details if you issue invoices, choose AI or manual entry under **Settings → Receipts & AI**. Configure email, bank feeds and other features only when needed.

The portable file uses a Docker named volume, avoiding host-path permissions on Windows/macOS. The existing Unraid templates and `compose.yaml`/`compose.registry.yaml` keep their existing mounts and configuration; do not switch an existing installation to an empty volume. Multiple installations need separate data volumes and ports, plus unique setup tokens if configured. Never share the same data volume between stable and beta.

The published server image is currently Linux AMD64. This Compose file selects that platform explicitly; Apple silicon and other ARM Docker hosts need AMD64 emulation. Native ARM images and host-specific installation tests remain release follow-up work. Ollama's companion image chooses its own available native platform.

The default port binds only to the host's loopback interface. For trusted LAN access, set `BIND_ADDRESS=0.0.0.0` and configure the host firewall. For access from a phone away from home use a VPN or a properly configured HTTPS reverse proxy. Do not expose unencrypted HTTP to the internet. Set `COOKIE_SECURE=true` when using HTTPS. The native app requires a direct Expense Pilot endpoint and does not bypass an external SSO wall or invalid TLS certificate.

## Receipt AI modes

**No AI** is the default when no legacy Ollama environment is present. Manual entry, receipt storage, invoices and tracking continue to work. Existing `OLLAMA_URL`/`OLLAMA_MODEL` settings are preserved until the owner explicitly saves settings in the application.

**Local Ollama:** start the optional companion with `docker compose -f compose.public.yaml --profile local-ai up -d`. Download a vision model explicitly, for example `docker compose -f compose.public.yaml exec ollama ollama pull gemma3:4b`. Choose Local Ollama and that model in Settings. The companion is reachable inside the Docker network at `http://ollama:11434`; it has no public host port. This generic profile uses CPU by default. Existing hardware-accelerated Ollama services can instead use the existing/remote mode; GPU configuration remains with that service. Model downloads need internet and adequate storage/memory. Choosing a model in Expense Pilot does not download it.

**Existing / remote Ollama:** enter the base URL of the existing service and an installed vision model. An existing `ollama-intel-gpu` container can be used through this mode. An optional bearer key supports authenticated proxies; use a direct endpoint without redirects. Public endpoints require HTTPS; trusted LAN/Docker endpoints can use HTTP.

**Cloud AI:** choose OpenAI or Anthropic, enter your API key and exact vision-capable model ID, and explicitly agree to provider processing and charges. Keys are encrypted server-side and never returned to the client. Changing destination clears the saved key. API usage is billed by the provider; a consumer chat subscription is separate. No automatic provider fallback is performed. **Test saved connection & load models** lists available models without sending a receipt or generating a response; it does not prove image support. All AI output stays a draft for review. OpenAI requests disable response storage; the provider's other retention policies still apply.

## Email copies

In **Settings → Email delivery**, enable **Send me a copy of client emails** and choose the destination (initially your owner email). The same message and PDF attachments are BCC'd for invoices, quotes, automatic/manual reminders, payment receipts and statements. Clients do not see the BCC address. Invitations and test messages are excluded. A rejected copy is recorded as a warning without retrying an already-delivered client email. Issuing an invoice without sending an email produces no email copy.

## Backup and restore

**Settings → Data & privacy → Download full backup / restore guide** creates a consistent database snapshot plus receipt originals and the key needed to decrypt saved credentials. It requires your current password and authenticator/recovery code when enabled. The ZIP is not encrypted: store it privately. Host `.env`, reverse-proxy configuration and earlier archives are separate. The existing `backup.sh` full host backup remains available and is useful for regular scheduled host backups. Large backups that exceed the container's temporary storage should use that host helper.

Restore a downloaded ZIP into a **new empty data volume** with the application stopped. Keep the old volume as rollback. For example, create `expense-pilot-restored` using `docker volume create expense-pilot-restored`, then run:

```
docker run --rm --mount type=volume,source=expense-pilot-restored,target=/data --mount type=bind,source=/absolute/path/expense-pilot-backup.zip,target=/backup.zip,readonly --entrypoint python ghcr.io/chrisk0007/expense-pilot:1.0.4-beta.2 restore_backup.py /backup.zip
```

Use the full host path to your downloaded file (Docker Desktop may ask to share that folder). The restore command validates the manifest, checksums, allowed paths, database integrity, migration checksums and complete receipt inventory before installing the data. It refuses a nonempty destination. Use this version or a compatible newer image, then configure the service to mount the restored volume, supply the original deployment settings and start it. Sign in again; restored login sessions are revoked. Never restore while another container writes to the target volume. Host-helper `.tar.gz` archives use the separate restore process in `architecture.md`.

Before upgrading, back up and retain the previous image version. Then run `docker compose -f compose.public.yaml pull` and `docker compose -f compose.public.yaml up -d`, or update the selected Unraid container. Numbered migrations run transactionally. An older image refuses a database with newer migrations; roll back using the matching older backup and image together. Stable remains on its own release channel.

## Privacy and account lifecycle

The `/privacy` page explains storage, optional AI/email/bank services, GPS/address lookup, phone permissions and deletion. It is available before login and linked from Settings. The operator must review this information against their own hosting and backup practices.

Account deletion requires a current password, 2FA when enabled and an exact confirmation phrase. An owner deletes the **entire shared workspace**, including other accounts, settings, receipts and financial records. A tax agent deletes their own login while the owner's records remain. Earlier exports, messages, backups and other devices are separate. Export anything you need first. Deletion is never performed by an update.

## Mobile protocol and release preparation

`GET /api/server-info` identifies the application, API version, minimum client API and installation identity without credentials. `/api/session` retains existing fields and includes feature capabilities. Clients must check capabilities before using newer features. API version 1 remains backward compatible; server and iOS app versions are independent.

New mobile expense and receipt uploads accept a UUID `client_ref`. Exact retries return a matching `id`, `client_ref` and `stored: true`. Changed payloads conflict; deleted records retain a tombstone so delayed retries cannot recreate them. Clients must keep local copies until the matching acknowledgement is received. Trips retain their existing route-preserving acknowledgement contract.

The [Docker release checklist](release-checklist.md) tracks public image access, installation tests, upgrades, restore and repository settings. The iPhone app has its own testing and release schedule; its App Store submission and CarPlay entitlement do not block the Docker release. Server alerts in the current test app refresh directly when it connects; no shared push relay is required.

## Workspace timezone

New owner setup suggests the browser or iPhone timezone. Confirm it for your workspace. Existing installations retain **Australia/Brisbane** until the owner changes **Settings → Workspace → Workspace timezone**. The setting applies to all accounts and devices and handles daylight saving automatically. It is independent of the Docker host's location and `TZ` variable; travelling with a phone does not change it. Refresh other connected devices after changing the setting.

Invoices, recurring drafts, reminders, budget date defaults, bank-feed sync ranges and tax-period progress use the workspace date. Saved invoice/expense/budget dates are never rewritten. Absolute event times stay in UTC; the audit table remains explicitly labelled UTC. Trip records retain their capture timezone, including offline iOS drafts and old Brisbane trips. Odometer entry uses workspace time and asks you to resolve repeated daylight-saving hours; nonexistent local times are rejected. Use a current compatible iPhone test build for timezone-aware native screens; see the companion repository for its current version.

The app remains Australian-focused: AUD, DD/MM/YYYY input, July–June financial years and Australian tax/allowance rules remain unchanged. Choosing another timezone does not select another country's accounting rules.

## Settings and optional setup

Settings is grouped into Workspace, Receipts & AI, Business & email, Bank feeds, Access & security, and Data & privacy. The topic buttons jump to each section. Features are personal preferences; timezone, AI and business configuration are shared owner-managed settings. Backup downloads are optional and are not setup checklist items. They do not schedule automatic backups.

The stable v1.0.4 Unraid template uses `:latest` and has no Ollama fields; the beta branch keeps its own `:beta` template. Existing containers keep their saved Unraid configuration when the image is updated. Save your AI configuration in the app before removing legacy `OLLAMA_URL` / `OLLAMA_MODEL` variables. Existing environment settings remain supported until you save in-app AI settings. If you still run v1.0.1, upgrade the image before adopting the optional-token and in-app AI setup described here.

`SETUP_TOKEN` is optional in stable v1.0.2 and the current beta. If set, the exact value (at least 24 characters) is required; an invalid or short configured token does not bypass protection. If blank/unset, the first person to reach the setup page can create the owner. Complete setup on a trusted network before exposing the server remotely. Existing logins and records are unaffected by removing the token. Initial owner creation remains locked once any account exists. An intentional full workspace deletion makes first-run setup available again.

## Source and licence downloads

Open **Source & licences** at login or in Settings → Data & privacy. The container serves its matching application source and build scripts, licence notices and version/checksum manifest without needing a GitHub account. Receipt files, financial records, credentials and Git history are excluded. Installation/help links use the build revision where available, otherwise the matching stable or beta branch.
