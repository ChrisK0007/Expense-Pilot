"""Stable category labels, annual tax choices and retained depreciation imports."""
from migrations import execute_script


def upgrade(c):
    if 'import_json' not in {r[1] for r in c.execute('PRAGMA table_info(equipment_assets)')}:
        c.execute("ALTER TABLE equipment_assets ADD COLUMN import_json TEXT NOT NULL DEFAULT '{}'")
    execute_script(c, '''
    CREATE TABLE IF NOT EXISTS category_labels(category TEXT PRIMARY KEY, label TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS equipment_tax_profiles(user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      year INTEGER NOT NULL, data TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(user_id,year));
    CREATE TABLE IF NOT EXISTS equipment_imports(id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      document_id TEXT NOT NULL REFERENCES tax_documents(id) ON DELETE RESTRICT,
      status TEXT NOT NULL DEFAULT 'saved', data TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
      version INTEGER NOT NULL DEFAULT 1, UNIQUE(user_id,document_id));
    CREATE TABLE IF NOT EXISTS equipment_import_rows(import_id TEXT NOT NULL REFERENCES equipment_imports(id) ON DELETE CASCADE,
      row_key TEXT NOT NULL, asset_id INTEGER REFERENCES equipment_assets(id) ON DELETE SET NULL, PRIMARY KEY(import_id,row_key));
    ''')
