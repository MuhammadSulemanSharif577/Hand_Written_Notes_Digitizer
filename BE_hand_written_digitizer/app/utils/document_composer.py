import os
import io
import requests
from PIL import Image
from docx import Document
from docx.shared import Inches
from fpdf import FPDF

def generate_docx(history_record) -> io.BytesIO:
    """
    Compiles digitized text and shapes from a scan history record
    into a clean Microsoft Word (DOCX) document stream.
    """
    doc = Document()
    
    # Document title
    doc.add_heading(f"Digitized Document: Scan #{history_record.id}", 0)
    
    # Add Extracted Text
    doc.add_heading("Extracted Text", level=1)
    doc.add_paragraph(history_record.extracted_text or "No text extracted.")
    
    # Add Diagrams
    diagram_regions = [r for r in history_record.segmented_regions if r.region_type == "diagram"]
    if diagram_regions:
        doc.add_heading("Digitized Diagrams", level=1)
        for idx, region in enumerate(diagram_regions):
            doc.add_heading(f"Diagram #{idx+1}", level=2)
            try:
                # Fetch shape image from Cloudinary
                resp = requests.get(region.image_url, timeout=15)
                if resp.status_code == 200:
                    image_bytes = io.BytesIO(resp.content)
                    doc.add_picture(image_bytes, width=Inches(4.5))
                else:
                    doc.add_paragraph(f"[Failed to load diagram image from {region.image_url}]")
            except Exception as e:
                doc.add_paragraph(f"[Error fetching diagram: {str(e)}]")
                
    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream

def generate_pdf(history_record) -> io.BytesIO:
    """
    Compiles digitized text and shapes from a scan history record
    into a formatted PDF document stream using fpdf2.
    """
    pdf = FPDF()
    pdf.add_page()
    
    # Set default encoding safe font
    pdf.set_font("Helvetica", size=12)
    
    # Document Title
    pdf.set_font("Helvetica", style="B", size=16)
    pdf.cell(0, 10, txt=f"Digitized Document: Scan #{history_record.id}", ln=True, align="C")
    pdf.ln(10)
    
    # Extracted Text Section
    pdf.set_font("Helvetica", style="B", size=14)
    pdf.cell(0, 10, txt="Extracted Text", ln=True)
    pdf.ln(2)
    
    pdf.set_font("Helvetica", size=11)
    text_content = history_record.extracted_text or "No text extracted."
    # Replace non-latin1 characters with standard placeholders to avoid fpdf2 encoding errors
    text_latin1 = text_content.encode("latin-1", "replace").decode("latin-1")
    pdf.multi_cell(0, 8, txt=text_latin1)
    pdf.ln(10)
    
    # Diagrams Section
    diagram_regions = [r for r in history_record.segmented_regions if r.region_type == "diagram"]
    if diagram_regions:
        pdf.set_font("Helvetica", style="B", size=14)
        pdf.cell(0, 10, txt="Digitized Diagrams", ln=True)
        pdf.ln(5)
        for idx, region in enumerate(diagram_regions):
            pdf.set_font("Helvetica", style="B", size=11)
            pdf.cell(0, 8, txt=f"Diagram #{idx+1}", ln=True)
            pdf.ln(2)
            try:
                # Fetch shape image from Cloudinary
                resp = requests.get(region.image_url, timeout=15)
                if resp.status_code == 200:
                    img_data = io.BytesIO(resp.content)
                    img = Image.open(img_data)
                    
                    # Convert to RGB mode if image is RGBA to prevent transparency format errors in PDF
                    if img.mode == 'RGBA':
                        img = img.convert('RGB')
                        
                    pdf.image(img, w=150)
                    pdf.ln(10)
                else:
                    pdf.set_font("Helvetica", style="I", size=10)
                    pdf.cell(0, 8, txt="[Failed to load diagram image]", ln=True)
            except Exception as e:
                pdf.set_font("Helvetica", style="I", size=10)
                pdf.cell(0, 8, txt=f"[Error loading diagram: {str(e)}]", ln=True)
                pdf.ln(5)
                
    pdf_bytes = pdf.output()
    if isinstance(pdf_bytes, bytearray):
        pdf_bytes = bytes(pdf_bytes)
    return io.BytesIO(pdf_bytes)
