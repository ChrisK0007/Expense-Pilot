# Docker public-release checklist

The maintainer authorized preparation and publication of the Docker release and
Community Apps submission on 18 October 2026. The separate iPhone app remains in
testing. Use [public-launch.md](public-launch.md) for exact manual steps.

## Release candidate

| Item | State |
| --- | --- |
| Candidate | Stable `1.0.5`, based on cleaned main `682eae4` |
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

- [ ] PR pipeline: dependency audit, image/source build, server/relay tests,
  hardened startup, browser workflows and source inventory checks.
- [ ] Merge pipeline publishes `1.0.5` and `latest`; record exact image digest.
- [ ] GitHub release `v1.0.5` contains source assets and SHA256SUMS.
- [ ] Review actual image inventory and source archive against installed
  packages and newly vendored libraries. See [licensing](licensing.md).

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
