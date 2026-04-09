import unittest
from unittest.mock import MagicMock

from banklite import PaymentProcessor, Transaction


def _tx(amount: float, tx_id: str = "t") -> Transaction:
    return Transaction(tx_id=tx_id, user_id=1, amount=amount)


class TestPaymentProcessor(unittest.TestCase):
    def setUp(self):
        self.gateway = MagicMock()
        self.audit = MagicMock()
        self.proc = PaymentProcessor(self.gateway, self.audit)

    def test_process_returns_success_when_gateway_charges(self):
        self.gateway.charge.return_value = True
        self.assertEqual(self.proc.process(_tx(50)), "success")

    def test_process_returns_declined_when_gateway_rejects(self):
        self.gateway.charge.return_value = False
        self.assertEqual(self.proc.process(_tx(50)), "declined")

    def test_process_raises_on_zero_amount(self):
        with self.assertRaises(ValueError):
            self.proc.process(_tx(0.0))
        self.gateway.charge.assert_not_called()
        self.audit.record.assert_not_called()

    def test_process_raises_on_negative_amount(self):
        with self.assertRaises(ValueError):
            self.proc.process(_tx(-0.01))
        self.gateway.charge.assert_not_called()
        self.audit.record.assert_not_called()

    def test_process_raises_when_amount_exceeds_limit(self):
        with self.assertRaises(ValueError):
            self.proc.process(_tx(10_000.01))
        self.gateway.charge.assert_not_called()
        self.audit.record.assert_not_called()

    def test_process_accepts_amount_at_max_limit(self):
        self.gateway.charge.return_value = True
        tx = _tx(10_000.00, "max")
        self.assertEqual(self.proc.process(tx), "success")
        self.gateway.charge.assert_called_once_with(tx)

    def test_audit_records_charged_event_on_success(self):
        self.gateway.charge.return_value = True
        tx = _tx(99.5, "a")
        self.proc.process(tx)
        self.audit.record.assert_called_once_with(
            "CHARGED", tx.tx_id, {"amount": tx.amount}
        )

    def test_audit_records_declined_event_on_failure(self):
        self.gateway.charge.return_value = False
        tx = _tx(12, "b")
        self.proc.process(tx)
        self.audit.record.assert_called_once_with(
            "DECLINED", tx.tx_id, {"amount": tx.amount}
        )


if __name__ == "__main__":
    unittest.main()
