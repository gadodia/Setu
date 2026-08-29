"""The final-demo evaluation is repeatable and does not require cloud access."""

from setu.evaluation import run_evaluation


def test_synthetic_safety_evaluation_passes_without_live_model(config):
    report = run_evaluation(config)

    assert report.passed is True
    assert {metric.name for metric in report.metrics} >= {
        "Document classification accuracy",
        "Golden reconciliation pass rate",
        "Mismatch escalation trigger",
        "Net-worth ground-truth error",
        "ROI evidence coverage",
        "Unsupported term-policy valuation rate",
        "Raw-document cloud tool exposure",
    }
