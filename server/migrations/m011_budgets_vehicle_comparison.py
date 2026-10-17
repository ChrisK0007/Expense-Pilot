from migrations import execute_script


def upgrade(connection):
    execute_script(connection, """
        CREATE TABLE IF NOT EXISTS category_budgets(
            id INTEGER PRIMARY KEY AUTOINCREMENT, month TEXT NOT NULL,
            category TEXT NOT NULL, scope TEXT NOT NULL, amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
            version INTEGER NOT NULL DEFAULT 1, UNIQUE(month,category,scope));
        CREATE TABLE IF NOT EXISTS vehicle_comparison_settings(
            vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
            year INTEGER NOT NULL, work_percent INTEGER NOT NULL DEFAULT 0,
            business_percent INTEGER NOT NULL DEFAULT 0, depreciation_cents INTEGER NOT NULL DEFAULT 0,
            logbook_start TEXT NOT NULL DEFAULT '', logbook_end TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY(vehicle_id,year));
        CREATE TABLE IF NOT EXISTS vehicle_cost_details(
            expense_id INTEGER PRIMARY KEY REFERENCES expenses(id) ON DELETE CASCADE,
            kind TEXT NOT NULL DEFAULT 'running', included INTEGER NOT NULL DEFAULT 1,
            gst_credit_cents INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1);
    """)
