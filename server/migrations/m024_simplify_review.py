"""Invoice revisions and explicit due-date choices; retire redundant review work."""
import json
from datetime import date, timedelta
from migrations import execute_script


def upgrade(c):
    columns={r[1] for r in c.execute("PRAGMA table_info(billing_documents)")}
    if 'due_date_manual' not in columns:
        c.execute("ALTER TABLE billing_documents ADD COLUMN due_date_manual INTEGER NOT NULL DEFAULT 1")
        # Preserve custom dates; recognise legacy invoices that follow their saved terms.
        for ident,issued,due,client,schedule_terms in c.execute("SELECT d.id,d.issue_date,d.due_date,d.client,s.terms FROM billing_documents d LEFT JOIN billing_schedules s ON s.id=d.schedule_id WHERE d.kind='invoice'").fetchall():
            try:
                terms=schedule_terms if schedule_terms is not None else json.loads(client)['terms']
                if due==(date.fromisoformat(issued)+timedelta(days=int(terms))).isoformat():
                    c.execute("UPDATE billing_documents SET due_date_manual=0 WHERE id=?",(ident,))
            except (ValueError,TypeError,KeyError,OverflowError): pass
    if 'needs_reissue' not in columns:
        c.execute("ALTER TABLE billing_documents ADD COLUMN needs_reissue INTEGER NOT NULL DEFAULT 0")
    c.execute("UPDATE vehicle_journeys SET review_confirmed=1 WHERE scope='personal' OR (scope IN ('work','business') AND trim(purpose)<>'')")
    execute_script(c, """
    CREATE TABLE IF NOT EXISTS billing_revision_history(
      id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES billing_documents(id) ON DELETE CASCADE,
      version INTEGER NOT NULL, user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
      previous TEXT NOT NULL, changed_at TEXT NOT NULL);
    """)
