# Support

Expense Pilot is a self-hosted Docker application. The iPhone companion is still in testing and is not a dependency of the Docker release.

## Before reporting a problem

1. Record the version in Settings and the container image tag. State whether you use stable or beta.
2. Read the [user guide](docs/guide.md) for that branch and the [stable](docs/CHANGELOG.md) or [beta](docs/beta-changelog.md) changelog.
3. Describe the smallest set of steps that reproduces the problem, the expected result and what happened instead.
4. For an upgrade problem, include the previous version and whether the original `/data` mount was retained.

Use the repository's **Issues → New issue** forms for a bug, installation question or feature request. Search existing issues first. Reports should use invented examples whenever possible. Support is provided as maintainer time permits; no response-time commitment is offered.

## Safe diagnostics

Replace `expense-pilot` below if your container has a different name:

```sh
docker inspect --format '{{.Config.Image}}' expense-pilot
docker logs --tail 100 expense-pilot
```

Read and redact logs before attaching them. Include the Docker host (Unraid, Linux or Docker Desktop), browser and relevant error text. For bank-feed or AI problems, name the service and model, but never provide its API key.

Do not post full `docker inspect` output, `.env`, `session.key`, passwords, cookies, setup tokens, authenticator/recovery codes, backups, bank statements, receipt originals, real client records or unredacted financial screenshots. Logs and URLs can also contain personal information. A maintainer should not need your private workspace backup to reproduce an ordinary bug.

## Security problems

Use the [security policy](SECURITY.md). Do not describe an exploitable vulnerability in a public issue.

## Recovering access or data

- [Account recovery and permissions](docs/guide.md#access)
- [Host backups and restoration](docs/architecture.md#backups)
- [Full backup and restore guide](docs/public-release.md#backup-and-restore)

Keep the original data volume when testing a restore. The maintainer does not hold a copy of your self-hosted records, passwords or encryption key.
