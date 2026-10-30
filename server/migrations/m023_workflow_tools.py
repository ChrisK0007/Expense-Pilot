"""Review workflows, reconciliation and security event history."""
from migrations import execute_script


def upgrade(c):
    for table, columns in {
        'login_sessions': [('ip_address', "TEXT NOT NULL DEFAULT ''"), ('user_agent', "TEXT NOT NULL DEFAULT ''")],
        'vehicle_journeys': [('review_confirmed', 'INTEGER NOT NULL DEFAULT 0')],
        'expenses': [('items_json', "TEXT NOT NULL DEFAULT '[]'")],
    }.items():
        existing = {r[1] for r in c.execute('PRAGMA table_info('+table+')')}
        for name, definition in columns:
            if name not in existing:
                c.execute('ALTER TABLE '+table+' ADD COLUMN '+name+' '+definition)
    execute_script(c, """
    CREATE TABLE IF NOT EXISTS known_signin_ips(user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      ip TEXT NOT NULL, first_seen REAL NOT NULL, last_seen REAL NOT NULL, PRIMARY KEY(user_id,ip));
    CREATE TABLE IF NOT EXISTS signin_events(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      ip TEXT NOT NULL, device TEXT NOT NULL, user_agent TEXT NOT NULL, at REAL NOT NULL,
      is_new INTEGER NOT NULL, state TEXT NOT NULL, error TEXT NOT NULL DEFAULT '', sent_at REAL NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS security_preferences(user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      signin_emails INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS categorisation_rules(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      merchant TEXT NOT NULL, category TEXT NOT NULL, work_percent INTEGER NOT NULL, business_percent INTEGER NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS workflow_changes(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      kind TEXT NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL, at TEXT NOT NULL, undone INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS record_questions(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      record_type TEXT NOT NULL, record_id TEXT NOT NULL, author_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
      question TEXT NOT NULL, answer TEXT NOT NULL DEFAULT '', resolved INTEGER NOT NULL DEFAULT 0,
      version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS income_details(income_id INTEGER PRIMARY KEY REFERENCES employment_income(id) ON DELETE CASCADE,
      net_cents INTEGER, ytd_gross_cents INTEGER, ytd_withheld_cents INTEGER, version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS annual_income_checks(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      year INTEGER NOT NULL, employer TEXT NOT NULL, gross_cents INTEGER NOT NULL, withheld_cents INTEGER NOT NULL,
      notes TEXT NOT NULL DEFAULT '', UNIQUE(user_id,year,employer));
    CREATE TABLE IF NOT EXISTS bank_reconciliations(id INTEGER PRIMARY KEY, bank_id INTEGER NOT NULL REFERENCES bank_transactions(id) ON DELETE CASCADE,
      kind TEXT NOT NULL, amount_cents INTEGER NOT NULL, income_id INTEGER REFERENCES employment_income(id) ON DELETE RESTRICT,
      invoice_id INTEGER REFERENCES billing_documents(id) ON DELETE RESTRICT, payment_id INTEGER REFERENCES billing_payments(id) ON DELETE RESTRICT,
      expense_id INTEGER REFERENCES expenses(id) ON DELETE RESTRICT, refund_id INTEGER REFERENCES expenses(id) ON DELETE RESTRICT,
      created_at TEXT NOT NULL);
    CREATE UNIQUE INDEX IF NOT EXISTS reconciled_pay ON bank_reconciliations(income_id) WHERE income_id IS NOT NULL;
    CREATE TABLE IF NOT EXISTS equipment_assets(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      expense_id INTEGER UNIQUE REFERENCES expenses(id) ON DELETE RESTRICT, name TEXT NOT NULL, acquired TEXT NOT NULL,
      cost_cents INTEGER NOT NULL, work_percent INTEGER NOT NULL, business_percent INTEGER NOT NULL,
      disposal_date TEXT NOT NULL DEFAULT '', proceeds_cents INTEGER NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '',
      version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS equipment_depreciation(asset_id INTEGER NOT NULL REFERENCES equipment_assets(id) ON DELETE CASCADE,
      year INTEGER NOT NULL, amount_cents INTEGER NOT NULL, notes TEXT NOT NULL, confirmed INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(asset_id,year));
    CREATE TABLE IF NOT EXISTS mail_intake_messages(user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      message_key TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL, at TEXT NOT NULL,
      PRIMARY KEY(user_id,message_key));
    """)
