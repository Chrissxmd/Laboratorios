from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OCRConfig:
    """Mantenido por compatibilidad con la UI existente.
    En v8 el OCR ya no se usa: los PDFs se envían directamente a la API.
    Todos los campos se ignoran en el procesamiento, pero la UI los sigue
    mostrando para no romper configuraciones guardadas.
    """
    enabled: bool = False          # deshabilitado por defecto en v8
    tesseract_cmd: str = ""
    lang: str = "spa+eng"
    dpi: int = 200
    max_pages_ocr: int = 10
    min_text_threshold: int = 50


def load_pdf_as_base64(file_path: str) -> str:
    """Lee el PDF del disco y lo devuelve codificado en base64."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    raw_bytes = path.read_bytes()
    return base64.standard_b64encode(raw_bytes).decode("ascii")


def get_pdf_page_count(file_path: str) -> int:
    """Devuelve el número de páginas del PDF (requiere PyMuPDF si está disponible)."""
    try:
        import fitz  # PyMuPDF — opcional en v8
        doc = fitz.open(file_path)
        count = len(doc)
        doc.close()
        return count
    except Exception:
        return 0


def pdf_pages_to_base64_images(file_path: str, dpi: int = 150, max_pages: int | None = None) -> list[str]:
    """Convierte páginas del PDF en JPEG base64 para proveedores vision.
    No ejecuta OCR local.
    """
    import fitz  # PyMuPDF
    doc = fitz.open(file_path)
    pages_b64: list[str] = []
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    try:
        limit = len(doc) if max_pages is None else min(len(doc), int(max_pages))
        for i in range(limit):
            page = doc[i]
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            jpeg_bytes = pix.tobytes("jpeg")
            pages_b64.append(base64.standard_b64encode(jpeg_bytes).decode("ascii"))
    finally:
        doc.close()
    return pages_b64
