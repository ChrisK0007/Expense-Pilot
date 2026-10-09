# Release history

## 0.8.2

- Organise the backend under `server/`, test suites under `tests/server/` and `tests/browser/`, deployment templates under `deploy/`, and documentation under `docs/`.
- Extract receipt, finance and billing-document routes into focused modules.
- Introduce numbered transactional database migrations and an applied-migration ledger.
- Read the server/API and Docker release version from `server/VERSION`.
- Exclude iOS, documentation and test files from Docker build context; skip Docker builds for iOS-only and documentation-only changes.
- Back up the actual configured container data mount and preserve whether the container was running.
- Preserve container paths, database name, host appdata mounts and root deployment commands. Keep iOS in the same repository.

## 0.8.1

- Retire employee account access while retaining historical financial records.
- Add server-side session revocation and strengthen login rate limits.
- Bound PDF inspection resources and restrict receipt image types and size.
- Update dependencies and verify dependency, backend and browser checks.

## iOS 0.1.0

- Initial SwiftUI app with a server-connected web workspace and native receipt scanning.
- Support installation through Xcode using a free Personal Team.

See [earlier release notes](legacy-release-notes.md) for the original 0.3–0.6 feature history.
