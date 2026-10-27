# Supporting documents

Open **Reports → Documents** to keep tax-time records that are not expenses or deductions: previous tax returns, private health fund statements, income statements, superannuation records, insurance, bank/investment statements, tax correspondence and other documents.

## Upload and organise

1. Select **Upload document**, choose the original file and enter a title.
2. Choose a category and optionally a financial year. **FY 2025–26** means 1 July 2025 to 30 June 2026. Leave it **Unassigned** for records spanning years or general reference material.
3. Add optional notes and upload. Identical file contents are detected; a repeat upload keeps the original document and its existing details.
4. Search by title, filename or notes and filter by category/year. **Edit details** changes the description, category, year and notes without modifying the original file. **Download** returns the original.

Supported files are PDF, PNG, JPG/JPEG, WebP, DOCX, XLSX, UTF-8 CSV and UTF-8 TXT, up to 10 MB each. PDFs are not subject to the receipt page limit, and password-protected PDFs can be stored/downloaded. The server checks file signatures/containers but does not render or execute documents, perform malware scanning or send their contents to AI services. Documents download as attachments; open them using an appropriate application.

## Access and accounting

The repository belongs to the workspace owner. Tax agents can view and download records; agents with read/write access can upload, edit and delete. Removing an agent's login retains the owner's documents.

Documents do not create expenses, receipts, income or tax deductions. Keep expense evidence in Expenses/Home office when it supports a claim. This repository is for other supporting records.

## Storage, backups and deletion

Originals are stored under `/data/documents` using internal identifiers; titles and filenames are metadata. No new Docker mount is needed. Manual and automatic full backups include every referenced original and its checksum, and restore validates the files against the database. A missing original fails the backup instead of silently omitting it.

Deleting a document removes its active metadata and original file. Deleting the owner workspace removes all active document files. Existing backups and downloaded copies are not erased. Keep backups privately because they contain the same sensitive records as the live workspace.

Migration m021 adds the document table and preserves existing records. Back up before updating. An older image cannot open a database after m021; rollback requires the matching pre-update backup and image.
