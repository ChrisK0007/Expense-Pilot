# Public launch and Unraid Community Apps

This guide is for the maintainer releasing Docker v1.0.5. The iPhone app remains in TestFlight. Do the host checks before announcing the release or submitting it for Community Apps review.

## 1. Confirm the published build

Open [Actions](https://github.com/ChrisK0007/Expense-Pilot/actions) and find the **Test and publish Docker image** run for the v1.0.5 merge into main. Both **test-and-publish** and **github-release** must be green. The run summary records the image digest. The [v1.0.5 release](https://github.com/ChrisK0007/Expense-Pilot/releases/tag/v1.0.5) must have application/dependency sources, notices, inventories and SHA256SUMS attached.

If only the GitHub-release job fails, rerun that failed job; do not rerun the successful publishing job. Numbered image tags cannot be replaced. A public GitHub release does not itself make the container package public.

## 2. Test a fresh Unraid installation

These commands create a separate test container on port 8791. They do not change the existing expense-pilot installation. Check that 8791 is free first. While the package is private, use your existing GHCR login.

```bash
docker pull ghcr.io/chrisk0007/expense-pilot:1.0.5
mkdir -p /mnt/user/appdata/expense-pilot-release-test/data
chown 99:100 /mnt/user/appdata/expense-pilot-release-test/data
chmod 770 /mnt/user/appdata/expense-pilot-release-test/data
docker run -d --name expense-pilot-release-test \
  --restart unless-stopped \
  --user 99:100 --read-only \
  --tmpfs /tmp:rw,size=256m,mode=1777 \
  --cap-drop ALL --security-opt no-new-privileges:true --memory 1g \
  -p 8791:8788 \
  -v /mnt/user/appdata/expense-pilot-release-test/data:/data \
  -e SETUP_TOKEN= -e COOKIE_SECURE=false \
  ghcr.io/chrisk0007/expense-pilot:1.0.5
```

Open `http://YOUR-SERVER-IP:8791`. Create a new owner account and complete setup. No setup token or backup-download acknowledgement should be required. Use synthetic records, for example Example Client and an expense for $12.34. Keep AI, SMTP, automatic invoice reminders and PocketSmith disconnected for this first test.

Verify:

1. The version is 1.0.5, page URLs change with navigation and refresh returns to the same page.
2. Upload a synthetic PDF/image, save its receipt draft as an expense, and confirm it leaves the draft inbox. Open the retained original; edit and delete the expense.
3. Create a client, quote, invoice and payment. Open the PDFs. Check allocations and menu labels.
4. Create a budget and manual drive/overnight record, then export sample records.
5. Open **Source code & licences** from login or Settings. Download application source, dependency source, notices and manifests. Dependency source is a large download; it should not require signing into GitHub.
6. Enable 2FA using a test account, save its recovery codes and test sign-out/sign-in/recovery. Confirm tax-agent access matches the documented workspace-wide scope.
7. Restart using `docker restart expense-pilot-release-test`; confirm records and the retained receipt survive.

Check health and record the installed digest:

```bash
docker inspect --format '{{.State.Health.Status}}' expense-pilot-release-test
docker image inspect --format '{{json .RepoDigests}}' ghcr.io/chrisk0007/expense-pilot:1.0.5
docker logs --tail 80 expense-pilot-release-test
```

The expected health result is `healthy`. Before sharing logs, remove account details, tokens and financial records.

## 3. Test full backup and restore

From the test installation, use **Settings → Data & privacy → Download full backup / restore guide**. Save the ZIP privately on your computer, then copy it to the Unraid share as `/mnt/user/appdata/expense-pilot-release-test/restore-test.zip`. The ZIP includes the session key and is not encrypted.

Create a separate, empty destination. If it already contains files from an earlier attempt, choose a new folder instead of deleting anything:

```bash
mkdir -p /mnt/user/appdata/expense-pilot-restore-test/data
chown 99:100 /mnt/user/appdata/expense-pilot-restore-test/data
chmod 770 /mnt/user/appdata/expense-pilot-restore-test/data
chown 99:100 /mnt/user/appdata/expense-pilot-release-test/restore-test.zip
chmod 600 /mnt/user/appdata/expense-pilot-release-test/restore-test.zip
docker run --rm --user 99:100 --network none \
  -v /mnt/user/appdata/expense-pilot-restore-test/data:/data \
  -v /mnt/user/appdata/expense-pilot-release-test/restore-test.zip:/backup.zip:ro \
  --entrypoint python ghcr.io/chrisk0007/expense-pilot:1.0.5 \
  restore_backup.py /backup.zip
```

After the command reports a verified restore, start a second test instance:

```bash
docker run -d --name expense-pilot-restore-test \
  --user 99:100 --read-only --tmpfs /tmp:rw,size=256m,mode=1777 \
  --cap-drop ALL --security-opt no-new-privileges:true --memory 1g \
  -p 8792:8788 \
  -v /mnt/user/appdata/expense-pilot-restore-test/data:/data \
  -e COOKIE_SECURE=false \
  ghcr.io/chrisk0007/expense-pilot:1.0.5
```

Open `http://YOUR-SERVER-IP:8792`, sign in again and compare the test records, receipt originals, totals and settings. Restored sessions are intentionally revoked. Use synthetic data without integrations for this procedure: a restored live database may otherwise send due reminders or connect to bank feeds.

## 4. Check an upgrade and update your stable installation

For a disposable upgrade rehearsal, start the previous stable version with its own folder and port:

```bash
mkdir -p /mnt/user/appdata/expense-pilot-upgrade-test/data
chown 99:100 /mnt/user/appdata/expense-pilot-upgrade-test/data
chmod 770 /mnt/user/appdata/expense-pilot-upgrade-test/data
docker run -d --name expense-pilot-upgrade-test \
  --user 99:100 --read-only --tmpfs /tmp:rw,size=256m,mode=1777 \
  --cap-drop ALL --security-opt no-new-privileges:true --memory 1g \
  -p 8793:8788 \
  -v /mnt/user/appdata/expense-pilot-upgrade-test/data:/data \
  -e SETUP_TOKEN= -e COOKIE_SECURE=false \
  ghcr.io/chrisk0007/expense-pilot:1.0.4
```

Open `http://YOUR-SERVER-IP:8793`, create an owner and synthetic receipt/invoice records, and download a full backup. Leave integrations disconnected. Then replace only this disposable test container, preserving its data:

```bash
docker stop expense-pilot-upgrade-test
docker rm expense-pilot-upgrade-test
docker run -d --name expense-pilot-upgrade-test \
  --user 99:100 --read-only --tmpfs /tmp:rw,size=256m,mode=1777 \
  --cap-drop ALL --security-opt no-new-privileges:true --memory 1g \
  -p 8793:8788 \
  -v /mnt/user/appdata/expense-pilot-upgrade-test/data:/data \
  -e COOKIE_SECURE=false \
  ghcr.io/chrisk0007/expense-pilot:1.0.5
```

Refresh the same address. Confirm v1.0.5, the original receipt and your sample totals. No database migration is added by v1.0.5. This exercises an actual in-place upgrade of a disposable installation; your original live data is untouched.

For your real stable container:

1. Download a full backup and keep the old image and its matching backup privately until recovery is confirmed. Note the current `/data` host path, port, environment values and image tag.
2. In Unraid **Docker → expense-pilot → Edit**, confirm the repository is `ghcr.io/chrisk0007/expense-pilot:latest` (or set `:1.0.5` to pin it). Preserve the existing `/data` path and other settings.
3. Use **Check for Updates → Update**. Refresh the browser and confirm 1.0.5 in Settings.
4. Check existing receipts, invoices, allocations, budgets, sign-in and integrations. Test SMTP copies using only an address you control; avoid sending real clients test invoices. Test the configured AI and PocketSmith connection without changing destinations.
5. If recovery is needed, stop the container and restore the matching old backup into a different folder with the old image. Do not overwrite the only copy of your current data.

Host verification on Linux/Docker Desktop must also be recorded before claiming those hosts have been tested. The current image is AMD64; ARM emulation is not a native ARM release.

## 5. Retire the old public-download candidates, then change visibility

After the new stable and beta images are verified, retain only the package versions carrying `1.0.5` / `latest` and `1.0.6-beta.1` / `beta` before changing package visibility. These replacements were built from the cleaned history and carry matching dependency sources. The older `1.0.4` and `1.0.4-beta.2` images predate that packaging.

If you need a private rollback image, save it locally before deleting its registry version. For example, while the old image is still available:

```bash
mkdir -p /mnt/user/backups/expense-pilot-release
chmod 700 /mnt/user/backups/expense-pilot-release
docker pull ghcr.io/chrisk0007/expense-pilot:1.0.4
docker image save ghcr.io/chrisk0007/expense-pilot:1.0.4 \
  -o /mnt/user/backups/expense-pilot-release/stable-1.0.4-private.tar
chmod 600 /mnt/user/backups/expense-pilot-release/stable-1.0.4-private.tar
```

Pair it with your matching private data backup. Keep this folder off public shares. A saved Docker image contains software, not a backup of `/data`.

On the GitHub package page, open **View and manage all versions**. Keep the two versions identified by the new stable/beta tags and their verified digests; each may have several tags including a `sha-` tag. Delete obsolete versions from their version menu/settings. Do not delete the entire package or a version carrying `latest` or `beta`. A version deletion removes all tags attached to that digest. Do not run a broad Docker prune or remove appdata.

Then change visibility:


GitHub administration is not exposed by the connected repository tools. Perform these changes yourself after checking the release:

1. Open [repository settings](https://github.com/ChrisK0007/Expense-Pilot/settings). Under **General → Danger Zone → Change repository visibility**, select **Public** and complete GitHub's confirmation. Retained Actions logs/history become visible too.
2. Open [the container package](https://github.com/ChrisK0007/Expense-Pilot/pkgs/container/expense-pilot), choose **Package settings**, then **Danger Zone → Change visibility → Public**. Repository visibility and package visibility are separate. All retained tags in this package, including beta tags, share its visibility. GitHub does not allow a public package to be made private again.
3. Open the repository in a signed-out/private browser window. Confirm README, licence, template, icon and v1.0.5 release assets load.
4. Test an anonymous image pull in the Unraid terminal without changing your existing Docker credentials:

```bash
ep_public_config=$(mktemp -d)
docker --config "$ep_public_config" pull ghcr.io/chrisk0007/expense-pilot:1.0.5
docker --config "$ep_public_config" pull ghcr.io/chrisk0007/expense-pilot:latest
rm -r "$ep_public_config"
```

Both pulls must succeed. Check their digest matches the publishing run. A browser login succeeding does not prove anonymous registry access.

## 6. Set repository information and protections

On the repository **Code** page, click the gear beside **About**. Use:

- Description: `Self-hosted expense tracking, receipts and invoicing for Australian sole traders and employees. Docker and Unraid; optional AI and PocketSmith bank feeds.`
- Website: `https://github.com/ChrisK0007/Expense-Pilot#readme`
- Topics: `self-hosted`, `expense-tracker`, `invoicing`, `receipts`, `docker`, `unraid`, `australia`, `pocketsmith`, `ollama`.

To keep the branch list tidy, open merged [PR #55](https://github.com/ChrisK0007/Expense-Pilot/pull/55) and [PR #56](https://github.com/ChrisK0007/Expense-Pilot/pull/56), then use **Delete branch** for their completed release branches. Keep `main` and `beta`. Under **Settings → General → Pull Requests**, enable **Automatically delete head branches** for future merged work.

Open **Settings → Branches → Add classic branch protection rule** (or the equivalent branch ruleset). Create a rule for `main`, then another for `beta`:

1. Require a pull request before merging. For a sole maintainer, leave **Require approvals** unchecked; you cannot approve your own release PR.
2. Require status checks to pass; select **test-and-publish** from the successful run. Do not require **github-release**, which runs after stable publication.
3. Require branches to be up to date and conversations resolved.
4. Leave force pushes and deletions disabled. Apply protection to administrators if you want it enforced on your own account too.

Pull-request checks run for every PR, including documentation changes, so the required check can complete. Push-triggered publishing retains its application/build path filter.

After the repository is public, open **Settings → Security and quality → Advanced Security → Private vulnerability reporting → Enable**. Confirm **Security → Advisories → Report a vulnerability** is available. Use private reporting for vulnerabilities, not public Issues.

## 7. Submit to Unraid Community Apps

The repository already contains the required root `LICENSE`, `README.md`, `ca_profile.xml`, the real icon and `deploy/unraid/expense-pilot.xml`. You do not need another repository.

1. Open [Community Apps submissions](https://ca.unraid.net/submit/new) and sign in with your own Unraid account.
2. Start a new repository submission and enter `https://github.com/ChrisK0007/Expense-Pilot` using branch `main` if asked.
3. Run **Validate**, then **Scan**. Review the detected app: `expense-pilot`, image `ghcr.io/chrisk0007/expense-pilot:latest`, category Productivity, port 8788 and persistent `/data` mapping.
4. Confirm the icon and README load. The canonical template URL is `https://raw.githubusercontent.com/ChrisK0007/Expense-Pilot/main/deploy/unraid/expense-pilot.xml`.
5. If the scan reports an error, correct the exact issue and rerun Validate and Scan. XML syntax checks in CI are not the Community Apps validator or an approval.
6. Submit for review once checks pass. Explain that the app is self-hosted, stores records locally, has optional user-configured AI/bank/email services and that the iPhone app remains in testing. GitHub Issues is the configured support destination.
7. Follow the submission in **My submissions** and respond to reviewer requests. If a dedicated Unraid forum support thread is requested, create one and update the template's Support URL to the real thread. Do not invent a forum URL.
8. After approval, find Expense Pilot in Unraid **Apps** and perform one installation using the actual listing into a disposable folder/port. Verify the listing's defaults before announcing it.

Official references: [builder guide](https://ca.unraid.net/submit/help/builders), [repository profile](https://ca.unraid.net/submit/help/repository-info-xml), [template fields](https://ca.unraid.net/submit/help/xml-field-reference), [GitHub repository visibility](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility), [package visibility](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility).

## Stop the disposable test containers

After checking their results, stop and remove only the containers created by this guide:

```bash
docker stop expense-pilot-release-test expense-pilot-restore-test expense-pilot-upgrade-test
docker rm expense-pilot-release-test expense-pilot-restore-test expense-pilot-upgrade-test
```

Omit names you did not create. These commands keep the test data folders. Keep backups private and retain the test folders until you have finished comparing results. Your real stable and beta containers are not named in these commands.

## Record completion

Record the image digest, Unraid version, fresh-install/upgrade/restore results, anonymous pull result and Community Apps submission URL. Update the release checklist with observed results. Do not mark a host test or external review complete just because the files have been prepared.
