"""Link reviewed payslips to income and preserve explicit cash choices."""
from migrations import execute_script


def upgrade(connection):
    for table, definitions in {
        'employment_income': [('receipt_id','TEXT REFERENCES receipts(id)'),('record_kind',"TEXT NOT NULL DEFAULT 'manual'"),('period_start',"TEXT NOT NULL DEFAULT ''"),('period_end',"TEXT NOT NULL DEFAULT ''"),('version','INTEGER NOT NULL DEFAULT 1')],
        'expenses': [('bank_match_excluded','INTEGER NOT NULL DEFAULT 0')],
    }.items():
        existing={row[1] for row in connection.execute('PRAGMA table_info('+table+')')}
        for name,definition in definitions:
            if name not in existing: connection.execute('ALTER TABLE '+table+' ADD COLUMN '+name+' '+definition)
    execute_script(connection, """
    CREATE UNIQUE INDEX IF NOT EXISTS employment_income_source ON employment_income(receipt_id) WHERE receipt_id IS NOT NULL;
    CREATE TRIGGER IF NOT EXISTS income_document_not_expense BEFORE INSERT ON employment_income
      WHEN NEW.receipt_id IS NOT NULL AND EXISTS(SELECT 1 FROM expenses WHERE receipt_id=NEW.receipt_id)
      BEGIN SELECT RAISE(ABORT,'Document is already an expense'); END;
    CREATE TRIGGER IF NOT EXISTS income_document_update_not_expense BEFORE UPDATE OF receipt_id ON employment_income
      WHEN NEW.receipt_id IS NOT NULL AND EXISTS(SELECT 1 FROM expenses WHERE receipt_id=NEW.receipt_id)
      BEGIN SELECT RAISE(ABORT,'Document is already an expense'); END;
    CREATE TRIGGER IF NOT EXISTS expense_document_not_income BEFORE INSERT ON expenses
      WHEN NEW.receipt_id IS NOT NULL AND EXISTS(SELECT 1 FROM employment_income WHERE receipt_id=NEW.receipt_id)
      BEGIN SELECT RAISE(ABORT,'Document is already employment income'); END;
    CREATE TRIGGER IF NOT EXISTS expense_document_update_not_income BEFORE UPDATE OF receipt_id ON expenses
      WHEN NEW.receipt_id IS NOT NULL AND EXISTS(SELECT 1 FROM employment_income WHERE receipt_id=NEW.receipt_id)
      BEGIN SELECT RAISE(ABORT,'Document is already employment income'); END;
    """)
