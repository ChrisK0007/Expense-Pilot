# Expense Pilot

A self-hosted expense workspace with a clean, Rounded-inspired interface. Separate employment, business and personal spending, attach receipts, track overnight meals and share selected records with your tax agent.

**Initial version: 0.1.0.** No live bank feeds: bank exports are imported as CSV using a column preview and mapping. AI receipt extraction requires a separately configured Ollama service. All financial records stay in your Unraid appdata folder; GitHub contains application code only.

## Features

- Separate Employment, Business and Personal expenses, percentage allocation and reimbursements.
- CommBank, Macquarie and American Express account labels; mapped CSV imports and duplicate detection.
- Receipt photos and PDFs; optional Ollama extraction into a draft you review before saving.
- Overnight trips, linked breakfast/lunch/dinner/incidentals and a separate allowance record.
- Owner, employee and read-only tax-agent logins with server-side access restrictions.
- Explicit sharing of expenses, receipts and linked trip details with tax-agent accounts.
- Financial-year CSV exports, activity history, password changes and account disabling.
- Persistent SQLite database, Docker health check and backup helper.

The app records actual expenses and allocations; it does not determine tax deductibility, automatically apply ATO meal rates, calculate BAS/GST, lodge returns or reconcile bank balances. Imported purchases and transfers start Personal / To review until you categorise them. Credits in bank CSVs are skipped; record expense refunds manually as negative amounts.

## GitHub and Docker updates

The workflow in `.github/workflows/docker.yml` builds the image and runs 15 integration tests before publishing. A passing push to `main` publishes:

```text
ghcr.io/chrisk0007/expense-pilot:latest
```

A `v0.1.0` Git tag also publishes the numbered `0.1.0` tag. Every build has a commit-derived image tag for rollback. Pull requests run checks without publishing. The workflow must succeed before the image exists. See the repository's **Actions** tab for its status.

The private repository does not make the application publicly accessible. GitHub Container Registry packages are private by default. To pull a private image, authenticate on Unraid with a GitHub personal access token (classic) that has `read:packages` access to this package:

```bash
docker login ghcr.io -u ChrisK0007
```

Paste the token at the password prompt. Never put it in this repository or a chat message. Check registry login again after an Unraid reboot if private-image pulls fail. The container image can optionally be made public separately for unauthenticated pulls, but that exposes the bundled application code and is not done by this project automatically.

## First install on Unraid

Download the repository ZIP, extract its contents to `/mnt/user/appdata/expense-pilot`, then open the Unraid terminal:

```bash
cd /mnt/user/appdata/expense-pilot
bash prepare.sh
```

This creates `.env` with a random first-run setup token and a `data` folder owned by UID 99/GID 100. Existing configuration is preserved.

### Unraid Docker page

A template is supplied in `unraid/expense-pilot.xml`. Copy it to `/boot/config/plugins/dockerMan/templates-user/my-expense-pilot.xml`, then go to **Docker → Add Container** and select the Expense Pilot template. Set:

| Setting | Value |
| --- | --- |
| Repository | `ghcr.io/chrisk0007/expense-pilot:latest` |
| Network | Bridge |
| Web port | Host 8788 → container 8788 |
| Appdata | `/mnt/user/appdata/expense-pilot/data` → `/data` |
| Setup token | `SETUP_TOKEN` value generated in `.env` |
| Ollama URL | Blank for manual entry, or your reachable Ollama address |
| Ollama model | Name of an installed model; photos/scans require vision support |
| Secure cookie | `false` for LAN HTTP setup; `true` when using HTTPS |

The template keeps the database and receipts outside the image. Open `http://YOUR-UNRAID-IP:8788`, enter the setup token and create your owner login. No default password is provided. Enable **Autostart** for the container in Unraid.

When a tested image is published, use the normal Unraid Docker update controls to pull it. Keep the `/data` mapping unchanged. For private packages the server must remain authenticated to GHCR. Back up before updating.

### Docker Compose alternative

Do not run this at the same time as the Unraid template installation. Add this line to your generated `.env`:

```text
IMAGE=ghcr.io/chrisk0007/expense-pilot:latest
```

Then:

```bash
docker compose -f compose.registry.yaml pull
docker compose -f compose.registry.yaml up -d
```

To update, run the same two commands. To roll back, change `IMAGE` to a previously published version or commit tag and run them again. Preserve the database and keep data compatibility in mind when rolling back.

### Build locally instead

If no registry image is available yet:

```bash
docker compose up -d --build
```

`compose.yaml` builds the source; `compose.registry.yaml` pulls the published image. Use only one installation method.

## AI receipt reading

Set `OLLAMA_URL` to an address reachable from inside the app container, such as your Unraid host's LAN IP and Ollama port. `localhost` means the expense container itself. Set `OLLAMA_MODEL` to an installed model. Text PDFs send extracted text; scanned PDFs are rendered into images, as are receipt photos. PDFs are limited to eight pages and uploads to 12 MB.

Nothing is sent to Ollama until you select **Read with AI**. Check all suggested values before saving. Foreign amounts need manual AUD conversion. This version supports Ollama, not OpenAI API connections. If using the Unraid template, edit its environment-variable fields and Apply; if using Compose, edit `.env` and recreate the container.

## Access

| Role | Access |
| --- | --- |
| Owner | All records, imports, sharing, people and reports |
| Employee | Only their own business expenses, receipts and trips |
| Tax agent | Read/export explicitly shared records and linked evidence/trip details |

All active tax-agent accounts see the same shared set. Disabling an account revokes active sessions. Personal expenses cannot be shared. Account creation does not send an invitation email; provide credentials through your normal secure channel. Employees can change passwords in Settings.

For terminal-only recovery:

```bash
docker exec -it expense-pilot python /app/reset_password.py
```

## Backup

```bash
cd /mnt/user/appdata/expense-pilot
bash backup.sh /mnt/user/backups/expense-pilot
```

The script pauses the app by stopping its container, backs up the database, receipts, signing key and `.env`, then restarts it. Data is not encrypted at rest; keep the appdata share and backups private. When using the Unraid template, its environment fields are stored in the Unraid template, so back up the boot-device configuration too. A generated `.env` does not automatically update those GUI fields.

## Verification

The first GitHub Actions build passed on 8 October 2026: Docker image build, all 15 integration tests and publication to GitHub Container Registry. [View the successful build](https://github.com/ChrisK0007/Expense-Pilot/actions/runs/37716069074). Application commit: `406df145794a993b1d27b6ddc3af173af566929f`.

Local syntax and SQLite-schema checks also passed. Actual bank-export samples, a live Ollama service and browser visual QA still require deployment checks. The app has not been installed on your Unraid server by this workflow.

The 15 tests cover authentication, CSRF, role isolation, sharing, session revocation, date/trip validation, receipt access, CSV duplicate/credit handling, amount rounding, formula escaping and export boundaries.

For manual test execution after a local image build:

```bash
docker build -t expense-pilot:test .
docker run --rm --entrypoint python -v "$PWD/tests:/app/tests:ro" expense-pilot:test -m unittest discover -s tests -v
```

Download and open `README.html` for the extended user guide, import instructions and restore steps. The app is an original implementation, not affiliated with Rounded.
