def upgrade(connection):
    columns = {
        'must_change_password': 'INTEGER NOT NULL DEFAULT 0',
        'invite_expires': 'REAL NOT NULL DEFAULT 0',
        'invite_status': "TEXT NOT NULL DEFAULT ''",
        'totp_enabled': 'INTEGER NOT NULL DEFAULT 0',
        'totp_secret': "TEXT NOT NULL DEFAULT ''",
        'totp_pending': "TEXT NOT NULL DEFAULT ''",
        'totp_pending_until': 'REAL NOT NULL DEFAULT 0',
        'totp_last_step': 'INTEGER NOT NULL DEFAULT -1',
        'recovery_hashes': "TEXT NOT NULL DEFAULT '[]'",
    }
    existing = {r[1] for r in connection.execute('PRAGMA table_info(users)')}
    for name, definition in columns.items():
        if name not in existing:
            connection.execute(f'ALTER TABLE users ADD COLUMN {name} {definition}')
    connection.execute("CREATE TABLE IF NOT EXISTS login_sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,kind TEXT NOT NULL,expires REAL NOT NULL)")
    connection.execute("UPDATE users SET active=0,version=version+1 WHERE role='employee' AND active=1")
