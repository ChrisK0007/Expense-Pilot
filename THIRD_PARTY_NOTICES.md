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
its build/install scripts and the bundled dataset notice. These application
sources do not include the third-party dependency sources.

Before public binary distribution, the maintainer must verify the generated
inventory and supply any required corresponding third-party source, including
applicable patches and build instructions. In particular, a notices archive or
an upstream homepage alone is not a complete source offer for GPL/LGPL binaries.
The remaining distribution check is recorded in docs/licensing.md and the
release checklist. This file is a component review, not a replacement for the
individual licence texts.
