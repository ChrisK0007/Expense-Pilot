# Docker public-release checklist

The Docker container and browser interface will be released first. The iPhone app remains in testing and is not a gate for the Docker launch. This checklist prepares a release; it does not change image tags, versions or repository visibility.

## Current baseline

| Item | State |
| --- | --- |
| Existing stable | `1.0.3` on `main` / `:latest` |
| Development candidate | `1.0.3-beta.1` on `beta` / `:beta` |
| Public availability | Pending owner decision and access verification |
| Project licence | AGPL-3.0-only; third-party notices retained |
| Container architectures | Linux AMD64; ARM uses emulation |
| iPhone | Separate repository; remains in testing |

## Verified v1.0.2 publication

- Published on 17 October 2026 from commit `a48c284d7b3c55bf15412191c818bc1b1f97c9d8` via [release PR #38](https://github.com/ChrisK0007/Expense-Pilot/pull/38).
- [Publishing workflow 38993632918](https://github.com/ChrisK0007/Expense-Pilot/actions/runs/38993632918) passed dependency audit, 8 release-channel checks, 295 server tests, 3 legacy relay tests, production startup and browser workflows.
- Tags `1.0.2`, `latest` and `sha-a48c284` were pushed with digest `sha256:a7405e917ef05ea432fbb57ad42ff4cdb980e9298d338d9841e86688d7c8daba`.
- Repository-only AGPL licensing and AI-development disclosure followed this build; they have not rebuilt the image. Public access, image licence packaging and host/live-service checks remain separate tasks below.

## Repository preparation

- [x] Provide a Docker-first README with explicit stable/beta boundaries.
- [x] Add installation, bug and feature issue forms, a pull-request template, support guidance and a security policy.
- [x] Separate current instructions from historical development notes.
- [x] Document the licence decision and retain bundled dataset attribution.
- [x] Select and add the project licence: AGPL-3.0-only, with application copyright notice.
- [ ] Complete the runtime dependency licence review.
- [x] Include LICENSE/COPYRIGHT and AGPL image metadata in the v1.0.3 Docker build.
- [ ] Provide accessible version-matched Corresponding Source and a source/licence link in the web interface, and complete the dependency notice review before public distribution.
- [ ] Review the complete remote Git history, tags, old branches, releases, attachments and CI artifacts for secrets or personal data before changing visibility. A current-tree scan alone is insufficient.
- [ ] Enable a private vulnerability-reporting channel and verify it works before the public announcement.
- [ ] Set the GitHub About description and topics. Suggested description: **Self-hosted expense tracking and invoicing for Australian sole traders and employment expenses.** Suggested topics: `self-hosted`, `docker`, `unraid`, `expense-tracker`, `invoicing`, `australia`.
- [ ] Confirm branch protections, Actions permissions and package publishing access. Retire only topic branches whose work is verified as merged; keep `main`, `beta` and any active work.

## Candidate verification

Use a disposable installation and synthetic records. Record image tag/digest, platform, result and any remaining limitations alongside the release notes.

- [ ] Fresh setup on Unraid and on each advertised Docker Desktop/Linux platform. Confirm AMD64 emulation explicitly if advertising ARM/Apple silicon support.
- [ ] Upgrade a copy of stable 1.0.1 data to the candidate; preserve receipts, allocations, invoices, payments, permissions and integration settings.
- [ ] Restore a full backup into a new empty volume and verify representative records and originals. Keep the original data and matching old image as rollback.
- [ ] Check token-free and token-protected first setup, login/2FA, password recovery and tax-agent read-only/read-write boundaries.
- [ ] Check No AI, existing Ollama and any cloud provider included in the release with deliberate test data. Confirm consent, key replacement and errors. Manual receipt entry must remain usable without AI.
- [ ] Check real SMTP delivery/copies/reminders and a live PocketSmith connection with operator-owned test accounts. Automated mocks do not establish live-service delivery.
- [ ] Verify upload limits, receipt review/deletion, invoice totals, refunds, export and account/workspace deletion.
- [ ] Review Australian tax/allowance estimates and explain their scope. A different timezone does not change currency, financial-year or tax rules.
- [x] Run the Docker dependency audit, integration, production startup and browser gates on the exact v1.0.2 release commit; evidence is recorded above. Repeat for any new image candidate.

## Stable publication and public launch

- [x] Select stable v1.0.2 and prepare its changelog and upgrade notes. Do not reuse a published numbered tag for changed code.
- [x] Update the Unraid template and portable Compose defaults to the approved stable image; align setup fields with that release. Stable 1.0.2 now includes optional setup tokens and in-app AI settings.
- [ ] Make the approved repository/install files and GHCR package publicly accessible. Package visibility and repository visibility are separate settings.
- [ ] From a logged-out environment, verify anonymous image pull and installation-file access. Do not publish using a tester's cached registry login as the only evidence.
- [x] Promote v1.0.2 through a release PR to `main` and verify the published digest, version and `latest` tag. Follow [release channels](releases.md).
- [ ] Publish the public-launch announcement after access and platform verification. Release notes, upgrade/restore instructions and support links are prepared; remove remaining preparation notices only when those checks are complete.
- [x] Reconcile stable release history and shared documentation into `beta` while retaining its prerelease installation defaults.

Public iPhone distribution, CarPlay approval and a central push service are not requirements for this Docker release. The existing source includes legacy optional relay tooling; it is not part of the standard installation or current iPhone notification path.
