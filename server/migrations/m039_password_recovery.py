from migrations import execute_script


def upgrade(connection):
    execute_script(connection, '''
    CREATE TABLE IF NOT EXISTS password_resets(
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        verifier TEXT NOT NULL UNIQUE, email TEXT NOT NULL,
        user_version INTEGER NOT NULL, expires REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS recovery_requests(
        key TEXT PRIMARY KEY, count INTEGER NOT NULL, until REAL NOT NULL
    );
    ''')
