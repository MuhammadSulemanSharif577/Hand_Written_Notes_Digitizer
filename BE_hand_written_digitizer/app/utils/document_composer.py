"""Build downloadable documents without discarding the source handwriting."""

import io

import requests
from PIL import Image
from docx import Document
from docx.shared import Inches
from fpdf import FPDF


_DOWNLOAD_TIMEOUT_SECONDS = 15


def _download_image(url: str | None) -> Image.Image | None:
    """Download an image and detach it from the response byte stream."""
    if not url:
        return None
    try:
        response = requests.get(url, timeout=_DOWNLOAD_TIMEOUT_SECONDS)
        response.raise_for_status()
        with Image.open(io.BytesIO(response.content)) as source:
            return source.convert("RGB")
    except (requests.RequestException, OSError):
        return None


def _image_stream(image: Image.Image) -> io.BytesIO:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    stream.seek(0)
    return stream


def _add_fitted_pdf_image(pdf: FPDF, image: Image.Image) -> None:
    """Place an image on the current page without stretching or cropping it."""
    margin = 10.0
    available_width = pdf.w - (2 * margin)
    available_height = pdf.h - (2 * margin)
    scale = min(available_width / image.width, available_height / image.height)
    width = image.width * scale
    height = image.height * scale
    x = (pdf.w - width) / 2
    y = (pdf.h - height) / 2
    pdf.image(_image_stream(image), x=x, y=y, w=width, h=height)


def generate_docx(history_record) -> io.BytesIO:
    """Create a DOCX containing the complete original and typed OCR text."""
    doc = Document()
    doc.add_heading(f"Digitized Document: Scan #{history_record.id}", 0)

    # The source page is deliberately included before OCR. A low-confidence
    # model prediction must never make handwriting disappear from an export.
    original = _download_image(getattr(history_record, "image_url", None))
    if original is not None:
        doc.add_heading("Original Document", level=1)
        doc.add_picture(_image_stream(original), width=Inches(6.2))
        doc.add_page_break()

    doc.add_heading("Typed Transcription", level=1)
    doc.add_paragraph(history_record.extracted_text or "No reliable text extracted.")

    diagram_regions = [
        region
        for region in (getattr(history_record, "segmented_regions", None) or [])
        if region.region_type == "diagram"
    ]
    if diagram_regions:
        doc.add_heading("Detected Diagrams", level=1)
        for index, region in enumerate(diagram_regions, start=1):
            doc.add_heading(f"Diagram #{index}", level=2)
            diagram = _download_image(region.image_url)
            if diagram is not None:
                doc.add_picture(_image_stream(diagram), width=Inches(4.5))
            else:
                doc.add_paragraph("[Diagram image could not be loaded]")

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream


def generate_pdf(history_record) -> io.BytesIO:
    """Create a PDF whose first page preserves the full uploaded photograph."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    original = _download_image(getattr(history_record, "image_url", None))
    if original is not None:
        pdf.add_page()
        _add_fitted_pdf_image(pdf, original)

    # OCR is an additional typed transcription, never a destructive
    # replacement for the original document.
    pdf.add_page()
    pdf.set_font("Helvetica", style="B", size=16)
    pdf.cell(0, 10, text=f"Digitized Document: Scan #{history_record.id}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(8)
    pdf.set_font("Helvetica", style="B", size=14)
    pdf.cell(0, 10, text="Typed Transcription", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("Helvetica", size=11)
    text_content = history_record.extracted_text or "No reliable text extracted."
    text_latin1 = text_content.encode("latin-1", "replace").decode("latin-1")
    pdf.multi_cell(0, 8, text=text_latin1)
    pdf.ln(8)

    diagram_regions = [
        region
        for region in (getattr(history_record, "segmented_regions", None) or [])
        if region.region_type == "diagram"
    ]
    if diagram_regions:
        pdf.set_font("Helvetica", style="B", size=14)
        pdf.cell(0, 10, text="Detected Diagrams", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        for index, region in enumerate(diagram_regions, start=1):
            pdf.set_font("Helvetica", style="B", size=11)
            pdf.cell(0, 8, text=f"Diagram #{index}", new_x="LMARGIN", new_y="NEXT")
            diagram = _download_image(region.image_url)
            if diagram is None:
                pdf.set_font("Helvetica", style="I", size=10)
                pdf.cell(0, 8, text="[Diagram image could not be loaded]", new_x="LMARGIN", new_y="NEXT")
                continue

            # Keep diagrams within the printable width and reserve space for
            # a heading on the following page when necessary.
            max_width = pdf.w - pdf.l_margin - pdf.r_margin
            max_height = 120.0
            scale = min(max_width / diagram.width, max_height / diagram.height)
            width = diagram.width * scale
            height = diagram.height * scale
            if pdf.get_y() + height > pdf.h - pdf.b_margin:
                pdf.add_page()
            pdf.image(_image_stream(diagram), x=pdf.l_margin, y=pdf.get_y(), w=width, h=height)
            pdf.set_y(pdf.get_y() + height + 8)

    pdf_bytes = pdf.output()
    if isinstance(pdf_bytes, bytearray):
        pdf_bytes = bytes(pdf_bytes)
    return io.BytesIO(pdf_bytes)
