import unittest
from unittest.mock import MagicMock, patch
from banklite import *

## Below are just the commands that need to be run to tst the code.

## Task 1: PaymentProcessor : python -m pytest test_banklite.py::TestPaymentProcessor -v
## Task 2: python -m pytest test_banklite.py::TestFraudAwareProcessor -v


class TestPaymentProcessor(unittest.TestCase):
    def setUp(self):
        self.gateway = MagicMock()
        self.audit = MagicMock()
        self.proc = PaymentProcessor(self.gateway, self.audit)

    def _make_tx(self, amount=100.00, tx_id="TX-001", user_id=1):
        """Helper: build a Transaction. Keeps test setup DRY.

        Default values mean each test only specifies what it cares about."""
        return Transaction(tx_id=tx_id, user_id=user_id, amount=amount)

    def test_process_returns_success_when_gateway_charges(self):
        self.gateway.charge.return_value = True
        self.assertEqual(self.proc.process(self._make_tx(amount=50)), "success")

    def test_process_returns_declined_when_gateway_rejects(self):
        self.gateway.charge.return_value = False
        self.assertEqual(self.proc.process(self._make_tx(amount=50)), "declined")

    def test_process_raises_on_zero_amount(self):
        with self.assertRaises(ValueError):
            self.proc.process(self._make_tx(amount=0.0))
        self.gateway.charge.assert_not_called()
        self.audit.record.assert_not_called()

    def test_process_raises_on_negative_amount(self):
        with self.assertRaises(ValueError):
            self.proc.process(self._make_tx(amount=-0.01))
        self.gateway.charge.assert_not_called()
        self.audit.record.assert_not_called()

    def test_process_raises_when_amount_exceeds_limit(self):
        with self.assertRaises(ValueError):
            self.proc.process(self._make_tx(amount=10_000.01))
        self.gateway.charge.assert_not_called()
        self.audit.record.assert_not_called()

    def test_process_accepts_amount_at_max_limit(self):
        self.gateway.charge.return_value = True
        tx = self._make_tx(amount=10_000.00, tx_id="max")
        self.assertEqual(self.proc.process(tx), "success")
        self.gateway.charge.assert_called_once_with(tx)

    def test_audit_records_charged_event_on_success(self):
        self.gateway.charge.return_value = True
        tx = self._make_tx(amount=99.5, tx_id="a")
        self.proc.process(tx)
        self.audit.record.assert_called_once_with(
            "CHARGED", tx.tx_id, {"amount": tx.amount}
        )

    def test_audit_records_declined_event_on_failure(self):
        self.gateway.charge.return_value = False
        tx = self._make_tx(amount=12, tx_id="b")
        self.proc.process(tx)
        self.audit.record.assert_called_once_with(
            "DECLINED", tx.tx_id, {"amount": tx.amount}
        )



## Task 2: FraudAwareProcessor : python -m pytest test_banklite.py::TestFraudAwareProcessor -v

class TestFraudAwareProcessor(unittest.TestCase):
    def setUp(self):
        self.gateway = MagicMock()
        self.detector = MagicMock()
        self.mailer = MagicMock()
        self.audit = MagicMock()
        self.proc = FraudAwareProcessor(
            gateway=self.gateway,
            detector=self.detector,
            mailer=self.mailer,
            audit=self.audit,
        )

    def _make_tx(self, amount=100.00, tx_id="TX-001", user_id=1):
        """Helper: build a Transaction. Keeps test setup DRY.

        Default values mean each test only specifies what it cares about."""
        return Transaction(tx_id=tx_id, user_id=user_id, amount=amount)

    def _safe_result(self, risk_score: float = 0.1) -> FraudCheckResult:
        return FraudCheckResult(approved=True, risk_score=risk_score)

    def _fraud_result(self, risk_score: float = 0.9) -> FraudCheckResult:
        return FraudCheckResult(approved=False, risk_score=risk_score, reason="x")

    def test_high_risk_returns_blocked(self):
        self.detector.check.return_value = self._fraud_result(0.9)
        self.assertEqual(self.proc.process(self._make_tx(amount=50)), "blocked")

    def test_high_risk_does_not_charge_the_card(self):
        self.detector.check.return_value = self._fraud_result(0.9)
        self.proc.process(self._make_tx(amount=50))
        self.gateway.charge.assert_not_called()

    def test_exactly_at_threshold_is_treated_as_fraud(self):
        self.detector.check.return_value = self._fraud_result(0.75)
        self.assertEqual(self.proc.process(self._make_tx(amount=10)), "blocked")
        self.gateway.charge.assert_not_called()

    def test_just_below_threshold_is_not_blocked(self):
        self.detector.check.return_value = self._safe_result(0.74)
        self.gateway.charge.return_value = True
        self.assertEqual(self.proc.process(self._make_tx(amount=20)), "success")
        self.gateway.charge.assert_called_once()

    def test_fraud_alert_email_sent_with_correct_args(self):
        tx = self._make_tx(amount=30, tx_id="tid-99", user_id=7)
        self.detector.check.return_value = self._fraud_result(0.9)
        self.proc.process(tx)
        self.mailer.send_fraud_alert.assert_called_once_with(7, "tid-99")

    def test_fraud_audit_records_blocked_event(self):
        tx = self._make_tx(amount=40, tx_id="tid-a")
        self.detector.check.return_value = FraudCheckResult(
            approved=False, risk_score=0.88, reason="Suspicious pattern"
        )
        self.proc.process(tx)
        self.audit.record.assert_called_once_with(
            "BLOCKED", "tid-a", {"risk": 0.88}
        )

    def test_low_risk_successful_charge_returns_success(self):
        self.detector.check.return_value = self._safe_result(0.1)
        self.gateway.charge.return_value = True
        self.assertEqual(self.proc.process(self._make_tx(amount=50)), "success")

    def test_receipt_email_sent_on_successful_charge(self):
        tx = self._make_tx(amount=60, tx_id="rcpt-1", user_id=3)
        self.detector.check.return_value = self._safe_result(0.1)
        self.gateway.charge.return_value = True
        self.proc.process(tx)
        self.mailer.send_receipt.assert_called_once_with(3, "rcpt-1", 60)

    def test_fraud_alert_not_sent_on_successful_charge(self):
        self.detector.check.return_value = self._safe_result(0.1)
        self.gateway.charge.return_value = True
        self.proc.process(self._make_tx(amount=50))
        self.mailer.send_fraud_alert.assert_not_called()

    def test_low_risk_declined_charge_returns_declined(self):
        self.detector.check.return_value = self._safe_result(0.2)
        self.gateway.charge.return_value = False
        self.assertEqual(self.proc.process(self._make_tx(amount=50)), "declined")

    def test_receipt_not_sent_on_declined_charge(self):
        self.detector.check.return_value = self._safe_result(0.2)
        self.gateway.charge.return_value = False
        self.proc.process(self._make_tx(amount=50))
        self.mailer.send_receipt.assert_not_called()

    def test_fraud_detector_connection_error_propagates(self):
        self.detector.check.side_effect = ConnectionError("API down")
        tx = self._make_tx(amount=50)
        with self.assertRaises(ConnectionError):
            self.proc.process(tx)
        self.gateway.charge.assert_not_called()


## Task 3: StatementBuilder : python -m pytest test_banklite.py::TestStatementBuilder -v

class TestStatementBuilder(unittest.TestCase):
    def setUp(self):
        self.repo = MagicMock()
        self.builder = StatementBuilder(self.repo)

    def _make_tx(self, amount=100.00, tx_id="TX-001", user_id=1, status="success"):
        """Helper: build a Transaction. Keeps test setup DRY.

        Default values mean each test only specifies what it cares about."""
        return Transaction(tx_id=tx_id, user_id=user_id, amount=amount, status=status)

    def test_build_empty_user_has_zero_count_and_total(self):
        self.repo.find_by_user.return_value = []
        result = self.builder.build(user_id=1)
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["total_charged"], 0.0)

    def test_build_only_success_transactions_sum_total(self):
        txs = [
            self._make_tx(100.00, "TX-A", 1),
            self._make_tx(200.00, "TX-B", 1),
        ]
        self.repo.find_by_user.return_value = txs
        result = self.builder.build(user_id=1)
        self.assertEqual(result["total_charged"], 300.00)
        self.assertEqual(result["count"], 2)

    def test_build_mixed_statuses_only_success_counts_toward_total(self):
        txs = [
            self._make_tx(100.00, "TX1", 99, status="success"),
            self._make_tx(50.00, "TX2", 99, status="declined"),
            self._make_tx(200.00, "TX3", 99, status="success"),
        ]
        self.repo.find_by_user.return_value = txs
        result = self.builder.build(user_id=99)
        self.assertEqual(result["total_charged"], 300.00)
        self.assertEqual(result["count"], 3)

    def test_build_rounds_total_charged_to_two_decimals(self):
        txs = [
            Transaction("TX1", 3, 10.555, status="success"),
            Transaction("TX2", 3, 0.005, status="success"),
        ]
        self.repo.find_by_user.return_value = txs
        result = self.builder.build(user_id=3)
        self.assertEqual(result["total_charged"], 10.56)

    def test_build_returns_same_transactions_list_as_repository(self):
        txs = [Transaction("TX1", 4, 100.00, status="success")]
        self.repo.find_by_user.return_value = txs
        result = self.builder.build(user_id=4)
        self.assertIs(result["transactions"], txs)


## Task 4: CheckoutServiceSpy : python -m pytest test_banklite.py::TestCheckoutServiceWithSpy -v

class TestCheckoutServiceWithSpy(unittest.TestCase):
    def _make_tx(self, amount=100.00, tx_id="TX-001", user_id=1, currency="USD"):
        """Helper: build a Transaction. Keeps test setup DRY.

        Default values mean each test only specifies what it cares about."""
        return Transaction(tx_id=tx_id, user_id=user_id, amount=amount, currency=currency)

    def test_usd_processing_fee_is_correct(self):
        real_calc = FeeCalculator()
        spy_calc = MagicMock(wraps=real_calc)
        gateway = MagicMock()
        gateway.charge.return_value = True
        svc = CheckoutService(spy_calc, gateway)
        tx = self._make_tx(amount=100.0)
        receipt = svc.checkout(tx)
        self.assertEqual(receipt["fee"], 3.20)

    def test_international_fee_includes_surcharge(self):
        real_calc = FeeCalculator()
        spy_calc = MagicMock(wraps=real_calc)
        gateway = MagicMock()
        gateway.charge.return_value = True
        svc = CheckoutService(spy_calc, gateway)
        tx = self._make_tx(amount=200.0, currency="EUR")
        receipt = svc.checkout(tx)
        self.assertEqual(receipt["fee"], 9.10)

    def test_processing_fee_called_with_correct_amount_and_currency(self):
        real_calc = FeeCalculator()
        spy_calc = MagicMock(wraps=real_calc)
        gateway = MagicMock()
        gateway.charge.return_value = True
        svc = CheckoutService(spy_calc, gateway)
        tx = self._make_tx(amount=200.0, currency="EUR")
        svc.checkout(tx)
        spy_calc.processing_fee.assert_called_once_with(tx.amount, tx.currency)

    def test_net_amount_called_with_correct_amount_and_currency(self):
        real_calc = FeeCalculator()
        spy_calc = MagicMock(wraps=real_calc)
        gateway = MagicMock()
        gateway.charge.return_value = True
        svc = CheckoutService(spy_calc, gateway)
        tx = self._make_tx(amount=200.0, currency="EUR")
        svc.checkout(tx)
        spy_calc.net_amount.assert_called_once_with(tx.amount, tx.currency)

    def test_each_fee_method_called_exactly_once_per_checkout(self):
        real_calc = FeeCalculator()
        spy_calc = MagicMock(wraps=real_calc)
        gateway = MagicMock()
        gateway.charge.return_value = True
        svc = CheckoutService(spy_calc, gateway)
        tx = self._make_tx(amount=100.0)
        svc.checkout(tx)
        spy_calc.processing_fee.assert_called_once()
        spy_calc.net_amount.assert_called_once()

    def test_spy_return_matches_fee_in_receipt(self):
        real_calc = FeeCalculator()
        spy_calc = MagicMock(wraps=real_calc)
        gateway = MagicMock()
        gateway.charge.return_value = True
        svc = CheckoutService(spy_calc, gateway)
        tx = self._make_tx(amount=100.0)
        receipt = svc.checkout(tx)
        expected_fee = round(100 * FeeCalculator.BASE_FEE_RATE + FeeCalculator.FIXED_FEE, 2)
        self.assertEqual(receipt["fee"], expected_fee)
        self.assertEqual(receipt["fee"], 3.20)

    def test_partial_spy_on_net_amount_only(self):
        real_calc = FeeCalculator()
        gateway = MagicMock()
        gateway.charge.return_value = True
        svc = CheckoutService(real_calc, gateway)
        tx = self._make_tx(amount=100.0)
        with patch.object(
            real_calc, "net_amount", wraps=real_calc.net_amount
        ) as spy_net:
            receipt = svc.checkout(tx)
        spy_net.assert_called_once_with(tx.amount, tx.currency)
        self.assertEqual(receipt["net"], receipt["amount"] - receipt["fee"])

    def test_contrast_mock_only_tests_wiring_not_formula(self):
        # With a plain mock, we verify CheckoutService passes calculator outputs into
        # the receipt—not that FeeCalculator's fee math is correct. A spy checks both.
        mock_calc = MagicMock()
        mock_calc.processing_fee.return_value = 5.00
        mock_calc.net_amount.return_value = 95.00
        gateway = MagicMock()
        gateway.charge.return_value = True
        svc = CheckoutService(mock_calc, gateway)
        tx = self._make_tx(amount=100.0)
        receipt = svc.checkout(tx)
        self.assertEqual(receipt["fee"], 5.00)
        self.assertEqual(receipt["net"], 95.00)


if __name__ == "__main__":
    unittest.main()
