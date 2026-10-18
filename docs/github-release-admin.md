# GitHub administration before public release

Status at preparation, 18 October 2026: repository and package remain private.
There are 51 branches, no Git tags and 142 workflow runs. The connected editor
can change repository files, but cannot administer packages, delete refs/runs,
create an orphan root, or change repository settings. None of the history,
image or administration operations below has been performed by this change.

## Preserve the current channels

Keep `main`, `beta`, and the current source snapshots for open pull requests.
PR #47 is the pending stable attribution cleanup; do not lose or merge it as
part of history removal. Preserve the stable image and the latest verified beta
image, including every platform/attestation manifest they reference.

Stable 1.0.3 currently points to:
`sha256:2bc318bdec6d52f84510dec82be3af2ceab4d6bb86289238585c731a22778ce6`.
The last verified beta before this change, 1.0.4-beta.1, points to:
`sha256:c9dae90c02aa6623ae6b99a269bef1b09ac896bb823b6bcb717403caec6a00d5`.
Resolve tags again after any new beta publication. Do not rely on an old digest
list when deleting package versions.

Stable 1.0.3 still contains the earlier copyright attribution. Keeping that
image means keeping that notice until an approved stable replacement. History
cleanup does not change the contents of existing images. Keep the project
private until this is resolved.

## Remove old Git history

Perform this in a fresh, private administrative clone with no other writers.
Keep a private offline `git bundle create ../expense-pilot-before-cleanup.bundle
--all` until the new branches and active work are verified. Never upload this
bundle or publish an archival branch: either would retain the old history.

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
