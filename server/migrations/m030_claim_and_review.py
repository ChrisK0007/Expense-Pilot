"""Add actual-cost calculations, recurring drafts and review links."""
from migrations import execute_script


def upgrade(connection):
    if not any(row[1] == "actual_json" for row in connection.execute("PRAGMA table_info(home_office_costs)")):
        connection.execute("ALTER TABLE home_office_costs ADD COLUMN actual_json TEXT NOT NULL DEFAULT '{}'")
    execute_script(connection, """

        CREATE TABLE IF NOT EXISTS recurring_expense_rules (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
            data TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
            version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS recurring_expense_occurrences (
            rule_id INTEGER NOT NULL REFERENCES recurring_expense_rules(id),
            due_date TEXT NOT NULL,
            bank_id INTEGER UNIQUE REFERENCES bank_transactions(id) ON DELETE SET NULL,
            expense_id INTEGER UNIQUE REFERENCES expenses(id) ON DELETE SET NULL,
            PRIMARY KEY (rule_id,due_date)
        );
        CREATE TABLE IF NOT EXISTS bank_transfer_pairs (
            id INTEGER PRIMARY KEY,
            debit_id INTEGER NOT NULL UNIQUE REFERENCES bank_transactions(id),
            credit_id INTEGER NOT NULL UNIQUE REFERENCES bank_transactions(id),
            debit_state TEXT NOT NULL, credit_state TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS billable_expenses (
            expense_id INTEGER PRIMARY KEY REFERENCES expenses(id) ON DELETE CASCADE,
            client_id INTEGER NOT NULL REFERENCES billing_clients(id),
            document_id INTEGER REFERENCES billing_documents(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS handover_revisions (
            year INTEGER NOT NULL, revision INTEGER NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            note TEXT NOT NULL, figures TEXT NOT NULL,
            PRIMARY KEY (year,revision,user_id)
        );
    """)
