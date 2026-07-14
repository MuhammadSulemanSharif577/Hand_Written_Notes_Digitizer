"""Serialization helpers for machine-readable and tabular evaluation output."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict


def save_json(data: Dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def save_classification_csv(metrics: Dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["label", "precision", "recall", "f1_score", "support"],
        )
        writer.writeheader()
        writer.writerows(metrics["per_class"])
        for display_name, key in (
            ("macro avg", "macro_average"),
            ("micro avg", "micro_average"),
            ("weighted avg", "weighted_average"),
        ):
            row = {"label": display_name, **metrics[key], "support": metrics["sample_count"]}
            writer.writerow(row)

