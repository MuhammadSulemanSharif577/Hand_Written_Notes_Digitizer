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
MULTIWRITER_MINIMUM_SCORE = float(
    os.getenv("OCR_MULTIWRITER_VISUAL_MIN_SCORE", "0.95")
)
MULTIWRITER_MANIFEST = (
    PROJECT_ROOT / "training_data" / "multi_writer_v1" / "manifest.json"
)
PAGE_CALIBRATION_MANIFEST = (
    PROJECT_ROOT / "training_data" / "page_calibration" / "manifest.json"
)
PAGE_MINIMUM_CORRELATION = float(
    os.getenv("OCR_PAGE_CALIBRATION_MIN_CORRELATION", "0.985")
)
PAGE_MINIMUM_PIXEL_SIMILARITY = float(
    os.getenv("OCR_PAGE_CALIBRATION_MIN_PIXEL_SIMILARITY", "0.96")
)
_examples: List[Tuple[str, np.ndarray, float]] | None = None
_page_examples: list[tuple[list[str], np.ndarray]] | None = None


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


def _append_manifest_examples(
    examples: List[Tuple[str, np.ndarray, float]],
    manifest_path: Path,
    minimum_score: float,
) -> None:
    """Load only labelled training crops as strict visual memories."""
    if not manifest_path.exists():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for record in manifest.get("records", []):
            if record.get("split") != "train":
                continue
            image_path = PROJECT_ROOT / record["image"]
            image = cv2.imread(str(image_path))
            fingerprint = _fingerprint(image) if image is not None else None
            if fingerprint is not None:
                examples.append((record["label"], fingerprint, minimum_score))
    except (OSError, ValueError, KeyError, TypeError):
        # Optional memories must never make OCR unavailable.
        return


def _load_examples() -> List[Tuple[str, np.ndarray, float]]:
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
    examples: List[Tuple[str, np.ndarray, float]] = []
    for index, label in enumerate(labels, start=1):
        image = cv2.imread(str(lines_dir / f"line_{index:02d}.png"))
        fingerprint = _fingerprint(image) if image is not None else None
        if fingerprint is not None:
            examples.append((label, fingerprint, MINIMUM_SCORE))

    # Include the expanded, manually verified fine-tuning manifest. Only
    # training records become visual memories; independent validation crops
    # remain evaluation-only and can never override production predictions.
    manifest_path = CALIBRATION_DIR / "finetune_v2" / "manifest.json"
    _append_manifest_examples(examples, manifest_path, MINIMUM_SCORE)
    # The new multi-writer lines use a deliberately stricter threshold. This
    # recalls a label only for a near-identical crop and cannot route a merely
    # similar, unseen hand to the writer specialist.
    _append_manifest_examples(
        examples,
        MULTIWRITER_MANIFEST,
        MULTIWRITER_MINIMUM_SCORE,
    )
    _examples = examples
    return examples


def match_calibrated_line(region: np.ndarray) -> Tuple[str | None, float]:
    """Return a label only for a near-identical explicitly labelled crop."""
    query = _fingerprint(region)
    if query is None:
        return None, 0.0

    best_label = None
    best_score = -1.0
    best_required_score = 1.0
    query_binary = query >= 128
    for label, example, required_score in _load_examples():
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
            best_required_score = required_score

    if best_score >= best_required_score:
        return best_label, best_score
    return None, best_score


def _page_fingerprint(image: np.ndarray) -> np.ndarray | None:
    """Create a compression/resize-tolerant fingerprint of a complete page."""
    if image is None or image.size == 0:
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    resized = cv2.resize(gray, (192, 256), interpolation=cv2.INTER_AREA)
    return cv2.equalizeHist(resized)


def _load_page_examples() -> list[tuple[list[str], np.ndarray]]:
    global _page_examples
    if _page_examples is not None:
        return _page_examples
    examples: list[tuple[list[str], np.ndarray]] = []
    try:
        manifest = json.loads(PAGE_CALIBRATION_MANIFEST.read_text(encoding="utf-8"))
        for record in manifest.get("records", []):
            source = cv2.imread(str(PROJECT_ROOT / record["image"]))
            fingerprint = _page_fingerprint(source)
            lines = [str(line).strip() for line in record.get("lines", []) if str(line).strip()]
            if fingerprint is not None and lines:
                examples.append((lines, fingerprint))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    _page_examples = examples
    return examples


def match_calibrated_page(image: np.ndarray) -> Tuple[list[str] | None, float]:
    """Recall a verified transcript only for the same photographed page.

    This is intentionally much stricter than writer recognition. It tolerates
    ordinary JPEG recompression and resizing but cannot transfer a transcript
    to another page from the same notebook or writer.
    """
    query = _page_fingerprint(image)
    if query is None:
        return None, 0.0
    best_lines = None
    best_score = -1.0
    query_float = query.astype(np.float32)
    for lines, example in _load_page_examples():
        correlation = float(
            cv2.matchTemplate(query, example, cv2.TM_CCOEFF_NORMED)[0, 0]
        )
        pixel_difference = float(
            np.mean(np.abs(query_float - example.astype(np.float32)))
        )
        pixel_similarity = 1.0 - pixel_difference / 255.0
        score = min(correlation, pixel_similarity)
        if score > best_score:
            best_score = score
            if (
                correlation >= PAGE_MINIMUM_CORRELATION
                and pixel_similarity >= PAGE_MINIMUM_PIXEL_SIMILARITY
            ):
                best_lines = lines
            else:
                best_lines = None
    return best_lines, best_score
