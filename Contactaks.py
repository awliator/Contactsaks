#!/usr/bin/env python3
"""
tg_full_backup.py

بکاپ کامل از تلگرام + تولید PDF مرتب.

چی بکاپ میگیره:
  - همه مخاطبین
  - همه کسایی که باهاشون چت کردی (حتی اگه تو لیست مخاطبین نیستن)
  - بیو، تولد، سن، کانال شخصی هر نفر
  - تا ۳ عکس پروفایل هر نفر

خروجی:
  backup/
    contacts.json
    photos/
      {user_id}_1.jpg
      {user_id}_2.jpg
      {user_id}_3.jpg
  contacts.pdf

پیش‌نیاز:
  pip install telethon reportlab arabic-reshaper python-bidi Pillow

راه‌اندازی یک‌باره:
  از my.telegram.org یه API ID و API Hash بگیر.
  اطلاعات رو پایین تو SETTINGS وارد کن.

اجرا:
  python3 tg_full_backup.py
  python3 tg_full_backup.py --output my_contacts.pdf
"""

import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

# ─── SETTINGS ────────────────────────────────────────────────────────────────
API_ID   = 0       # عدد — از my.telegram.org
API_HASH = ""      # رشته — از my.telegram.org
SESSION  = "tg_backup_session"
BACKUP_DIR = Path("backup")
# ─────────────────────────────────────────────────────────────────────────────

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

PHOTO_SIZE  = 3.6   # سانتی‌متر — اندازه هر عکس پروفایل
MAX_PHOTOS  = 3     # حداکثر عکس برای هر نفر


# ══════════════════════════════════════════════════════════════════════════════
# بخش تلگرام
# ══════════════════════════════════════════════════════════════════════════════

async def fetch_users(client):
    from telethon.tl.types import User

    seen = {}

    # مخاطبین
    result = await client.get_contacts()
    for u in result.users:
        if isinstance(u, User) and not u.bot:
            seen[u.id] = (u, True)

    # همه چت‌ها
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, User) and not entity.bot and entity.id not in seen:
            seen[entity.id] = (entity, False)

    return seen


async def get_full_info(client, user):
    from telethon.tl.functions.users import GetFullUserRequest
    try:
        full = await client(GetFullUserRequest(user.id))
        fu   = full.full_user
        bio  = fu.about or ""

        age      = None
        birthday = ""
        if hasattr(fu, "birthday") and fu.birthday:
            b = fu.birthday
            if hasattr(b, "year") and b.year:
                age = datetime.now().year - b.year
                birthday = f"{b.year}/{b.month:02d}/{b.day:02d}"
            else:
                birthday = f"{b.month:02d}/{b.day:02d}"

        channel = ""
        if hasattr(fu, "personal_channel_id") and fu.personal_channel_id:
            channel = str(fu.personal_channel_id)

        return bio, age, birthday, channel
    except Exception:
        return "", None, "", ""


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
        print(f"  عکس {user.id}: {e}")
    return paths


async def run_backup():
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError

    if not API_ID or not API_HASH:
        print("اول API_ID و API_HASH رو تو اسکریپت وارد کن.")
        return []

    BACKUP_DIR.mkdir(exist_ok=True)
    photos_dir = BACKUP_DIR / "photos"
    photos_dir.mkdir(exist_ok=True)

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        phone = input("شماره تلفن (با کد کشور، مثلاً +989123456789): ").strip()
        await client.send_code_request(phone)
        code = input("کدی که تلگرام فرستاد: ").strip()
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            password = input("رمز دومرحله‌ای (2FA): ").strip()
            await client.sign_in(password=password)

    print("وصل شدم.")
    users_map = await fetch_users(client)
    total = len(users_map)
    print(f"{total} نفر پیدا شد (مخاطب + چت‌ها).")

    contacts = []
    for i, (uid, (user, in_contacts)) in enumerate(users_map.items(), 1):
        name = f"{user.first_name or ''} {user.last_name or ''}".strip() or str(uid)
        print(f"[{i}/{total}] {name}")

        bio, age, birthday, channel = await get_full_info(client, user)
        photos = await download_photos(client, user, photos_dir)

        contacts.append({
            "id":               uid,
            "first_name":       user.first_name or "",
            "last_name":        user.last_name  or "",
            "username":         user.username   or "",
            "phone":            user.phone      or "",
            "is_bot":           user.bot,
            "in_contacts":      in_contacts,
            "bio":              bio,
            "age":              age,
            "birthday":         birthday,
            "personal_channel": channel,
            "photos":           photos,
            "backed_up_at":     datetime.now().isoformat(),
        })

        await asyncio.sleep(0.4)

    out = BACKUP_DIR / "contacts.json"
    out.write_text(json.dumps(contacts, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nبکاپ ذخیره شد: {out}")
    await client.disconnect()
    return contacts


# ══════════════════════════════════════════════════════════════════════════════
# بخش PDF
# ══════════════════════════════════════════════════════════════════════════════

def load_font():
    for path in FONT_PATHS:
        if Path(path).exists():
            pdfmetrics.registerFont(TTFont("Persian", path))
            return "Persian"
    return "Helvetica"


def rtl(text):
    if not text:
        return ""
    try:
        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:
        return str(text)


def make_card(contact, font):
    photo_paths = contact.get("photos") or []
    # اگه فیلد قدیمی photo_file هم داشت
    if not photo_paths and contact.get("photo_file"):
        photo_paths = [contact["photo_file"]]

    valid_photos = [p for p in photo_paths if p and Path(p).exists()]

    # ── ردیف عکس‌ها ──────────────────────────────────────────────────────────
    if valid_photos:
        photo_cells = []
        for p in valid_photos[:MAX_PHOTOS]:
            try:
                img = RLImage(p, width=PHOTO_SIZE*cm, height=PHOTO_SIZE*cm)
                img.hAlign = "CENTER"
                photo_cells.append(img)
            except Exception:
                photo_cells.append(Paragraph("", ParagraphStyle("e", fontName=font, fontSize=8)))

        # پر کردن جاهای خالی تا ۳ تا
        while len(photo_cells) < MAX_PHOTOS:
            photo_cells.append(Paragraph("", ParagraphStyle("e", fontName=font, fontSize=8)))

        col_w = [PHOTO_SIZE*cm] * MAX_PHOTOS
        photo_row = Table([photo_cells], colWidths=col_w)
        photo_row.setStyle(TableStyle([
            ("ALIGN",         (0,0), (-1,-1), "CENTER"),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING",    (0,0), (-1,-1), 0),
            ("BOTTOMPADDING", (0,0), (-1,-1), 0),
            ("LEFTPADDING",   (0,0), (-1,-1), 4),
            ("RIGHTPADDING",  (0,0), (-1,-1), 4),
        ]))
    else:
        photo_row = Paragraph(rtl("بدون عکس"),
                              ParagraphStyle("np", fontName=font, fontSize=8,
                                             alignment=1, textColor=colors.grey))

    # ── اطلاعات ───────────────────────────────────────────────────────────────
    fn   = contact.get("first_name") or ""
    ln   = contact.get("last_name")  or ""
    name = (fn + " " + ln).strip() or "?"

    username    = contact.get("username")         or ""
    phone       = contact.get("phone")            or ""
    uid         = contact.get("id")               or ""
    bio         = contact.get("bio")              or ""
    age         = contact.get("age")
    birthday    = contact.get("birthday")         or ""
    channel     = contact.get("personal_channel") or ""
    in_contacts = contact.get("in_contacts", True)

    name_s = ParagraphStyle("name", fontName=font, fontSize=11, leading=16,
                             alignment=1, textColor=colors.HexColor("#1a1a2e"), spaceAfter=2)
    info_s = ParagraphStyle("info", fontName=font, fontSize=8.5, leading=13,
                             alignment=1, textColor=colors.HexColor("#333344"))
    bio_s  = ParagraphStyle("bio",  fontName=font, fontSize=8, leading=12,
                             alignment=1, textColor=colors.HexColor("#555566"))
    tag_s  = ParagraphStyle("tag",  fontName=font, fontSize=7.5, leading=11,
                             alignment=1, textColor=colors.HexColor("#888899"))
    uid_s  = ParagraphStyle("uid",  fontName=font, fontSize=7,
                             alignment=1, textColor=colors.HexColor("#bbbbbb"))

    info_block = [Paragraph(rtl(name), name_s)]

    if not in_contacts:
        info_block.append(Paragraph(rtl("(فقط از چت‌ها)"), tag_s))

    if username:
        info_block.append(Paragraph("@" + username, info_s))
    if phone:
        info_block.append(Paragraph(phone, info_s))

    age_parts = []
    if age:
        age_parts.append(rtl("سن: " + str(age)))
    if birthday:
        age_parts.append(rtl("تولد: " + birthday))
    if age_parts:
        info_block.append(Paragraph("   |   ".join(age_parts), info_s))

    if bio:
        info_block.append(Spacer(1, 2))
        info_block.append(Paragraph(rtl(bio), bio_s))

    if channel:
        info_block.append(Paragraph(rtl("کانال: " + channel), tag_s))

    info_block.append(Spacer(1, 2))
    info_block.append(Paragraph("ID: " + str(uid), uid_s))

    # ── کارت نهایی: عکس بالا، داده پایین ────────────────────────────────────
    card_data = [[photo_row], [info_block]]
    card = Table(card_data, colWidths=[16*cm])
    card.setStyle(TableStyle([
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor("#f7f9fc")),
        ("BOX",           (0,0), (-1,-1), 0.5, colors.HexColor("#dde3ec")),
        ("LINEBELOW",     (0,0), (0,0),   0.5, colors.HexColor("#dde3ec")),
        ("TOPPADDING",    (0,0), (0,0),   8),
        ("BOTTOMPADDING", (0,0), (0,0),   6),
        ("TOPPADDING",    (0,1), (0,1),   6),
        ("BOTTOMPADDING", (0,1), (0,1),   10),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
    ]))

    return [card, Spacer(1, 0.35*cm)]


def build_pdf(contacts, output: Path):
    print(f"\nساخت PDF برای {len(contacts)} نفر ...")
    font = load_font()
    doc  = BaseDocTemplate(str(output), pagesize=A4,
                           rightMargin=1.5*cm, leftMargin=1.5*cm,
                           topMargin=2.2*cm, bottomMargin=2*cm)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    total = len(contacts)

    def header(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 10)
        canvas.drawRightString(A4[0]-1.5*cm, A4[1]-1.4*cm,
                               rtl("لیست مخاطبین تلگرام  —  " + str(total) + " نفر"))
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
    print("PDF ساخته شد: " + str(output))


# ══════════════════════════════════════════════════════════════════════════════
# اجرا
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",      default="contacts.pdf")
    parser.add_argument("--pdf-only",    action="store_true",
                        help="فقط PDF بساز از contacts.json موجود، به تلگرام وصل نشو")
    parser.add_argument("--backup-dir",  default=str(BACKUP_DIR))
    args = parser.parse_args()

    backup_path = Path(args.backup_dir)

    if args.pdf_only:
        contacts_file = backup_path / "contacts.json"
        if not contacts_file.exists():
            print("contacts.json پیدا نشد.")
            return
        contacts = json.loads(contacts_file.read_text(encoding="utf-8"))
    else:
        contacts = asyncio.run(run_backup())

    if contacts:
        build_pdf(contacts, Path(args.output))


if __name__ == "__main__":
    main()
