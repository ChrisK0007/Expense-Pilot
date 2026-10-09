from migrations import execute_script


def upgrade(connection):
    execute_script(connection, """
        CREATE TABLE IF NOT EXISTS pocketsmith_connection(
            id INTEGER PRIMARY KEY CHECK(id=1), key_encrypted TEXT NOT NULL DEFAULT '',
            remote_user_id TEXT NOT NULL DEFAULT '', display_name TEXT NOT NULL DEFAULT '',
            start_date TEXT NOT NULL DEFAULT '', auto_sync INTEGER NOT NULL DEFAULT 0,
            version INTEGER NOT NULL DEFAULT 1, last_sync TEXT NOT NULL DEFAULT '',
            last_attempt REAL NOT NULL DEFAULT 0, next_sync REAL NOT NULL DEFAULT 0,
            retry_after REAL NOT NULL DEFAULT 0, last_error TEXT NOT NULL DEFAULT '',
            lock_token TEXT NOT NULL DEFAULT '', lock_until REAL NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO pocketsmith_connection(id) VALUES (1);
        CREATE TABLE IF NOT EXISTS pocketsmith_accounts(
            id INTEGER PRIMARY KEY, remote_user_id TEXT NOT NULL, remote_id TEXT NOT NULL,
            name TEXT NOT NULL, institution TEXT NOT NULL DEFAULT '', currency TEXT NOT NULL,
            local_account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
            enabled INTEGER NOT NULL DEFAULT 0, available INTEGER NOT NULL DEFAULT 1,
            UNIQUE(remote_user_id,remote_id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS pocketsmith_account_mapping
            ON pocketsmith_accounts(local_account_id) WHERE local_account_id IS NOT NULL;
        CREATE TABLE IF NOT EXISTS bank_transactions(
            id INTEGER PRIMARY KEY, feed_account_id INTEGER NOT NULL REFERENCES pocketsmith_accounts(id),
            remote_user_id TEXT NOT NULL, remote_id TEXT NOT NULL, date TEXT NOT NULL,
            payee TEXT NOT NULL, amount_cents INTEGER NOT NULL, currency TEXT NOT NULL,
            memo TEXT NOT NULL DEFAULT '', source_category TEXT NOT NULL DEFAULT '',
            source_status TEXT NOT NULL, is_transfer INTEGER NOT NULL DEFAULT 0,
            source_updated_at TEXT NOT NULL DEFAULT '', fingerprint TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'review', expense_id INTEGER REFERENCES expenses(id) ON DELETE SET NULL,
            changed INTEGER NOT NULL DEFAULT 0, missing INTEGER NOT NULL DEFAULT 0,
            version INTEGER NOT NULL DEFAULT 1, last_seen TEXT NOT NULL,
            UNIQUE(remote_user_id,remote_id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS bank_expense_link ON bank_transactions(expense_id) WHERE expense_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS bank_review_queue ON bank_transactions(state,date);
        CREATE TRIGGER IF NOT EXISTS bank_expense_deleted BEFORE DELETE ON expenses BEGIN
            UPDATE bank_transactions SET expense_id=NULL,state='ignored',changed=0,version=version+1 WHERE expense_id=OLD.id;
        END;
    """)
