from fastapi import APIRouter, Depends, status, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas, security
from ..services.summarization import summarize_document
from ..services.cloudinary_assets import delete_document_assets
from ..utils.document_composer import generate_docx, generate_pdf

router = APIRouter(prefix="/history", tags=["history"])

@router.get("", response_model=List[schemas.HistoryResponse])
def get_user_history(
    current_user: models.User = Depends(security.get_current_user),
    db: Session = Depends(security.get_db)
):
    # Retrieve all scan history for the authenticated user, sorted newest first
    history_records = db.query(models.History)\
        .filter(models.History.user_id == current_user.id)\
        .order_by(models.History.upload_time.desc())\
        .all()
    # Backfill summaries for documents scanned before the summary column was
    # introduced. New uploads are summarized immediately in the upload route.
    changed = False
    for record in history_records:
        if not record.summary and record.extracted_text:
            record.summary = summarize_document(record.extracted_text)
            changed = True
    if changed:
        db.commit()
    return history_records


@router.delete("/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    history_id: int,
    current_user: models.User = Depends(security.get_current_user),
    db: Session = Depends(security.get_db),
):
    history_record = (
        db.query(models.History)
        .filter(
            models.History.id == history_id,
            models.History.user_id == current_user.id,
        )
        .first()
    )
    if not history_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    asset_urls = [history_record.image_url, history_record.overlay_image_url]
    asset_urls.extend(region.image_url for region in history_record.segmented_regions)

    try:
        # Keep the database row when remote cleanup fails so deletion can be
        # retried without leaving an untracked Cloudinary document behind.
        delete_document_assets(asset_urls)
        db.delete(history_record)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not delete document assets: {exc}",
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/{history_id}/export/{export_format}")
def export_document(
    history_id: int,
    export_format: str,
    current_user: models.User = Depends(security.get_current_user),
    db: Session = Depends(security.get_db)
):
    # Fetch history record
    history_record = db.query(models.History)\
        .filter(models.History.id == history_id)\
        .first()
        
    if not history_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan record not found"
        )
        
    # Verify ownership
    if history_record.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this document"
        )
        
    export_format = export_format.lower()
    if export_format == "docx":
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"digitized_document_{history_id}.docx"
        file_stream = generate_docx(history_record)
    elif export_format == "pdf":
        media_type = "application/pdf"
        filename = f"digitized_document_{history_id}.pdf"
        file_stream = generate_pdf(history_record)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported export format. Supported formats: docx, pdf"
        )
        
    return StreamingResponse(
        file_stream,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
