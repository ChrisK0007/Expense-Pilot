"""Store seen release notes, client contacts and reusable travel salary bands."""
from migrations import execute_script


def upgrade(connection):
    if not any(row[1] == 'phone' for row in connection.execute('PRAGMA table_info(billing_clients)')):
        connection.execute("ALTER TABLE billing_clients ADD COLUMN phone TEXT NOT NULL DEFAULT ''")
    if not any(row[1] == 'annual_base_cents' for row in connection.execute('PRAGMA table_info(employment_income)')):
        connection.execute('ALTER TABLE employment_income ADD COLUMN annual_base_cents INTEGER '
                           'CHECK(annual_base_cents IS NULL OR annual_base_cents > 0)')
    execute_script(connection, """
        CREATE TABLE IF NOT EXISTS billing_client_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL REFERENCES billing_clients(id) ON DELETE CASCADE,
            name TEXT NOT NULL DEFAULT '', department TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '',
            is_default INTEGER NOT NULL DEFAULT 0 CHECK(is_default IN (0,1))
        );
        CREATE INDEX IF NOT EXISTS billing_contacts_client ON billing_client_contacts(client_id);
        CREATE UNIQUE INDEX IF NOT EXISTS billing_contacts_default ON billing_client_contacts(client_id) WHERE is_default=1;
        CREATE TABLE IF NOT EXISTS release_notice_seen (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            version TEXT NOT NULL,
            PRIMARY KEY(user_id,version)
        );
        CREATE TABLE IF NOT EXISTS overnight_salary_bands (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            year INTEGER NOT NULL, employer_key TEXT NOT NULL,
            employer TEXT NOT NULL, band INTEGER NOT NULL CHECK(band BETWEEN 0 AND 2),
            PRIMARY KEY(user_id,year,employer_key)
        );
    """)
