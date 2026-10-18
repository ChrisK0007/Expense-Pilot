<img src="server/static/expense-pilot-logo.png" alt="Expense Pilot logo" width="104">

# Expense Pilot

*A clearer view of every dollar.*

Self-hosted expense tracking and invoicing for Australian sole traders and people tracking employment expenses. Run the Docker container on your own server and use it in a browser.

**Stable Docker release: 1.0.5.** The optional iPhone app remains in testing and is not required to use Expense Pilot.

This checkout is the beta channel; use the [beta installation guide](docs/public-release.md) and a separate test data volume.

## Built with AI

Expense Pilot is developed with substantial assistance from AI tools, including OpenAI’s ChatGPT and Codex. AI assists with writing code, debugging, tests and documentation. The project maintainer sets the direction and approves releases.

Development use of AI is separate from the app’s optional receipt-reading features. You can use Expense Pilot without enabling receipt AI; any configured AI service is controlled through the app’s settings.

## What it does

- Track Employment, Business and Personal expenses, including split allocations and retained receipt originals.
- Review receipt drafts with optional AI assistance and organise overnight trip spending.
- Manage clients, quotes, invoices, payments, recurring drafts and email reminders.
- Import bank CSVs or connect your own PocketSmith account, then review and match transactions.
- Give a tax agent read-only or read/write access to your workspace and export records for tax time.

Records live in the Docker data volume. Optional AI, bank feeds and email use the services you configure. There is no required Expense Pilot cloud account or central relay. Expense Pilot records and estimates amounts; it does not lodge tax returns or decide which expenses are deductible.

## Choose the right channel

| Channel | Image | Documentation |
| --- | --- | --- |
| Stable — 1.0.5 | `ghcr.io/chrisk0007/expense-pilot:latest` or `:1.0.5` | [Stable installation guide](https://github.com/ChrisK0007/Expense-Pilot/blob/main/docs/public-release.md) |
| Beta — 1.0.6-beta.1 | `ghcr.io/chrisk0007/expense-pilot:beta` or `:1.0.6-beta.1` | [Beta installation and setup](https://github.com/ChrisK0007/Expense-Pilot/blob/beta/docs/public-release.md) |

**Use the template and instructions from the same branch as your image.** AI is configured in the app and the setup token is optional.

Public installations do not require a GitHub account or registry login. See [release channels and upgrades](docs/releases.md).

## Install or update

- **Unraid:** follow the [installation guide](docs/public-release.md#unraid-installation) and use `deploy/unraid/expense-pilot.xml`. Community Apps listing is subject to Unraid review.
- **Docker Desktop / Linux:** the [portable Compose guide](docs/public-release.md#new-portable-installation) uses a named volume. The current image is Linux AMD64; ARM hosts require emulation and have not been verified.
- **Existing installations:** preserve the `/data` mount and deployment settings, back up first, then update the same channel. Switching an image tag does not undo database migrations.
- **Separate stable and beta:** use different data volumes and host ports. Never share a data directory between running containers.

The web port is `8788`; persistent records are under `/data`, including `rounded.sqlite`, receipt files and `session.key`. The database filename is retained for upgrade compatibility. Remote access needs your own VPN or HTTPS reverse proxy. Complete owner setup on a trusted connection before exposing a fresh installation.

## Documentation and help

- [Documentation index](docs/README.md)
- [User guide and operations](docs/guide.md)
- [Release history](docs/CHANGELOG.md)
- [Support](SUPPORT.md) · [Security reporting](SECURITY.md)
- [Contributing](CONTRIBUTING.md) · [Licensing and notices](docs/licensing.md)

The iPhone companion is developed separately and remains in testing. Docker releases do not depend on an App Store release; server notifications can be read when the app connects, without a shared push relay.

## Repository layout

| Path | Purpose |
| --- | --- |
| `server/` | Backend, browser interface, migrations and bundled data |
| `tests/` | Server, browser and release checks |
| `deploy/unraid/` | Channel-specific Unraid template |
| `scripts/` | Setup, backup and release helpers |
| `docs/` | Installation, operations and release documentation |

Licensed under the [GNU Affero General Public License v3.0 only](LICENSE) (`AGPL-3.0-only`). Copyright (C) 2026 ChrisK0007. Third-party components retain their own licences; see [licensing and notices](docs/licensing.md). The separately maintained iPhone app is outside this repository licence.
