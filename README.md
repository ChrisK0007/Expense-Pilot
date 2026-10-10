# Expense Pilot

*a clearer view of every dollar*

Self-hosted expense tracking for sole traders and people tracking employment expenses, with receipt capture, split deductions, invoicing and optional tax-agent access.

## Install and update

- [Installation, Unraid, HTTPS, backups and account recovery](docs/guide.md)
- [iPhone app and free Xcode installation](https://github.com/ChrisK0007/expense-pilot-ios)
- [PocketSmith bank feeds](docs/pocketsmith.md)
- [Stable and beta release channels](docs/releases.md)
- [Development and repository structure](docs/architecture.md)
- [Release history](docs/CHANGELOG.md)

Stable Docker image: `ghcr.io/chrisk0007/expense-pilot:latest` (or pin `:1.0.1`). Beta development image: `ghcr.io/chrisk0007/expense-pilot:beta`.

`main` is the stable release branch; `beta` is for ongoing development. Beta builds publish only the beta channel and their numbered prerelease tag. Run beta in a separate container with its own data directory; see the release-channel guide.

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
| `tests/server/` | Backend integration and migration tests |
| `tests/browser/` | Browser workflows and disposable test server |
| `tests/release/` | Stable/beta publishing checks |
| `deploy/unraid/` | Unraid container template |
| `scripts/` | Preparation and backup utilities |
| `docs/` | Installation guide, architecture and release history |

The root Dockerfile and Compose files stay as stable deployment entry points. Root `prepare.sh` and `backup.sh` forward to `scripts/` so existing commands continue to work. The iPhone app has its own source, version and build workflow in [expense-pilot-ios](https://github.com/ChrisK0007/expense-pilot-ios).

## Vehicle odometer log (1.0.2-beta.2)

Open **Tracking → Vehicles → Odometer log** to add an actual dashboard reading with its date/time. The estimated odometer adds the full distance of later uploaded journeys, including personal driving; allocation percentages do not reduce vehicle mileage. Editing/deleting journeys recalculates the estimate. Add another actual reading to reconcile GPS differences or unrecorded driving without overwriting previous readings. Actual readings can be edited or deleted, with protection against stale concurrent edits.

The iPhone app 0.4.0 adds address search, driving-route choices, optional via locations, manual trips, GPS route extensions/gap corrections and a native odometer screen. It includes local pending mileage in its estimate and deduplicates journeys already uploaded. Maps and route geometry stay on the iPhone. Address search/routing use Apple Maps and need internet access; the web journey form continues to accept entered kilometres or odometer readings.

Trips without a time on the baseline day, or trips spanning the reading time, are flagged and excluded rather than guessed. Add the reading after stopping the trip, or add a later reading to establish a clear baseline. The web estimate only includes server journeys. New iPhone uploads include timestamps and an idempotency reference; identical repeated uploads resolve to the original journey. Existing server/API clients remain compatible.

Update the **beta** container to `ghcr.io/chrisk0007/expense-pilot:beta` after backing up its appdata. The migration adds odometer history and journey metadata; the stable container is unchanged.
