"""Dependency-free classification and OCR sequence metrics."""

from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np

EPSILON_LABEL = "<eps>"


def edit_distance(left: Sequence, right: Sequence) -> int:
    """Return Levenshtein distance for characters, words or class labels."""
    previous = list(range(len(right) + 1))
    for left_index, left_item in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_item in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_item != right_item),
                )
            )
        previous = current
    return previous[-1]


def align_sequences(
    reference: Sequence[str], prediction: Sequence[str]
) -> List[Tuple[str, str]]:
    """Backtrace a minimum-edit alignment, representing gaps as ``<eps>``."""
    rows, columns = len(reference) + 1, len(prediction) + 1
    costs = np.zeros((rows, columns), dtype=np.int32)
    costs[:, 0] = np.arange(rows)
    costs[0, :] = np.arange(columns)
    for row in range(1, rows):
        for column in range(1, columns):
            costs[row, column] = min(
                costs[row - 1, column] + 1,
                costs[row, column - 1] + 1,
                costs[row - 1, column - 1]
                + (reference[row - 1] != prediction[column - 1]),
            )

    alignment = []
    row, column = len(reference), len(prediction)
    while row > 0 or column > 0:
        if (
            row > 0
            and column > 0
            and costs[row, column]
            == costs[row - 1, column - 1]
            + (reference[row - 1] != prediction[column - 1])
        ):
            alignment.append((reference[row - 1], prediction[column - 1]))
            row -= 1
            column -= 1
        elif row > 0 and costs[row, column] == costs[row - 1, column] + 1:
            alignment.append((reference[row - 1], EPSILON_LABEL))
            row -= 1
        else:
            alignment.append((EPSILON_LABEL, prediction[column - 1]))
            column -= 1
    return list(reversed(alignment))


def confusion_matrix(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    labels: Sequence[str] | None = None,
) -> Tuple[np.ndarray, List[str]]:
    """Build a standard rows=true, columns=predicted confusion matrix."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must contain the same number of items")
    resolved_labels = list(labels) if labels is not None else sorted(set(y_true) | set(y_pred))
    index = {label: position for position, label in enumerate(resolved_labels)}
    matrix = np.zeros((len(resolved_labels), len(resolved_labels)), dtype=np.int64)
    for truth, prediction in zip(y_true, y_pred):
        if truth in index and prediction in index:
            matrix[index[truth], index[prediction]] += 1
    return matrix, resolved_labels


def classification_metrics(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    labels: Sequence[str] | None = None,
) -> Dict:
    """Calculate accuracy and per-class/macro/micro/weighted PRF metrics."""
    matrix, resolved_labels = confusion_matrix(y_true, y_pred, labels)
    total = int(matrix.sum())
    per_class = []
    true_positives = false_positives = false_negatives = 0

    for index, label in enumerate(resolved_labels):
        tp = int(matrix[index, index])
        fp = int(matrix[:, index].sum() - tp)
        fn = int(matrix[index, :].sum() - tp)
        support = int(matrix[index, :].sum())
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        per_class.append(
            {
                "label": str(label),
                "precision": precision,
                "recall": recall,
                "f1_score": f1,
                "support": support,
            }
        )
        true_positives += tp
        false_positives += fp
        false_negatives += fn

    supported = [item for item in per_class if item["support"] > 0]
    support_total = sum(item["support"] for item in supported)

    def average(metric: str) -> float:
        return (
            sum(item[metric] for item in supported) / len(supported)
            if supported
            else 0.0
        )

    def weighted(metric: str) -> float:
        return (
            sum(item[metric] * item["support"] for item in supported) / support_total
            if support_total
            else 0.0
        )

    micro_precision = (
        true_positives / (true_positives + false_positives)
        if true_positives + false_positives
        else 0.0
    )
    micro_recall = (
        true_positives / (true_positives + false_negatives)
        if true_positives + false_negatives
        else 0.0
    )
    micro_f1 = (
        2 * micro_precision * micro_recall / (micro_precision + micro_recall)
        if micro_precision + micro_recall
        else 0.0
    )
    return {
        "sample_count": total,
        "accuracy": float(np.trace(matrix) / total) if total else 0.0,
        "macro_average": {
            "precision": average("precision"),
            "recall": average("recall"),
            "f1_score": average("f1_score"),
        },
        "micro_average": {
            "precision": micro_precision,
            "recall": micro_recall,
            "f1_score": micro_f1,
        },
        "weighted_average": {
            "precision": weighted("precision"),
            "recall": weighted("recall"),
            "f1_score": weighted("f1_score"),
        },
        "per_class": per_class,
        "labels": [str(label) for label in resolved_labels],
        "confusion_matrix": matrix.tolist(),
    }


def sequence_ocr_metrics(
    references: Sequence[str], predictions: Sequence[str]
) -> Dict:
    """Calculate CER, WER, exact-line accuracy and aligned character PRF."""
    if len(references) != len(predictions):
        raise ValueError("references and predictions must have equal length")

    normalized_references = [" ".join(text.upper().split()) for text in references]
    normalized_predictions = [" ".join(text.upper().split()) for text in predictions]
    character_errors = sum(
        edit_distance(reference, prediction)
        for reference, prediction in zip(normalized_references, normalized_predictions)
    )
    character_total = sum(len(reference) for reference in normalized_references)
    word_errors = sum(
        edit_distance(reference.split(), prediction.split())
        for reference, prediction in zip(normalized_references, normalized_predictions)
    )
    word_total = sum(len(reference.split()) for reference in normalized_references)

    aligned_true = []
    aligned_predicted = []
    for reference, prediction in zip(normalized_references, normalized_predictions):
        reference_characters = [character for character in reference if not character.isspace()]
        predicted_characters = [character for character in prediction if not character.isspace()]
        for truth, predicted in align_sequences(reference_characters, predicted_characters):
            aligned_true.append(truth)
            aligned_predicted.append(predicted)

    character_report = classification_metrics(aligned_true, aligned_predicted)
    exact_matches = sum(
        reference == prediction
        for reference, prediction in zip(normalized_references, normalized_predictions)
    )
    return {
        "line_count": len(references),
        "exact_line_accuracy": exact_matches / len(references) if references else 0.0,
        "character_error_rate": character_errors / character_total if character_total else 0.0,
        "word_error_rate": word_errors / word_total if word_total else 0.0,
        "character_errors": character_errors,
        "reference_characters": character_total,
        "word_errors": word_errors,
        "reference_words": word_total,
        "character_classification": character_report,
        "predictions": [
            {"reference": reference, "prediction": prediction}
            for reference, prediction in zip(normalized_references, normalized_predictions)
        ],
    }

