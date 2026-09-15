"""Background OCR model warm-up orchestration.

The API remains available while the large local models are loaded. Model
loaders have their own locks, so an immediate upload safely waits for the same
singleton instead of loading a duplicate copy.
"""

from __future__ import annotations

import logging
import threading
from time import perf_counter

logger = logging.getLogger(__name__)

_warmup_thread: threading.Thread | None = None
_thread_lock = threading.Lock()


def _warm_models() -> None:
    started = perf_counter()
    try:
        from ..handwriting_ocr import warmup_handwriting_model

        warmup_handwriting_model()
        logger.info("TrOCR warm-up completed in %.2fs", perf_counter() - started)

        cnn_started = perf_counter()
        from ..ocr_components.cnn_model import load_ocr_model

        load_ocr_model()
        logger.info("CNN warm-up completed in %.2fs", perf_counter() - cnn_started)
    except Exception:
        # OCR already has safe failure handling. A warm-up failure must never
        # prevent FastAPI from serving authentication/history routes.
        logger.exception("Background OCR model warm-up failed")


def start_ocr_model_warmup() -> None:
    """Start one daemon warm-up worker for this API process."""
    global _warmup_thread
    with _thread_lock:
        if _warmup_thread is not None and _warmup_thread.is_alive():
            return
        _warmup_thread = threading.Thread(
            target=_warm_models,
            name="ocr-model-warmup",
            daemon=True,
        )
        _warmup_thread.start()
