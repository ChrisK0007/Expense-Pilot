"""Migration history, existing-data adoption and failure atomicity."""
import importlib
import sqlite3
import unittest
from unittest.mock import patch
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
        c.execute("INSERT INTO login_sessions VALUES ('kept-session',1,'full',9999999999)")
        c.execute('DROP TABLE schema_migrations')  # 0.8.1 has no ledger.
        c.commit()
        apply(c)
        self.assertEqual(c.execute('SELECT amount_cents,work_percent,business_percent,receipt_id FROM expenses').fetchone(), (12345,30,20,'receipt'))
        self.assertEqual(c.execute('SELECT active,version FROM users WHERE id=2').fetchone(),(0,8))
        self.assertEqual(c.execute('SELECT active,version FROM users WHERE id=1').fetchone(),(1,3))
        self.assertEqual(c.execute('SELECT count(*) FROM login_sessions').fetchone()[0],1)
        ledger = c.execute('SELECT * FROM schema_migrations ORDER BY version').fetchall()
        self.assertEqual(len(ledger),6)
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
        self.assertEqual(c.execute('SELECT count(*) FROM schema_migrations').fetchone()[0],6)

    def test_modified_migration_is_rejected(self):
        apply(self.connection)
        self.connection.execute("UPDATE schema_migrations SET checksum='tampered' WHERE version='m001_core'")
        self.connection.commit()
        with self.assertRaisesRegex(RuntimeError,'modified'):
            apply(self.connection)
        self.assertFalse(self.connection.in_transaction)

    def test_future_database_is_rejected(self):
        apply(self.connection)
        self.connection.execute("INSERT INTO schema_migrations(version,checksum) VALUES ('m999_future','future')")
        self.connection.commit()
        with self.assertRaisesRegex(RuntimeError,'newer migrations'):
            apply(self.connection)
