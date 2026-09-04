"""
Synthetic Financial Data Generator - Phase 3.1.

Generates 100 reproducible transactions across payments, ledger, bank, and adjustments
with intentional reconciliation exceptions and ground truth for Phase 1 and Phase 2.
"""

import csv
import os
import random
from typing import Any, Dict, List, Optional, Tuple


class SyntheticDataGenerator:
    """Generates synthetic multi-source financial records for reconciliation and AI investigation."""

    def __init__(
        self,
        seed: int = 42,
        total_transactions: int = 100,
        scenario_distribution: Optional[Dict[str, int]] = None,
        explainable_counts: Optional[Dict[str, int]] = None,
    ):
        self.seed = seed
        self.total_transactions = total_transactions
        self.scenario_distribution = scenario_distribution
        self.explainable_counts = explainable_counts
        random.seed(self.seed)

    def generate(self) -> Tuple[
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        List[Dict[str, Any]]
    ]:
        """
        Generates synthetic datasets for payments, ledger, bank, adjustments, and ground truth.

        Returns:
            Tuple of (payments, ledger_records, bank_records, adjustments, ground_truth)
        """
        random.seed(self.seed)

        # Target Phase 1 error distribution counts
        if self.scenario_distribution is not None:
            total_scenarios = sum(self.scenario_distribution.values())
            if total_scenarios != self.total_transactions:
                raise ValueError(
                    f"Sum of scenario counts ({total_scenarios}) does not match total_transactions ({self.total_transactions})"
                )
            scenarios = []
            for sc_name, count in self.scenario_distribution.items():
                scenarios.extend([sc_name] * count)
        else:
            scenarios = (
                ["RECONCILED"] * 70
                + ["GROSS_AMOUNT_MISMATCH"] * 10
                + ["MISSING_LEDGER_RECORD"] * 5
                + ["MISSING_BANK_RECORD"] * 5
                + ["BANK_AMOUNT_MISMATCH"] * 4
                + ["DUPLICATE_BANK_RECORD"] * 3
                + ["LEDGER_CALCULATION_ERROR"] * 3
            )

        random.shuffle(scenarios)

        payments: List[Dict[str, Any]] = []
        ledger_records: List[Dict[str, Any]] = []
        bank_records: List[Dict[str, Any]] = []
        adjustments: List[Dict[str, Any]] = []
        ground_truth: List[Dict[str, Any]] = []

        bank_ref_counter = 1
        adj_ref_counter = 1

        # Specific exception cases explainable with adjustments
        max_bank_explainable = (
            self.explainable_counts.get("BANK_AMOUNT_MISMATCH", 4)
            if self.explainable_counts is not None
            else 4
        )
        max_gross_explainable = (
            self.explainable_counts.get("GROSS_AMOUNT_MISMATCH", 4)
            if self.explainable_counts is not None
            else 4
        )

        explainable_indices = set()
        gross_mismatch_count = 0
        bank_mismatch_count = 0

        for idx, sc in enumerate(scenarios):
            if sc == "BANK_AMOUNT_MISMATCH":
                bank_mismatch_count += 1
                if bank_mismatch_count <= max_bank_explainable:
                    explainable_indices.add(idx)
            elif sc == "GROSS_AMOUNT_MISMATCH":
                gross_mismatch_count += 1
                if gross_mismatch_count <= max_gross_explainable:
                    explainable_indices.add(idx)

        for i, scenario in enumerate(scenarios, start=1):
            txn_id = f"TXN{i:03d}"
            merchant_id = f"M{random.randint(1, 20):03d}"
            date = f"2026-08-{random.randint(1, 28):02d}"

            # Base amount (in round figures e.g. 1,000 to 50,000)
            base_amount = random.randint(10, 500) * 100
            fee_percentage = random.choice([0.015, 0.02, 0.025, 0.03])
            fee = int(base_amount * fee_percentage)
            expected_net = base_amount - fee

            # 1. Payment Record
            payment_status = "CAPTURED"
            payments.append({
                "transaction_id": txn_id,
                "merchant_id": merchant_id,
                "amount": base_amount,
                "date": date,
                "status": payment_status
            })

            is_explainable = (i - 1) in explainable_indices

            # Ground Truth setup
            if scenario == "RECONCILED":
                gt_phase1_status = "RECONCILED"
                gt_phase1_exception = None
                gt_phase2_decision = "N/A"
            else:
                gt_phase1_status = "EXCEPTION"
                gt_phase1_exception = scenario
                gt_phase2_decision = "AUTO_RESOLVED" if is_explainable else "HUMAN_REVIEW"

            ground_truth.append({
                "transaction_id": txn_id,
                "expected_phase1_status": gt_phase1_status,
                "expected_phase1_exception": gt_phase1_exception,
                "expected_phase2_decision": gt_phase2_decision,
                "expected_status": gt_phase1_status,
                "expected_exception": gt_phase1_exception,
                # Explicit detection label so Phase 1 can be scored for
                # false positives and false negatives, not assumed correct.
                "is_phase1_exception": gt_phase1_status == "EXCEPTION",
            })

            # 2. Ledger & Bank Record Construction
            if scenario == "MISSING_LEDGER_RECORD":
                bank_records.append({
                    "bank_reference": f"BNK_REF_{bank_ref_counter:04d}",
                    "transaction_id": txn_id,
                    "credited_amount": expected_net,
                    "date": date
                })
                bank_ref_counter += 1

            elif scenario == "GROSS_AMOUNT_MISMATCH":
                diff = random.choice([200, 500, 1000])
                bad_gross = base_amount + diff
                bad_net = bad_gross - fee
                ledger_records.append({
                    "transaction_id": txn_id,
                    "gross_amount": bad_gross,
                    "fee": fee,
                    "net_amount": bad_net,
                    "date": date,
                    "status": "POSTED"
                })
                bank_records.append({
                    "bank_reference": f"BNK_REF_{bank_ref_counter:04d}",
                    "transaction_id": txn_id,
                    "credited_amount": expected_net,
                    "date": date
                })
                bank_ref_counter += 1

                if is_explainable:
                    adjustments.append({
                        "transaction_id": txn_id,
                        "adjustment_type": "GROSS_INVOICE_ADJUSTMENT",
                        "amount": diff,
                        "reason": "Merchant gross amount adjustment reference",
                        "date": date,
                        "reference": f"ADJ{adj_ref_counter:03d}"
                    })
                    adj_ref_counter += 1

            elif scenario == "LEDGER_CALCULATION_ERROR":
                bad_net = expected_net + random.choice([-100, 100, 250, -250])
                ledger_records.append({
                    "transaction_id": txn_id,
                    "gross_amount": base_amount,
                    "fee": fee,
                    "net_amount": bad_net,
                    "date": date,
                    "status": "POSTED"
                })
                bank_records.append({
                    "bank_reference": f"BNK_REF_{bank_ref_counter:04d}",
                    "transaction_id": txn_id,
                    "credited_amount": expected_net,
                    "date": date
                })
                bank_ref_counter += 1

            elif scenario == "MISSING_BANK_RECORD":
                ledger_records.append({
                    "transaction_id": txn_id,
                    "gross_amount": base_amount,
                    "fee": fee,
                    "net_amount": expected_net,
                    "date": date,
                    "status": "POSTED"
                })

            elif scenario == "BANK_AMOUNT_MISMATCH":
                adj_amount = random.choice([100, 250, 500])
                bad_credited = expected_net - adj_amount
                ledger_records.append({
                    "transaction_id": txn_id,
                    "gross_amount": base_amount,
                    "fee": fee,
                    "net_amount": expected_net,
                    "date": date,
                    "status": "POSTED"
                })
                bank_records.append({
                    "bank_reference": f"BNK_REF_{bank_ref_counter:04d}",
                    "transaction_id": txn_id,
                    "credited_amount": bad_credited,
                    "date": date
                })
                bank_ref_counter += 1

                if is_explainable:
                    adj_type = random.choice(["BANK_PROCESSING_FEE", "SETTLEMENT_ADJUSTMENT"])
                    adjustments.append({
                        "transaction_id": txn_id,
                        "adjustment_type": adj_type,
                        "amount": adj_amount,
                        "reason": f"Standard {adj_type.lower().replace('_', ' ')} charge",
                        "date": date,
                        "reference": f"ADJ{adj_ref_counter:03d}"
                    })
                    adj_ref_counter += 1

            elif scenario == "DUPLICATE_BANK_RECORD":
                ledger_records.append({
                    "transaction_id": txn_id,
                    "gross_amount": base_amount,
                    "fee": fee,
                    "net_amount": expected_net,
                    "date": date,
                    "status": "POSTED"
                })
                bank_records.append({
                    "bank_reference": f"BNK_REF_{bank_ref_counter:04d}",
                    "transaction_id": txn_id,
                    "credited_amount": expected_net,
                    "date": date
                })
                bank_ref_counter += 1
                bank_records.append({
                    "bank_reference": f"BNK_REF_{bank_ref_counter:04d}",
                    "transaction_id": txn_id,
                    "credited_amount": expected_net,
                    "date": date
                })
                bank_ref_counter += 1

            elif scenario == "RECONCILED":
                ledger_records.append({
                    "transaction_id": txn_id,
                    "gross_amount": base_amount,
                    "fee": fee,
                    "net_amount": expected_net,
                    "date": date,
                    "status": "POSTED"
                })
                bank_records.append({
                    "bank_reference": f"BNK_REF_{bank_ref_counter:04d}",
                    "transaction_id": txn_id,
                    "credited_amount": expected_net,
                    "date": date
                })
                bank_ref_counter += 1

        return payments, ledger_records, bank_records, adjustments, ground_truth

    def save_to_csv(self, data_dir: str) -> Tuple[str, str, str, str]:
        """Saves payments.csv, ledger.csv, bank.csv, and adjustments.csv."""
        os.makedirs(data_dir, exist_ok=True)
        payments, ledger_records, bank_records, adjustments, _ = self.generate()

        payments_path = os.path.join(data_dir, "payments.csv")
        with open(payments_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["transaction_id", "merchant_id", "amount", "date", "status"])
            writer.writeheader()
            writer.writerows(payments)

        ledger_path = os.path.join(data_dir, "ledger.csv")
        with open(ledger_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["transaction_id", "gross_amount", "fee", "net_amount", "date", "status"])
            writer.writeheader()
            writer.writerows(ledger_records)

        bank_path = os.path.join(data_dir, "bank.csv")
        with open(bank_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["bank_reference", "transaction_id", "credited_amount", "date"])
            writer.writeheader()
            writer.writerows(bank_records)

        adjustments_path = os.path.join(data_dir, "adjustments.csv")
        with open(adjustments_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["transaction_id", "adjustment_type", "amount", "reason", "date", "reference"])
            writer.writeheader()
            writer.writerows(adjustments)

        return payments_path, ledger_path, bank_path, adjustments_path

    def save_ground_truth_csv(self, data_dir: str) -> str:
        """Saves ground_truth.csv matching the generated transactions."""
        os.makedirs(data_dir, exist_ok=True)
        _, _, _, _, ground_truth = self.generate()
        gt_path = os.path.join(data_dir, "ground_truth.csv")
        with open(gt_path, "w", newline="", encoding="utf-8") as f:
            fieldnames = [
                "transaction_id",
                "expected_phase1_status",
                "expected_phase1_exception",
                "expected_phase2_decision",
                "expected_status",
                "expected_exception",
                "is_phase1_exception",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(ground_truth)
        return gt_path

    def save_all_to_csv(self, data_dir: str) -> Tuple[str, str, str, str, str]:
        """Saves payments.csv, ledger.csv, bank.csv, adjustments.csv, and ground_truth.csv."""
        payments_path, ledger_path, bank_path, adjustments_path = self.save_to_csv(data_dir)
        gt_path = self.save_ground_truth_csv(data_dir)
        return payments_path, ledger_path, bank_path, adjustments_path, gt_path
