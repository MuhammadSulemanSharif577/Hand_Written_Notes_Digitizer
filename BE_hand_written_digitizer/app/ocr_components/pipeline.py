"""Public page/region OCR orchestration."""

from __future__ import annotations

import logging
import os
from typing import List, Tuple

import numpy as np

from .character_segmentation import remove_box_borders
from .fusion import (
    extract_cnn_hypotheses_batch,
    extract_text_with_cnn,
    extract_text_with_cnn_batch,
    fuse_sequence_with_cnn,
)
from .region_preparation import (
    is_plausible_text_region,
    looks_like_sequence_hallucination,
    prepare_text_region,
)

logger = logging.getLogger(__name__)


def _recognize_lines_with_confidence(regions):
    try:
        from ..handwriting_ocr import recognize_lines_with_confidence
    except (ImportError, ValueError):
        from handwriting_ocr import recognize_lines_with_confidence
    return recognize_lines_with_confidence(regions)


def _recognize_lines(regions):
    try:
        from ..handwriting_ocr import recognize_lines
    except (ImportError, ValueError):
        from handwriting_ocr import recognize_lines
    return recognize_lines(regions)


def _match_calibrated_line(region):
    try:
        from ..writer_calibration import match_calibrated_line
    except (ImportError, ValueError):
        from writer_calibration import match_calibrated_line
    return match_calibrated_line(region)


def extract_text_from_regions(
    binary_regions: List[np.ndarray],
) -> List[Tuple[str, bool]]:
    """Recognize page text rows with TrOCR, CNN assistance and calibration."""
    cleaned_regions = []
    sequence_regions = []
    sequence_indexes = []
    border_flags = []
    calibrated_matches = {}
    for region in binary_regions:
        sequence_region, cnn_binary = prepare_text_region(region)
        # Page segmentation already removes diagram containers. Running the
        # legacy border eraser on a tight handwriting crop mistakes connected
        # cursive strokes for a frame and deletes real characters.
        cleaned_regions.append(cnn_binary)
        border_flags.append(False)
        if is_plausible_text_region(sequence_region):
            index = len(cleaned_regions) - 1
            try:
                calibrated_text, score = _match_calibrated_line(sequence_region)
            except Exception as exc:
                logger.warning("Visual writer calibration unavailable: %s", exc)
                calibrated_text, score = None, 0.0
            if calibrated_text:
                calibrated_matches[index] = calibrated_text
                logger.info(
                    "Applied visual line calibration %r (score %.3f)",
                    calibrated_text,
                    score,
                )
            else:
                sequence_indexes.append(index)
                sequence_regions.append(sequence_region)

    try:
        recognized = _recognize_lines_with_confidence(sequence_regions)
        minimum_confidence = float(
            os.getenv("OCR_MIN_SEQUENCE_CONFIDENCE", "0.55")
        )
        result = [("", has_border) for has_border in border_flags]
        for index, calibrated_text in calibrated_matches.items():
            result[index] = (calibrated_text, border_flags[index])
        cnn_hypotheses = extract_cnn_hypotheses_batch(
            [cleaned_regions[index] for index in sequence_indexes]
        )

        for index, (text, confidence), cnn_hypothesis in zip(
            sequence_indexes, recognized, cnn_hypotheses
        ):
            if (
                text
                and confidence >= minimum_confidence
                and not looks_like_sequence_hallucination(text)
            ):
                result[index] = (
                    fuse_sequence_with_cnn(text, confidence, cnn_hypothesis),
                    border_flags[index],
                )
            else:
                logger.info(
                    "Rejecting uncertain sequence OCR guess %r (confidence %.3f)",
                    text,
                    confidence,
                )
                # The isolated-character CNN is a conservative aligned helper,
                # not a line recognizer. Falling back to its complete glyph
                # stream is what produced irregular random characters.

        return result
    except Exception as exc:
        logger.warning("Sequence OCR unavailable; suppressing unsafe CNN line fallback: %s", exc)
        result = [("", has_border) for has_border in border_flags]
        for index, calibrated_text in calibrated_matches.items():
            result[index] = (calibrated_text, border_flags[index])
        return result


def extract_text_from_region(
    binary_region: np.ndarray,
    prefer_sequence: bool = True,
) -> Tuple[str, bool]:
    """Recognize one legacy text region and report an outer-border flag."""
    source_region, cnn_binary = prepare_text_region(binary_region)
    cleaned_region, has_border = remove_box_borders(cnn_binary)
    if prefer_sequence:
        try:
            text = _recognize_lines([source_region])[0]
            if text:
                return text, has_border
        except Exception as exc:
            logger.warning("Falling back to EMNIST CNN OCR: %s", exc)
    return extract_text_with_cnn(cleaned_region), has_border
