"""Public page/region OCR orchestration."""

from __future__ import annotations

import logging
import os
from typing import List, Tuple

import numpy as np

from .character_segmentation import remove_box_borders, segment_words
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


def _looks_like_projection_fragment(
    region: np.ndarray,
    word_boxes: list[tuple[int, int, int, int]],
) -> bool:
    """Reject notebook rules and partial ascender/descender projection rows."""
    if not word_boxes:
        return True
    region_height = max(1, region.shape[0])
    word_heights = [height for _, _, _, height in word_boxes]
    median_word_height = float(np.median(word_heights))
    if median_word_height < region_height * 0.60:
        return True
    aspects = [width / max(1, height) for _, _, width, height in word_boxes]
    if len(word_boxes) <= 3 and max(aspects, default=0.0) > 9.0:
        return True
    return False


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
    natural_regions = []
    border_flags = []
    calibrated_matches = {}
    for region in binary_regions:
        sequence_region, cnn_binary = prepare_text_region(region)
        # Page segmentation already removes diagram containers. Running the
        # legacy border eraser on a tight handwriting crop mistakes connected
        # cursive strokes for a frame and deletes real characters.
        cleaned_regions.append(cnn_binary)
        natural_regions.append(sequence_region)
        border_flags.append(False)

    # Projection-based page segmentation can emit shallow duplicates made of
    # ascenders, descenders, or a notebook rule. Compare against the page's
    # normal handwriting height so those fragments never reach either model.
    plausible_indexes = [
        index
        for index, region in enumerate(cleaned_regions)
        if is_plausible_text_region(region)
    ]
    minimum_page_line_height = 0
    if len(plausible_indexes) >= 5:
        median_height = float(
            np.median([cleaned_regions[index].shape[0] for index in plausible_indexes])
        )
        minimum_page_line_height = max(14, int(median_height * 0.72))

    word_regions = []
    word_layouts = {}
    for index, (sequence_region, cnn_binary) in enumerate(
        zip(natural_regions, cleaned_regions)
    ):
        # Judge text evidence from the cleaned mask, not from the natural page
        # crop sent to TrOCR. Ruled paper and shadows must not make an empty
        # region look valid, but they may remain visible to the sequence model.
        if (
            index in plausible_indexes
            and cnn_binary.shape[0] >= minimum_page_line_height
        ):
            boxes = segment_words(cnn_binary)
            if _looks_like_projection_fragment(cnn_binary, boxes):
                logger.info("Rejecting shallow/rule projection fragment %d", index)
                continue
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
                word_layouts[index] = (len(word_regions), len(boxes))
                word_regions.extend(
                    sequence_region[y:y + height, x:x + width]
                    for x, y, width, height in boxes
                )

    try:
        recognized_words = _recognize_lines_with_confidence(word_regions)
        minimum_confidence = float(
            os.getenv("OCR_MIN_WORD_CONFIDENCE", "0.30")
        )
        result = [("", has_border) for has_border in border_flags]
        for index, calibrated_text in calibrated_matches.items():
            result[index] = (calibrated_text, border_flags[index])
        accepted_lines = []
        for index, (offset, count) in word_layouts.items():
            predictions = recognized_words[offset:offset + count]
            accepted_words = []
            accepted_confidences = []
            for text, confidence in predictions:
                text = " ".join(text.strip().split())
                if (
                    text
                    and confidence >= minimum_confidence
                    and not looks_like_sequence_hallucination(text)
                ):
                    accepted_words.append(text)
                    accepted_confidences.append(confidence)
                else:
                    logger.info(
                        "Rejecting uncertain word OCR guess %r (confidence %.3f)",
                        text,
                        confidence,
                    )
            if accepted_words:
                text = " ".join(accepted_words)
                confidence = float(np.mean(accepted_confidences))
                accepted_lines.append((index, text, confidence))
            else:
                logger.info(
                    "Rejecting OCR line %d because no word passed confidence",
                    index,
                )

        # CNN hypotheses cannot affect rejected/blank TrOCR lines. Segmenting
        # and classifying their glyphs was pure overhead, so run the identical
        # helper/fusion path only for accepted lines.
        cnn_hypotheses = extract_cnn_hypotheses_batch(
            [cleaned_regions[index] for index, _, _ in accepted_lines]
        )
        for (index, text, confidence), cnn_hypothesis in zip(
            accepted_lines, cnn_hypotheses
        ):
            result[index] = (
                fuse_sequence_with_cnn(text, confidence, cnn_hypothesis),
                border_flags[index],
            )

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
