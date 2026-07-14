"""Matplotlib visualizations for OCR training and prediction performance."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def save_confusion_heatmap(
    matrix: Sequence[Sequence[int]],
    labels: Sequence[str],
    output_path: Path,
    title: str,
    normalize: bool = True,
) -> None:
    """Save a readable confusion-matrix heatmap for small or large alphabets."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    values = np.asarray(matrix, dtype=np.float64)
    if normalize and values.size:
        row_totals = values.sum(axis=1, keepdims=True)
        values = np.divide(values, row_totals, out=np.zeros_like(values), where=row_totals != 0)

    figure_size = max(8, min(18, len(labels) * 0.28))
    fig, axis = plt.subplots(figsize=(figure_size, figure_size))
    image = axis.imshow(values, cmap="Blues", aspect="auto", vmin=0)
    axis.set_title(title)
    axis.set_xlabel("Predicted label")
    axis.set_ylabel("True label")
    axis.set_xticks(range(len(labels)))
    axis.set_yticks(range(len(labels)))
    axis.set_xticklabels(labels, rotation=90, fontsize=7)
    axis.set_yticklabels(labels, fontsize=7)
    if len(labels) <= 20:
        for row in range(values.shape[0]):
            for column in range(values.shape[1]):
                value = values[row, column]
                text = f"{value:.2f}" if normalize else str(int(value))
                axis.text(column, row, text, ha="center", va="center", fontsize=6)
    fig.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def save_average_metrics_chart(metrics: Dict, output_path: Path, title: str) -> None:
    """Compare macro, micro and weighted precision/recall/F1 values."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    average_names = ["macro_average", "micro_average", "weighted_average"]
    display_names = ["Macro", "Micro", "Weighted"]
    metric_names = ["precision", "recall", "f1_score"]
    x_positions = np.arange(len(display_names))
    width = 0.24

    fig, axis = plt.subplots(figsize=(9, 5))
    for offset, metric_name in enumerate(metric_names):
        values = [metrics[name][metric_name] for name in average_names]
        bars = axis.bar(
            x_positions + (offset - 1) * width,
            values,
            width,
            label=metric_name.replace("_", " ").title(),
        )
        axis.bar_label(bars, labels=[f"{value:.3f}" for value in values], fontsize=8)
    axis.set_ylim(0, 1.08)
    axis.set_xticks(x_positions)
    axis.set_xticklabels(display_names)
    axis.set_ylabel("Score")
    axis.set_title(title)
    axis.grid(axis="y", linestyle="--", alpha=0.35)
    axis.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def save_training_history_plot(history: Sequence[Dict], output_path: Path) -> None:
    """Plot calibration loss and validation character error by epoch."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    epochs = [entry["epoch"] for entry in history if entry.get("loss") is not None]
    losses = [entry["loss"] for entry in history if entry.get("loss") is not None]
    validation = [entry for entry in history if entry.get("character_error") is not None]

    fig, loss_axis = plt.subplots(figsize=(10, 5))
    loss_axis.plot(epochs, losses, color="#d62728", linewidth=2, label="Training loss")
    loss_axis.set_xlabel("Epoch")
    loss_axis.set_ylabel("Training loss", color="#d62728")
    loss_axis.tick_params(axis="y", labelcolor="#d62728")
    loss_axis.grid(linestyle="--", alpha=0.3)

    error_axis = loss_axis.twinx()
    if validation:
        error_axis.plot(
            [entry["epoch"] for entry in validation],
            [entry["character_error"] for entry in validation],
            color="#1f77b4",
            marker="o",
            linewidth=2,
            label="Validation character errors",
        )
    error_axis.set_ylabel("Validation character errors", color="#1f77b4")
    error_axis.tick_params(axis="y", labelcolor="#1f77b4")
    fig.suptitle("Writer Calibration Training History")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)

