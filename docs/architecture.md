# Development and deployment structure

This repository contains the backend and web client. The iPhone app, Xcode project, native tests and simulator workflow are maintained in [expense-pilot-ios](https://github.com/ChrisK0007/expense-pilot-ios). Coordinate API changes across the two repositories. Documentation-only changes do not rebuild the Docker image.

## Backend

Run commands below from the repository root. Python imports resolve from `server/`. Docker copies that directory to `/app`, preserving the production entry point `app:app` and recovery utility `/app/reset_password.py`.

- `app.py`: application setup, shared request helpers, core accounts, trips and expenses.
- `receipt_routes.py`: receipt upload, inspection, extraction and inbox endpoints.
- `finance_routes.py`: bank imports, exports, employment income and forecast endpoints.
- `billing.py`: billing setup, shared services, clients, schedules and payments.
- `billing_documents.py`: document endpoints.
- `security.py`, `tracking.py`, `features.py`: feature registration and services.
- `*_core.py`: calculations and parsing independent of HTTP routes.
- `static/` and `datasets/`: browser assets and bundled suburb lookup data.

Route modules are loaded after their shared decorators are defined. Function-local imports resolve shared services at request time, including service replacements used by tests. Import `app` as the application entry point, rather than importing a route module directly.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r server/requirements.txt
PYTHONPATH=server python -m unittest discover -s tests/server -v
# Use a disposable DATA_DIR for local development; configure SETUP_TOKEN first.
DATA_DIR=/tmp/expense-pilot-dev python server/app.py
```

Production uses Gunicorn, not Flask's development server. Browser suites live in `tests/browser/`; see the Docker workflow for their Playwright setup. The disposable browser server is excluded from the production image. CI also boots the real Gunicorn entry point and checks its reported version.

## Database migrations

Startup applies `server/migrations/mNNN_description.py` in filename order. Each module exposes `upgrade(connection)`. A `schema_migrations` ledger records the name, checksum and application time. `BEGIN IMMEDIATE` serialises concurrent startup; a failed migration rolls back its schema/data changes and its ledger entry together. Successful earlier migrations remain committed.

The first six migrations adopt existing installations using idempotent table/column creation. Existing receipts, accounts, allocations and historical employee records remain present; legacy employee accounts remain disabled. The SQLite filename and receipt storage paths do not change.

Add a new numbered file for future schema changes. Never edit a released migration: checksums detect accidental drift. Use `migrations.execute_script` for transactional SQL, not `connection.executescript`, and never commit inside `upgrade`. Migrations must not change filesystem data. Take a backup before upgrading; rollback to an older release requires restoring the matching backup, because startup rejects unknown newer migrations.

## Versions and image context

`server/VERSION` is the source for the API version and numbered Docker image tag. `main` requires `X.Y.Z` and publishes `latest`; `beta` requires `X.Y.Z-beta.N` and publishes `beta`. CI rejects versions assigned to the wrong branch, verifies any `v` Git tag matches, and never publishes pull requests or topic branches. Matching Git tags publish their numbered image without moving either channel. See [release channels](releases.md) for development and promotion steps.

iOS keeps independent marketing/build versions in its separate Xcode repository. Docker's allowlist includes only the Dockerfile and `server/`, excluding tests, local data and secrets. `python -m unittest discover -s tests/release -v` checks the publishing rules before the Docker build; the existing backend, startup and browser checks still gate every published image.

## Backups

```sh
bash backup.sh /path/to/private/backups
# A different container name:
CONTAINER_NAME=my-expense-pilot bash backup.sh /path/to/private/backups
```

The backup utility inspects the selected container's actual `/data` mount instead of assuming the checkout's `data/` directory. It stops a running container, creates the archive and restarts it even when archiving fails. A container that was already stopped stays stopped. It refuses to place backups inside the data directory. Run with access to Docker and the host mount (usually as root on Unraid).

Archives contain `data/` including `rounded.sqlite`, receipts and `session.key`; the checkout's `.env` is included when present. For a different `.env` location, set `EXPENSE_PILOT_ENV_FILE` to that file. Unraid template environment settings live outside the data mount; preserve those settings separately using your normal Unraid configuration backup.

For offline data without a Docker container, first stop every process using the database, then set `EXPENSE_PILOT_DATA_DIR` to the data directory. This explicit mode does not stop or restart any container. Protect archives as sensitive financial data. Restore `data/` to the configured host mount while the app is stopped and retain the existing ownership (normally UID 99/GID 100).

## PocketSmith bank feeds

`pocketsmith_client.py` is a GET-only client for the fixed PocketSmith v2 HTTPS host. It passes developer keys in a header, blocks redirects, bounds pages, response sizes and duration, validates pagination and sanitises upstream failures. `pocketsmith.py` manages an encrypted per-instance connection, account mapping, sync leases, the transaction ledger and review routes. `bank-feeds.js` provides connection settings and the bank review queue.

Migration m008 adds the connection, account mapping and source transaction tables. Keys use a dedicated Fernet derivation from `session.key`; backups must retain both the database and key. The Gunicorn hook starts a polling thread; a durable lease and connection version prevent overlapping workers or superseded configuration from committing stale syncs. Automatic sync is disabled until selected by the owner.

A sync fetches the complete selected date window before an atomic upsert. The unique source user/transaction ID prevents repeated imports. Absent transactions are flagged as not returned, not silently deleted. Financial changes to linked source records flag review and never change expense amounts or allocations. Creating an expense and linking its source row share one database transaction; deleting a linked expense leaves an ignored source record to prevent recreation. Existing-expense matching is explicit and limited to equal AUD amounts within three days and the same or unassigned account.

Tests replace only the PocketSmith client in the disposable browser server; the production image contains neither test credentials nor test endpoints. Tests cover failed sync atomicity, pagination, retry limits, pending replacement, duplicate protection, changed/missing records, permission boundaries, encryption and configuration changes during sync.
