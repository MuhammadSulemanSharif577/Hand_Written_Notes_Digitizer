"""CNN hypothesis assembly and conservative TrOCR/CNN character fusion."""

from __future__ import annotations

import os
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List, Tuple

import numpy as np

from .character_segmentation import segment_characters
from .cnn_model import load_ocr_model, predict_characters


@dataclass
class CnnHypothesis:
    """CNN text plus the unfiltered glyph stream and per-glyph confidence."""

    text: str
    helper_text: str
    helper_confidences: List[float]


def assemble_cnn_hypothesis(
    cleaned_region: np.ndarray,
    lines_of_boxes: List[List[Tuple[int, int, int, int]]],
    predictions: List[Tuple[str, float]],
) -> CnnHypothesis:
    """Rebuild spatial lines and word gaps from character predictions."""
    lines_text = []
    helper_lines = []
    helper_line_confidences = []
    prediction_offset = 0

    for line in lines_of_boxes:
        widths = [width for _, _, width, _ in line]
        median_width = np.median(widths) if widths else 10.0
        space_threshold = max(8.0, median_width * 0.7)
        line_predictions = predictions[
            prediction_offset:prediction_offset + len(line)
        ]
        prediction_offset += len(line)

        line_text = ""
        helper_text = ""
        helper_confidences = []
        for index, (box, (character, confidence)) in enumerate(
            zip(line, line_predictions)
        ):
            x, _, width, _ = box
            helper_text += character
            helper_confidences.append(confidence)
            if confidence >= 0.35:
                line_text += character

            if index < len(line) - 1:
                next_x = line[index + 1][0]
                gap = next_x - (x + width)
                if gap >= space_threshold:
                    helper_text += " "
                    helper_confidences.append(1.0)
                if gap >= space_threshold and line_text and confidence >= 0.35:
                    line_text += " "

        if line_text.strip():
            lines_text.append(line_text)
        if helper_text.strip():
            helper_lines.append(helper_text)
            helper_line_confidences.append(helper_confidences)

    flattened_helper = " ".join(helper_lines)
    flattened_confidences = []
    for line_index, confidences in enumerate(helper_line_confidences):
        if line_index:
            flattened_confidences.append(1.0)
        flattened_confidences.extend(confidences)
    return CnnHypothesis(
        text="\n".join(lines_text),
        helper_text=flattened_helper,
        helper_confidences=flattened_confidences,
    )


def extract_cnn_hypotheses_batch(
    cleaned_regions: List[np.ndarray],
) -> List[CnnHypothesis]:
    """Predict every isolated glyph from all page rows in one CNN call."""
    layouts = [segment_characters(region) for region in cleaned_regions]
    all_crops = []
    for region, lines in zip(cleaned_regions, layouts):
        for line in lines:
            all_crops.extend(
                [region[y:y + height, x:x + width] for x, y, width, height in line]
            )
    if not all_crops:
        return [CnnHypothesis("", "", []) for _ in cleaned_regions]

    model = load_ocr_model()
    all_predictions = predict_characters(all_crops, model)
    results = []
    offset = 0
    for region, lines in zip(cleaned_regions, layouts):
        count = sum(len(line) for line in lines)
        region_predictions = all_predictions[offset:offset + count]
        offset += count
        results.append(
            assemble_cnn_hypothesis(region, lines, region_predictions)
        )
    return results


def extract_text_with_cnn_batch(cleaned_regions: List[np.ndarray]) -> List[str]:
    """Return only the filtered CNN text for multiple regions."""
    return [
        hypothesis.text
        for hypothesis in extract_cnn_hypotheses_batch(cleaned_regions)
    ]


def extract_text_with_cnn(cleaned_region: np.ndarray) -> str:
    """Return the filtered CNN text for one region."""
    return extract_text_with_cnn_batch([cleaned_region])[0]


def fuse_sequence_with_cnn(
    sequence_text: str,
    sequence_confidence: float,
    cnn: CnnHypothesis,
) -> str:
    """Repair only aligned, high-confidence TrOCR glyphs with the CNN."""
    sequence_positions = [
        (index, character)
        for index, character in enumerate(sequence_text)
        if character.isalnum()
    ]
    cnn_positions = [
        (index, character, cnn.helper_confidences[index])
        for index, character in enumerate(cnn.helper_text)
        if character.isalnum() and index < len(cnn.helper_confidences)
    ]
    if not sequence_positions or not cnn_positions:
        return sequence_text

    sequence_alnum = "".join(character.upper() for _, character in sequence_positions)
    cnn_alnum = "".join(character.upper() for _, character, _ in cnn_positions)
    matcher = SequenceMatcher(None, sequence_alnum, cnn_alnum, autojunk=False)
    result = list(sequence_text)
    minimum_confidence = float(os.getenv("OCR_CNN_HELPER_CONFIDENCE", "0.82"))
    identifier_like = sum(character.isdigit() for character in sequence_alnum) >= 2
    confusion_groups = (
        set("0ODQ"),
        set("1ILT"),
        set("2Z"),
        set("5S"),
        set("6G"),
        set("8B"),
        set("9GQ"),
    )

    for operation, seq_start, seq_end, cnn_start, cnn_end in matcher.get_opcodes():
        if operation != "replace" or seq_end - seq_start != cnn_end - cnn_start:
            continue
        for offset in range(seq_end - seq_start):
            sequence_index, sequence_character = sequence_positions[seq_start + offset]
            _, cnn_character, cnn_confidence = cnn_positions[cnn_start + offset]
            sequence_upper = sequence_character.upper()
            cnn_upper = cnn_character.upper()
            if sequence_upper == cnn_upper or cnn_confidence < minimum_confidence:
                continue

            ambiguous_pair = any(
                sequence_upper in group and cnn_upper in group
                for group in confusion_groups
            )
            identifier_digit = (
                identifier_like
                and (sequence_character.isdigit() or cnn_character.isdigit())
                and cnn_confidence >= 0.88
            )
            exceptionally_strong = (
                sequence_confidence < 0.65 and cnn_confidence >= 0.97
            )
            if ambiguous_pair or identifier_digit or exceptionally_strong:
                result[sequence_index] = (
                    cnn_upper if sequence_character.isupper() else cnn_character
                )
    return "".join(result)


# Compatibility aliases used by the original public module.
_assemble_cnn_hypothesis = assemble_cnn_hypothesis
_extract_cnn_hypotheses_batch = extract_cnn_hypotheses_batch
_extract_text_with_cnn_batch = extract_text_with_cnn_batch
_extract_text_with_cnn = extract_text_with_cnn
_fuse_sequence_with_cnn = fuse_sequence_with_cnn

