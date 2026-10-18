# Docker public-release checklist

The maintainer authorized preparation and publication of the Docker release and
Community Apps submission on 18 October 2026. The separate iPhone app remains in
testing. Use [public-launch.md](public-launch.md) for exact manual steps.

## Release candidate

| Item | State |
| --- | --- |
| Published stable | `1.0.5`, built from cleaned-history commit `d4c799d` |
| Previous published stable | `1.0.4` |
| Existing beta | `1.0.4-beta.2`; separate data and moving tag |
| Licence | AGPL-3.0-only; component-specific notices retained |
| Architecture | Linux AMD64; native ARM has not been published |
| Visibility | Admin must verify repository and package separately |
| iPhone | Separate repository; stays in testing |

## Prepared and locally checked

- [x] Cleaned main/beta branch history verified; obsolete branches removed.
  The maintainer reports removing obsolete images. Retained PR/cache views and
  Actions history were acknowledged separately; do not repeat the rewrite.
- [x] Application source bundle excludes history, data and credentials.
- [x] Dependency source collector retains exact Debian sources/patches/build rules,
  Python distributions, CPython source and detected Pillow FriBiDi source.
  Missing source and checksum failures stop builds.
- [x] Public source, dependency source, notices and inventory download routes.
- [x] Unraid template has public icon, licence, template/support/readme URLs,
  optional setup token and in-app AI configuration. Root CA profile is present.
- [x] Stable release notes and automatic GitHub release/source assets.
- [x] Pull-request checks cover documentation changes; numbered image tags
  cannot be overwritten by the publishing workflow.
- [x] Local release/archive/template tests and syntax checks.

## Candidate verification and publication

- [x] Stable PR pipeline: dependency audit, image/source build, server/relay tests,
  hardened startup, browser workflows and source inventory checks.
- [x] Stable merge pipeline published `1.0.5` and `latest`; digest recorded below.
- [x] GitHub release `v1.0.5` contains all ten source/notice/manifest/checksum assets.
- [x] Build and integration checks compare the actual Debian/Python runtime
  inventory to retained source versions; archive files and hashes are verified.
  Current collection: 111 Debian source packages, 16 Python distributions,
  matching CPython and the Pillow native-source check. Future dependency
  changes still require licence/source review; see [licensing](licensing.md).

## Verified stable publication — 18 October 2026

- [PR #55](https://github.com/ChrisK0007/Expense-Pilot/pull/55) and the
  [publishing run](https://github.com/ChrisK0007/Expense-Pilot/actions/runs/39088736705)
  passed 13 release tests, the dependency vulnerability audit, image/source
  build, 301 server tests, 3 relay tests, hardened startup and browser workflows.
- Runtime revision: `d4c799d32c8f876d7c2865cf908531322cb3cd6c`.
- Tags `1.0.5`, `latest`, `sha-d4c799d` share digest
  `sha256:8c29cace0dd6b782072e74410924da6bec6d9f1f68680a09262452ee6a49ab14`.
- [GitHub release v1.0.5](https://github.com/ChrisK0007/Expense-Pilot/releases/tag/v1.0.5)
  was created successfully. Its dependency-source archive is 631,872,595 bytes,
  SHA-256 `b9369883c60888c3c04b6c578ea37a03d0f18af4add64878401dd2287115e6d9`.
- These are automated and publishing results, not an Unraid host acceptance test
  or Community Apps approval. Visibility and admin settings still require the
  maintainer's account.

## Maintainer host and service checks

- [ ] Fresh Unraid install with optional token omitted and protected setup tested.
- [ ] Disposable upgrade and full backup restore; originals, records and totals.
- [ ] Real stable upgrade after private backup; existing settings and sign-in.
- [ ] Configured AI, SMTP copies/reminders and PocketSmith using deliberate tests.
- [ ] Owner/2FA/recovery and workspace-wide tax-agent permissions.
- [ ] Docker Desktop/Linux host results before claiming tested support; ARM
  emulation remains unverified unless specifically tested.

## Public launch and listing

- [ ] Repository About/topics and main/beta protections with required checks.
- [ ] Repository and GHCR package made public separately by the maintainer.
- [ ] Private vulnerability reporting enabled and reporting route checked.
- [ ] Signed-out source/icon/template/release downloads and anonymous image pull.
- [ ] Community Apps Validate and Scan on the public main branch.
- [ ] Submit for review and record the real submission URL/outcome.
- [ ] After approval, test installation from the actual Apps listing.

A prepared XML template is not a Community Apps approval. Automated tests do not
prove an Unraid host test or real-service delivery. Update this checklist only
with observed results; keep backup data and private diagnostics out of GitHub.
