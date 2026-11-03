"""Supporting tax documents are separate from expenses and deductions."""
from migrations import execute_script


def upgrade(connection):
    execute_script(connection, """
    CREATE TABLE IF NOT EXISTS tax_documents (
        id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title TEXT NOT NULL, filename TEXT NOT NULL, content_type TEXT NOT NULL,
        size_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'other', year INTEGER,
        notes TEXT NOT NULL DEFAULT '', uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        version INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id,sha256), CHECK(size_bytes > 0), CHECK(year IS NULL OR year BETWEEN 1900 AND 2099)
    );
    CREATE INDEX IF NOT EXISTS tax_documents_year_category ON tax_documents(user_id,year,category);
    """)
