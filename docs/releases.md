# Stable and beta releases

| Channel | Git branch | Docker image | Current version |
| --- | --- | --- | --- |
| Stable | `main` | `ghcr.io/chrisk0007/expense-pilot:latest` | `1.0.1` |
| Beta | `beta` | `ghcr.io/chrisk0007/expense-pilot:beta` | `1.0.2-beta.1` |

Stable v1.0.1 promotes all changes through v1.0.1-beta.4: [PocketSmith bank feeds](pocketsmith.md), the nullable transfer flag fix, shared billing navigation including Clients, invoice reminder controls and permanent expense/receipt deletion.

Beta v1.0.2-beta.1 adds editable services/prices and invoice numbers, reuse of newly deleted invoice numbers, per-invoice reminder schedules and email wording, and interface improvements. Migration m009 runs automatically and retains existing records. Back up beta `/data` before updating; restore that backup to return to an older image. Stable stays on v1.0.1.

The first stable release is v1.0.0, carrying forward v0.8.6. The initial beta starts from the same application features, identified as v1.0.1-beta.1 so future development is clearly separate. Each published build also has its exact version tag and a `sha-` tag.

## Using the channels on Unraid

For normal use, keep the existing `expense-pilot` container on `ghcr.io/chrisk0007/expense-pilot:latest`. Use **Docker → Check for Updates → Update**, then refresh the browser and check the version in Settings. To pin this stable release, set the image to `ghcr.io/chrisk0007/expense-pilot:1.0.1` instead. Preserve the existing `/data` mapping and environment settings.

For testing, create a separate `expense-pilot-beta` container using `ghcr.io/chrisk0007/expense-pilot:beta`. Map `/data` to a different host directory, such as `/mnt/user/appdata/expense-pilot-beta`, and choose a different host port, such as `8787` mapped to container port `8788`. Give this fresh instance its own setup token and test records. Do not mount the live data directory in both containers. Keep automatic reminders and real email delivery disabled in a test instance unless deliberately testing them with test recipients.

The beta container updates only when the beta image is published; the stable container updates only when a stable image is published. A beta may later introduce database migrations that an older stable build cannot read. Returning that data to an older release requires restoring its matching backup; changing only the image tag does not undo migrations.

## Upgrading from v1.0.0 to v1.0.1

Back up each stable instance’s `/data` directory before updating. Migration m008 adds the PocketSmith tables automatically; existing users, expenses, receipts, invoices and settings are retained. No new container variables are needed. Configure PocketSmith separately in each instance if desired. Returning to v1.0.0 requires restoring that instance’s pre-upgrade backup.

## Developing and promoting a release

1. Start new work from `beta` and submit feature changes back to `beta`. Increment the prerelease version in `server/VERSION` for each new beta release, for example `1.0.1-beta.2`.
2. Both channels must pass release metadata validation, dependency auditing, backend tests, production startup and browser workflows before publishing. Pull requests run checks without publishing.
3. To promote tested work, create a release branch from `beta`, change `server/VERSION` to the intended stable version (for example `1.0.1`), update the changelog and open a pull request to `main`. Merge after the checks pass. The `main` build publishes the numbered image and moves `latest`.
4. Bring the stable merge back into beta development, and set the next prerelease version (for example `1.0.2-beta.1`) before pushing to `beta`. Use one prepared update so `beta` always has a prerelease version.

Do not merge an unmodified beta version into `main`: CI rejects it. Beta builds never publish a stable numbered tag or `latest`. Manual workflow runs publish only from `main`, `beta` or an exact matching version tag. Git tags such as `v1.0.0` must match `server/VERSION`; tag builds publish the numbered image without moving `latest` or `beta`.

## iPhone development

Continue iPhone work in [expense-pilot-ios](https://github.com/ChrisK0007/expense-pilot-ios). Download or clone that repository and open `ExpensePilot.xcodeproj` at its root. Keep the same Personal Team and bundle identifier for the app already installed on your phone. The move keeps iPhone version 0.1.1 and does not require reinstalling the app. Its simulator build is separate from Docker publishing.

The iPhone app connects to the server address you select. Using the normal server address keeps it on the stable workspace; using a separate beta server address connects it to beta test data. Earlier iPhone source history remains available in the server repository before the v1.0.0 split.
