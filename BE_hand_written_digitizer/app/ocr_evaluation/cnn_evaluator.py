"""Evaluate the isolated-character CNN on the EMNIST ByClass test split."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import numpy as np

from app.ocr_components.cnn_model import label_to_char, load_ocr_model

from .metrics import classification_metrics
from .plots import save_average_metrics_chart, save_confusion_heatmap
from .reporting import save_classification_csv, save_json


def _stratified_indexes(labels: np.ndarray, maximum_samples: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    classes = np.unique(labels)
    per_class = max(1, maximum_samples // len(classes))
    selected = []
    for class_label in classes:
        candidates = np.where(labels == class_label)[0]
        count = min(per_class, len(candidates))
        selected.extend(rng.choice(candidates, size=count, replace=False).tolist())
    remaining = maximum_samples - len(selected)
    if remaining > 0:
        available = np.setdiff1d(np.arange(len(labels)), np.asarray(selected), assume_unique=False)
        count = min(remaining, len(available))
        selected.extend(rng.choice(available, size=count, replace=False).tolist())
    return np.asarray(selected, dtype=np.int64)


def evaluate_cnn(
    dataset_path: Path,
    output_dir: Path,
    maximum_samples: int = 10000,
    batch_size: int = 256,
    seed: int = 42,
) -> Dict:
    """Run a balanced test subset and save JSON, CSV and PNG results."""
    dataset = np.load(dataset_path)
    images = dataset["x_test"]
    labels = dataset["y_test"].astype(np.int64)
    if 0 < maximum_samples < len(labels):
        indexes = _stratified_indexes(labels, maximum_samples, seed)
        images = images[indexes]
        labels = labels[indexes]

    normalized_images = images.reshape(-1, 28, 28, 1).astype(np.float32) / 255.0
    model = load_ocr_model()
    probabilities = model.predict(normalized_images, batch_size=batch_size, verbose=0)
    predicted_labels = np.argmax(probabilities, axis=1)
    confidence = np.max(probabilities, axis=1)
    class_labels = [label_to_char(index) for index in range(62)]
    true_characters = [label_to_char(int(label)) for label in labels]
    predicted_characters = [label_to_char(int(label)) for label in predicted_labels]
    metrics = classification_metrics(
        true_characters,
        predicted_characters,
        labels=class_labels,
    )
    metrics.update(
        {
            "model": "EMNIST ByClass CNN",
            "dataset": str(dataset_path),
            "evaluated_samples": len(labels),
            "mean_prediction_confidence": float(np.mean(confidence)),
            "mean_correct_confidence": float(
                np.mean(confidence[predicted_labels == labels])
            ) if np.any(predicted_labels == labels) else 0.0,
            "mean_incorrect_confidence": float(
                np.mean(confidence[predicted_labels != labels])
            ) if np.any(predicted_labels != labels) else 0.0,
        }
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    save_json(metrics, output_dir / "metrics.json")
    save_classification_csv(metrics, output_dir / "classification_report.csv")
    save_confusion_heatmap(
        metrics["confusion_matrix"],
        metrics["labels"],
        output_dir / "confusion_matrix_heatmap.png",
        "CNN Character Confusion Matrix (Row Normalized)",
    )
    save_average_metrics_chart(
        metrics,
        output_dir / "precision_recall_f1_averages.png",
        "CNN Precision, Recall and F1 Averages",
    )
    return metrics

