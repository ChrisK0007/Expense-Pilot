# Stable and beta releases

| Channel | Git branch | Docker image | Current version |
| --- | --- | --- | --- |
| Stable | `main` | `ghcr.io/chrisk0007/expense-pilot:latest` | `1.0.3` |
| Development beta | `beta` | `ghcr.io/chrisk0007/expense-pilot:beta` | `1.0.2-beta.13` |

The Docker public release is being prepared separately from iPhone testing. Stable 1.0.3 adds rolling 30-day website sessions to the features promoted in v1.0.2. See the [release checklist](release-checklist.md) for remaining verification and publication work.

## Choose a matching image and guide

Stable 1.0.2 includes PocketSmith feeds, invoice/service controls, budgets and vehicle comparisons, overnight spending, in-app AI modes, portable setup, full backup/account controls, workspace timezone, saved-address sync, mobile session/notification support and split-allocation badges. Setup tokens are optional and AI is configured in the application. Use the [stable setup guide](https://github.com/ChrisK0007/Expense-Pilot/blob/main/docs/public-release.md) and main-branch Unraid template. Beta remains available separately at 1.0.2-beta.13. Its prerelease history is in the [beta changelog](beta-changelog.md). See the [changelog](CHANGELOG.md) for the release history.

`latest` follows approved stable releases. Stable v1.0.2 currently contains the features tested through beta.13. A numbered tag pins a published release. Each published image also has a commit-derived `sha-` tag. Do not change the contents of a numbered release tag after publication.

## Run stable and beta separately

For normal existing stable use, keep `ghcr.io/chrisk0007/expense-pilot:latest` (or pin `:1.0.3`). On Unraid use **Docker → Check for Updates → Update**, then refresh the browser and check the version in Settings. Preserve the `/data` mapping and deployment settings.

For testing, use the beta image with a different container name, host port and data directory. For example, use container `expense-pilot-beta`, host port `8787` mapped to container `8788`, and `/mnt/user/appdata/expense-pilot-beta/data` mapped to `/data`. First-run tokens are optional in stable 1.0.2 and the current beta. Keep test email/reminders disabled unless deliberately testing delivery to addresses you control.

Never mount the same data directory into two running installations. Do not point a beta installation at your live stable data just to try it. A copied backup should be restored into a separate volume with email and integrations reviewed before startup.

## Updates and rollback

Back up each instance before upgrading. Startup runs numbered migrations; existing records and receipt paths are retained. An older image refuses a database containing newer migrations. Rollback therefore means restoring the matching older backup and image together, not only changing the image tag. Keep the current data volume intact until recovery is verified.

Stable 1.0.0 → 1.0.1 adds migration m008 for PocketSmith. Stable 1.0.2 adds migrations m009–m019 from the beta series; do not downgrade its database directly to stable 1.0.1. Check [backup architecture](architecture.md#backups) and the [full-backup guide](public-release.md#backup-and-restore).

## Development and promotion

1. Start application work from `beta` and submit a PR targeting `beta`. Increment the prerelease version for changed application releases.
2. Docker-triggering changes run release validation, dependency auditing, server integration tests, production startup and browser checks. PRs never publish images.
3. After candidate verification and owner agreement to publish, prepare a release branch from `beta`, set the chosen stable version and update release notes, templates and installation defaults together. Target `main` in the release PR.
4. Merge only after the release checks pass. The main workflow publishes the numbered version and updates `latest`. Verify the resulting digest and anonymous pull before announcing public availability.
5. Reconcile the stable release and documentation back into `beta`, setting the next prerelease version before application development continues.

Do not merge an unmodified prerelease version into `main`; the release checks reject it. Beta builds never publish `latest`. A matching `v` Git tag publishes the numbered image without moving either channel. Manual workflow runs can publish from the selected release ref; do not use them merely to validate documentation.

The existing Docker workflow filters by application/build/deployment paths. Changes confined to README files, `docs/`, support policies, issue/PR templates and `.gitignore` do not rebuild or publish the image. Changes under `server/`, `tests/`, `deploy/`, `scripts/`, Compose, Dockerfile or the Docker workflow do trigger it.

## iPhone testing

The iPhone app is independently versioned in its separate repository. It remains in testing while Docker release preparation proceeds. A phone connects to the server URL selected by its user; Docker upgrades do not update the installed iPhone build. Keep the registered bundle identifier and paid signing team when updating an existing test installation. The Docker release does not require CarPlay approval, an App Store launch or a central push service.
