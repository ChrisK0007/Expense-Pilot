def upgrade(connection):
    existing = {r[1] for r in connection.execute('PRAGMA table_info(login_sessions)')}
    for name, definition in {
        'device_name': "TEXT NOT NULL DEFAULT ''",
        'created_at': 'REAL NOT NULL DEFAULT 0',
        'last_used': 'REAL NOT NULL DEFAULT 0',
        'user_version': 'INTEGER NOT NULL DEFAULT 0',
    }.items():
        if name not in existing:
            connection.execute(f'ALTER TABLE login_sessions ADD COLUMN {name} {definition}')
