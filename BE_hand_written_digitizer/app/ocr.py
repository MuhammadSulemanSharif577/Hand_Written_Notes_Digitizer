"""Backward-compatible facade for the OCR subsystem.

Implementation details live in :mod:`ocr_components`:

* ``character_segmentation`` - OpenCV contour and line ordering
* ``cnn_model`` - EMNIST model loading and glyph prediction
* ``region_preparation`` - ruled-line cleanup and input validation
* ``fusion`` - CNN hypothesis assembly and TrOCR character assistance
* ``pipeline`` - public OCR orchestration

Keeping this facade means existing code can continue importing from ``ocr``.
"""

try:  # Package import: ``from app.ocr import ...``
    from .ocr_components.character_segmentation import (
        merge_overlapping_boxes,
        remove_box_borders,
        segment_characters,
        split_wide_box,
    )
    from .ocr_components.cnn_model import (
        label_to_char,
        load_ocr_model,
        predict_character,
        predict_characters,
        prepare_character,
    )
    from .ocr_components.fusion import (
        CnnHypothesis,
        _assemble_cnn_hypothesis,
        _extract_cnn_hypotheses_batch,
        _extract_text_with_cnn,
        _extract_text_with_cnn_batch,
        _fuse_sequence_with_cnn,
    )
    from .ocr_components.pipeline import (
        extract_text_from_region,
        extract_text_from_regions,
    )
    from .ocr_components.region_preparation import (
        _is_plausible_text_region,
        _looks_like_sequence_hallucination,
        _prepare_text_region,
    )
except ImportError:  # Legacy startup with ``app`` directly on sys.path.
    from ocr_components.character_segmentation import (
        merge_overlapping_boxes,
        remove_box_borders,
        segment_characters,
        split_wide_box,
    )
    from ocr_components.cnn_model import (
        label_to_char,
        load_ocr_model,
        predict_character,
        predict_characters,
        prepare_character,
    )
    from ocr_components.fusion import (
        CnnHypothesis,
        _assemble_cnn_hypothesis,
        _extract_cnn_hypotheses_batch,
        _extract_text_with_cnn,
        _extract_text_with_cnn_batch,
        _fuse_sequence_with_cnn,
    )
    from ocr_components.pipeline import (
        extract_text_from_region,
        extract_text_from_regions,
    )
    from ocr_components.region_preparation import (
        _is_plausible_text_region,
        _looks_like_sequence_hallucination,
        _prepare_text_region,
    )


__all__ = [
    "CnnHypothesis",
    "extract_text_from_region",
    "extract_text_from_regions",
    "label_to_char",
    "load_ocr_model",
    "merge_overlapping_boxes",
    "predict_character",
    "predict_characters",
    "prepare_character",
    "remove_box_borders",
    "segment_characters",
    "split_wide_box",
]

