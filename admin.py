"""Admin panel — event management, broadcasting, exports, stats.

All handlers are guarded by an admin-id check. Admins are configured
via the ADMIN_IDS environment variable.
"""

import asyncio
import html
import logging
import os
from datetime import datetime

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import config
import db
import texts

logger = logging.getLogger("atlon-bot.admin")

# Conversation states
AE_CITY, AE_TITLE, AE_DATE, AE_DESC, AE_PRICE = range(10, 15)
BC_TARGET, BC_MSG = range(20, 22)
ME_VALUE = 40

EXPORT_DIR = "exports"


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


async def _guard(update: Update) -> bool:
    """Return True if the caller is an admin; otherwise reply and stop."""
    if is_admin(update.effective_user.id):
        return True
    if update.message:
        await update.message.reply_text("⛔️ Bu buyruq faqat adminlar uchun.")
    return False


# ── /admin help ──────────────────────────────────────────────────

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    await update.message.reply_text(
        "🛠 <b>Admin panel</b>\n\n"
        "/addevent — yangi tadbir qo‘shish (shahar bo‘yicha bildirishnoma bilan)\n"
        "/events — tadbirlarni tahrirlash yoki o‘chirish\n"
        "/pending — tekshirilmagan tadbir arizalarini ko‘rish\n"
        "/broadcast — hammaga yoki shahar bo‘yicha xabar yuborish\n"
        "/export — arizalarni Excel faylga yuklab olish\n"
        "/stats — statistika\n"
        "/id — chat ID ni bilish\n"
        "/bekor — jarayonni bekor qilish",
        parse_mode=ParseMode.HTML,
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    users = db.count_users()
    apps = db.count_applications()
    lines = [
        "📊 <b>Statistika</b>\n",
        f"👥 Foydalanuvchilar: <b>{users}</b>",
        f"🤝 Volontyor arizalari: <b>{apps}</b>",
        f"🎫 Tadbir arizalari: <b>{db.count_registrations()}</b>",
        f"   ⏳ kutilmoqda: <b>{db.count_registrations(db.PENDING)}</b>",
        f"   ✅ tasdiqlangan: <b>{db.count_registrations(db.APPROVED)}</b>",
        f"   ❌ rad etilgan: <b>{db.count_registrations(db.REJECTED)}</b>\n",
        "<b>Shahar bo‘yicha obunachilar:</b>",
    ]
    for c in config.CITIES:
        n = len(db.user_ids_for_city(c["key"]))
        lines.append(f"• {c['name']}: {n}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ── Export to Excel ──────────────────────────────────────────────

async def export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    from openpyxl import Workbook

    apps = db.all_applications()
    wb = Workbook()
    ws = wb.active
    ws.title = "Volontyorlar"
    headers = [
        "ID", "Sana", "Ism-familiya", "Yosh", "Telefon",
        "Shahar", "Qiziqishlar", "Bio", "Username", "User ID",
    ]
    ws.append(headers)
    for a in apps:
        ws.append([
            a.id,
            a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
            a.full_name,
            a.age,
            a.phone,
            a.city_name,
            a.interests,
            a.bio,
            f"@{a.username}" if a.username else "",
            a.user_id,
        ])
    # Widen columns a little for readability.
    for col, width in zip("ABCDEFGHIJ", [6, 17, 24, 6, 16, 14, 24, 40, 16, 14]):
        ws.column_dimensions[col].width = width

    # Second sheet: event registrations.
    regs = db.all_registrations()
    events = {e.id: e for e in db.all_events()}
    ws2 = wb.create_sheet("Tadbir arizalari")
    ws2.append([
        "ID", "Sana", "Tadbir", "Shahar", "Ism-familiya", "Yosh",
        "Telefon", "Holat", "Username", "User ID",
    ])
    status_label = {
        db.PENDING: "Kutilmoqda",
        db.APPROVED: "Tasdiqlangan",
        db.REJECTED: "Rad etilgan",
    }
    for r in regs:
        ev = events.get(r.event_id)
        city = config.CITY_BY_KEY.get(ev.city) if ev else None
        ws2.append([
            r.id,
            r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
            ev.title if ev else f"#{r.event_id}",
            city["name"] if city else "",
            r.full_name,
            r.age,
            r.phone,
            status_label.get(r.status, r.status),
            f"@{r.username}" if r.username else "",
            r.user_id,
        ])
    for col, width in zip("ABCDEFGHIJ", [6, 17, 26, 14, 24, 6, 16, 14, 16, 14]):
        ws2.column_dimensions[col].width = width

    os.makedirs(EXPORT_DIR, exist_ok=True)
    path = os.path.join(
        EXPORT_DIR, f"atlon_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    wb.save(path)

    with open(path, "rb") as f:
        await update.message.reply_document(
            document=f,
            filename=os.path.basename(path),
            caption=(
                f"📄 Volontyor arizalari: {len(apps)} ta\n"
                f"🎫 Tadbir arizalari: {len(regs)} ta"
            ),
        )


# ── Add event ────────────────────────────────────────────────────

def _admin_city_keyboard(prefix: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(c["name"], callback_data=f"{prefix}:{c['key']}")
        for c in config.CITIES
    ]
    return InlineKeyboardMarkup(texts.chunk(buttons, config.CITY_COLUMNS))


async def addevent_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _guard(update):
        return ConversationHandler.END
    context.user_data["new_event"] = {}
    await update.message.reply_text(
        "🏙 Tadbir qaysi shaharda bo‘ladi?",
        reply_markup=_admin_city_keyboard("aecity"),
    )
    return AE_CITY


async def addevent_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    city_key = query.data.split(":", 1)[1]
    context.user_data["new_event"]["city"] = city_key
    city = config.CITY_BY_KEY.get(city_key)
    await query.edit_message_text(
        f"📍 Shahar: <b>{city['name']}</b>\n\nTadbir nomini yozing:",
        parse_mode=ParseMode.HTML,
    )
    return AE_TITLE


async def addevent_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_event"]["title"] = update.message.text.strip()
    await update.message.reply_text(
        "🗓 Tadbir sanasini yozing (masalan: 5-avgust, 18:00). "
        "Agar aniq bo‘lmasa, «-» yuboring:"
    )
    return AE_DATE


async def addevent_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    context.user_data["new_event"]["date"] = None if text == "-" else text
    await update.message.reply_text(
        "📝 Tadbir haqida qisqacha tavsif yozing (yoki «-» yuboring):"
    )
    return AE_DESC


async def addevent_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    context.user_data["new_event"]["description"] = None if text == "-" else text
    await update.message.reply_text(
        "💰 To‘lov summasini yozing (masalan: <b>50 000 so‘m</b>).\n"
        "Tadbir bepul bo‘lsa <b>Bepul</b> deb yozing, "
        "yoki ko‘rsatmaslik uchun «-» yuboring:",
        parse_mode=ParseMode.HTML,
    )
    return AE_PRICE


async def addevent_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    ev = context.user_data["new_event"]
    ev["price"] = None if text == "-" else text

    db.add_event(
        ev["city"], ev["title"], ev.get("date"), ev.get("description"), ev.get("price")
    )
    city = config.CITY_BY_KEY.get(ev["city"])

    await update.message.reply_text(
        f"✅ Tadbir qo‘shildi: <b>{ev['title']}</b> ({city['name']}).",
        parse_mode=ParseMode.HTML,
    )

    # Notify users interested in that city.
    notice = (
        f"🔔 <b>{html.escape(city['name'])}da yangi tadbir!</b>\n\n"
        f"🎉 <b>{html.escape(ev['title'])}</b>"
    )
    if ev.get("date"):
        notice += f"\n🗓 {html.escape(ev['date'])}"
    if ev.get("description"):
        notice += f"\n{html.escape(ev['description'])}"
    if ev.get("price"):
        notice += f"\n💰 To‘lov: {html.escape(ev['price'])}"

    sent = await _notify_users(context, db.user_ids_for_city(ev["city"]), notice)
    await update.message.reply_text(f"📨 {sent} ta foydalanuvchiga bildirishnoma yuborildi.")

    context.user_data.pop("new_event", None)
    return ConversationHandler.END


# ── Broadcast ────────────────────────────────────────────────────

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _guard(update):
        return ConversationHandler.END
    rows = [[InlineKeyboardButton("📣 Hammaga", callback_data="bcast:all")]]
    rows += texts.chunk(
        [
            InlineKeyboardButton(c["name"], callback_data=f"bcast:{c['key']}")
            for c in config.CITIES
        ],
        config.CITY_COLUMNS,
    )
    await update.message.reply_text(
        "📢 Xabarni kimga yuboramiz?", reply_markup=InlineKeyboardMarkup(rows)
    )
    return BC_TARGET


async def broadcast_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    target = query.data.split(":", 1)[1]
    context.user_data["bcast_target"] = target
    label = "hammaga" if target == "all" else config.CITY_BY_KEY[target]["name"]
    await query.edit_message_text(
        f"✍️ Yuboriladigan xabar matnini yozing (<b>{label}</b>):",
        parse_mode=ParseMode.HTML,
    )
    return BC_MSG


async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    target = context.user_data.get("bcast_target", "all")
    text = update.message.text

    if target == "all":
        user_ids = db.all_user_ids()
    else:
        user_ids = db.user_ids_for_city(target)

    await update.message.reply_text(f"⏳ Yuborilmoqda… ({len(user_ids)} ta)")
    # Broadcast is sent as plain text so arbitrary admin content never
    # breaks HTML parsing (which would silently drop every message).
    sent = await _notify_users(context, user_ids, text, parse_mode=None)
    await update.message.reply_text(f"✅ Tayyor. {sent} ta foydalanuvchiga yuborildi.")
    context.user_data.pop("bcast_target", None)
    return ConversationHandler.END


# ── Event management (list / edit / delete) ──────────────────────

EDITABLE = {
    "title": "Nom",
    "date": "Sana",
    "description": "Tavsif",
    "price": "To‘lov summasi",
}


async def manage_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    await update.message.reply_text(
        "🗂 <b>Tadbirlarni boshqarish</b>\n\nShaharni tanlang:",
        reply_markup=_admin_city_keyboard("admcity"),
        parse_mode=ParseMode.HTML,
    )


def _event_list_keyboard(city_key: str, events) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                (ev.title[:50] + "…") if len(ev.title) > 50 else ev.title,
                callback_data=f"admev:{ev.id}",
            )
        ]
        for ev in events
    ]
    rows.append([InlineKeyboardButton("⬅️ Shaharlar", callback_data="admlist")])
    return InlineKeyboardMarkup(rows)


async def manage_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return

    city_key = query.data.split(":", 1)[1]
    city = config.CITY_BY_KEY.get(city_key)
    if not city:
        return

    events = db.events_for_city(city_key)
    if not events:
        await query.edit_message_text(
            f"📍 <b>{html.escape(city['name'])}</b>\n\nBu shaharda tadbirlar yo‘q.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Shaharlar", callback_data="admlist")]]
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    await query.edit_message_text(
        f"📍 <b>{html.escape(city['name'])}</b> — {len(events)} ta tadbir.\n\n"
        "Tahrirlash yoki o‘chirish uchun tanlang:",
        reply_markup=_event_list_keyboard(city_key, events),
        parse_mode=ParseMode.HTML,
    )


async def manage_back_to_cities(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return
    await query.edit_message_text(
        "🗂 <b>Tadbirlarni boshqarish</b>\n\nShaharni tanlang:",
        reply_markup=_admin_city_keyboard("admcity"),
        parse_mode=ParseMode.HTML,
    )


def _event_detail_text(ev) -> str:
    city = config.CITY_BY_KEY.get(ev.city)
    regs = db.count_registrations_for_event(ev.id)
    return (
        f"🎉 <b>{html.escape(ev.title)}</b>\n"
        f"📍 {html.escape(city['name']) if city else '—'}\n"
        f"🗓 {html.escape(ev.date) if ev.date else '—'}\n"
        f"📝 {html.escape(ev.description) if ev.description else '—'}\n"
        f"💰 {html.escape(ev.price) if ev.price else '—'}\n\n"
        f"🎫 Arizalar: <b>{regs}</b>\n"
        f"🆔 <code>{ev.id}</code>"
    )


def _event_detail_keyboard(ev) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"✏️ {label}", callback_data=f"admedit:{ev.id}:{field}"
            )
        ]
        for field, label in EDITABLE.items()
    ]
    rows.append([InlineKeyboardButton("🗑 O‘chirish", callback_data=f"admdel:{ev.id}")])
    rows.append(
        [InlineKeyboardButton("⬅️ Orqaga", callback_data=f"admcity:{ev.city}")]
    )
    return InlineKeyboardMarkup(rows)


async def manage_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return

    event_id = int(query.data.split(":", 1)[1])
    ev = db.get_event(event_id)
    if ev is None:
        await query.edit_message_text("❗️ Tadbir topilmadi.")
        return

    await query.edit_message_text(
        _event_detail_text(ev),
        reply_markup=_event_detail_keyboard(ev),
        parse_mode=ParseMode.HTML,
    )


async def manage_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return

    event_id = int(query.data.split(":", 1)[1])
    ev = db.get_event(event_id)
    if ev is None:
        await query.edit_message_text("❗️ Tadbir topilmadi.")
        return

    regs = db.count_registrations_for_event(event_id)
    warning = (
        f"\n\n⚠️ Bu tadbirga <b>{regs} ta ariza</b> yuborilgan. "
        "Tadbir foydalanuvchilardan yashiriladi, lekin arizalar "
        "hisobotda (/export) saqlanib qoladi."
        if regs
        else ""
    )
    await query.edit_message_text(
        f"🗑 <b>O‘chirishni tasdiqlang</b>\n\n"
        f"🎉 {html.escape(ev.title)}{warning}",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Ha, o‘chirilsin", callback_data=f"admdelok:{ev.id}")],
                [InlineKeyboardButton("⬅️ Yo‘q, orqaga", callback_data=f"admev:{ev.id}")],
            ]
        ),
        parse_mode=ParseMode.HTML,
    )


async def manage_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not is_admin(update.effective_user.id):
        await query.answer("⛔️ Faqat adminlar uchun.", show_alert=True)
        return

    event_id = int(query.data.split(":", 1)[1])
    ev = db.get_event(event_id)
    ok = db.delete_event(event_id)
    await query.answer("🗑 O‘chirildi" if ok else "❗️ Topilmadi")

    if not ok:
        await query.edit_message_text("❗️ Tadbir topilmadi.")
        return

    await query.edit_message_text(
        f"🗑 <b>O‘chirildi:</b> {html.escape(ev.title) if ev else ''}",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⬅️ Tadbirlar ro‘yxati",
                        callback_data=f"admcity:{ev.city}" if ev else "admlist",
                    )
                ]
            ]
        ),
        parse_mode=ParseMode.HTML,
    )


async def manage_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    _, raw_id, field = query.data.split(":")
    event_id = int(raw_id)
    ev = db.get_event(event_id)
    if ev is None:
        await query.edit_message_text("❗️ Tadbir topilmadi.")
        return ConversationHandler.END

    context.user_data["edit_event"] = {"id": event_id, "field": field}
    current = getattr(ev, field, None)

    await query.edit_message_text(
        f"✏️ <b>{EDITABLE[field]}</b>ni tahrirlash\n\n"
        f"Hozirgi qiymat: <i>{html.escape(str(current)) if current else '—'}</i>\n\n"
        "Yangi qiymatni yuboring"
        + ("" if field == "title" else " (tozalash uchun «-» yuboring)")
        + ".\nBekor qilish: /bekor",
        parse_mode=ParseMode.HTML,
    )
    return ME_VALUE


async def manage_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    info = context.user_data.get("edit_event")
    if not info:
        return ConversationHandler.END

    text = update.message.text.strip()
    field = info["field"]

    if field == "title" and (not text or text == "-"):
        await update.message.reply_text("❗️ Nom bo‘sh bo‘lishi mumkin emas.")
        return ME_VALUE

    value = None if text == "-" else text
    ok = db.update_event(info["id"], field, value)
    context.user_data.pop("edit_event", None)

    if not ok:
        await update.message.reply_text("❗️ Tadbir topilmadi.")
        return ConversationHandler.END

    ev = db.get_event(info["id"])
    await update.message.reply_text(f"✅ <b>{EDITABLE[field]}</b> yangilandi.", parse_mode=ParseMode.HTML)
    await update.message.reply_text(
        _event_detail_text(ev),
        reply_markup=_event_detail_keyboard(ev),
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


# ── Registration review (approve / reject) ───────────────────────

async def review_registration_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle an admin tapping Tasdiqlash / Rad etish on a registration."""
    query = update.callback_query
    admin_id = update.effective_user.id

    if not is_admin(admin_id):
        await query.answer("⛔️ Faqat adminlar uchun.", show_alert=True)
        return

    action, raw_id = query.data.split(":", 1)
    reg_id = int(raw_id)
    new_status = db.APPROVED if action == "regok" else db.REJECTED

    changed, reg = db.review_registration(reg_id, new_status, admin_id)

    if reg is None:
        await query.answer("❗️ Ariza topilmadi.", show_alert=True)
        return

    if not changed:
        # Another admin already decided this one — don't notify the user twice.
        label = "tasdiqlangan" if reg.status == db.APPROVED else "rad etilgan"
        await query.answer(f"ℹ️ Bu ariza allaqachon {label}.", show_alert=True)
        await _mark_reviewed(query, reg.status, already=True)
        return

    await query.answer("✅ Tasdiqlandi" if new_status == db.APPROVED else "❌ Rad etildi")
    await _mark_reviewed(query, new_status)

    await _notify_applicant(context, reg, new_status)


async def _mark_reviewed(query, status: str, already: bool = False) -> None:
    """Stamp the decision onto the admin's message and drop the buttons."""
    stamp = (
        "\n\n✅ <b>TASDIQLANDI</b>"
        if status == db.APPROVED
        else "\n\n❌ <b>RAD ETILDI</b>"
    )
    if already:
        stamp += " <i>(boshqa admin tomonidan)</i>"
    try:
        if query.message.caption is not None:
            base = query.message.caption_html or query.message.caption
            await query.edit_message_caption(
                caption=base + stamp, parse_mode=ParseMode.HTML, reply_markup=None
            )
        else:
            # /pending falls back to a plain text message when a receipt
            # photo is missing — that one needs edit_message_text.
            base = query.message.text_html or query.message.text or ""
            await query.edit_message_text(
                text=base + stamp, parse_mode=ParseMode.HTML, reply_markup=None
            )
    except Exception as exc:  # noqa: BLE001 — message may be too old to edit
        logger.info("Could not update review message: %s", exc)


async def _notify_applicant(
    context: ContextTypes.DEFAULT_TYPE, reg, status: str
) -> None:
    """Tell the applicant the outcome; on approval include event details."""
    approved = status == db.APPROVED
    event = db.get_event(reg.event_id) if approved else None
    message = texts.decision_message(approved, event)

    try:
        await context.bot.send_message(
            chat_id=reg.user_id, text=message, parse_mode=ParseMode.HTML
        )
    except Exception as exc:  # noqa: BLE001 — user may have blocked the bot
        logger.info("Could not notify applicant %s: %s", reg.user_id, exc)


async def pending_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Re-send every still-unreviewed registration to the requesting admin."""
    if not await _guard(update):
        return

    pending = db.pending_registrations()
    if not pending:
        await update.message.reply_text("✅ Tekshirilmagan arizalar yo‘q.")
        return

    await update.message.reply_text(f"⏳ {len(pending)} ta ariza kutilmoqda:")
    for reg in pending:
        event = db.get_event(reg.event_id)
        caption = (
            "🧾 <b>Tadbir arizasi</b>\n\n"
            f"🎉 <b>Tadbir:</b> {html.escape(event.title) if event else '—'}\n"
            f"👤 <b>Ism:</b> {html.escape(reg.full_name or '—')}\n"
            f"🎂 <b>Yosh:</b> {reg.age or '—'}\n"
            f"📞 <b>Telefon:</b> {html.escape(reg.phone or '—')}\n\n"
            f"🆔 Ariza №{reg.id}"
        )
        try:
            if reg.receipt_file_id:
                kwargs = dict(
                    chat_id=update.effective_user.id,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=texts.review_keyboard(reg.id),
                )
                if (reg.receipt_kind or "photo") == "photo":
                    await context.bot.send_photo(photo=reg.receipt_file_id, **kwargs)
                else:
                    await context.bot.send_document(
                        document=reg.receipt_file_id, **kwargs
                    )
            else:
                await update.message.reply_text(
                    caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=texts.review_keyboard(reg.id),
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("Could not resend registration %s: %s", reg.id, exc)
        await asyncio.sleep(0.05)


# ── Shared helpers ───────────────────────────────────────────────

async def _notify_users(
    context: ContextTypes.DEFAULT_TYPE, user_ids, text: str, parse_mode=ParseMode.HTML
) -> int:
    sent = 0
    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=text, parse_mode=parse_mode)
            sent += 1
        except Exception as exc:  # noqa: BLE001 — user may have blocked the bot
            logger.info("Notify failed for %s: %s", uid, exc)
        await asyncio.sleep(0.05)  # gentle rate limiting
    return sent


async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("new_event", None)
    context.user_data.pop("bcast_target", None)
    context.user_data.pop("edit_event", None)
    await update.message.reply_text(
        "❌ Bekor qilindi.", reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


# ── Registration ─────────────────────────────────────────────────

def register_admin_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("admin", admin_help))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("export", export))
    application.add_handler(CommandHandler("pending", pending_list))
    application.add_handler(
        CallbackQueryHandler(review_registration_cb, pattern=r"^reg(ok|no):\d+$")
    )

    # Event management: list → detail → edit/delete
    edit_event_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                manage_edit_start,
                pattern=r"^admedit:\d+:(title|date|description|price)$",
            )
        ],
        states={
            ME_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manage_edit_value)
            ]
        },
        fallbacks=[
            CommandHandler("bekor", admin_cancel),
            CommandHandler("cancel", admin_cancel),
        ],
        allow_reentry=True,
    )

    application.add_handler(CommandHandler("events", manage_start))
    application.add_handler(edit_event_conv)
    application.add_handler(CallbackQueryHandler(manage_city, pattern=r"^admcity:"))
    application.add_handler(
        CallbackQueryHandler(manage_back_to_cities, pattern=r"^admlist$")
    )
    application.add_handler(CallbackQueryHandler(manage_event, pattern=r"^admev:\d+$"))
    application.add_handler(
        CallbackQueryHandler(manage_delete_confirm, pattern=r"^admdel:\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(manage_delete, pattern=r"^admdelok:\d+$")
    )

    addevent_conv = ConversationHandler(
        entry_points=[CommandHandler("addevent", addevent_start)],
        states={
            AE_CITY: [CallbackQueryHandler(addevent_city, pattern="^aecity:")],
            AE_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, addevent_title)],
            AE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, addevent_date)],
            AE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, addevent_desc)],
            AE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, addevent_price)],
        },
        fallbacks=[CommandHandler("bekor", admin_cancel), CommandHandler("cancel", admin_cancel)],
        allow_reentry=True,
    )

    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={
            BC_TARGET: [CallbackQueryHandler(broadcast_target, pattern="^bcast:")],
            BC_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message)],
        },
        fallbacks=[CommandHandler("bekor", admin_cancel), CommandHandler("cancel", admin_cancel)],
        allow_reentry=True,
    )

    application.add_handler(addevent_conv)
    application.add_handler(broadcast_conv)
