"""Attach an original to an existing deduction without inventing a second purchase."""
from migrations import execute_script


def upgrade(c):
    if 'evidence_receipt_id' not in {r[1] for r in c.execute('PRAGMA table_info(equipment_assets)')}:
        c.execute('ALTER TABLE equipment_assets ADD COLUMN evidence_receipt_id TEXT REFERENCES receipts(id) ON DELETE RESTRICT')
    execute_script(c, '''
    CREATE UNIQUE INDEX IF NOT EXISTS equipment_original ON equipment_assets(evidence_receipt_id) WHERE evidence_receipt_id IS NOT NULL;
    CREATE TRIGGER IF NOT EXISTS equipment_original_insert BEFORE INSERT ON equipment_assets
      WHEN NEW.evidence_receipt_id IS NOT NULL AND (
        NOT EXISTS(SELECT 1 FROM receipts WHERE id=NEW.evidence_receipt_id AND user_id=NEW.user_id)
        OR EXISTS(SELECT 1 FROM expenses WHERE receipt_id=NEW.evidence_receipt_id)
        OR EXISTS(SELECT 1 FROM employment_income WHERE receipt_id=NEW.evidence_receipt_id))
      BEGIN SELECT RAISE(ABORT,'Receipt is already filed or belongs to another person'); END;
    CREATE TRIGGER IF NOT EXISTS equipment_original_update BEFORE UPDATE OF evidence_receipt_id,user_id ON equipment_assets
      WHEN NEW.evidence_receipt_id IS NOT NULL AND (
        NOT EXISTS(SELECT 1 FROM receipts WHERE id=NEW.evidence_receipt_id AND user_id=NEW.user_id)
        OR EXISTS(SELECT 1 FROM expenses WHERE receipt_id=NEW.evidence_receipt_id)
        OR EXISTS(SELECT 1 FROM employment_income WHERE receipt_id=NEW.evidence_receipt_id))
      BEGIN SELECT RAISE(ABORT,'Receipt is already filed or belongs to another person'); END;
    CREATE TRIGGER IF NOT EXISTS expense_not_equipment_original_insert BEFORE INSERT ON expenses
      WHEN NEW.receipt_id IS NOT NULL AND EXISTS(SELECT 1 FROM equipment_assets WHERE evidence_receipt_id=NEW.receipt_id)
      BEGIN SELECT RAISE(ABORT,'Receipt is already attached to a deduction'); END;
    CREATE TRIGGER IF NOT EXISTS expense_not_equipment_original_update BEFORE UPDATE OF receipt_id ON expenses
      WHEN NEW.receipt_id IS NOT NULL AND EXISTS(SELECT 1 FROM equipment_assets WHERE evidence_receipt_id=NEW.receipt_id)
      BEGIN SELECT RAISE(ABORT,'Receipt is already attached to a deduction'); END;
    CREATE TRIGGER IF NOT EXISTS income_not_equipment_original_insert BEFORE INSERT ON employment_income
      WHEN NEW.receipt_id IS NOT NULL AND EXISTS(SELECT 1 FROM equipment_assets WHERE evidence_receipt_id=NEW.receipt_id)
      BEGIN SELECT RAISE(ABORT,'Receipt is already attached to a deduction'); END;
    CREATE TRIGGER IF NOT EXISTS income_not_equipment_original_update BEFORE UPDATE OF receipt_id ON employment_income
      WHEN NEW.receipt_id IS NOT NULL AND EXISTS(SELECT 1 FROM equipment_assets WHERE evidence_receipt_id=NEW.receipt_id)
      BEGIN SELECT RAISE(ABORT,'Receipt is already attached to a deduction'); END;
    ''')
