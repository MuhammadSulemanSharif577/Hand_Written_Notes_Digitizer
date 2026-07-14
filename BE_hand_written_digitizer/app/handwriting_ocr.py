"""Lazy line-level handwriting OCR using Microsoft's TrOCR model.

The existing EMNIST CNN is useful for isolated glyphs, but it has no language
context and cannot decode connected handwriting.  TrOCR is loaded only when an
upload is processed, so authentication and other API routes do not pay the
startup cost.  If the model/runtime is unavailable, callers can fall back to
the existing CNN OCR.
"""

from __future__ import annotations

import logging
import os
import json
from typing import List, Tuple

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

_LOCAL_HANDWRITTEN_MODEL_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "models", "trocr-small-handwritten")
)
_LOCAL_PRINTED_MODEL_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "models", "trocr-small-printed")
)
_LOCAL_CALIBRATED_MODEL_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "models", "trocr-writer-calibrated")
)
_LOCAL_FINE_TUNED_MODEL_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "models", "trocr-writer-calibrated-v2")
)
_LOCAL_FINE_TUNED_MODEL_V3_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "models", "trocr-writer-calibrated-v3")
)


def _is_promoted_model(model_dir: str) -> bool:
    marker = os.path.join(model_dir, "promotion.json")
    weights = os.path.join(model_dir, "model.safetensors")
    if not os.path.exists(marker) or not os.path.exists(weights):
        return False
    try:
        with open(marker, "r", encoding="utf-8") as handle:
            return bool(json.load(handle).get("promoted"))
    except (OSError, ValueError):
        return False


if _is_promoted_model(_LOCAL_FINE_TUNED_MODEL_V3_DIR):
    _DEFAULT_MODEL = _LOCAL_FINE_TUNED_MODEL_V3_DIR
elif _is_promoted_model(_LOCAL_FINE_TUNED_MODEL_DIR):
    _DEFAULT_MODEL = _LOCAL_FINE_TUNED_MODEL_DIR
elif (
    os.path.exists(os.path.join(_LOCAL_CALIBRATED_MODEL_DIR, "model.safetensors"))
    and os.path.exists(os.path.join(_LOCAL_CALIBRATED_MODEL_DIR, "calibration.json"))
):
    _DEFAULT_MODEL = _LOCAL_CALIBRATED_MODEL_DIR
elif os.path.exists(os.path.join(_LOCAL_PRINTED_MODEL_DIR, "model.safetensors")):
    _DEFAULT_MODEL = _LOCAL_PRINTED_MODEL_DIR
elif os.path.exists(os.path.join(_LOCAL_HANDWRITTEN_MODEL_DIR, "pytorch_model.bin")):
    _DEFAULT_MODEL = _LOCAL_HANDWRITTEN_MODEL_DIR
else:
    _DEFAULT_MODEL = "microsoft/trocr-small-printed"
MODEL_ID = os.getenv("HANDWRITING_OCR_MODEL", _DEFAULT_MODEL)
_processor = None
_model = None
_load_error: Exception | None = None


def _load_model():
    """Load the processor/model once, on the first OCR request."""
    global _processor, _model, _load_error
    if _processor is not None and _model is not None:
        return _processor, _model
    if _load_error is not None:
        raise RuntimeError("Handwriting OCR model is unavailable") from _load_error

    try:
        # TensorFlow is already loaded by the existing CNN service. Limit
        # PyTorch/OpenMP thread pools to avoid Windows DLL contention and keep
        # CPU inference predictable in the same FastAPI process.
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        os.environ.setdefault("MKL_NUM_THREADS", "1")
        os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
        import torch
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel

        torch.set_num_threads(1)

        _processor = TrOCRProcessor.from_pretrained(MODEL_ID, use_fast=False)
        _model = VisionEncoderDecoderModel.from_pretrained(MODEL_ID)
        _model.to(torch.device("cpu"))
        _model.eval()
        return _processor, _model
    except Exception as exc:  # pragma: no cover - depends on local model/cache
        _load_error = exc
        logger.exception("Unable to load handwriting OCR model '%s'", MODEL_ID)
        raise RuntimeError(
            "Handwriting OCR model could not be loaded. "
            "The CNN fallback will be used."
        ) from exc


def _region_to_pil(region: np.ndarray) -> Image.Image:
    """Convert a cleaned BGR/grayscale crop to TrOCR's normal scan format."""
    if region.ndim == 3:
        rgb = cv2.cvtColor(region, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb).convert("RGB")

    binary_region = region
    if binary_region.ndim == 3:
        gray = cv2.cvtColor(binary_region, cv2.COLOR_BGR2GRAY)
    else:
        gray = binary_region
    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    # The backend mask is white foreground on black. TrOCR expects dark ink
    # on a light page, matching its handwritten training images.
    gray = cv2.bitwise_not(gray)
    return Image.fromarray(gray).convert("RGB")


def recognize_lines_with_confidence(
    binary_regions: List[np.ndarray],
) -> List[Tuple[str, float]]:
    """Recognize text lines and return decoder confidence for every line.

    Sequence decoders can produce fluent-looking text even for an empty ruled
    line.  Returning the geometric mean probability of the generated tokens
    lets the page pipeline suppress those guesses instead of presenting them
    as extracted text.
    """
    if not binary_regions:
        return []

    processor, model = _load_model()
    images = [_region_to_pil(region) for region in binary_regions]
    inputs = processor(images=images, return_tensors="pt")
    pixel_values = inputs.pixel_values

    import torch

    with torch.inference_mode():
        generated = model.generate(
            pixel_values,
            max_new_tokens=48,
            num_beams=1,
            return_dict_in_generate=True,
            output_scores=True,
        )
    texts = processor.batch_decode(generated.sequences, skip_special_tokens=True)

    # For TrOCR the first sequence item is the decoder start token and each
    # subsequent item corresponds to one entry in ``generated.scores``.
    sequence_ids = generated.sequences[:, 1:1 + len(generated.scores)]
    batch_size = sequence_ids.shape[0]
    log_probability_sum = torch.zeros(batch_size, dtype=torch.float32)
    token_counts = torch.zeros(batch_size, dtype=torch.float32)
    active = torch.ones(batch_size, dtype=torch.bool)
    pad_token_id = model.config.pad_token_id
    eos_token_id = model.config.eos_token_id

    for step, logits in enumerate(generated.scores):
        token_ids = sequence_ids[:, step]
        token_log_probabilities = torch.log_softmax(logits.float(), dim=-1)
        selected = token_log_probabilities.gather(1, token_ids.unsqueeze(1)).squeeze(1)
        valid = active.clone()
        if pad_token_id is not None:
            valid &= token_ids.ne(pad_token_id)
        log_probability_sum += selected.cpu() * valid.cpu()
        token_counts += valid.cpu().float()
        if eos_token_id is not None:
            active &= token_ids.ne(eos_token_id).cpu()

    confidence = torch.exp(log_probability_sum / token_counts.clamp_min(1.0))
    normalized = [" ".join(text.strip().split()) for text in texts]
    return list(zip(normalized, confidence.tolist()))


def recognize_lines(binary_regions: List[np.ndarray]) -> List[str]:
    """Backward-compatible text-only wrapper."""
    return [text for text, _ in recognize_lines_with_confidence(binary_regions)]
