from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
import models
import schemas
import security
import cloudinary.uploader
import cloudinary_config  # Initializes Cloudinary configuration
import numpy as np
import cv2
from services.preprocessing import preprocess_image, segment_document, remove_background, digitize_diagram
from ocr import extract_text_from_regions
from services.summarization import summarize_document

router = APIRouter(tags=["upload"])

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
    Assembles a fully computerized digital page layout on a clean white canvas.
    Overlays OCR text and digitized diagrams at their original positions.
    """
    canvas = np.ones_like(img) * 255  # Solid white background
    
    # Layer 1: Draw all diagram/box shapes first (background)
    for region in regions:
        if region["type"] == "diagram":
            x, y, w, h = region["box"]
            region_binary = binary_img[y:y+h, x:x+w]
            processed_img = digitize_diagram(region_binary)
            
            # Draw the digitized diagram directly onto the canvas at original coordinates
            crop_h, crop_w = processed_img.shape[:2]
            target_h = min(crop_h, canvas.shape[0] - y)
            target_w = min(crop_w, canvas.shape[1] - x)
            canvas[y:y+target_h, x:x+target_w] = processed_img[:target_h, :target_w]
            
    # Layer 2: Draw all text lines second (foreground)
    for region in regions:
        if region["type"] == "text":
            x, y, w, h = region["box"]
            if region.get("has_border", False):
                cv2.rectangle(canvas, (x, y), (x + w, y + h), (15, 23, 42), 2, lineType=cv2.LINE_AA)
            text = region.get("extracted_text", "")
            if text.strip():
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.55
                thickness = 1
                color = (15, 23, 42)  # Slate-900 (charcoal black)
                
                # Wrap text to fit inside the region width (minus padding)
                wrapped_lines = wrap_text(text, w - 20, font, font_scale, thickness)
                
                # Render lines sequentially
                line_height = 20
                y_offset = y + line_height
                
                for line in wrapped_lines:
                    if y_offset < y + h:
                        cv2.putText(canvas, line, (x + 10, y_offset), font, font_scale, color, thickness, cv2.LINE_AA)
                        y_offset += line_height
                        
    return canvas

@router.post("/upload", response_model=schemas.HistoryResponse, status_code=status.HTTP_201_CREATED)
def upload_image(
    file: UploadFile = File(...),
    current_user: models.User = Depends(security.get_current_user),
    db: Session = Depends(security.get_db)
):
    # Ensure the uploaded file is indeed an image
    import os
    allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic"}
    _, ext = os.path.splitext(file.filename.lower())
    if not file.content_type.startswith("image/") and ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be an image"
        )
    
    try:
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
            
        # Run preprocessing and segmentation
        binary = preprocess_image(img)
        cleaned_img = remove_background(img, binary)
        regions, _ = segment_document(cleaned_img, binary)
        
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

        recognized_regions = extract_text_from_regions(text_region_inputs)
        extracted_text_list = []
        for region, (text, has_border) in zip(text_region_items, recognized_regions):
            region["extracted_text"] = text
            region["has_border"] = has_border
            if text.strip():
                extracted_text_list.append(text)
        for region in regions:
            if region["type"] != "text":
                region["extracted_text"] = ""
        
        extracted_text = "\n".join(extracted_text_list) if extracted_text_list else ""
        document_summary = summarize_document(extracted_text)
        
        # Generate the fully computerized reconstructed page
        reconstructed_img = reconstruct_digital_page(img, binary, regions)
        
        # Upload the original file to Cloudinary
        upload_result = cloudinary.uploader.upload(file.file)
        image_url = upload_result.get("secure_url")
        if not image_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Cloudinary upload of original image did not return a secure URL"
            )
            
        # Upload the reconstructed computerized image to Cloudinary as overlay_url
        _, reconstructed_encoded = cv2.imencode(".png", reconstructed_img)
        reconstructed_bytes = reconstructed_encoded.tobytes()
        reconstructed_upload = cloudinary.uploader.upload(reconstructed_bytes)
        overlay_url = reconstructed_upload.get("secure_url")
        
        # Insert a new record in the history database table
        new_history = models.History(
            user_id=current_user.id,
            image_url=image_url,
            overlay_image_url=overlay_url,
            extracted_text=extracted_text,
            summary=document_summary,
        )
        
        db.add(new_history)
        db.commit()
        db.refresh(new_history)
        
        # Upload each segmented region cropped image to Cloudinary and save to DB
        for region in regions:
            x, y, w, h = region["box"]
            region_type = region["type"]
            
            if region_type == "diagram":
                # Run OpenCV shape detection and digitization on diagram regions
                region_binary = binary[y:y+h, x:x+w]
                processed_img = digitize_diagram(region_binary)
            else:
                # Keep original color crop for text regions
                processed_img = region["cropped_image"]
            
            # Encode processed region to PNG bytes
            _, cropped_encoded = cv2.imencode(".png", processed_img)
            cropped_bytes = cropped_encoded.tobytes()
            
            # Upload crop to Cloudinary
            crop_upload = cloudinary.uploader.upload(cropped_bytes)
            crop_url = crop_upload.get("secure_url")
            
            # Save SegmentedRegion to database
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
        return new_history
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process and store image: {str(e)}"
        )
