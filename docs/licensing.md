# Licensing and third-party notices

## Expense Pilot application

Copyright (C) 2026 ChrisK0007.

Expense Pilot's server and web interface are licensed under the **GNU Affero General Public License, version 3 only** (`AGPL-3.0-only`). The complete, unmodified licence text is in [LICENSE](../LICENSE); the application notice is in [COPYRIGHT](../COPYRIGHT).

This applies to the original project material in this repository unless a file or component states a different licence. Third-party components retain their own terms. The separately maintained iOS repository is not relicensed by this change.

You may use, modify and redistribute the application under the licence. Distribution of covered versions carries source and notice obligations. If you modify it and let users interact with that version remotely over a network, section 13 requires a prominent offer of its Corresponding Source to those users. Commercial use and paid hosting are permitted. These obligations concern program source, not users' receipts, account credentials or financial records. The licence text governs; this paragraph is a summary.

The application is provided without warranty, subject to applicable law. Use the repository's [support guidance](../SUPPORT.md) and [security policy](../SECURITY.md) for reports.

## Distribution and source access

Include the licence and application notice in distributed packages and provide the Corresponding Source required for the actual version supplied, including relevant build/install scripts. A link to a different version or an inaccessible private repository is not sufficient source access for recipients.

Starting with v1.0.3, the image includes LICENSE and COPYRIGHT under `/app` and an AGPL-3.0-only image label. Stable 1.0.4 (first tested in 1.0.4-beta.2) adds a public `/about` page, linked from login, the sidebar and Settings, with a `/source` download served by the container itself. The archive is created at build time, includes build/install scripts, tests and documentation, and identifies the application version and build revision with file checksums. It is independent of GitHub visibility. It excludes Git history, runtime data, receipts, backups and credentials. The server never creates a source archive from its live data volume.

The `/legal/manifest` endpoint records the archive checksum; `/legal/dependencies` and `/legal/inventory` provide the notices and resolved dependency versions from that image. Source checkouts without a build bundle show an explicit unavailable state. Modified distributors must rebuild the bundle with their changes. Keep numbered image tags immutable.

## Bundled Australian suburb data

The lookup is derived from `michalsn/australian-suburbs`, copyright 2019 Michal Sniatala, under MIT. The original licence is retained in [LICENSE-au-suburbs.txt](../server/datasets/LICENSE-au-suburbs.txt). The [dataset README](../server/datasets/README.md) records the source blob, retrieval date, transformations and limitations. This third-party notice remains in force.

## Runtime dependencies and assets

The Python dependency versions are listed in [requirements.txt](../server/requirements.txt). The Dockerfile also installs Poppler and DejaVu fonts, and uses the Python base image. These components keep their own licences and notices. Review the exact published image's dependency/source obligations before distributing it; a dependency vulnerability scan does not perform a licence review.

Retain required notices and check rights to any newly added icons, screenshots, datasets or templates. Public screenshots and examples must use synthetic financial records. The former `rounded.sqlite` filename is retained solely for data compatibility; Expense Pilot is not affiliated with Rounded.

## Dependency review — 18 October 2026

The direct pinned dependencies are reviewed in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). Their upstream licences are permissive; retain the actual notices, including bundled libraries and fonts. The image build collects installed distribution notices (including transitive dependencies), Debian package copyright files, common licence texts and Python's licence. The inventory records Debian source package names/versions and upstream references instead of assuming the floating base image contains a fixed package set.

Primary references: [Flask](https://pypi.org/project/Flask/3.1.3/), [Gunicorn](https://pypi.org/project/gunicorn/26.2.0/), [Pillow licence](https://github.com/python-pillow/Pillow/blob/12.3.0/LICENSE), [pypdf](https://pypi.org/project/pypdf/6.19.0/), [ReportLab](https://pypi.org/project/reportlab/5.0.1/), [cryptography](https://pypi.org/project/cryptography/50.0.2/), [Poppler](https://poppler.freedesktop.org/) and [DejaVu](https://dejavu-fonts.github.io/License.html).

**Remaining public-distribution gate:** inspect the generated inventory for missing notices and satisfy corresponding-source obligations for the actual GPL/LGPL native components (including Poppler and relevant libraries/base packages). Retain or host exact required sources, patches and build instructions alongside the binary distribution, with a compliant source-access arrangement. Upstream references and a vulnerability scan alone do not establish this. The current application archive covers Expense Pilot's source, not all dependency sources. Do not mark the full container licence distribution review complete until this has been verified on the release candidate.
