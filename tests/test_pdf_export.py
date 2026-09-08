"""B18: iso + GA PDF; page count = sheet count; pypdf text has line + NFC."""

from __future__ import annotations

from threadforge.exporters.pdf import NFC, export_ga_pdf, export_iso_pdf, extract_pdf_text, pdf_page_count
from threadforge.generators import generate_isometric, write_pcf_text
from threadforge.spooling import crafted_straight_30m


def test_iso_pdf_pages_match_sheets_and_text(tmp_path):
    g = crafted_straight_30m()
    write_pcf_text(g, "LINE-CRAFT-30M")
    iso = generate_isometric(g, "LINE-CRAFT-30M")
    n_sheets = int(iso.payload["sheet_count"])
    art = export_iso_pdf(g, "LINE-CRAFT-30M", tmp_path / "craft.iso.pdf")
    path = tmp_path / "craft.iso.pdf"
    pages = pdf_page_count(path)
    text = extract_pdf_text(path)
    assert pages == n_sheets == 3
    assert pages == art.payload["page_count"]
    assert "CRAFT-30M" in text
    assert NFC in text
    assert "NOT FOR CONSTRUCTION" in text


def test_ga_pdf_one_page_has_line_and_nfc(tmp_path):
    g = crafted_straight_30m()
    art = export_ga_pdf(g, tmp_path / "ga.pdf")
    text = extract_pdf_text(tmp_path / "ga.pdf")
    assert pdf_page_count(tmp_path / "ga.pdf") == 1 == art.payload["sheet_count"]
    assert "CRAFT-30M" in text
    assert NFC in text
