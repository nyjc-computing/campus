#!/usr/bin/env python3
"""Test query operators for storage filtering."""

import unittest
import dataclasses


class TestQueryOperators(unittest.TestCase):
    """Test query operator classes."""

    def test_operator_is_frozen_dataclass(self):
        """Operator instances should be immutable."""
        from campus.storage.query import gt

        op = gt(100)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            op.value = 200

    def test_gt_operator(self):
        """gt operator stores value correctly."""
        from campus.storage.query import gt, is_operator

        op = gt(100)
        self.assertEqual(op.value, 100)
        self.assertTrue(is_operator(op))

    def test_gte_operator(self):
        """gte operator stores value correctly."""
        from campus.storage.query import gte, is_operator

        op = gte("2024-01-01")
        self.assertEqual(op.value, "2024-01-01")
        self.assertTrue(is_operator(op))

    def test_lt_operator(self):
        """lt operator stores value correctly."""
        from campus.storage.query import lt, is_operator

        op = lt(5000)
        self.assertEqual(op.value, 5000)
        self.assertTrue(is_operator(op))

    def test_lte_operator(self):
        """lte operator stores value correctly."""
        from campus.storage.query import lte, is_operator

        op = lte(3)
        self.assertEqual(op.value, 3)
        self.assertTrue(is_operator(op))

    def test_is_operator_returns_true_for_operators(self):
        """is_operator returns True for all operator types."""
        from campus.storage.query import gt, gte, lt, lte, is_operator

        self.assertTrue(is_operator(gt(100)))
        self.assertTrue(is_operator(gte(100)))
        self.assertTrue(is_operator(lt(100)))
        self.assertTrue(is_operator(lte(100)))

    def test_is_operator_returns_false_for_non_operators(self):
        """is_operator returns False for regular values."""
        from campus.storage.query import is_operator

        self.assertFalse(is_operator(100))
        self.assertFalse(is_operator("string"))
        self.assertFalse(is_operator(None))
        self.assertFalse(is_operator({"key": "value"}))
        self.assertFalse(is_operator([1, 2, 3]))

    def test_operators_are_hashable(self):
        """Operators should be hashable for use in sets/dicts."""
        from campus.storage.query import gt

        op1 = gt(100)
        op2 = gt(100)
        op3 = gt(200)

        # Same values should be equal
        self.assertEqual(op1, op2)
        self.assertNotEqual(op1, op3)

        # Should be hashable
        op_set = {op1, op2, op3}
        self.assertEqual(len(op_set), 2)  # op1 and op2 are equal

    def test_operators_with_different_types(self):
        """Operators should work with various value types."""
        from campus.storage.query import gt, lt, gte, lte, is_operator
        from datetime import datetime

        # Integer
        self.assertTrue(is_operator(gt(100)))

        # Float
        self.assertTrue(is_operator(lt(3.14)))

        # String
        self.assertTrue(is_operator(gte("2024-01-01")))

        # DateTime
        dt = datetime(2024, 1, 1)
        self.assertTrue(is_operator(lte(dt)))

    def test_operator_type_checking(self):
        """Operator instances are identified by their type."""
        from campus.storage.query import gt, gte, lt, lte, is_operator, Operator

        gt_op = gt(100)
        gte_op = gte(100)
        lt_op = lt(100)
        lte_op = lte(100)

        # All are operators
        self.assertTrue(is_operator(gt_op))
        self.assertTrue(is_operator(gte_op))
        self.assertTrue(is_operator(lt_op))
        self.assertTrue(is_operator(lte_op))

        # Each is a different type
        self.assertIsInstance(gt_op, gt)
        self.assertIsInstance(gte_op, gte)
        self.assertIsInstance(lt_op, lt)
        self.assertIsInstance(lte_op, lte)

        # All inherit from Operator
        self.assertIsInstance(gt_op, Operator)
        self.assertIsInstance(gte_op, Operator)
        self.assertIsInstance(lt_op, Operator)
        self.assertIsInstance(lte_op, Operator)


if __name__ == "__main__":
    unittest.main()
