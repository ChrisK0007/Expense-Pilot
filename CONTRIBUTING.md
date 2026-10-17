# Contributing

This repository owns the Docker server and web interface. The iPhone companion is separate and remains in testing. Read [architecture](docs/architecture.md) before changing application code.

## Discuss the change

Use an issue to describe a bug or proposed feature, with synthetic examples. Report security problems through [SECURITY.md](SECURITY.md). This repository uses [AGPL-3.0-only](LICENSE). Submit contributions under the same licence and only include material you have permission to contribute. Preserve third-party notices; see [licensing](docs/licensing.md).

## Branches and releases

- Start application changes from `beta` and target `beta` in a pull request.
- `main` is stable. A merge that changes Docker-triggering files can publish `latest`; do not use it for unfinished feature work.
- Documentation can be updated without a container build. Keep stable instructions accurate for the shipped stable version and beta instructions accurate for beta.
- Never edit an already-released migration. Add a new numbered migration, preserve existing data and cover upgrade behaviour.
- Do not bump versions, create release tags, change repository/package visibility or trigger publishing as part of a routine documentation change.

## Local development

Use Python 3.12 and a disposable data directory. Run from the repository root:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r server/requirements.txt
PYTHONPATH=server python -m unittest discover -s tests/server -v
python -m unittest discover -s tests/release -v
```

The [architecture guide](docs/architecture.md) explains local startup and storage. The Docker workflow is the source of truth for production startup, dependency auditing and browser checks. Run checks relevant to your change; a wording-only change needs documentation review, not new application tests.

## Pull requests

Explain the problem, resulting behaviour and checks performed. Identify migrations, API compatibility changes and any operator action. Preserve the existing receipt/trip acknowledgement and retry guarantees. Use accessible labels, consistent menus and clear error messages.

Do not commit credentials, production data, backups, receipt examples containing real personal data or generated test evidence. Use invented fixtures. Keep your own unrelated changes out of the pull request. Maintainers may request a smaller scope or defer a feature beyond the current release.
