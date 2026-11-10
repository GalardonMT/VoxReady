"""
Unittest suite for metrics editor, agreement summary and labeling cases.
Runs with standard library unittest without requiring pytest.
"""

import sys
import unittest
import json
from pathlib import Path
from types import SimpleNamespace

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import metrics_store
import metrics_migration
from metrics_catalog import METRICS


def definitions():
    return [
        dict(
            key=item[0],
            min=item[5],
            max=item[6],
            step=item[7],
            thresholdKeys=json.dumps(list(item[-1])),
        )
        for item in METRICS
    ]


def updates():
    return [SimpleNamespace(key=item[0], thresholds=dict(item[-1])) for item in METRICS]


class TestMetricsEditorUnittest(unittest.TestCase):

    def test_approved_catalog_has_exact_dictionary_and_initial_intervals(self):
        self.assertEqual(len(METRICS), 16)
        self.assertEqual(len({item[0] for item in METRICS}), 16)
        self.assertEqual(
            {item[1] for item in METRICS},
            {"voice", "vision", "content", "empathy", "governance"},
        )
        self.assertEqual(
            next(item[-1] for item in METRICS if item[0] == "voice.hesitation_pause"),
            {"optimalMax": 2, "warningMax": 5},
        )
        self.assertEqual(
            next(item[-1] for item in METRICS if item[0] == "voice.phonation_ratio"),
            {"criticalBelow": 45, "optimalLow": 60, "optimalHigh": 85},
        )
        # Validation should succeed without error
        metrics_store._validate(definitions(), updates())

    def test_agreement_evaluation_against_dynamic_target(self):
        class Cursor:
            def __init__(self, count, avg_ratio):
                self.count = count
                self.avg_ratio = avg_ratio
                self.sql = ""

            def execute(self, sql, *args):
                self.sql = sql
                return self

            def fetchone(self):
                if "labeling_correction" in self.sql:
                    return (self.count, self.avg_ratio)
                return None

        # 1. Sin muestras -> insufficient_data
        c_empty = Cursor(0, None)
        s_empty = metrics_store.get_ai_human_agreement_summary(c_empty)
        self.assertEqual(s_empty["status"], "insufficient_data")
        self.assertEqual(s_empty["samplesCount"], 0)
        self.assertIsNone(s_empty["aiHumanAgreement"])

        # Mock de versión publicada
        fake_published = {
            "metrics": [
                {
                    "key": "gov.agreement_target",
                    "thresholds": {"warningLow": 0.70, "optimalLow": 0.85},
                }
            ]
        }
        original_latest = metrics_store.latest_published
        try:
            metrics_store.latest_published = lambda _cur: fake_published

            # 2. Optimal (>= 0.85)
            c_opt = Cursor(10, 0.90)
            s_opt = metrics_store.get_ai_human_agreement_summary(c_opt)
            self.assertEqual(s_opt["status"], "optimal")
            self.assertEqual(s_opt["aiHumanAgreement"], 0.90)
            self.assertEqual(s_opt["samplesCount"], 10)

            # 3. Warning (0.70 <= x < 0.85)
            c_warn = Cursor(10, 0.75)
            s_warn = metrics_store.get_ai_human_agreement_summary(c_warn)
            self.assertEqual(s_warn["status"], "warning")
            self.assertEqual(s_warn["aiHumanAgreement"], 0.75)

            # 4. Critical (< 0.70)
            c_crit = Cursor(10, 0.65)
            s_crit = metrics_store.get_ai_human_agreement_summary(c_crit)
            self.assertEqual(s_crit["status"], "critical")
            self.assertEqual(s_crit["aiHumanAgreement"], 0.65)
        finally:
            metrics_store.latest_published = original_latest

    def test_pending_labeling_cases_summary(self):
        class Cursor:
            def execute(self, sql, *args):
                return self

            def fetchall(self):
                return [("low_confidence", 3), ("borderline", 5), ("random", 2)]

        c = Cursor()
        res = metrics_store.get_pending_labeling_cases_summary(c)
        self.assertEqual(res["total"], 10)
        self.assertEqual(res["low_confidence"], 3)
        self.assertEqual(res["borderline"], 5)
        self.assertEqual(res["random"], 2)

    def test_schema_steps_include_labeling_tables(self):
        steps = " ".join(metrics_migration.SCHEMA_STEPS)
        self.assertIn("dbo.labeling_case", steps)
        self.assertIn("dbo.labeling_correction", steps)


if __name__ == "__main__":
    unittest.main()
