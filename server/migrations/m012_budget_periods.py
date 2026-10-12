from migrations import execute_script


def upgrade(connection):
    # Also safe when adopting an existing database without its migration ledger.
    if 'period' in {row[1] for row in connection.execute('PRAGMA table_info(category_budgets)')}:
        return
    sequence = connection.execute("SELECT seq FROM sqlite_sequence WHERE name='category_budgets'").fetchone()
    execute_script(connection, """
        CREATE TABLE category_budgets_new(
            id INTEGER PRIMARY KEY AUTOINCREMENT, month TEXT NOT NULL,
            period TEXT NOT NULL DEFAULT 'monthly' CHECK(period IN ('monthly','quarterly','yearly')),
            category TEXT NOT NULL, scope TEXT NOT NULL, amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
            version INTEGER NOT NULL DEFAULT 1, UNIQUE(month,period,category,scope));
        INSERT INTO category_budgets_new(id,month,category,scope,amount_cents,version)
            SELECT id,month,category,scope,amount_cents,version FROM category_budgets;
        DROP TABLE category_budgets;
        ALTER TABLE category_budgets_new RENAME TO category_budgets;
    """)
    if sequence:
        connection.execute("UPDATE sqlite_sequence SET seq=MAX(seq,?) WHERE name='category_budgets'", (sequence[0],))
