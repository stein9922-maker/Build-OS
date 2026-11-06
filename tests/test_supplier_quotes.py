import sqlite3
import unittest
from datetime import date

from tests.helpers import TempDatabaseTestCase


class SupplierQuoteTests(TempDatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.project = self.make_project("Quote project")
        self.activity = self.make_activity(self.project.id, "A1")
        with self.db.connect() as conn:
            self.material_id = conn.execute(
                "INSERT INTO materials(project_id,name,category,unit) VALUES(?,?,?,?)",
                (self.project.id, "Cement", "Concrete", "bag"),
            ).lastrowid
            self.supplier_id = conn.execute(
                "INSERT INTO suppliers(project_id,name) VALUES(?,?)",
                (self.project.id, "Supplier A"),
            ).lastrowid

    def test_quote_can_be_saved_and_read(self):
        with self.db.connect() as conn:
            conn.execute("""INSERT INTO supplier_quotes
                (project_id,material_id,supplier_id,unit_price,currency,quote_date,valid_until,notes)
                VALUES(?,?,?,?,?,?,?,?)""",
                (self.project.id, self.material_id, self.supplier_id, 399.50, "INR",
                 "2026-10-15", "2026-11-15", "test quote"))
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM supplier_quotes").fetchone()
        self.assertEqual(row["unit_price"], 399.50)
        self.assertEqual(row["currency"], "INR")
        self.assertEqual(row["notes"], "test quote")

    def test_negative_quote_price_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError), self.db.connect() as conn:
            conn.execute("""INSERT INTO supplier_quotes
                (project_id,material_id,supplier_id,unit_price,currency,quote_date,valid_until)
                VALUES(?,?,?,?,?,?,?)""",
                (self.project.id, self.material_id, self.supplier_id, -1, "INR",
                 "2026-10-15", "2026-11-15"))


if __name__ == "__main__":
    unittest.main()
