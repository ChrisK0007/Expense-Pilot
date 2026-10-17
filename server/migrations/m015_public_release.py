from migrations import execute_script


def upgrade(connection):
    execute_script(connection, '''
        CREATE TABLE IF NOT EXISTS mobile_upload_receipts(
            user_id INTEGER NOT NULL, kind TEXT NOT NULL, client_ref TEXT NOT NULL,
            record_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
            PRIMARY KEY(user_id,kind,client_ref));
    ''')
