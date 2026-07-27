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
AE_CITY, AE_TITLE, AE_DATE, AE_DESC = range(10, 14)
BC_TARGET, BC_MSG = range(20, 22)

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
        "/addevent — yangi tadbir qo‘shish (hudud bo‘yicha bildirishnoma bilan)\n"
        "/broadcast — hammaga yoki hudud bo‘yicha xabar yuborish\n"
        "/export — arizalarni Excel faylga yuklab olish\n"
        "/stats — statistika\n"
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
        f"📝 Arizalar: <b>{apps}</b>\n",
        "<b>Hudud bo‘yicha obunachilar:</b>",
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

    os.makedirs(EXPORT_DIR, exist_ok=True)
    path = os.path.join(
        EXPORT_DIR, f"volontyorlar_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    wb.save(path)

    with open(path, "rb") as f:
        await update.message.reply_document(
            document=f,
            filename=os.path.basename(path),
            caption=f"📄 Jami {len(apps)} ta ariza.",
        )


# ── Add event ────────────────────────────────────────────────────

def _admin_city_keyboard(prefix: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(c["name"], callback_data=f"{prefix}:{c['key']}")
        for c in config.CITIES
    ]
    return InlineKeyboardMarkup(texts._in_pairs(buttons))


async def addevent_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _guard(update):
        return ConversationHandler.END
    context.user_data["new_event"] = {}
    await update.message.reply_text(
        "🏙 Tadbir qaysi hududda bo‘ladi?",
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
        f"📍 Hudud: <b>{city['name']}</b>\n\nTadbir nomini yozing:",
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
    ev = context.user_data["new_event"]
    ev["description"] = None if text == "-" else text

    db.add_event(ev["city"], ev["title"], ev.get("date"), ev.get("description"))
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

    sent = await _notify_users(context, db.user_ids_for_city(ev["city"]), notice)
    await update.message.reply_text(f"📨 {sent} ta foydalanuvchiga bildirishnoma yuborildi.")

    context.user_data.pop("new_event", None)
    return ConversationHandler.END


# ── Broadcast ────────────────────────────────────────────────────

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _guard(update):
        return ConversationHandler.END
    rows = [[InlineKeyboardButton("📣 Hammaga", callback_data="bcast:all")]]
    rows += texts._in_pairs([
        InlineKeyboardButton(c["name"], callback_data=f"bcast:{c['key']}")
        for c in config.CITIES
    ])
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
    await update.message.reply_text(
        "❌ Bekor qilindi.", reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


# ── Registration ─────────────────────────────────────────────────

def register_admin_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("admin", admin_help))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("export", export))

    addevent_conv = ConversationHandler(
        entry_points=[CommandHandler("addevent", addevent_start)],
        states={
            AE_CITY: [CallbackQueryHandler(addevent_city, pattern="^aecity:")],
            AE_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, addevent_title)],
            AE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, addevent_date)],
            AE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, addevent_desc)],
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
