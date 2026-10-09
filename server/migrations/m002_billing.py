from migrations import execute_script

def upgrade(connection):
    execute_script(connection, """
        CREATE TABLE IF NOT EXISTS billing_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS billing_counters(kind TEXT PRIMARY KEY,next_number INTEGER NOT NULL);
        INSERT OR IGNORE INTO billing_counters VALUES ('invoice',1),('quote',1);
        CREATE TABLE IF NOT EXISTS billing_clients(id INTEGER PRIMARY KEY,name TEXT NOT NULL,contact TEXT NOT NULL DEFAULT '',email TEXT NOT NULL DEFAULT '',address TEXT NOT NULL DEFAULT '',abn TEXT NOT NULL DEFAULT '',terms INTEGER NOT NULL DEFAULT 14,notes TEXT NOT NULL DEFAULT '',archived INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS billing_services(id INTEGER PRIMARY KEY,description TEXT NOT NULL,unit_cents INTEGER NOT NULL,tax TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS billing_schedules(id INTEGER PRIMARY KEY,client_id INTEGER NOT NULL REFERENCES billing_clients(id),template TEXT NOT NULL,interval TEXT NOT NULL,next_date TEXT NOT NULL,anchor_day INTEGER NOT NULL,end_date TEXT,terms INTEGER NOT NULL,active INTEGER NOT NULL DEFAULT 1,last_error TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS billing_documents(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,number TEXT NOT NULL UNIQUE,state TEXT NOT NULL DEFAULT 'draft',version INTEGER NOT NULL DEFAULT 1,client_id INTEGER NOT NULL REFERENCES billing_clients(id),client TEXT NOT NULL,business TEXT NOT NULL,issue_date TEXT NOT NULL,due_date TEXT NOT NULL,tax_mode TEXT NOT NULL,lines TEXT NOT NULL,subtotal_cents INTEGER NOT NULL,gst_cents INTEGER NOT NULL,total_cents INTEGER NOT NULL,reference TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',payment_details TEXT NOT NULL DEFAULT '',shared INTEGER NOT NULL DEFAULT 0,source_quote INTEGER UNIQUE REFERENCES billing_documents(id),schedule_id INTEGER REFERENCES billing_schedules(id),occurrence TEXT,created_at TEXT NOT NULL,UNIQUE(schedule_id,occurrence));
        CREATE TABLE IF NOT EXISTS billing_wording_history(id INTEGER PRIMARY KEY,document_id INTEGER NOT NULL REFERENCES billing_documents(id) ON DELETE CASCADE,version INTEGER NOT NULL,user_id INTEGER NOT NULL REFERENCES users(id),previous TEXT NOT NULL,changed_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS billing_payments(id INTEGER PRIMARY KEY,document_id INTEGER NOT NULL REFERENCES billing_documents(id),date TEXT NOT NULL,amount_cents INTEGER NOT NULL CHECK(amount_cents>0),reference TEXT NOT NULL,request_key TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL,reversed_at TEXT,reversal_reason TEXT);
        CREATE TABLE IF NOT EXISTS billing_outbox(id INTEGER PRIMARY KEY,document_id INTEGER NOT NULL REFERENCES billing_documents(id),recipient TEXT NOT NULL,subject TEXT NOT NULL,body TEXT NOT NULL,state TEXT NOT NULL,request_key TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL,error TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS billing_time(id INTEGER PRIMARY KEY,client_id INTEGER NOT NULL REFERENCES billing_clients(id),date TEXT NOT NULL,description TEXT NOT NULL,hours TEXT NOT NULL,rate_cents INTEGER NOT NULL,billable INTEGER NOT NULL DEFAULT 1,document_id INTEGER REFERENCES billing_documents(id));
        CREATE INDEX IF NOT EXISTS billing_payment_document ON billing_payments(document_id);
        CREATE INDEX IF NOT EXISTS billing_outbox_document ON billing_outbox(document_id);
        CREATE INDEX IF NOT EXISTS billing_due_schedule ON billing_schedules(active,next_date);
        """)
