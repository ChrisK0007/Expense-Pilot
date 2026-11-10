"""Keep an owner's weekly schedule and reminder selection across devices."""


def upgrade(connection):
    connection.execute("""CREATE TABLE wfh_schedules (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        version INTEGER NOT NULL DEFAULT 1,
        data TEXT NOT NULL
    )""")
