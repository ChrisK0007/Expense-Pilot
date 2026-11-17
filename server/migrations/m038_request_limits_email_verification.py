from migrations import execute_script


def upgrade(connection):
    execute_script(connection, """
    CREATE TABLE IF NOT EXISTS request_limits(
        key TEXT PRIMARY KEY,
        count INTEGER NOT NULL,
        until REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS email_verification(
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        email TEXT NOT NULL,
        verified_at REAL NOT NULL DEFAULT 0,
        challenge_hash TEXT NOT NULL DEFAULT '',
        challenge_version INTEGER NOT NULL DEFAULT 0,
        expires REAL NOT NULL DEFAULT 0,
        attempts INTEGER NOT NULL DEFAULT 0,
        send_count INTEGER NOT NULL DEFAULT 0,
        send_until REAL NOT NULL DEFAULT 0
    );
    """)
