#!/usr/bin/env python3
"""
customer_list.py

Builds a PDF of your Telegram customers (work account) - name, username,
phone, and photos only. No bio/birthday/personal channel.

Output:
  backup/
    contacts.json
    photos/{user_id}_1.jpg ... _3.jpg
  customers.pdf

Requirements:
  pip install telethon reportlab arabic-reshaper python-bidi Pillow

One-time setup:
  Get an API ID and API Hash from my.telegram.org and fill them in below.

Run:
  python3 customer_list.py
  python3 customer_list.py --pdf-only   (if contacts.json already exists)
"""

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

# --- SETTINGS ----------------------------------------------------------------
API_ID   = 0       # int - from my.telegram.org
API_HASH = ""      # string - from my.telegram.org
SESSION  = "tg_backup_session"
BACKUP_DIR = Path("backup")
OUTPUT     = Path("customers.pdf")
# -------------------------------------------------------------------------------

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

FONT_PATHS = [
    "/usr/share/fonts/truetype/vazir/Vazir.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

PHOTO_SIZE = 3.6
MAX_PHOTOS = 3


# ============================================================================
# Telegram part
# ============================================================================

async def fetch_users(client):
    from telethon.tl.types import User
    from telethon.tl.functions.contacts import GetContactsRequest
    seen = {}

    result = await client(GetContactsRequest(hash=0))
    for u in result.users:
        if isinstance(u, User) and not u.bot:
            seen[u.id] = (u, True)

    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, User) and not entity.bot and entity.id not in seen:
            seen[entity.id] = (entity, False)

    return seen


async def download_photos(client, user, photos_dir: Path):
    paths = []
    try:
        photos = await client.get_profile_photos(user, limit=MAX_PHOTOS)
        for i, photo in enumerate(photos[:MAX_PHOTOS], 1):
            dest = photos_dir / f"{user.id}_{i}.jpg"
            if not dest.exists():
                await client.download_media(photo, file=str(dest))
            if dest.exists():
                paths.append(str(dest))
    except Exception as e:
        print(f"  photo {user.id}: {e}")
    return paths


async def run_backup():
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError

    if not API_ID or not API_HASH:
        print("Set API_ID and API_HASH in the script first.")
        return []

    BACKUP_DIR.mkdir(exist_ok=True)
    photos_dir = BACKUP_DIR / "photos"
    photos_dir.mkdir(exist_ok=True)

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        phone = input("Phone number (with country code, e.g. +989123456789): ").strip()
        await client.send_code_request(phone)
        code = input("Code sent by Telegram: ").strip()
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            password = input("Two-step (2FA) password: ").strip()
            await client.sign_in(password=password)

    print("Connected.")
    users_map = await fetch_users(client)
    total = len(users_map)
    print(f"{total} people found.")

    contacts = []
    for i, (uid, (user, in_contacts)) in enumerate(users_map.items(), 1):
        name = f"{user.first_name or ''} {user.last_name or ''}".strip() or str(uid)
        print(f"[{i}/{total}] {name}")

        photos = await download_photos(client, user, photos_dir)

        contacts.append({
            "id":           uid,
            "first_name":   user.first_name or "",
            "last_name":    user.last_name  or "",
            "username":     user.username   or "",
            "phone":        user.phone      or "",
            "in_contacts":  in_contacts,
            "photos":       photos,
            "backed_up_at": datetime.now().isoformat(),
        })

        await asyncio.sleep(0.4)

    out = BACKUP_DIR / "contacts.json"
    out.write_text(json.dumps(contacts, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {out}")
    await client.disconnect()
    return contacts


# ============================================================================
# PDF part
# ============================================================================

def load_font():
    for path in FONT_PATHS:
        if Path(path).exists():
            pdfmetrics.registerFont(TTFont("Persian", path))
            return "Persian"
    return "Helvetica"


def rtl(text):
    """Reshapes Persian/Arabic text for correct right-to-left display in the PDF."""
    if not text:
        return ""
    try:
        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:
        return str(text)


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
        info_block.append(Paragraph("@" + username, info_s))
    if phone:
        info_block.append(Paragraph(phone, info_s))
    info_block.append(Spacer(1, 2))
    info_block.append(Paragraph("ID: " + str(uid), uid_s))

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
    print(f"\nBuilding PDF for {len(contacts)} people ...")
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
        story.extend(make_card(c, font))

    print()
    doc.build(story)
    print("PDF built: " + str(output))


# ============================================================================
# Entry point
# ============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--pdf-only", action="store_true",
                        help="Only build the PDF from an existing contacts.json")
    parser.add_argument("--backup-dir", default=str(BACKUP_DIR))
    args = parser.parse_args()

    backup_path = Path(args.backup_dir)

    if args.pdf_only:
        contacts_file = backup_path / "contacts.json"
        if not contacts_file.exists():
            print("contacts.json not found.")
            return
        contacts = json.loads(contacts_file.read_text(encoding="utf-8"))
    else:
        contacts = asyncio.run(run_backup())

    if contacts:
        build_pdf(contacts, Path(args.output))


if __name__ == "__main__":
    main()
