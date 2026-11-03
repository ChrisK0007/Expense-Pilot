from migrations import execute_script


def upgrade(connection):
    if 'quantity_type' not in {r[1] for r in connection.execute('PRAGMA table_info(billing_services)')}:
        connection.execute("ALTER TABLE billing_services ADD COLUMN quantity_type TEXT NOT NULL DEFAULT 'Units'")
    if 'attachments_json' not in {r[1] for r in connection.execute('PRAGMA table_info(billing_outbox)')}:
        connection.execute("ALTER TABLE billing_outbox ADD COLUMN attachments_json TEXT NOT NULL DEFAULT '[]'")
    execute_script(connection, '''
        CREATE TABLE IF NOT EXISTS billing_editor_drafts(
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            draft_key TEXT NOT NULL, payload TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL, PRIMARY KEY(user_id,draft_key)
        );
        CREATE TABLE IF NOT EXISTS billing_attachments(
            id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES billing_documents(id) ON DELETE CASCADE,
            filename TEXT NOT NULL, mime TEXT NOT NULL, content BLOB NOT NULL,
            sha256 TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workspace_preferences(
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            data TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS owner_notification_emails(
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            event_key TEXT NOT NULL, state TEXT NOT NULL, error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, PRIMARY KEY(user_id,event_key)
        );
    ''')
