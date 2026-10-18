from migrations import execute_script


def upgrade(connection):
    columns = {r[1] for r in connection.execute('PRAGMA table_info(trips)')}
    if 'comparison_json' not in columns:
        connection.execute("ALTER TABLE trips ADD COLUMN comparison_json TEXT NOT NULL DEFAULT '{}'")
        connection.execute('ALTER TABLE trips ADD COLUMN comparison_version INTEGER NOT NULL DEFAULT 1')
    # Retain request tombstones after invoice deletion so a late retry cannot recreate it.
    execute_script(connection, """
        CREATE TABLE IF NOT EXISTS billing_document_requests(
            user_id INTEGER NOT NULL REFERENCES users(id), request_key TEXT NOT NULL,
            fingerprint TEXT NOT NULL, document_id INTEGER NOT NULL,
            PRIMARY KEY(user_id,request_key));
    """)
