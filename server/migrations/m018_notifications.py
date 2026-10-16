from migrations import execute_script


def upgrade(connection):
    execute_script(connection, '''
        CREATE TABLE IF NOT EXISTS notification_devices(
            installation TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            user_version INTEGER NOT NULL,
            session_hash TEXT NOT NULL,
            context TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,
            preferences TEXT NOT NULL,
            seen TEXT NOT NULL DEFAULT '{}',
            expires REAL NOT NULL,
            next_attempt REAL NOT NULL DEFAULT 0,
            lease_until REAL NOT NULL DEFAULT 0,
            failures INTEGER NOT NULL DEFAULT 0
        );
    ''')
