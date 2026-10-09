# Expense Pilot

*a clearer view of every dollar*

Self-hosted expense tracking for sole traders and people tracking employment expenses, with receipt capture, split deductions, invoicing and optional tax-agent access.

## Install and update

- [Installation, Unraid, HTTPS, backups and account recovery](docs/guide.md)
- [iPhone app and free Xcode installation](ios/README.md)
- [Development and repository structure](docs/architecture.md)
- [Release history](docs/CHANGELOG.md)

Docker image: `ghcr.io/chrisk0007/expense-pilot:latest` (or pin `:0.8.2`).

Existing Unraid installations can update the image normally. Container paths remain `/app` and `/data`; the database remains `/data/rounded.sqlite`. Keep your current appdata mount and environment settings.

For a new source installation, run these commands from the repository root:

```sh
bash prepare.sh
docker compose up -d --build
```

Read the installation guide before exposing the application outside your local network.

## Repository layout

| Path | Purpose |
| --- | --- |
| `server/` | Python backend, browser assets, suburb data and database migrations |
| `ios/` | Native iPhone app and Xcode project |
| `tests/server/` | Backend integration and migration tests |
| `tests/browser/` | Browser workflows and disposable test server |
| `deploy/unraid/` | Unraid container template |
| `scripts/` | Preparation and backup utilities |
| `docs/` | Installation guide, architecture and release history |

The root Dockerfile and Compose files stay as stable deployment entry points. Root `prepare.sh` and `backup.sh` forward to `scripts/` so existing commands continue to work. iOS remains in this repository, with its own version and build workflow.
