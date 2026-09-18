from pathlib import Path

import pymupdf
from docx import Document

from app.knowledge_base import add_document, delete_document, list_documents, search_documents


def test_local_library_indexes_and_cites_pdf_pages(tmp_path: Path):
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "Tower A-101 routine inspection was normal.")
    pdf.new_page().insert_text((72, 72), "Tower B-202 hot insulator reached 47 C. Inspect the upper connector.")
    path = tmp_path / "inspection.pdf"
    pdf.save(path)
    pdf.close()

    document = add_document(tmp_path, path, path.name)
    assert document["pages"] == 2
    hits = search_documents(tmp_path, "B-202 hot insulator")
    assert hits and hits[0]["filename"] == "inspection.pdf"
    assert any(hit["page"] == 2 and "47 C" in hit["excerpt"] for hit in hits)
    assert len(list_documents(tmp_path)) == 1
    assert add_document(tmp_path, path, path.name)["id"] == document["id"]
    assert delete_document(tmp_path, document["id"])
    assert not search_documents(tmp_path, "insulator")


def test_local_library_extracts_word_text(tmp_path: Path):
    document = Document()
    document.add_paragraph("Replace damaged conductor clamp during maintenance.")
    path = tmp_path / "work-order.docx"
    document.save(path)
    add_document(tmp_path, path, path.name)
    results = search_documents(tmp_path, "conductor clamp")
    assert results and "damaged conductor clamp" in results[0]["excerpt"]
