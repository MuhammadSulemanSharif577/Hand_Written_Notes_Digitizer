"""Evaluate the line-level TrOCR checkpoint on labelled handwriting crops."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import cv2

from app.handwriting_ocr import MODEL_ID, recognize_lines_with_confidence

from .metrics import sequence_ocr_metrics
from .plots import save_average_metrics_chart, save_confusion_heatmap
from .reporting import save_classification_csv, save_json


def evaluate_sequence_model(
    labels_path: Path,
    lines_dir: Path,
    output_dir: Path,
) -> Dict:
    labels = [
        line.strip()
        for line in labels_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    images = []
    for index in range(1, len(labels) + 1):
        image_path = lines_dir / f"line_{index:02d}.png"
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(f"Missing labelled OCR line: {image_path}")
        images.append(image)

    recognized = recognize_lines_with_confidence(images)
    predictions = [text for text, _ in recognized]
    confidences = [confidence for _, confidence in recognized]
    metrics = sequence_ocr_metrics(labels, predictions)
    metrics.update(
        {
            "model": str(MODEL_ID),
            "dataset": str(lines_dir),
            "mean_sequence_confidence": (
                sum(confidences) / len(confidences) if confidences else 0.0
            ),
            "sequence_confidences": confidences,
        }
    )
    character_metrics = metrics["character_classification"]

    output_dir.mkdir(parents=True, exist_ok=True)
    save_json(metrics, output_dir / "metrics.json")
    save_classification_csv(
        character_metrics,
        output_dir / "character_classification_report.csv",
    )
    save_confusion_heatmap(
        character_metrics["confusion_matrix"],
        character_metrics["labels"],
        output_dir / "character_confusion_heatmap.png",
        "TrOCR Aligned Character Confusion Matrix",
    )
    save_average_metrics_chart(
        character_metrics,
        output_dir / "character_precision_recall_f1_averages.png",
        "TrOCR Character Precision, Recall and F1 Averages",
    )
    return metrics

