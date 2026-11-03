"""Scoped adviser access and reproducible equipment schedules; no legacy sharing inferred."""
from migrations import execute_script


def upgrade(c):
    for table, columns in {
        'equipment_assets': [('calculation_json', "TEXT NOT NULL DEFAULT '{}'" )],
        'equipment_depreciation': [('work_percent', 'INTEGER'), ('business_percent', 'INTEGER'), ('claimable_cents', 'INTEGER')],
    }.items():
        existing={r[1] for r in c.execute('PRAGMA table_info('+table+')')}
        for name,definition in columns:
            if name not in existing: c.execute('ALTER TABLE '+table+' ADD COLUMN '+name+' '+definition)
    execute_script(c, '''
    CREATE TABLE IF NOT EXISTS adviser_years(agent_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      year INTEGER NOT NULL, PRIMARY KEY(agent_id,year));
    CREATE TABLE IF NOT EXISTS adviser_documents(agent_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      document_id TEXT NOT NULL REFERENCES tax_documents(id) ON DELETE CASCADE, PRIMARY KEY(agent_id,document_id));
    CREATE TABLE IF NOT EXISTS equipment_usage(asset_id INTEGER NOT NULL REFERENCES equipment_assets(id) ON DELETE CASCADE,
      year INTEGER NOT NULL, work_percent INTEGER NOT NULL, business_percent INTEGER NOT NULL, notes TEXT NOT NULL,
      PRIMARY KEY(asset_id,year));
    ''')

    c.execute('UPDATE equipment_depreciation SET work_percent=(SELECT work_percent FROM equipment_assets WHERE id=asset_id),business_percent=(SELECT business_percent FROM equipment_assets WHERE id=asset_id) WHERE work_percent IS NULL OR business_percent IS NULL')
    # Keep billing revision evidence when removing the login that authored it.
    if 'author_name' not in {r[1] for r in c.execute('PRAGMA table_info(billing_wording_history)')}:
        execute_script(c, """
        CREATE TABLE billing_wording_history_new(id INTEGER PRIMARY KEY,document_id INTEGER NOT NULL REFERENCES billing_documents(id) ON DELETE CASCADE,
          version INTEGER NOT NULL,user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,previous TEXT NOT NULL,changed_at TEXT NOT NULL,
          author_name TEXT NOT NULL DEFAULT '');
        INSERT INTO billing_wording_history_new SELECT h.*,COALESCE(u.name,'Former account') FROM billing_wording_history h LEFT JOIN users u ON u.id=h.user_id;
        DROP TABLE billing_wording_history;
        ALTER TABLE billing_wording_history_new RENAME TO billing_wording_history;
        """)
