"""EMNIST CNN loading, glyph normalization and batched prediction."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Tuple

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import cv2
import numpy as np
import tensorflow as tf

logging.getLogger("tensorflow").setLevel(logging.ERROR)
tf.get_logger().setLevel("ERROR")

_model = None


def load_ocr_model():
    """Load the EMNIST CNN lazily as a process-wide singleton."""
    global _model
    if _model is None:
        model_path = Path(__file__).resolve().parents[1] / "trained_model" / "ocr_model.keras"
        if not model_path.exists():
            raise FileNotFoundError(f"Trained OCR model not found at {model_path}")
        _model = tf.keras.models.load_model(str(model_path))
    return _model


def label_to_char(label: int) -> str:
    """Map an EMNIST ByClass class index to its character."""
    if 0 <= label <= 9:
        return str(label)
    if 10 <= label <= 35:
        return chr(label - 10 + 65)
    if 36 <= label <= 61:
        return chr(label - 36 + 97)
    return ""


def prepare_character(char_crop: np.ndarray) -> np.ndarray:
    """Normalize one binary glyph to the CNN's centered 28x28 input."""
    height, width = char_crop.shape[:2]
    if height == 0 or width == 0:
        return np.zeros((28, 28, 1), dtype=np.float32)

    max_dimension = max(width, height)
    padding = max(4, int(max_dimension * 0.15))
    canvas_size = max_dimension + 2 * padding
    canvas = np.zeros((canvas_size, canvas_size), dtype=np.uint8)
    offset_x = padding + (max_dimension - width) // 2
    offset_y = padding + (max_dimension - height) // 2
    canvas[offset_y:offset_y + height, offset_x:offset_x + width] = char_crop

    resized = cv2.resize(canvas, (28, 28), interpolation=cv2.INTER_AREA)
    normalized = resized.astype(np.float32) / 255.0
    return normalized.reshape(28, 28, 1)


def predict_characters(char_crops: List[np.ndarray], model) -> List[Tuple[str, float]]:
    """Predict multiple glyphs in one CNN invocation."""
    if not char_crops:
        return []
    batch = np.stack([prepare_character(crop) for crop in char_crops])
    predictions = model.predict(batch, verbose=0)
    return [
        (label_to_char(int(np.argmax(probabilities))), float(np.max(probabilities)))
        for probabilities in predictions
    ]


def predict_character(char_crop: np.ndarray, model) -> str:
    """Backward-compatible single-character prediction wrapper."""
    predictions = predict_characters([char_crop], model)
    return predictions[0][0] if predictions else ""

