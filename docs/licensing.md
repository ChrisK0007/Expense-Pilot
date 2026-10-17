# Licensing and third-party notices

## Project licence decision

A licence for the Expense Pilot application has not yet been selected. The plan is a free, self-hosted Docker release; that does not by itself specify permission to modify or redistribute its source.

Before publishing the source or container for general use, the owner needs to select and add the intended project licence. Two possible open-source approaches are:

| Option | Intended approach |
| --- | --- |
| MIT | Broad reuse, modification and commercial redistribution with the copyright and licence notice retained. |
| AGPL-3.0 | Copyleft, including source-availability obligations for modified software offered over a network. |

These are alternatives for review, not licences applied by this document. See GitHub's [licensing guide](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository), the [MIT text](https://choosealicense.com/licenses/mit/) and [AGPL-3.0 text](https://choosealicense.com/licenses/agpl-3.0/) before choosing. A free binary/container release with retained source rights is a separate option and needs suitable distribution terms.

## Bundled Australian suburb data

The lookup is derived from `michalsn/australian-suburbs`, copyright 2019 Michal Sniatala, under MIT. The original licence is retained in [LICENSE-au-suburbs.txt](../server/datasets/LICENSE-au-suburbs.txt). The [dataset README](../server/datasets/README.md) records the source blob, retrieval date, transformations and limitations. This licence applies to that dataset, not automatically to Expense Pilot's application code.

## Runtime dependencies and assets

The Python dependency versions are listed in [requirements.txt](../server/requirements.txt). The Dockerfile also installs Poppler and DejaVu fonts, and uses the Python base image. These components keep their own licences and notices. Review the exact published image's dependency/source obligations before distributing it; a dependency vulnerability scan does not perform a licence review.

Retain required notices and check rights to any newly added icons, screenshots, datasets or templates. Public screenshots and examples must use synthetic financial records. The former `rounded.sqlite` filename is retained solely for data compatibility; Expense Pilot is not affiliated with Rounded.
