from migrations import execute_script

def upgrade(connection):
    execute_script(connection, """
      CREATE TABLE IF NOT EXISTS employment_income(id INTEGER PRIMARY KEY,date TEXT NOT NULL,employer TEXT NOT NULL,gross_cents INTEGER NOT NULL,withheld_cents INTEGER NOT NULL,notes TEXT NOT NULL DEFAULT '');
      CREATE TABLE IF NOT EXISTS tax_settings(year INTEGER PRIMARY KEY,settings TEXT NOT NULL);
    """)
