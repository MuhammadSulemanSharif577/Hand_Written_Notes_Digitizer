"""Conservative one-shot visual memory for explicitly labelled line crops."""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CALIBRATION_DIR = PROJECT_ROOT / "training_data" / "writer_junaid"
CALIBRATION_DIR = Path(
    os.getenv("OCR_VISUAL_CALIBRATION_DIR", str(DEFAULT_CALIBRATION_DIR))
)
MINIMUM_SCORE = float(os.getenv("OCR_VISUAL_CALIBRATION_MIN_SCORE", "0.90"))
_examples: List[Tuple[str, np.ndarray]] | None = None


def _fingerprint(region: np.ndarray) -> np.ndarray | None:
    if region is None or region.size == 0:
        return None
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY) if region.ndim == 3 else region
    ink = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )[1]
    coordinates = cv2.findNonZero(ink)
    if coordinates is None:
        return None
    x, y, width, height = cv2.boundingRect(coordinates)
    ink = ink[y:y + height, x:x + width]

    canvas_height, canvas_width = 64, 320
    scale = min(
        (canvas_width - 12) / max(1, width),
        (canvas_height - 12) / max(1, height),
    )
    resized_width = max(1, int(round(width * scale)))
    resized_height = max(1, int(round(height * scale)))
    resized = cv2.resize(
        ink,
        (resized_width, resized_height),
        interpolation=cv2.INTER_AREA,
    )
    canvas = np.zeros((canvas_height, canvas_width), dtype=np.uint8)
    x_offset = (canvas_width - resized_width) // 2
    y_offset = (canvas_height - resized_height) // 2
    canvas[
        y_offset:y_offset + resized_height,
        x_offset:x_offset + resized_width,
    ] = resized
    return canvas


def _load_examples() -> List[Tuple[str, np.ndarray]]:
    global _examples
    if _examples is not None:
        return _examples

    labels_path = CALIBRATION_DIR / "labels.txt"
    lines_dir = CALIBRATION_DIR / "lines"
    if not labels_path.exists() or not lines_dir.exists():
        _examples = []
        return _examples

    labels = [
        line.strip()
        for line in labels_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    examples: List[Tuple[str, np.ndarray]] = []
    for index, label in enumerate(labels, start=1):
        image = cv2.imread(str(lines_dir / f"line_{index:02d}.png"))
        fingerprint = _fingerprint(image) if image is not None else None
        if fingerprint is not None:
            examples.append((label, fingerprint))

    # Include the expanded, manually verified fine-tuning manifest. Only
    # training records become visual memories; independent validation crops
    # remain evaluation-only and can never override production predictions.
    manifest_path = CALIBRATION_DIR / "finetune_v2" / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for record in manifest.get("records", []):
                if record.get("split") != "train":
                    continue
                image_path = PROJECT_ROOT / record["image"]
                image = cv2.imread(str(image_path))
                fingerprint = _fingerprint(image) if image is not None else None
                if fingerprint is not None:
                    examples.append((record["label"], fingerprint))
        except (OSError, ValueError, KeyError, TypeError):
            # A malformed optional manifest must not make OCR unavailable.
            pass
    _examples = examples
    return examples


def match_calibrated_line(region: np.ndarray) -> Tuple[str | None, float]:
    """Return a label only for a near-identical explicitly labelled crop."""
    query = _fingerprint(region)
    if query is None:
        return None, 0.0

    best_label = None
    best_score = -1.0
    query_binary = query >= 128
    for label, example in _load_examples():
        correlation = float(
            cv2.matchTemplate(query, example, cv2.TM_CCOEFF_NORMED)[0, 0]
        )
        example_binary = example >= 128
        union = int(np.count_nonzero(query_binary | example_binary))
        intersection = int(np.count_nonzero(query_binary & example_binary))
        overlap = intersection / union if union else 0.0
        score = 0.60 * correlation + 0.40 * overlap
        if score > best_score:
            best_label = label
            best_score = score

    if best_score >= MINIMUM_SCORE:
        return best_label, best_score
    return None, best_score
