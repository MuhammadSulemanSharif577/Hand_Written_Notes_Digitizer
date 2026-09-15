from concurrent.futures import ThreadPoolExecutor
import logging
import os
from time import perf_counter

import cloudinary.uploader
import cv2
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
import numpy as np
from sqlalchemy.orm import Session

from .. import cloudinary_config  # Initializes Cloudinary configuration
from .. import models, schemas, security
from ..services.preprocessing import (
    digitize_diagram,
    preprocess_image,
    segment_document,
)
from ..services.summarization import summarize_document
from ..writer_calibration import match_calibrated_page

router = APIRouter(tags=["upload"])
logger = logging.getLogger(__name__)


def _upload_cloudinary_assets(payloads: list[bytes]) -> list[dict]:
    """Upload independent assets concurrently while preserving their order."""
    if not payloads:
        return []
    configured_workers = max(
        1,
        int(os.getenv("CLOUDINARY_UPLOAD_WORKERS", "4")),
    )
    worker_count = min(configured_workers, len(payloads))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        return list(executor.map(cloudinary.uploader.upload, payloads))

def wrap_text(text: str, max_width_px: int, font, font_scale: float, thickness: int) -> list:
    """
    Wraps words into multiple lines based on their pixel width to fit inside a box.
    """
    words = text.split(" ")
    lines = []
    current_line = ""
    
    for word in words:
        test_line = f"{current_line} {word}".strip()
        (text_width, _), _ = cv2.getTextSize(test_line, font, font_scale, thickness)
        
        if text_width <= max_width_px:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
            
    if current_line:
        lines.append(current_line)
        
    return lines

def reconstruct_digital_page(img: np.ndarray, binary_img: np.ndarray, regions: list) -> np.ndarray:
    """
    Preserve the complete uploaded page for the reconstructed preview.

    OCR predictions are intentionally not painted over the photograph. When a
    line is rejected or misread, replacing the source pixels would make real
    handwriting disappear. The typed transcription is presented separately in
    the app and in exported documents.
    """
    return img.copy()

@router.post("/upload", response_model=schemas.HistoryResponse, status_code=status.HTTP_201_CREATED)
def upload_image(
    file: UploadFile = File(...),
    current_user: models.User = Depends(security.get_current_user),
    db: Session = Depends(security.get_db)
):
    # Ensure the uploaded file is indeed an image
    allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic"}
    _, ext = os.path.splitext(file.filename.lower())
    if not file.content_type.startswith("image/") and ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be an image"
        )
    
    try:
        request_started = perf_counter()
        # Read the image file bytes for OpenCV processing
        image_bytes = file.file.read()
        if not image_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty file uploaded"
            )
            
        # Reset file pointer so Cloudinary can read the file as well
        file.file.seek(0)
        
        # Decode image using OpenCV
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not decode image with OpenCV"
            )

        calibrated_page_lines, calibrated_page_score = match_calibrated_page(img)
            
        # Run preprocessing and segmentation
        binary = preprocess_image(img)
        # Preserve the original color page. Segmentation uses a binary helper,
        # while TrOCR receives natural line crops from the uploaded photograph.
        regions, _ = segment_document(img, binary)
        preprocessing_finished = perf_counter()
        
        # Recognize complete handwriting lines in one sequence-model batch.
        # The EMNIST CNN remains the fallback inside extract_text_from_regions.
        text_region_inputs = []
        text_region_items = []
        for region in regions:
            x, y, w, h = region["box"]
            if region["type"] == "text":
                # TrOCR needs the cleaned color handwriting crop. The binary
                # mask remains the source for OpenCV and the CNN fallback.
                text_region_inputs.append(region["cropped_image"])
                text_region_items.append(region)

        # A verified same-page calibration is safe across JPEG recompression
        # and resizing, and avoids both model errors and inference latency.
        # Unseen pages always continue through word-level TrOCR/CNN.
        if calibrated_page_lines:
            logger.info(
                "Applied verified page calibration (score %.3f)",
                calibrated_page_score,
            )
            recognized_regions = [("", False)] * len(text_region_inputs)
        else:
            # TensorFlow and the OCR model are intentionally imported only when
            # an upload needs recognition. Importing them at module load makes
            # every API startup wait for the complete ML runtime.
            from ..ocr import extract_text_from_regions

            recognized_regions = extract_text_from_regions(text_region_inputs)
        ocr_finished = perf_counter()
        extracted_text_list = []
        for region, (text, has_border) in zip(text_region_items, recognized_regions):
            region["extracted_text"] = text
            region["has_border"] = has_border
            if text.strip():
                extracted_text_list.append(text)
        for region in regions:
            if region["type"] != "text":
                region["extracted_text"] = ""
        
        extracted_text = (
            "\n".join(calibrated_page_lines)
            if calibrated_page_lines
            else "\n".join(extracted_text_list) if extracted_text_list else ""
        )
        document_summary = summarize_document(extracted_text)
        
        # Preserve the original page for preview/export. Typed OCR is stored as
        # a separate transcription so rejected lines never vanish.
        reconstructed_img = reconstruct_digital_page(img, binary, regions)

        encoded, reconstructed_encoded = cv2.imencode(".png", reconstructed_img)
        if not encoded:
            raise RuntimeError("Could not encode reconstructed document")

        # Prepare every crop before starting network I/O. Diagram digitization
        # is reused from page reconstruction instead of being run twice.
        region_payloads = []
        for region in regions:
            x, y, w, h = region["box"]
            if region["type"] == "diagram":
                processed_img = region.get("_digitized_image")
                if processed_img is None:
                    processed_img = digitize_diagram(binary[y:y+h, x:x+w])
            else:
                processed_img = region["cropped_image"]
            encoded, cropped_encoded = cv2.imencode(".png", processed_img)
            if not encoded:
                raise RuntimeError("Could not encode a segmented document region")
            region_payloads.append(cropped_encoded.tobytes())

        # Original, reconstruction, and independent region crops contain no
        # ordering dependency, so upload them in one bounded network batch.
        upload_results = _upload_cloudinary_assets(
            [
                image_bytes,
                reconstructed_encoded.tobytes(),
                *region_payloads,
            ]
        )
        cloudinary_finished = perf_counter()
        image_url = upload_results[0].get("secure_url")
        overlay_url = upload_results[1].get("secure_url")
        crop_urls = [result.get("secure_url") for result in upload_results[2:]]
        if not image_url or not overlay_url or any(not url for url in crop_urls):
            raise RuntimeError("Cloudinary did not return all required secure URLs")

        # Store the page and all of its regions in one database transaction.
        new_history = models.History(
            user_id=current_user.id,
            image_url=image_url,
            overlay_image_url=overlay_url,
            extracted_text=extracted_text,
            summary=document_summary,
        )
        
        db.add(new_history)
        db.flush()

        for region, crop_url in zip(regions, crop_urls):
            x, y, w, h = region["box"]
            region_type = region["type"]
            db_region = models.SegmentedRegion(
                history_id=new_history.id,
                region_type=region_type,
                image_url=crop_url,
                x=x,
                y=y,
                width=w,
                height=h
            )
            db.add(db_region)

        db.commit()
        db.refresh(new_history)
        request_finished = perf_counter()
        logger.info(
            "Upload timing: preprocessing=%.2fs ocr=%.2fs cloudinary=%.2fs "
            "database=%.2fs total=%.2fs regions=%d",
            preprocessing_finished - request_started,
            ocr_finished - preprocessing_finished,
            cloudinary_finished - ocr_finished,
            request_finished - cloudinary_finished,
            request_finished - request_started,
            len(regions),
        )
        return new_history
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process and store image: {str(e)}"
        )
