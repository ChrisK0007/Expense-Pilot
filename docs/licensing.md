# Licensing and third-party notices

## Expense Pilot application

Copyright (C) 2026 ChrisK0007.

Expense Pilot's server and web interface are licensed under the **GNU Affero General Public License, version 3 only** (`AGPL-3.0-only`). The complete, unmodified licence text is in [LICENSE](../LICENSE); the application notice is in [COPYRIGHT](../COPYRIGHT).

This applies to the original project material in this repository unless a file or component states a different licence. Third-party components retain their own terms. The separately maintained iOS repository is not relicensed by this change.

You may use, modify and redistribute the application under the licence. Distribution of covered versions carries source and notice obligations. If you modify it and let users interact with that version remotely over a network, section 13 requires a prominent offer of its Corresponding Source to those users. Commercial use and paid hosting are permitted. These obligations concern program source, not users' receipts, account credentials or financial records. The licence text governs; this paragraph is a summary.

The application is provided without warranty, subject to applicable law. Use the repository's [support guidance](../SUPPORT.md) and [security policy](../SECURITY.md) for reports.

## Distribution and source access

Include the licence and application notice in distributed packages and provide the Corresponding Source required for the actual version supplied, including relevant build/install scripts. A link to a different version or an inaccessible private repository is not sufficient source access for recipients.

The existing 1.0.2 container predates this repository licensing change and has not been rebuilt by it. Starting with v1.0.3, the Docker image includes LICENSE and COPYRIGHT under /app and an AGPL-3.0-only image label. Before public distribution, provide accessible version-matched source and a source/licence link in the web interface, and complete the dependency licence review. Keep numbered image tags immutable. The [release checklist](release-checklist.md) tracks these tasks separately from selecting the licence.

## Bundled Australian suburb data

The lookup is derived from `michalsn/australian-suburbs`, copyright 2019 Michal Sniatala, under MIT. The original licence is retained in [LICENSE-au-suburbs.txt](../server/datasets/LICENSE-au-suburbs.txt). The [dataset README](../server/datasets/README.md) records the source blob, retrieval date, transformations and limitations. This third-party notice remains in force.

## Runtime dependencies and assets

The Python dependency versions are listed in [requirements.txt](../server/requirements.txt). The Dockerfile also installs Poppler and DejaVu fonts, and uses the Python base image. These components keep their own licences and notices. Review the exact published image's dependency/source obligations before distributing it; a dependency vulnerability scan does not perform a licence review.

Retain required notices and check rights to any newly added icons, screenshots, datasets or templates. Public screenshots and examples must use synthetic financial records. The former `rounded.sqlite` filename is retained solely for data compatibility; Expense Pilot is not affiliated with Rounded.
