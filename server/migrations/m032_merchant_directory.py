"""Seed saved merchant names while preserving existing expense and source data."""
from merchant_directory import remember, merchant_key
from migrations import execute_script


def upgrade(connection):
    execute_script(connection, """
        CREATE TABLE IF NOT EXISTS merchants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            UNIQUE (id,user_id)
        );
        CREATE INDEX IF NOT EXISTS merchant_owner_name ON merchants(user_id,name);
        CREATE TABLE IF NOT EXISTS merchant_names (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            match_key TEXT NOT NULL,
            merchant_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            PRIMARY KEY (user_id,match_key),
            FOREIGN KEY (merchant_id,user_id) REFERENCES merchants(id,user_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS merchant_aliases_by_merchant ON merchant_names(merchant_id,user_id);
    """)
    seen = set()
    for user_id, name in connection.execute("SELECT user_id,merchant FROM expenses ORDER BY status='ready' DESC,date DESC,id DESC"):
        key = (user_id, merchant_key(name))
        if key not in seen:
            remember(connection, user_id, name.strip())
            seen.add(key)
