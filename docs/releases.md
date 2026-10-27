# Stable and beta releases

| Channel | Git branch | Docker image | Current version |
| --- | --- | --- | --- |
| Stable | `main` | `ghcr.io/chrisk0007/expense-pilot:latest` | `1.0.5` |
| Development beta | `beta` | `ghcr.io/chrisk0007/expense-pilot:beta` | `1.0.6-beta.9` |

The Docker server and web interface are released independently of the optional iPhone app, which remains in testing. See the [stable changelog](CHANGELOG.md) for shipped changes and [GitHub Releases](https://github.com/ChrisK0007/Expense-Pilot/releases) for versioned downloads.

## Choose a matching image and guide

Use the [stable setup guide](https://github.com/ChrisK0007/Expense-Pilot/blob/main/docs/public-release.md) and main-branch Unraid template for production. Use the [beta setup guide](https://github.com/ChrisK0007/Expense-Pilot/blob/beta/docs/public-release.md) and beta template for testing. Setup tokens are optional and AI is configured in the application. Prerelease changes are recorded in the [beta changelog](beta-changelog.md).

`latest` follows approved stable releases. A numbered tag pins a published release. Each published image also has a commit-derived `sha-` tag. Do not change the contents of a numbered release tag after publication.

## Run stable and beta separately

For normal existing stable use, keep `ghcr.io/chrisk0007/expense-pilot:latest` (or pin `:1.0.5`). On Unraid use **Docker → Check for Updates → Update**, then refresh the browser and check the version in Settings. Preserve the `/data` mapping and deployment settings.

For testing, use the beta image with a different container name, host port and data directory. For example, use container `expense-pilot-beta`, host port `8787` mapped to container `8788`, and `/mnt/user/appdata/expense-pilot-beta/data` mapped to `/data`. First-run tokens are optional. Keep test email/reminders disabled unless deliberately testing delivery to addresses you control.

Never mount the same data directory into two running installations. Do not point a beta installation at your live stable data just to try it. A copied backup should be restored into a separate volume with email and integrations reviewed before startup.

## Updates and rollback

Back up each instance before upgrading. Startup runs numbered migrations; existing records and receipt paths are retained. An older image refuses a database containing newer migrations. Rollback therefore means restoring the matching older backup and image together, not only changing the image tag. Keep the current data volume intact until recovery is verified.

Stable 1.0.0 → 1.0.1 adds migration m008 for PocketSmith. Stable 1.0.2 adds migrations m009–m019 from the beta series; do not downgrade its database directly to stable 1.0.1. Check [backup architecture](architecture.md#backups) and the [full-backup guide](public-release.md#backup-and-restore).

## Development and promotion

1. Start application work from `beta` and submit a PR targeting `beta`. Increment the prerelease version for changed application releases.
2. Docker-triggering changes run release validation, dependency auditing, server integration tests, production startup and browser checks. PRs never publish images.
3. After candidate verification and owner agreement to publish, prepare a release branch from `beta`, set the chosen stable version and update release notes, templates and installation defaults together. Target `main` in the release PR.
4. Merge only after the release checks pass. The main workflow publishes the numbered version, updates `latest`, and creates a matching GitHub release with source assets. Add `docs/release-notes/X.Y.Z.md` before publishing a stable version. Verify the resulting digest and anonymous pull before announcing public availability.
5. Reconcile the stable release and documentation back into `beta`, setting the next prerelease version before application development continues.

Do not merge an unmodified prerelease version into `main`; the release checks reject it. Beta builds never publish `latest`. A matching `v` Git tag publishes the numbered image without moving either channel. Manual workflow runs can publish from the selected release ref; do not use them merely to validate documentation.

The Docker workflow runs checks for every pull request. Push-triggered publishing filters by application/build/deployment paths. Changes confined to README files, `docs/`, support policies, issue/PR templates and `.gitignore` do not rebuild or publish the image. Changes under `server/`, `tests/`, `deploy/`, `scripts/`, Compose, Dockerfile or the Docker workflow do trigger it.

Beta builds reuse inline cache metadata from the published `:beta` image. This does not create a GitHub Actions cache or an extra build-record artifact. It caches fewer intermediate stages than a full registry/GHA cache but avoids a separate cache storage footprint. The base image is pulled each build, and `DEPENDENCY_REFRESH` changes each UTC day to rerun dependency installation. Stable and tag builds use no cache. All tests still run against the exact image that is published; dependency source archives remain inside that image.

## Release checklist

Use this checklist for each release. Record results against the candidate version in its pull request or GitHub release; keep private data and diagnostics out of the repository.

- [ ] Set the version, channel defaults and changelog together. Add `docs/release-notes/X.Y.Z.md` for a stable release; never replace an existing numbered image.
- [ ] Pass `test-and-publish` on the current pull request. This covers dependency auditing, source archives, server tests, hardened startup and browser workflows.
- [ ] Test a fresh installation using synthetic records and disconnected integrations. Check owner setup, receipt review, invoice PDFs, account permissions, restart persistence and source downloads.
- [ ] Test an upgrade using a separate data directory. Restore a [full backup](public-release.md#backup-and-restore) into an empty destination and compare records, totals and receipt originals. Keep the original data and matching old image until recovery is confirmed.
- [ ] Test any configured AI, bank feed and email features deliberately; send test messages only to addresses you control. Record which hosts were tested. Linux AMD64 is the published image architecture; do not describe ARM emulation as native ARM support.
- [ ] After merging a release, verify the publishing run, image digest and tags. For stable releases, check `github-release` and the attached source archives, notices, manifests and checksums. If only that job fails, rerun the failed job; do not rerun successful publication of an immutable numbered image.
- [ ] Confirm signed-out access to the repository, release assets, template and icon, and test anonymous image pulls before announcing availability.
- [ ] For an Unraid listing, complete the Community Apps review and test an installation from the actual listing.

To check anonymous pulls without using your saved Docker login, substitute the candidate's numbered tag:

```bash
ep_public_config=$(mktemp -d)
docker --config "$ep_public_config" pull ghcr.io/chrisk0007/expense-pilot:1.0.5
docker --config "$ep_public_config" pull ghcr.io/chrisk0007/expense-pilot:latest
rm -r "$ep_public_config"
```

For beta, check its numbered tag and `:beta` instead. Compare the returned digests with the publishing run.

The repository and container package have separate visibility controls. Keep required pull requests and the `test-and-publish` check on both `main` and `beta`; keep force pushes and deletions disabled. A sole maintainer can leave required approvals off. Private vulnerability reporting should be available through the [security policy](../SECURITY.md).

## Published build references

These records identify the published software; they do not certify a particular host installation or Community Apps approval.

| Version | Runtime revision | Publishing run |
| --- | --- | --- |
| Stable 1.0.5 | `d4c799d32c8f876d7c2865cf908531322cb3cd6c` | [39088736705](https://github.com/ChrisK0007/Expense-Pilot/actions/runs/39088736705) |
| Beta 1.0.6-beta.1 | `1600ad5132745634bff8e5c18aab36e8ce068795` | [39089596737](https://github.com/ChrisK0007/Expense-Pilot/actions/runs/39089596737) |

- Stable digest: `sha256:8c29cace0dd6b782072e74410924da6bec6d9f1f68680a09262452ee6a49ab14`.
- Beta digest: `sha256:708398312b6dabec90de4c171ef7dc4549af86f5955a787e936a6235b3c79d84`.
- [v1.0.5 release assets](https://github.com/ChrisK0007/Expense-Pilot/releases/tag/v1.0.5) include matching source archives and `SHA256SUMS`.

## Unraid Community Apps

The stable template is [deploy/unraid/expense-pilot.xml](https://github.com/ChrisK0007/Expense-Pilot/blob/main/deploy/unraid/expense-pilot.xml); the repository profile is [ca_profile.xml](../ca_profile.xml). Keep the icon, support destination and installation instructions accessible publicly.

1. Open [Community Apps submissions](https://ca.unraid.net/submit/new) and sign in with your Unraid account.
2. Submit `https://github.com/ChrisK0007/Expense-Pilot` using branch `main` if asked.
3. Run **Validate**, then **Scan**. Check the detected app uses `ghcr.io/chrisk0007/expense-pilot:latest`, port 8788 and persistent storage at `/data`.
4. Check the icon and README. The canonical template URL is `https://raw.githubusercontent.com/ChrisK0007/Expense-Pilot/main/deploy/unraid/expense-pilot.xml`.
5. Correct reported errors, rerun the checks and submit for review. Track the result in **My submissions** and respond to reviewer requests.
6. After approval, install from Unraid **Apps** into a separate test folder and port, then check the listing's defaults.

GitHub Issues is the configured support destination. If reviewers request a forum support thread, use the real thread URL in the template. Follow the [official builder guide](https://ca.unraid.net/submit/help/builders) and [template field reference](https://ca.unraid.net/submit/help/xml-field-reference). Passing the repository's XML tests does not itself mean Community Apps approval.

## iPhone testing

The iPhone app is independently versioned in its separate repository. It remains in testing. A phone connects to the server URL selected by its user; Docker upgrades do not update the installed iPhone build. Keep the registered bundle identifier and paid signing team when updating an existing test installation. The Docker release does not require CarPlay approval, an App Store launch or a central push service.
