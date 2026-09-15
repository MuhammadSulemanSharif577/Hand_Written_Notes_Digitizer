"""Safety policy for selecting a TrOCR checkpoint in production.

A writer specialist may be useful for its labelled cohort while regressing on
held-out handwriting.  Such a checkpoint must never become the universal
model merely because its specialist promotion marker is true.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


_LOWER_IS_BETTER = ("character_error_rate", "word_error_rate")
_HIGHER_IS_BETTER = ("exact_line_accuracy",)


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def validation_does_not_regress(
    baseline: dict,
    candidate: dict,
    tolerance: float = 0.0,
) -> bool:
    """Require the candidate to be no worse on every generalization metric."""
    tolerance = max(0.0, float(tolerance))
    for metric in _LOWER_IS_BETTER:
        old = _finite_number(baseline.get(metric))
        new = _finite_number(candidate.get(metric))
        if old is None or new is None or new > old + tolerance:
            return False
    for metric in _HIGHER_IS_BETTER:
        old = _finite_number(baseline.get(metric))
        new = _finite_number(candidate.get(metric))
        if old is None or new is None or new + tolerance < old:
            return False

    old_classification = baseline.get("character_classification", {})
    new_classification = candidate.get("character_classification", {})
    old_accuracy = _finite_number(old_classification.get("accuracy"))
    new_accuracy = _finite_number(new_classification.get("accuracy"))
    old_weighted_f1 = _finite_number(
        old_classification.get("weighted_average", {}).get("f1_score")
    )
    new_weighted_f1 = _finite_number(
        new_classification.get("weighted_average", {}).get("f1_score")
    )
    return bool(
        old_accuracy is not None
        and new_accuracy is not None
        and old_weighted_f1 is not None
        and new_weighted_f1 is not None
        and new_accuracy + tolerance >= old_accuracy
        and new_weighted_f1 + tolerance >= old_weighted_f1
    )


def is_safe_general_checkpoint(model_dir: str | os.PathLike[str]) -> bool:
    """Return true only for a promoted checkpoint with no held-out regression."""
    directory = Path(model_dir)
    marker_path = directory / "promotion.json"
    comparison_path = directory / "comparison.json"
    weights_path = directory / "model.safetensors"
    if not (marker_path.exists() and comparison_path.exists() and weights_path.exists()):
        return False
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        baseline = comparison["baseline"]["validation"]
        candidate = comparison["candidate"]["validation"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    if not marker.get("promoted") or not comparison.get("promoted"):
        return False
    # New checkpoints explicitly record their deployment role and absolute
    # quality floor. A specialist or a high-error candidate must never become
    # the universal model merely because it improved over a weak baseline.
    if "general_deployment_safe" in marker and not marker.get(
        "general_deployment_safe"
    ):
        return False
    if marker.get("deployment_role") not in {None, "general"}:
        return False
    if "meets_absolute_quality_floor" in marker and not marker.get(
        "meets_absolute_quality_floor"
    ):
        return False
    tolerance = float(os.getenv("OCR_GENERAL_METRIC_TOLERANCE", "0"))
    return validation_does_not_regress(baseline, candidate, tolerance)
