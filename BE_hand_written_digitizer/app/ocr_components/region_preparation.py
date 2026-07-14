"""Text-region cleanup, ruled-line rejection and hallucination guards."""

from __future__ import annotations

import re
from typing import Tuple

import cv2
import numpy as np


def is_plausible_text_region(region: np.ndarray) -> bool:
    """Reject empty crops and residual notebook rules before OCR inference."""
    if region is None or region.size == 0:
        return False
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY) if region.ndim == 3 else region
    height, width = gray.shape[:2]
    if height < 14 or width < 12:
        return False

    ink = (gray < 210).astype(np.uint8) * 255
    ink_count = int(np.count_nonzero(ink))
    if ink_count < max(18, int(height * width * 0.004)):
        return False
    coordinates = cv2.findNonZero(ink)
    if coordinates is None:
        return False
    _, _, ink_width, ink_height = cv2.boundingRect(coordinates)
    if ink_height < 7:
        return False
    if ink_width / max(1, ink_height) > 18 and ink_height <= 10:
        return False
    return True


def looks_like_sequence_hallucination(text: str) -> bool:
    """Detect fluent decoder patterns unsupported by a normal text line."""
    tokens = text.split()
    if not tokens:
        return True
    isolated = [token for token in tokens if len(re.sub(r"\W", "", token)) == 1]
    if len(tokens) >= 5 and len(isolated) / len(tokens) >= 0.70:
        return True
    punctuation_only = [
        token for token in tokens if not re.search(r"[A-Za-z0-9]", token)
    ]
    if len(tokens) >= 5 and len(punctuation_only) / len(tokens) >= 0.50:
        return True
    if re.search(r"(?:[:._-]\s*){4,}", text):
        return True
    if re.search(r"(?:\b[0-9]\b[\s,]*){6,}", text):
        return True
    return False


def prepare_text_region(region: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Create cleaned color and binary crops for TrOCR and the CNN."""
    if region.ndim == 3:
        source_color = region
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        ink = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )[1]
    else:
        gray = region
        unique_values = np.unique(gray)
        looks_binary = unique_values.size <= 3
        if looks_binary and float(np.mean(gray)) < 127:
            ink = gray.copy()
            source_gray = cv2.bitwise_not(gray)
        else:
            ink = cv2.threshold(
                gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )[1]
            source_gray = gray
        source_color = cv2.cvtColor(source_gray, cv2.COLOR_GRAY2BGR)

    height, width = ink.shape
    if height == 0 or width == 0:
        return source_color, ink

    # Remove only genuinely continuous horizontal page rules.
    line_width = max(45, int(width * 0.35))
    horizontal_rules = cv2.morphologyEx(
        ink,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (line_width, 1)),
    )
    horizontal_rules = cv2.dilate(
        horizontal_rules,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
        iterations=1,
    )
    ink = cv2.bitwise_and(ink, cv2.bitwise_not(horizontal_rules))

    contours, _ = cv2.findContours(ink, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, _, component_width, component_height = cv2.boundingRect(contour)
        is_shallow_rule_piece = (
            component_height <= 3
            and component_width >= max(20, int(width * 0.05))
        )
        is_page_edge_piece = (
            (x <= 2 or x + component_width >= width - 2)
            and component_height >= height * 0.45
            and component_width <= max(8, int(height * 0.35))
        )
        if is_shallow_rule_piece or is_page_edge_piece:
            cv2.drawContours(ink, [contour], -1, 0, thickness=-1)

    # Keep every surviving glyph cluster. A previous "dominant cluster" rule
    # deleted valid words whenever a writer left a large natural space (for
    # example it removed "3. Use Cases:" before "Configure/Create Exam Paper").
    # Page-edge and ruled-line residue has already been removed above, so
    # dropping secondary clusters here is both unnecessary and destructive.

    coordinates = cv2.findNonZero(ink)
    if coordinates is None:
        return np.full_like(source_color, 255), ink
    x, y, ink_width, ink_height = cv2.boundingRect(coordinates)
    padding = max(4, int(max(ink_height, 1) * 0.20))
    x0 = max(0, x - padding)
    y0 = max(0, y - padding)
    x1 = min(width, x + ink_width + padding)
    y1 = min(height, y + ink_height + padding)

    sequence_color = np.full_like(source_color, 255)
    sequence_color[ink > 0] = source_color[ink > 0]
    return sequence_color[y0:y1, x0:x1], ink[y0:y1, x0:x1]


# Compatibility aliases used by the original public module.
_is_plausible_text_region = is_plausible_text_region
_looks_like_sequence_hallucination = looks_like_sequence_hallucination
_prepare_text_region = prepare_text_region
