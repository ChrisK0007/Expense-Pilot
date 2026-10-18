# Docker public-release checklist

Release the Docker container and browser interface first. The separate iPhone
app remains in testing. Preparing this checklist does not make the repository
or package public or authorize a public launch. Stable 1.0.4 promotion has been approved separately.

## Current baseline

| Item | State |
| --- | --- |
| Verified stable | `1.0.4` on `main` / `:latest` |
| Previous verified stable | `1.0.3` |
| Verified beta | `1.0.4-beta.2` on `beta` / `:beta` |
| Previous verified beta | `1.0.4-beta.1` |
| Visibility | Repository and package remain private |
| Project licence | AGPL-3.0-only; third-party notices retained |
| Container architecture | Linux AMD64; ARM requires emulation |
| iPhone | Separate repository; remains in testing |

## Recorded publication evidence

- Stable 1.0.3: commit `4b018e30059e6abf42ecbd2de248b2d7fb4a7307`,
  [publishing run 39076003001](https://github.com/ChrisK0007/Expense-Pilot/actions/runs/39076003001),
  image digest `sha256:2bc318bdec6d52f84510dec82be3af2ceab4d6bb86289238585c731a22778ce6`.
- Beta 1.0.4-beta.1: commit `d76f9a5cb9aff9c87ebfb390a83370acd8d6dbcd`,
  [publishing run 39078172216](https://github.com/ChrisK0007/Expense-Pilot/actions/runs/39078172216),
  image digest `sha256:c9dae90c02aa6623ae6b99a269bef1b09ac896bb823b6bcb717403caec6a00d5`.
- These runs passed the dependency audit, release-channel checks, 298 server
  tests, legacy relay tests, production startup and browser workflows.
- Beta 1.0.4-beta.2: commit `cfeaf8d1e37eb1342fe4f561ed99b2efa5bb6a92`,
  [publishing run 39082371434](https://github.com/ChrisK0007/Expense-Pilot/actions/runs/39082371434),
  image digest `sha256:23cd14d77f3c364650756366274fe1fc50727de19abd537adcf82072c440f235`.
  The audit, 11 release/source tests, 301 server tests, 3 relay tests, production
  startup and all browser workflows passed. Both `1.0.4-beta.2` and `beta` were
  pushed with this digest; `main` / stable 1.0.3 remained unchanged.
- Stable 1.0.4: commit `cdbc884488bbc4048d50abc436414d33b6e5146e`,
  [publishing run 39083800683](https://github.com/ChrisK0007/Expense-Pilot/actions/runs/39083800683),
  image digest `sha256:0dfb95426bbe738b16220f5b026339539bb171fd7ed2789f9cb8a9f4f844e3d0`.
  The audit, 11 release/source tests, 301 server tests, 3 relay tests, production
  startup and all browser workflows passed. Tags `1.0.4`, `latest` and
  `sha-cdbc884` were pushed with this digest. The beta image remains unchanged.
  PR #52 supersedes the now-closed attribution-only PR #47.
- Repeat these gates on every new image. Preserve the candidate's source,
  dependency inventory and exact image digest when recording its result.

## Privacy, source and licensing

- [x] Add AGPL-3.0-only licence, copyright notice and image metadata.
- [x] Use the maintainer's GitHub username and a generic network example in stable 1.0.4.
- [x] Review the current tree, accessible remote history/branches and PR text.
  Findings were old attribution and local-network examples; no real credentials
  or financial records were identified in the inspected material.
- [x] Add source/licence links and build-time application source downloads
  with version/checksum metadata; no dependency on public GitHub access.
- [x] Review direct Python/dataset/font licences and capture installed Python,
  native package and bundled component notices in the image build.
- [ ] Verify the actual candidate's complete dependency inventory and required
  GPL/LGPL corresponding-source distribution. See [licensing](licensing.md).
- [ ] Remove old Git history, obsolete refs/images, CI artifacts/caches and any
  retained PR/cache views. Deletion has **not** been performed. The administration
  connection does not expose these operations; see [the exact procedure](github-release-admin.md).
- [x] Verify the approved 1.0.4 stable publication, including the attribution cleanup.
  Retire old images only after the replacement is confirmed working. Old images
  still contain their original notices; keep them private until deletion.

## Repository and documentation

- [x] Docker-first README, stable/beta boundaries, changelog starting at v1.0,
  installation/upgrade/restore guides, issue forms and PR template.
- [x] Support, security, privacy, licensing and AI-development disclosure.
- [x] Fix in-app help links to the build revision or matching release channel.
- [x] Reconcile this checklist with the actual stable/beta baseline.
- [ ] Apply GitHub About description and topics from [administration guidance](github-release-admin.md).
- [ ] Protect `main` and `beta`, verify required checks and Actions/package
  permissions; apply protections after the authorized history rewrite.
- [ ] At the separately approved public launch, enable and test GitHub private
  vulnerability reporting. It is not available on a private repository.

## Host and live-service verification

Use a disposable installation and synthetic records. Record the image digest,
platform and result. Existing CI checks are not evidence of testing a real host
or third-party service.

- [ ] Fresh setup on Unraid and each advertised Docker Desktop/Linux platform.
- [ ] Upgrade a copy of stable data; verify records, receipts, allocations,
  invoices/payments, permissions and integration settings.
- [ ] Restore a full backup to an empty volume and verify representative records
  and originals. Keep a private matching image/backup for rollback.
- [ ] Token-free/token-protected setup, login/2FA/recovery and tax-agent boundaries.
- [ ] No AI/manual entry, local/remote Ollama and advertised cloud providers.
- [ ] Real SMTP delivery/copies/reminders and live PocketSmith integration.
- [ ] Upload limits, receipt deletion, invoice totals/refunds, export and deletion.
- [ ] Review tax/allowance estimate wording and scope. Timezone selection does
  not change AUD, Australian financial years or tax rules.

## Public launch — separately approved

- [ ] Approve a stable candidate, run its full gates, publish and verify its digest.
- [ ] Make the approved repository/install files and GHCR package public;
  these are separate visibility controls.
- [ ] Test anonymous image pull and installation links without cached credentials.
- [ ] Verify source downloads, notices, source obligations and private reporting
  from the public installation, then announce the release.

CarPlay approval, public iPhone distribution and a central push service are not
requirements for this Docker launch. Legacy optional relay tooling is not part
of the standard installation or current iPhone notification path.
