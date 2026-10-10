"""Editable services, reusable invoice numbers and invoice reminder overrides."""
from migrations import execute_script


def upgrade(connection):
    for table, name, definition in [
        ('billing_services', 'version', 'INTEGER NOT NULL DEFAULT 1'),
        ('billing_documents', 'reminder_options', "TEXT NOT NULL DEFAULT '{}'"),
    ]:
        if name not in {r[1] for r in connection.execute('PRAGMA table_info(' + table + ')')}:
            connection.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
    execute_script(connection, """
        CREATE TABLE IF NOT EXISTS billing_reusable_invoice_numbers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number TEXT NOT NULL UNIQUE COLLATE NOCASE
        );
    """)
    # Delivery claims must survive invoice renumbering. Keep prior claims so an
    # already sent, failed or uncertain reminder cannot be resent by this upgrade.
    for oid, did, key in connection.execute('SELECT id,document_id,automation_key FROM billing_outbox WHERE automation_key IS NOT NULL').fetchall():
        dates = key.rsplit(':', 2)[-2:]
        connection.execute('UPDATE billing_outbox SET automation_key=? WHERE id=?',
                           ('invoice:' + str(did) + ':' + ':'.join(dates), oid))
