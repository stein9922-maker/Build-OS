from datetime import date
import unittest

from buildos.procurement import (
    net_purchase_quantity,
    outstanding_order_quantity,
    recommended_order_date,
    usable_stock,
)


class ProcurementCalculationTests(unittest.TestCase):
    def test_usable_stock_excludes_reserved(self):
        self.assertEqual(usable_stock(100, 25), 75)

    def test_usable_stock_never_negative(self):
        self.assertEqual(usable_stock(10, 15), 0)

    def test_net_purchase_accounts_for_stock_and_eligible_incoming(self):
        self.assertEqual(net_purchase_quantity(100, 30, 10, 20), 60)

    def test_net_purchase_never_negative(self):
        self.assertEqual(net_purchase_quantity(10, 20, 0, 5), 0)

    def test_only_active_incoming_orders_count(self):
        self.assertEqual(outstanding_order_quantity(100, 25, "Ordered"), 75)
        self.assertEqual(outstanding_order_quantity(100, 25, "Partially delivered"), 75)
        self.assertEqual(outstanding_order_quantity(100, 100, "Delivered"), 0)
        self.assertEqual(outstanding_order_quantity(100, 0, "Draft"), 0)
        self.assertEqual(outstanding_order_quantity(100, 0, "Cancelled"), 0)

    def test_recommended_order_date_subtracts_lead_and_buffer(self):
        self.assertEqual(
            recommended_order_date(date(2026, 11, 20), 7, 2),
            date(2026, 11, 11),
        )

    def test_negative_lead_time_is_rejected(self):
        with self.assertRaises(ValueError):
            recommended_order_date(date(2026, 11, 20), -1, 0)


if __name__ == "__main__":
    unittest.main()
