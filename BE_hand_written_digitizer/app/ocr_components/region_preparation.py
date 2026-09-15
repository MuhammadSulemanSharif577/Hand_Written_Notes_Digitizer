"""Text-region cleanup, ruled-line rejection and hallucination guards."""

from __future__ import annotations

import os
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
        # A global Otsu threshold turns the shadowed side of a phone photo into
        # a solid black block. Line-local adaptive thresholding follows the
        # paper illumination instead and retains only locally darker strokes.
        minimum_dimension = max(3, min(gray.shape[:2]))
        block_size = min(
            31,
            minimum_dimension
            if minimum_dimension % 2
            else minimum_dimension - 1,
        )
        block_size = max(3, block_size)
        ink = cv2.adaptiveThreshold(
            cv2.GaussianBlur(gray, (3, 3), 0),
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            block_size,
            8,
        )
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
    original_ink = ink.copy()

    # Protect genuinely dark or saturated pen strokes when a notebook rule
    # crosses through a word. The rule itself is normally neutral gray and
    # lighter than black ink; blue/purple ballpoint is identified by hue.
    hsv = cv2.cvtColor(source_color, cv2.COLOR_BGR2HSV)
    saturated_pen = cv2.inRange(
        hsv,
        np.array([72, 32, 20], dtype=np.uint8),
        np.array([158, 255, 250], dtype=np.uint8),
    )

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

    # Morphological opening only catches perfectly horizontal rules. In phone
    # photographs the same notebook rules are commonly slanted or curved by a
    # few degrees, and page borders appear as tall edge fragments. Detect only
    # page-spanning line segments so underlines, equation bars, and normal
    # character strokes remain available to OCR.
    rule_mask = horizontal_rules.copy()
    page_border_mask = np.zeros_like(ink)
    detected_lines = cv2.HoughLinesP(
        ink,
        1,
        np.pi / 720,
        threshold=max(18, int(width * 0.18)),
        minLineLength=max(35, int(width * 0.58)),
        maxLineGap=max(8, int(width * 0.10)),
    )
    if detected_lines is not None:
        for x1, y1, x2, y2 in detected_lines[:, 0]:
            angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
            length = float(np.hypot(x2 - x1, y2 - y1))
            is_page_rule = angle <= 7.0 and length >= width * 0.58
            near_side = min(x1, x2) <= width * 0.25 or max(x1, x2) >= width * 0.75
            is_page_border = (
                angle >= 80.0
                and near_side
                and length >= height * 0.45
            )
            if is_page_rule or is_page_border:
                cv2.line(
                    rule_mask,
                    (x1, y1),
                    (x2, y2),
                    255,
                    max(3, int(height * 0.10)),
                )
                if is_page_border:
                    cv2.line(
                        page_border_mask,
                        (x1, y1),
                        (x2, y2),
                        255,
                        max(3, int(width * 0.008)),
                    )
    without_rules = cv2.bitwise_and(ink, cv2.bitwise_not(rule_mask))
    # Restore handwriting at rule crossings using character-shape evidence,
    # not darkness alone. Photographed notebook rules can be very dark near a
    # shadow; the old strong-ink restoration therefore rebuilt the complete
    # background line. Real letters normally retain short vertical/curved
    # strokes away from the rule, which safely identify the crossing area.
    vertical_support = cv2.morphologyEx(
        original_ink,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (1, max(3, min(7, int(height * 0.16)))),
        ),
    )
    character_neighborhood = cv2.dilate(
        vertical_support,
        cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (
                max(5, min(11, int(height * 0.18))),
                max(5, min(11, int(height * 0.18))),
            ),
        ),
        iterations=1,
    )
    protected_pen = cv2.bitwise_and(
        original_ink,
        cv2.bitwise_or(saturated_pen, character_neighborhood),
    )
    # A photographed page edge/margin has strong vertical support too. Do not
    # let it re-enter through the character-restoration path; genuine glyphs
    # retain the padding added by line segmentation.
    interior = np.zeros_like(ink)
    margin_x = max(3, min(int(width * 0.04), max(3, width // 10)))
    margin_y = max(2, min(int(height * 0.04), max(2, height // 10)))
    interior[
        margin_y:max(margin_y + 1, height - margin_y),
        margin_x:max(margin_x + 1, width - margin_x),
    ] = 255
    protected_pen = cv2.bitwise_and(protected_pen, interior)
    ink = cv2.bitwise_or(without_rules, protected_pen)
    ink = cv2.bitwise_and(ink, cv2.bitwise_not(page_border_mask))

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

    # A slanted notebook rule can touch a letter and make one contour span the
    # whole crop, defeating component filtering. Locate the true text window
    # by column density instead: a thin rule contributes only a few pixels per
    # column, whereas character stems occupy a meaningful part of line height.
    # Apply a wider boundary exclusion only to page-spanning crops; tight word
    # crops must keep letters that naturally begin near x=0.
    edge_margin = max(3, int(width * 0.045)) if width >= 500 else 2
    column_counts = np.count_nonzero(ink, axis=0)
    minimum_column_ink = max(3, int(height * 0.09))
    dense_columns = np.flatnonzero(column_counts >= minimum_column_ink)
    dense_columns = dense_columns[
        (dense_columns >= edge_margin)
        & (dense_columns < width - edge_margin)
    ]
    if dense_columns.size:
        text_x0 = max(0, int(dense_columns[0]) - max(4, int(height * 0.20)))
        text_x1 = min(
            width,
            int(dense_columns[-1]) + max(5, int(height * 0.20)) + 1,
        )
        if text_x1 - text_x0 >= 12:
            ink[:, :text_x0] = 0
            ink[:, text_x1:] = 0

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

    # TrOCR was pretrained on natural handwriting scans and can use stroke
    # color/texture that a hard binary renderer destroys. Keep the untouched
    # line crop by default; the cleaned binary remains the plausibility mask and
    # CNN input. The normalized renderer is retained as an opt-in diagnostic.
    use_original_sequence = os.getenv(
        "OCR_SEQUENCE_USE_ORIGINAL",
        "true",
    ).lower() in {"1", "true", "yes"}
    if use_original_sequence:
        # Keep the natural pixels, but crop them to exactly the same ink window
        # as the binary helper. Besides removing empty ruled-paper margins,
        # this alignment allows reliable word boxes to be mapped back onto the
        # untouched photograph.
        return source_color[y0:y1, x0:x1], ink[y0:y1, x0:x1]

    sequence_color = np.full_like(source_color, 255)
    sequence_color[ink > 0] = (12, 12, 12)
    return sequence_color[y0:y1, x0:x1], ink[y0:y1, x0:x1]


# Compatibility aliases used by the original public module.
_is_plausible_text_region = is_plausible_text_region
_looks_like_sequence_hallucination = looks_like_sequence_hallucination
_prepare_text_region = prepare_text_region
