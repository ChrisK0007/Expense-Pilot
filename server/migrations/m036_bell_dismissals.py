"""Remember which informational alerts the owner has cleared from the bell."""


def upgrade(connection):
    connection.execute("""
        CREATE TABLE IF NOT EXISTS owner_bell_dismissals (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            event_key TEXT NOT NULL,
            PRIMARY KEY (user_id, event_key)
        )
    """)
