> Historical cleanup procedure. The maintainer completed the branch/history reset on 18 October 2026 and reported removal of obsolete images. Do not repeat the rewrite. Current launch, visibility, protection and Community Apps steps are in [public-launch.md](public-launch.md). Retained PR/cache views and Actions history are separate from reachable branch history.

# GitHub administration before public release

Stable 1.0.4 is published and verified. Update your running containers and
confirm the displayed version before removing previous images.
Repository and package visibility remain private. These instructions do not
perform any deletion automatically.

## Keep these versions

- Stable: the package version carrying **both `latest` and `1.0.4`**.
- Beta: the package version carrying **both `beta` and `1.0.4-beta.2`**.
- Keep all `sha-...` tags attached to those same retained versions. Deleting a
  package version deletes the image behind every tag attached to it.
- If a retained version is a multi-platform index, keep all referenced platform
  and attestation digests too, including untagged versions. The current pipeline
  publishes a single Linux AMD64 image, but inspect before assuming this later.

Verified retained digests on 18 October 2026:

| Channel | Tags attached to the retained version | Digest |
| --- | --- | --- |
| Stable | `latest`, `1.0.4`, `sha-cdbc884` | `sha256:0dfb95426bbe738b16220f5b026339539bb171fd7ed2789f9cb8a9f4f844e3d0` |
| Beta | `beta`, `1.0.4-beta.2`, `sha-cfeaf8d` | `sha256:23cd14d77f3c364650756366274fe1fc50727de19abd537adcf82072c440f235` |

See the [release checklist](release-checklist.md) for publishing evidence.
Resolve the tags again if another release has occurred before cleanup. Stable
1.0.4 includes the GitHub-username attribution cleanup; older stable images
still carry their original notices. Removing old images does not update running
containers. Update every stable and beta instance, including any separately hosted
instance, before removing the old version it would need for a reinstall.

## Delete old Docker versions on GitHub

1. Open your GitHub profile → **Packages** → **expense-pilot**:
   https://github.com/users/ChrisK0007/packages/container/package/expense-pilot
2. Select **View and manage all versions**.
3. Identify the two retained versions above by their tags and compare their
   digests with the release checklist. Keep the complete version rows.
4. For each older version, select **⋯ → Delete version**, enter `expense-pilot`
   when asked, and confirm. Do not choose **Delete this package**.
5. Check the untagged view separately; do not blindly delete untagged manifests
   referenced by a retained image. Recheck that the retained tags still pull.

This removes registry copies. It does not delete receipts, container settings
or `/data`. For old local Unraid images, use Docker's image list to identify an
obsolete Expense Pilot image and `docker image rm IMAGE_ID` only after no
container uses it. Do not use `docker system prune --volumes` for this task.

## Remove old Git history

Perform this in a fresh, private administrative clone with no other writers.
Keep a private offline `git bundle create ../expense-pilot-before-cleanup.bundle
--all` until the new branches and active work are verified. Never upload this
bundle or publish an archival branch: either would retain the old history.
Delete the offline bundle after verification when it is no longer needed;
otherwise the removed history still exists in that private backup.

1. Fetch all heads and tags, record their exact SHAs, list open PRs, and inspect
   unmerged topic branches. Save active branch **trees**, not their ancestors.
2. Create a parentless commit with the current `main` tree using `git commit-tree`.
   Use the GitHub username and noreply email as author/committer, and include
   `[skip ci]` in the snapshot message so this operation cannot republish stable.
3. Create a commit with the current `beta` tree whose only parent is the new
   `main` root. This keeps the channels mergeable without any old ancestors.
4. Recreate each active PR head from its saved tree with the new base as its
   only parent. Review its resulting diff before updating the remote PR branch.
5. Push the reviewed root/channel/active-branch replacements together using
   explicit `--force-with-lease=refs/heads/BRANCH:RECORDED_SHA` leases and
   `--atomic`. Delete only reviewed obsolete branch/tag refs, with expected-SHA
   leases, in that same operation. Stop if any ref changed or a protection rule
   blocks the push; do not silently remove protection.
6. Reclone and verify branch trees, active PR diffs, root ancestry, and that
   `latest` and `beta` image digests did not change. Collaborators must reclone;
   merging an old clone would reintroduce history.

### Copyable history reset after old branch removal

Use **Git Bash on Windows**, or Bash on macOS/Linux, with GitHub authentication
already working. This resets history; it is not needed just to delete Docker
images. First merge or close all open pull requests and stop concurrent pushes.
Delete obsolete branches in GitHub's **Branches** page, keeping only `main` and
`beta`. Delete obsolete Git tags if any exist; registry image tags are separate.
Do not delete an active branch until its work is retained.

In a new directory, clone and check the remaining refs:

```bash
git clone https://github.com/ChrisK0007/Expense-Pilot.git Expense-Pilot-cleanup
cd Expense-Pilot-cleanup
git branch -r
git tag
```

Continue only if the remote branches are `origin/main`, `origin/beta` and the
`origin/HEAD` pointer, and the tag list is empty. No other developer or automation
should push until the reset is finished. The following block makes snapshots
with exactly the same files and checks the remote refs before preparing them:

```bash
set -euo pipefail
git config user.name ChrisK0007
git config user.email 160002899+ChrisK0007@users.noreply.github.com
git fetch origin --prune

ep_refs=$(git ls-remote --heads --tags origin)
while read -r ep_sha ep_ref; do
  case "$ep_ref" in
    refs/heads/main|refs/heads/beta) ;;
    *) echo "Stop: another branch or tag still exists: $ep_ref"; exit 1 ;;
  esac
done <<< "$ep_refs"

ep_main_before=$(git rev-parse origin/main)
ep_beta_before=$(git rev-parse origin/beta)
# Stop if the release state changed since these instructions were prepared.
test "$(git show "$ep_main_before:server/VERSION")" = "1.0.4"
test "$(git show "$ep_beta_before:server/VERSION")" = "1.0.4-beta.2"
git bundle create ../expense-pilot-before-cleanup.bundle --all

ep_main_tree=$(git rev-parse "$ep_main_before^{tree}")
ep_beta_tree=$(git rev-parse "$ep_beta_before^{tree}")
ep_main_new=$(printf '%s\n' 'Stable source snapshot [skip ci]' | git commit-tree "$ep_main_tree")
ep_beta_new=$(printf '%s\n' 'Beta source snapshot [skip ci]' | git commit-tree "$ep_beta_tree" -p "$ep_main_new")
git diff --exit-code "$ep_main_before" "$ep_main_new"
git diff --exit-code "$ep_beta_before" "$ep_beta_new"

git push --dry-run --atomic \
  "--force-with-lease=refs/heads/main:$ep_main_before" \
  "--force-with-lease=refs/heads/beta:$ep_beta_before" \
  origin "$ep_main_new:refs/heads/main" "$ep_beta_new:refs/heads/beta"
```

The dry run must show only the two intended branch updates, and both `git diff`
commands must be empty. Then apply those exact updates in the **same terminal**:

```bash
git push --atomic \
  "--force-with-lease=refs/heads/main:$ep_main_before" \
  "--force-with-lease=refs/heads/beta:$ep_beta_before" \
  origin "$ep_main_new:refs/heads/main" "$ep_beta_new:refs/heads/beta"
```

A rejected lease means someone changed a branch: stop and start from a fresh
clone, rather than replacing the expected SHAs or adding `--force`. A protection
rule may also reject the operation; stop and review the repository settings.
The snapshot messages skip the current Actions push workflow, so the reset does
not rebuild or change the published image tags.

Reclone once more into a new directory. `git rev-list --count origin/main`
should print `1`, and `git rev-list --count origin/beta` should print `2`.
Confirm again that only `main` and `beta` branches remain and no tags exist.
Compare their tree SHAs with `ep_main_tree` and `ep_beta_tree` saved above. Confirm
the retained Docker tags still pull. Delete the temporary clones and private
bundle once verification is complete; they otherwise retain the old history.
Use the new clone for all future work. Do not merge or push from an old clone.

The container's local `/source` download continues to work. GitHub links to old
commit IDs, including build-specific help links, can stop working after old
objects are purged; use the current main-branch installation guide until the
next container release carries the new history.

A force-push does not erase GitHub's PR refs, cached commit views, forks, local
clones or backups. Ask GitHub Support about the affected historical views using
its sensitive-data-removal process. Do not describe the cleanup as complete
until the retained views and references have been checked.

## Remove old images and workflow artifacts

With an owner-authorized `gh` session, inventory the personal GHCR package:

```sh
gh api --paginate '/users/ChrisK0007/packages/container/expense-pilot/versions?per_page=100' --jq '.[] | {id, name, tags: .metadata.container.tags}'
gh run list --repo ChrisK0007/Expense-Pilot --limit 1000 --json databaseId,headSha,status,conclusion,displayTitle
```

Resolve the current `latest` and `beta` with `docker buildx imagetools inspect`.
If either is an index, inspect its raw manifest and retain all referenced
platform/attestation digests recursively. Keep each package version whose
`name` is a retained digest, regardless of whether it has tags. Do not delete
all untagged versions blindly.

After reviewing the exact deletion IDs, remove each obsolete package version:

```sh
gh api --method DELETE /user/packages/container/expense-pilot/versions/VERSION_ID
```

Delete obsolete completed workflow runs (which removes their logs/artifacts)
with `gh run delete RUN_ID --repo ChrisK0007/Expense-Pilot`. Retain current
stable/beta verification runs and any active PR checks. Review/download any
needed evidence privately first. Delete remaining obsolete Actions artifacts
and caches in the repository Actions settings. Check release attachments and
PR uploads separately; deleting runs does not delete those.

Do not delete the package itself, move `latest`, overwrite numbered tags, or
run a Docker host-wide prune. Recheck both retained image pulls after deletion.

## About, protections and reporting

Set the description without changing visibility:

```sh
gh repo edit ChrisK0007/Expense-Pilot --description 'Self-hosted expense tracking and invoicing for Australian sole traders and employment expenses.'
gh api --method PUT repos/ChrisK0007/Expense-Pilot/topics --input - <<'JSON'
{"names":["self-hosted","docker","unraid","expense-tracker","invoicing","australia"]}
JSON
```

After history cleanup, protect both `main` and `beta`: require pull requests,
resolved conversations, and the successful `test-and-publish` check. Require
branches to be up to date. Disable deletion and force-pushes. Keep normal
Actions permissions read-only; the publishing job alone needs `packages:write`.
Do not require an additional human approval while the project has one maintainer.
Verify protections with a disposable PR; availability depends on the repository
plan/visibility. Record any unavailable gate rather than claiming it is enabled.

GitHub private vulnerability reporting is available for public repositories.
At the separately approved public launch, enable it in Settings → Code security
(or the REST private-vulnerability-reporting endpoint), verify the private report
form and update SECURITY.md if necessary. Do not switch visibility as part of
this preparation.

References:
- https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
- https://docs.github.com/en/rest/packages/packages
- https://docs.github.com/en/packages/learn-github-packages/deleting-and-restoring-a-package
- https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository
