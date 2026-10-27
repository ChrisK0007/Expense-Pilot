"""Home-office diary, annual elections, bill classification and immutable history."""
from migrations import execute_script


def upgrade(connection):
    execute_script(connection, """
    CREATE TABLE IF NOT EXISTS home_office_entries (
        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        date TEXT NOT NULL, start_at INTEGER NOT NULL, end_at INTEGER NOT NULL,
        timezone TEXT NOT NULL, start_time TEXT NOT NULL, end_time TEXT NOT NULL,
        break_minutes INTEGER NOT NULL DEFAULT 0, scope TEXT NOT NULL CHECK(scope IN ('work','business')),
        activity TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
        client_ref TEXT NOT NULL, fingerprint TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id,client_ref), CHECK(end_at > start_at)
    );
    CREATE INDEX IF NOT EXISTS home_office_entry_dates ON home_office_entries(user_id,date,deleted);
    CREATE TABLE IF NOT EXISTS home_office_settings (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, year INTEGER NOT NULL,
        data TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(user_id,year)
    );
    CREATE TABLE IF NOT EXISTS home_office_costs (
        expense_id INTEGER PRIMARY KEY REFERENCES expenses(id) ON DELETE CASCADE,
        kind TEXT NOT NULL, claim_base_cents INTEGER,
        basis TEXT NOT NULL DEFAULT '', reviewed INTEGER NOT NULL DEFAULT 0,
        version INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS home_office_allowances (
        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        date TEXT NOT NULL, employer TEXT NOT NULL, amount_cents INTEGER NOT NULL,
        included_in_pay INTEGER NOT NULL DEFAULT 1, notes TEXT NOT NULL DEFAULT '',
        version INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS home_office_history (
        id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        actor_id INTEGER, at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        entity TEXT NOT NULL, action TEXT NOT NULL, before_json TEXT, after_json TEXT
    );
    """)
