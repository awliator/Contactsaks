#!/usr/bin/env python3
"""
build_pdf.py

Builds customers.pdf from an already-existing backup folder:
  /root/Contactaks/backup/contacts.json
  /root/Contactaks/backup/photos/...

No Telegram connection needed - just reads the JSON and images already on disk.

Requirements:
  pip install reportlab arabic-reshaper python-bidi Pillow

Run:
  python3 build_pdf.py
"""

import json
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image as RLImage,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

# --- SETTINGS ------------------------------------------------------------
BACKUP_DIR = Path("/root/Contactaks/backup")
CONTACTS_JSON = BACKUP_DIR / "contacts.json"
OUTPUT = Path("/root/Contactaks/customers.pdf")
# ---------------------------------------------------------------------------

FONT_PATHS = [
    "/usr/share/fonts/truetype/vazir/Vazir.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

PHOTO_SIZE = 3.6
MAX_PHOTOS = 3


def load_font():
    for path in FONT_PATHS:
        if Path(path).exists():
            pdfmetrics.registerFont(TTFont("Persian", path))
            return "Persian"
    return "Helvetica"


import unicodedata


def clean_text(text):
    """Removes characters that are unsafe/unsupported for PDF rendering
    (control characters, broken surrogates, unassigned code points, emoji
    the font can't draw) while keeping normal letters (any language),
    digits, spaces and punctuation intact. Never drops the whole field:
    if nothing usable is left, returns '.' as a placeholder."""
    if not text:
        return ""
    text = str(text)
    kept = []
    for ch in text:
        if ch in ("\u200c", "\u200d"):  # ZWNJ/ZWJ - needed for Persian joining
            kept.append(ch)
            continue
        cat = unicodedata.category(ch)
        if cat in ("Cc", "Cf", "Cs", "Co", "Cn"):
            continue  # control / format / surrogate / private-use / unassigned
        if cat == "So":
            continue  # symbols like emoji - font can't render, drop silently
        kept.append(ch)
    cleaned = "".join(kept).strip()
    return cleaned if cleaned else "."


def rtl(text):
    """Reshapes Persian/Arabic text for correct right-to-left display in the PDF.
    Also escapes <, >, & so ReportLab's paragraph parser doesn't choke on names
    that happen to contain those characters."""
    if not text:
        return ""
    text = clean_text(text)
    try:
        shaped = get_display(arabic_reshaper.reshape(text))
    except Exception:
        shaped = text
    return xml_escape(shaped)


def make_card(contact, font):
    photo_paths = [p for p in (contact.get("photos") or []) if p and Path(p).exists()]

    if photo_paths:
        cells = []
        for p in photo_paths[:MAX_PHOTOS]:
            try:
                img = RLImage(p, width=PHOTO_SIZE*cm, height=PHOTO_SIZE*cm)
                img.hAlign = "CENTER"
                cells.append(img)
            except Exception:
                cells.append(Paragraph("", ParagraphStyle("e", fontName=font, fontSize=8)))
        while len(cells) < MAX_PHOTOS:
            cells.append(Paragraph("", ParagraphStyle("e", fontName=font, fontSize=8)))

        photo_row = Table([cells], colWidths=[PHOTO_SIZE*cm]*MAX_PHOTOS)
        photo_row.setStyle(TableStyle([
            ("ALIGN", (0,0), (-1,-1), "CENTER"),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING", (0,0), (-1,-1), 0),
            ("BOTTOMPADDING", (0,0), (-1,-1), 0),
            ("LEFTPADDING", (0,0), (-1,-1), 4),
            ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ]))
    else:
        photo_row = Paragraph(rtl("No photo"),
                              ParagraphStyle("np", fontName=font, fontSize=8,
                                             alignment=1, textColor=colors.grey))

    fn = contact.get("first_name") or ""
    ln = contact.get("last_name") or ""
    name = (fn + " " + ln).strip() or "?"
    username = contact.get("username") or ""
    phone = contact.get("phone") or ""
    uid = contact.get("id") or ""
    in_contacts = contact.get("in_contacts", True)

    name_s = ParagraphStyle("name", fontName=font, fontSize=11, leading=16,
                             alignment=1, textColor=colors.HexColor("#1a1a2e"), spaceAfter=2)
    info_s = ParagraphStyle("info", fontName=font, fontSize=9, leading=14,
                             alignment=1, textColor=colors.HexColor("#333344"))
    tag_s = ParagraphStyle("tag", fontName=font, fontSize=7.5, leading=11,
                            alignment=1, textColor=colors.HexColor("#888899"))
    uid_s = ParagraphStyle("uid", fontName=font, fontSize=7,
                            alignment=1, textColor=colors.HexColor("#bbbbbb"))

    info_block = [Paragraph(rtl(name), name_s)]
    if not in_contacts:
        info_block.append(Paragraph(rtl("(from chats)"), tag_s))
    if username:
        info_block.append(Paragraph("@" + xml_escape(clean_text(username)), info_s))
    if phone:
        info_block.append(Paragraph(xml_escape(clean_text(phone)), info_s))
    info_block.append(Spacer(1, 2))
    info_block.append(Paragraph("ID: " + xml_escape(str(uid)), uid_s))

    card_data = [[photo_row], [info_block]]
    card = Table(card_data, colWidths=[16*cm])
    card.setStyle(TableStyle([
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#f7f9fc")),
        ("BOX", (0,0), (-1,-1), 0.5, colors.HexColor("#dde3ec")),
        ("LINEBELOW", (0,0), (0,0), 0.5, colors.HexColor("#dde3ec")),
        ("TOPPADDING", (0,0), (0,0), 8),
        ("BOTTOMPADDING", (0,0), (0,0), 6),
        ("TOPPADDING", (0,1), (0,1), 6),
        ("BOTTOMPADDING", (0,1), (0,1), 10),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
    ]))

    return [card, Spacer(1, 0.35*cm)]


def build_pdf(contacts, output: Path):
    print(f"Building PDF for {len(contacts)} people ...")
    font = load_font()
    doc = BaseDocTemplate(str(output), pagesize=A4,
                          rightMargin=1.5*cm, leftMargin=1.5*cm,
                          topMargin=2.2*cm, bottomMargin=2*cm)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    total = len(contacts)

    def header(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 10)
        canvas.drawRightString(A4[0]-1.5*cm, A4[1]-1.4*cm,
                               "Customer List - " + str(total) + " people")
        canvas.setStrokeColor(colors.HexColor("#dde3ec"))
        canvas.line(1.5*cm, A4[1]-1.6*cm, A4[0]-1.5*cm, A4[1]-1.6*cm)
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.grey)
        canvas.drawCentredString(A4[0]/2, 0.8*cm, str(doc.page))
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=header)])

    story = [Spacer(1, 0.3*cm)]
    for i, c in enumerate(contacts, 1):
        print(f"\r  [{i}/{total}]", end="")
        try:
            story.extend(make_card(c, font))
        except Exception as e:
            # Never drop a contact - fall back to a minimal ID-only card.
            print(f"\n  simplified contact {c.get('id')}: {e}")
            uid_s = ParagraphStyle("uid_fallback", fontName=font, fontSize=9,
                                    alignment=1, textColor=colors.HexColor("#888899"))
            fallback = Table([[Paragraph(".", uid_s)],
                              [Paragraph("ID: " + xml_escape(str(c.get("id"))), uid_s)]],
                             colWidths=[16*cm])
            fallback.setStyle(TableStyle([
                ("ALIGN", (0,0), (-1,-1), "CENTER"),
                ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#f7f9fc")),
                ("BOX", (0,0), (-1,-1), 0.5, colors.HexColor("#dde3ec")),
                ("TOPPADDING", (0,0), (-1,-1), 8),
                ("BOTTOMPADDING", (0,0), (-1,-1), 8),
            ]))
            story.extend([fallback, Spacer(1, 0.35*cm)])

    print()
    doc.build(story)
    print("PDF built: " + str(output))


def main():
    if not CONTACTS_JSON.exists():
        print(f"Not found: {CONTACTS_JSON}")
        return
    contacts = json.loads(CONTACTS_JSON.read_text(encoding="utf-8"))
    build_pdf(contacts, OUTPUT)


if __name__ == "__main__":
    main()
