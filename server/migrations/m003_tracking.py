from migrations import execute_script

def upgrade(connection):
    execute_script(connection, """
        CREATE TABLE IF NOT EXISTS custom_categories(name TEXT PRIMARY KEY COLLATE NOCASE);
        CREATE TABLE IF NOT EXISTS receipt_preferences(user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS receipt_drafts(receipt_id TEXT PRIMARY KEY REFERENCES receipts(id) ON DELETE CASCADE,data TEXT NOT NULL,saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS vehicles(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),name TEXT NOT NULL,registration TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS vehicle_journeys(id INTEGER PRIMARY KEY,vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),date TEXT NOT NULL,origin TEXT NOT NULL,destination TEXT NOT NULL,purpose TEXT NOT NULL,scope TEXT NOT NULL,odometer_start INTEGER,odometer_end INTEGER,distance_m INTEGER NOT NULL,percent INTEGER NOT NULL DEFAULT 100);
        """)
    if "vehicle_id" not in {r[1] for r in connection.execute("PRAGMA table_info(expenses)")}:
        connection.execute("ALTER TABLE expenses ADD COLUMN vehicle_id INTEGER REFERENCES vehicles(id)")
