"""Project-scoped experiment ledger and research mode (autoresearch subset)."""

from butler.experiments.ledger import (
    append_record,
    best_record,
    experiments_ledger_path,
    list_recent,
    maybe_record_from_job_result,
)
from butler.experiments.metrics import parse_metrics_from_text
from butler.experiments.mode import (
    check_experiment_mode_block,
    experiment_mode_enabled,
    is_harness_path,
    is_experiment_writable_path,
)

__all__ = [
    "append_record",
    "best_record",
    "check_experiment_mode_block",
    "experiment_mode_enabled",
    "experiments_ledger_path",
    "is_experiment_writable_path",
    "is_harness_path",
    "list_recent",
    "maybe_record_from_job_result",
    "parse_metrics_from_text",
]
