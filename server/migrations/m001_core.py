from migrations import execute_script

def upgrade(connection):
    execute_script(connection, """

    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('owner','employee','tax_agent')),active INTEGER NOT NULL DEFAULT 1,version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY,name TEXT NOT NULL,bank TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS trips(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),scope TEXT NOT NULL,location TEXT NOT NULL,start TEXT NOT NULL,end TEXT NOT NULL,purpose TEXT NOT NULL,allowance_cents INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),filename TEXT NOT NULL,mime TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),date TEXT NOT NULL,merchant TEXT NOT NULL,amount_cents INTEGER NOT NULL,scope TEXT NOT NULL,category TEXT NOT NULL,percent INTEGER NOT NULL DEFAULT 100,reimbursed INTEGER NOT NULL DEFAULT 0,notes TEXT NOT NULL DEFAULT '',trip_id INTEGER REFERENCES trips(id),meal TEXT NOT NULL DEFAULT '',receipt_id TEXT REFERENCES receipts(id),account_id INTEGER REFERENCES accounts(id),status TEXT NOT NULL DEFAULT 'review',shared INTEGER NOT NULL DEFAULT 0,import_key TEXT UNIQUE);
    CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,user_id INTEGER,action TEXT,entity TEXT);
    CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY,count INTEGER,until REAL);
    CREATE TABLE IF NOT EXISTS receipt_details(receipt_id TEXT PRIMARY KEY REFERENCES receipts(id) ON DELETE CASCADE,uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,fingerprint TEXT NOT NULL DEFAULT '',extraction TEXT NOT NULL DEFAULT '{}',scan_status TEXT NOT NULL DEFAULT 'captured',scan_error TEXT NOT NULL DEFAULT '');
    """)
    if "permission" not in {r[1] for r in connection.execute("PRAGMA table_info(users)")}:
        connection.execute("ALTER TABLE users ADD COLUMN permission TEXT NOT NULL DEFAULT 'read_only'")
    columns = {r[1] for r in connection.execute('PRAGMA table_info(expenses)')}
    for name in ('work_percent', 'business_percent'):
        if name not in columns:
            connection.execute(f'ALTER TABLE expenses ADD COLUMN {name} INTEGER')
    connection.execute("UPDATE expenses SET work_percent=CASE WHEN scope='work' THEN percent ELSE 0 END,business_percent=CASE WHEN scope='business' THEN percent ELSE 0 END WHERE work_percent IS NULL OR business_percent IS NULL")
