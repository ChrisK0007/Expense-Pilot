"""Migration history, existing-data adoption and failure atomicity."""
import importlib
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
import migrations
from migrations import apply, execute_script


class MigrationTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(':memory:')
        self.connection.execute('PRAGMA foreign_keys=ON')
        self.addCleanup(self.connection.close)

    def test_existing_database_adoption_preserves_values_and_retires_employee(self):
        c = self.connection
        apply(c)
        c.execute("INSERT INTO users(id,name,email,password,role,version) VALUES (1,'Owner','owner@test','hash','owner',3),(2,'Legacy','old@test','hash','employee',7)")
        c.execute("INSERT INTO receipts VALUES ('receipt',2,'kept.png','image/png')")
        c.execute("INSERT INTO expenses(user_id,date,merchant,amount_cents,scope,category,percent,work_percent,business_percent,receipt_id) VALUES (2,'2026-01-01','Kept',12345,'split','Other',50,30,20,'receipt')")
        c.execute("INSERT INTO login_sessions(token_hash,user_id,kind,expires) VALUES ('kept-session',1,'full',9999999999)")
        c.execute('DROP TABLE schema_migrations')  # 0.8.1 has no ledger.
        c.commit()
        apply(c)
        self.assertEqual(c.execute('SELECT amount_cents,work_percent,business_percent,receipt_id FROM expenses').fetchone(), (12345,30,20,'receipt'))
        self.assertEqual(c.execute('SELECT active,version FROM users WHERE id=2').fetchone(),(0,8))
        self.assertEqual(c.execute('SELECT active,version FROM users WHERE id=1').fetchone(),(1,3))
        self.assertEqual(c.execute('SELECT count(*) FROM login_sessions').fetchone()[0],1)
        ledger = c.execute('SELECT * FROM schema_migrations ORDER BY version').fetchall()
        self.assertEqual(len(ledger),21)
        apply(c)
        self.assertEqual(c.execute('SELECT * FROM schema_migrations ORDER BY version').fetchall(),ledger)
        self.assertEqual(c.execute('SELECT version FROM users WHERE id=2').fetchone()[0],8)
        self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_failed_migration_rolls_back_schema_data_and_ledger_then_retries(self):
        module = importlib.import_module('migrations.m002_billing')
        def broken(c):
            execute_script(c, "CREATE TABLE partial(id INTEGER); INSERT INTO partial VALUES (1);")
            c.execute("INSERT INTO accounts(name,bank) VALUES ('Should roll back','Test')")
            raise RuntimeError('simulated failure')
        with patch.object(module, 'upgrade', broken):
            with self.assertRaisesRegex(RuntimeError,'simulated failure'):
                apply(self.connection)
        c = self.connection
        self.assertIsNone(c.execute("SELECT name FROM sqlite_master WHERE name='partial'").fetchone())
        self.assertEqual(c.execute('SELECT count(*) FROM accounts').fetchone()[0],0)
        self.assertEqual(c.execute('SELECT version FROM schema_migrations').fetchall(), [('m001_core',)])
        self.assertFalse(c.in_transaction)
        apply(c)
        self.assertEqual(c.execute('SELECT count(*) FROM schema_migrations').fetchone()[0],21)

    def test_stable_100_upgrade_preserves_records_and_starts_disconnected(self):
        c = self.connection
        stable_files = sorted(p for p in Path(migrations.__file__).parent.glob('m[0-9][0-9][0-9]_*.py')
                              if p.name < 'm008_')
        with patch('migrations.Path.glob', return_value=stable_files):
            apply(c)
        self.assertEqual(c.execute('SELECT count(*) FROM schema_migrations').fetchone()[0],7)
        c.execute("INSERT INTO users(id,name,email,password,role) VALUES (1,'Owner','owner@test','hash','owner')")
        c.execute("INSERT INTO receipts VALUES ('kept-receipt',1,'kept.png','image/png')")
        c.execute("INSERT INTO expenses(user_id,date,merchant,amount_cents,scope,category,percent,work_percent,business_percent,receipt_id) VALUES (1,'2026-10-08','Kept expense',17999,'split','Other',80,30,50,'kept-receipt')")
        c.execute("INSERT INTO billing_clients(id,name,email) VALUES (1,'Kept client','client@example.test')")
        c.execute("INSERT INTO billing_documents(kind,number,client_id,client,business,issue_date,due_date,tax_mode,lines,subtotal_cents,gst_cents,total_cents,created_at,reminders_enabled) VALUES ('invoice','INV-0042',1,'{}','{}','2026-10-08','2026-10-22','none','[]',4500,0,4500,'2026-10-08',0)")
        c.execute("INSERT INTO billing_settings VALUES ('custom-setting','keep this value')")
        c.commit()
        tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        columns = {table:','.join('"'+r[1]+'"' for r in c.execute('PRAGMA table_info("'+table+'")')) for table in tables}
        before = {table:c.execute('SELECT '+columns[table]+' FROM "'+table+'"').fetchall() for table in tables}
        apply(c)
        for table, records in before.items():
            with self.subTest(table=table):
                current = c.execute('SELECT '+columns[table]+' FROM "'+table+'"').fetchall()
                self.assertEqual(current[:len(records)] if table=='schema_migrations' else current,records)
        self.assertEqual(c.execute('SELECT count(*) FROM schema_migrations').fetchone()[0],21)
        self.assertEqual(c.execute('SELECT key_encrypted,auto_sync FROM pocketsmith_connection').fetchone(),('',0))
        self.assertEqual(c.execute('SELECT count(*) FROM bank_transactions').fetchone()[0],0)
        self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
        apply(c)
        self.assertEqual(c.execute('SELECT count(*) FROM schema_migrations').fetchone()[0],21)

    def test_modified_migration_is_rejected(self):
        apply(self.connection)
        self.connection.execute("UPDATE schema_migrations SET checksum='tampered' WHERE version='m001_core'")
        self.connection.commit()
        with self.assertRaisesRegex(RuntimeError,'modified'):
            apply(self.connection)
        self.assertFalse(self.connection.in_transaction)

    def test_budget_duration_upgrade_preserves_ids_amounts_versions_and_sequence(self):
        c = self.connection
        old_files = sorted(p for p in Path(migrations.__file__).parent.glob('m[0-9][0-9][0-9]_*.py') if p.name < 'm012_')
        with patch('migrations.Path.glob', return_value=old_files):
            apply(c)
        c.execute("INSERT INTO category_budgets(id,month,category,scope,amount_cents,version) VALUES (42,'2026-10','Other','all',120000,7),(99,'2026-11','Other','all',100,1)")
        c.execute('DELETE FROM category_budgets WHERE id=99')
        c.commit()
        apply(c)
        self.assertEqual(c.execute('SELECT id,month,category,scope,amount_cents,version,period FROM category_budgets').fetchall(),[(42,'2026-10','Other','all',120000,7,'monthly')])
        new_id=c.execute("INSERT INTO category_budgets(month,period,category,scope,amount_cents) VALUES ('2026-10','yearly','Other','all',120000)").lastrowid
        self.assertGreater(new_id,99)
        c.commit()
        apply(c)
        self.assertEqual(c.execute('SELECT count(*) FROM category_budgets').fetchone()[0],2)

    def test_future_database_is_rejected(self):
        apply(self.connection)
        self.connection.execute("INSERT INTO schema_migrations(version,checksum) VALUES ('m999_future','future')")
        self.connection.commit()
        with self.assertRaisesRegex(RuntimeError,'newer migrations'):
            apply(self.connection)

    def test_home_office_upgrade_preserves_existing_rows_and_settings(self):
        c=self.connection
        previous=sorted(p for p in Path(migrations.__file__).parent.glob('m[0-9][0-9][0-9]_*.py') if p.name<'m020_')
        with patch('migrations.Path.glob',return_value=previous): apply(c)
        self.assertEqual(c.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0],19)
        c.execute("INSERT INTO users(id,name,email,password,role) VALUES (1,'Owner','owner@test','hash','owner')")
        c.execute("INSERT INTO receipts VALUES ('receipt',1,'kept.png','image/png')")
        c.execute("INSERT INTO expenses(user_id,date,merchant,amount_cents,scope,category,percent,work_percent,business_percent,receipt_id) VALUES (1,'2026-10-08','Kept expense',17999,'split','Other',80,30,50,'receipt')")
        c.execute("INSERT INTO login_sessions(token_hash,user_id,kind,expires) VALUES ('session',1,'full',9999999999)")
        c.execute("INSERT INTO billing_settings VALUES ('custom-setting','keep this value')")
        c.commit()
        tables=[r[0] for r in c.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        before={t:c.execute('SELECT * FROM "'+t+'" ORDER BY rowid').fetchall() for t in tables}
        apply(c)
        for table,records in before.items():
            after=c.execute('SELECT * FROM "'+table+'" ORDER BY rowid').fetchall()
            self.assertEqual(after[:len(records)] if table=='schema_migrations' else after,records,table)
        self.assertEqual(c.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0],21)
        self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
        apply(c)
        self.assertEqual(c.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0],21)

    def test_document_upgrade_preserves_all_beta_four_records(self):
        c=self.connection
        previous=sorted(p for p in Path(migrations.__file__).parent.glob('m[0-9][0-9][0-9]_*.py') if p.name<'m021_')
        with patch('migrations.Path.glob',return_value=previous): apply(c)
        c.execute("INSERT INTO users(id,name,email,password,role) VALUES (1,'Owner','owner@test','hash','owner')")
        c.execute("INSERT INTO home_office_settings(user_id,year,data,version) VALUES (1,2026,'{\"method\":\"fixed\"}',3)")
        c.execute("INSERT INTO expenses(user_id,date,merchant,amount_cents,scope,category) VALUES (1,'2026-10-08','Kept',10000,'work','Other')")
        c.commit()
        tables=[r[0] for r in c.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        before={t:c.execute('SELECT * FROM "'+t+'" ORDER BY rowid').fetchall() for t in tables}
        apply(c)
        for table,records in before.items():
            current=c.execute('SELECT * FROM "'+table+'" ORDER BY rowid').fetchall()
            self.assertEqual(current[:len(records)] if table=='schema_migrations' else current,records)
        self.assertEqual(c.execute('SELECT count(*) FROM tax_documents').fetchone()[0],0)
        apply(c)
        self.assertEqual(c.execute('SELECT count(*) FROM schema_migrations').fetchone()[0],21)
