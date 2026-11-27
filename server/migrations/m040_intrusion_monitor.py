from migrations import execute_script


def upgrade(connection):
    execute_script(connection, '''
    CREATE TABLE IF NOT EXISTS intrusion_sources(
        key TEXT PRIMARY KEY, hits INTEGER NOT NULL,
        window_until REAL NOT NULL, blocked_until REAL NOT NULL,
        last_seen REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS intrusion_events(
        id INTEGER PRIMARY KEY, source_key TEXT NOT NULL,
        at REAL NOT NULL, kind TEXT NOT NULL, action TEXT NOT NULL
    );
    ''')
