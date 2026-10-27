# Third-party components

Expense Pilot's AGPL-3.0-only licence applies to its original application code.
Dependencies, datasets and fonts retain their own licences and copyright notices.

| Direct component | Pinned version | Upstream licence |
| --- | --- | --- |
| Flask | 3.1.3 | BSD-3-Clause |
| Gunicorn | 26.2.0 | MIT |
| Pillow | 12.3.0 | MIT-CMU; bundled libraries have additional notices |
| pypdf | 6.19.0 | BSD-3-Clause |
| ReportLab | 5.0.1 | BSD; bundled fonts retain their notices |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause; bundled libraries retain their notices |
| SQLite library used by Python | 3.54.1 | Public domain; https://www.sqlite.org/copyright.html |
| Australian suburb dataset | See server/datasets/README.md | MIT; original notice in server/datasets/LICENSE-au-suburbs.txt |
| Python 3.12 base image | Resolved at build time | Python PSF and component-specific licences |
| Poppler utilities | Resolved by Debian at build time | GPL-2.0-or-later and component-specific notices |
| DejaVu fonts | Resolved by Debian at build time | Bitstream Vera and applicable font notices; DejaVu changes are public domain |

`/legal/dependencies` downloads the notices copied from the actual installed
Python distributions and Debian packages, plus Debian common licence texts and
Python's licence. It includes notices for transitive and vendored components
where supplied in their installed distributions. The original installed notices
are retained in the image as well.

`/legal/inventory` lists exact installed versions, included notice paths and
upstream source references. `/source` contains the Expense Pilot application,
its build/install scripts and the bundled dataset notice. The separate `/legal/dependency-sources` archive retains the exact Debian source
packages and their patches/build rules, Python source distributions, CPython
source/configure arguments, the pinned SQLite amalgamation and compiler arguments,
and the detected FriBiDi source when loaded by Pillow. The native SQLite entry in
the inventory identifies Python's loaded library separately from Debian's package.
`/legal/dependency-source-manifest` records versions and SHA-256 checksums. The
build refuses incomplete source collection or an unreviewed libimagequant build.

These sources accompany the image and are also attached to stable GitHub
releases. Rebuilding with changed dependencies requires rechecking their terms,
notices and any newly vendored native components. Keep each published image's
source assets available for its recipients. See docs/licensing.md for scope and
reconstruction instructions. Individual component licence texts govern.
