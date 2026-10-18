import json
from migrations import execute_script


def upgrade(connection):
    for table, columns in {
        'billing_documents': {'reminders_enabled': 'INTEGER NOT NULL DEFAULT 1'},
        'billing_outbox': {'message_kind': "TEXT NOT NULL DEFAULT 'document'", 'signature_html': "TEXT NOT NULL DEFAULT ''", 'automation_key': 'TEXT'},
    }.items():
        existing = {row[1] for row in connection.execute('PRAGMA table_info(' + table + ')')}
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
    execute_script(connection, """
        CREATE UNIQUE INDEX IF NOT EXISTS billing_email_automation ON billing_outbox(automation_key) WHERE automation_key IS NOT NULL;
        CREATE TABLE IF NOT EXISTS billing_statement_outbox(
            id INTEGER PRIMARY KEY, client_id INTEGER NOT NULL REFERENCES billing_clients(id) ON DELETE CASCADE,
            recipient TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL, signature_html TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL, request_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, error TEXT NOT NULL DEFAULT '',
            snapshot TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS billing_statement_client ON billing_statement_outbox(client_id);
    """)
    # Replace the old factory wording, including copies saved by the defaults form.
    # User-edited wording remains available, with a reset action in Email templates.
    row = connection.execute("SELECT value FROM billing_settings WHERE key='document_defaults'").fetchone()
    if row:
        values = json.loads(row[0])
        old = dict(subject='{kind} {number} from {business}', body='Hi {client},\n\nPlease find your {kind} {number} attached.\nTotal: {total}\nDue / valid until: {due_date}\n\nThank you,\n{business}')
        defaults = {
            'invoice': dict(subject='Invoice from {business}', body="Hi {client},\nI've created invoice {number}, payment before the {due_date} would be appreciated.\nBest regards,\n{full_name}"),
            'quote': dict(subject='Quote from {business}', body="Hi {client},\nI've created a quote for {total}.\nBest regards,\n{full_name}"),
        }
        for kind in defaults:
            for field in ('subject', 'body'):
                key = kind + '_email_' + field
                if values.get(key) == old[field]:
                    values[key] = defaults[kind][field]
        connection.execute("UPDATE billing_settings SET value=? WHERE key='document_defaults'", (json.dumps(values),))
