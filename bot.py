"""ATLON GROUP Telegram bot — entry point and core user flows.

Flow:
  /start → subscription gate → main menu
  main menu → About / Events (by city) / Volunteer application
  application → saved to DB + Excel export + forwarded to the city group
  new events → city-based notifications to interested users
"""

import html
import logging

from telegram import Update
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
import texts
import db
from admin import register_admin_handlers

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("atlon-bot")

# Conversation states for the volunteer application
CITY, NAME, AGE, PHONE, INTERESTS, BIO = range(6)

# Conversation states for event registration
REG_NAME, REG_AGE, REG_PHONE, REG_RECEIPT = range(30, 34)


# ── Subscription gate ────────────────────────────────────────────

async def is_subscribed(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """True if the user is a member of the required channel.

    If no channel is configured, the gate is disabled (everyone passes).
    If the check fails because the bot is mis-configured (e.g. not an
    admin of the channel), we log it and let the user through rather
    than locking everyone out.
    """
    if not config.CHANNEL_USERNAME:
        return True
    try:
        member = await context.bot.get_chat_member(
            chat_id=config.CHANNEL_USERNAME, user_id=user_id
        )
        return member.status in ("member", "administrator", "creator", "owner")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Subscription check failed for %s (channel=%s): %s. "
            "Is the bot an admin of the channel? Letting user through.",
            user_id,
            config.CHANNEL_USERNAME,
            exc,
        )
        return True


# ── /start and menu ──────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.full_name)

    if await is_subscribed(context, user.id):
        db.set_user_subscribed(user.id, True)
        await update.message.reply_text(
            texts.MENU_TITLE,
            reply_markup=texts.main_menu_keyboard(),
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            texts.WELCOME,
            reply_markup=texts.subscribe_keyboard(),
            parse_mode=ParseMode.HTML,
        )


async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    if await is_subscribed(context, user.id):
        db.set_user_subscribed(user.id, True)
        await query.edit_message_text(
            texts.MENU_TITLE,
            reply_markup=texts.main_menu_keyboard(),
            parse_mode=ParseMode.HTML,
        )
    else:
        await query.edit_message_text(
            texts.STILL_NOT_SUBSCRIBED,
            reply_markup=texts.subscribe_keyboard(),
            parse_mode=ParseMode.HTML,
        )


async def chat_id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Report the current chat's id — used to configure city groups.

    Run /id inside a group to get its chat id (looks like -100…), then put
    that value in the matching GROUP_* environment variable on Railway.
    """
    chat = update.effective_chat
    user = update.effective_user
    await update.message.reply_text(
        "🆔 <b>Chat ma’lumotlari</b>\n\n"
        f"<b>Chat ID:</b> <code>{chat.id}</code>\n"
        f"<b>Turi:</b> {chat.type}\n"
        f"<b>Sizning ID:</b> <code>{user.id}</code>",
        parse_mode=ParseMode.HTML,
    )


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        texts.MENU_TITLE,
        reply_markup=texts.main_menu_keyboard(),
        parse_mode=ParseMode.HTML,
    )


async def show_about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        texts.ABOUT,
        reply_markup=texts.back_to_menu_keyboard(),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


# ── Events ───────────────────────────────────────────────────────

async def events_pick_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        texts.EVENTS_PICK_CITY,
        reply_markup=texts.city_inline_keyboard("evcity"),
    )


def _e(value) -> str:
    """HTML-escape a dynamic value for safe insertion into HTML messages."""
    if value is None:
        return "—"
    return html.escape(str(value))


def format_event_card(event, city_name: str, index: int, total: int) -> str:
    """Render a single event as a card, with its position in the list."""
    lines = [
        f"📍 <b>{_e(city_name)}</b>  <i>({index + 1}/{total})</i>\n",
        f"🎉 <b>{_e(event.title)}</b>",
    ]
    if event.date:
        lines.append(f"🗓 {_e(event.date)}")
    if event.description:
        lines.append(f"\n{_e(event.description)}")
    if event.price:
        lines.append(f"\n💰 <b>To‘lov:</b> {_e(event.price)}")
    # Same on every event, so it comes from the configured channel rather
    # than being retyped into each event's description.
    lines.append(f"\n{texts.channel_note()}")
    return "\n".join(lines)


async def show_event_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show one event at a time for a city.

    Handles both the initial city pick ('evcity:<key>') and paging
    ('ev:<key>:<index>'). Editing the message replaces the city buttons
    with the event card, so the city list disappears as requested.
    """
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    city_key = parts[1]
    index = int(parts[2]) if len(parts) > 2 else 0

    city = config.CITY_BY_KEY.get(city_key)
    if not city:
        return

    # Remember the user's city interest for future notifications.
    db.set_user_city(update.effective_user.id, city_key)

    events = db.events_for_city(city_key)
    if not events:
        await query.edit_message_text(
            f"📍 <b>{_e(city['name'])}</b>\n\n{texts.NO_EVENTS}",
            reply_markup=texts.no_events_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        return

    # Clamp the index in case events were removed while the user was browsing.
    index = max(0, min(index, len(events) - 1))
    event = events[index]

    await query.edit_message_text(
        format_event_card(event, city["name"], index, len(events)),
        reply_markup=texts.event_card_keyboard(city_key, index, len(events), event.id),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


# ── Volunteer application conversation ───────────────────────────

async def vol_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["application"] = {}
    # Inline keyboards can't be replaced with a reply keyboard on the same
    # message, so send a fresh message carrying the city reply keyboard.
    await query.message.reply_text(
        texts.VOL_INTRO,
        reply_markup=texts.city_reply_keyboard(),
        parse_mode=ParseMode.HTML,
    )
    return CITY


async def vol_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    city = config.CITY_BY_NAME.get(name)
    if not city:
        await update.message.reply_text(
            "❗️ Iltimos, ro‘yxatdagi tugmalardan birini tanlang.",
            reply_markup=texts.city_reply_keyboard(),
        )
        return CITY
    context.user_data["application"]["city"] = city["key"]
    context.user_data["application"]["city_name"] = city["name"]
    await update.message.reply_text(texts.VOL_ASK_NAME)
    return NAME


async def vol_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["application"]["full_name"] = update.message.text.strip()
    await update.message.reply_text(texts.VOL_ASK_AGE)
    return AGE


async def vol_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if not raw.isdigit() or not (5 <= int(raw) <= 100):
        await update.message.reply_text(texts.VOL_AGE_INVALID)
        return AGE
    context.user_data["application"]["age"] = int(raw)
    await update.message.reply_text(
        texts.VOL_ASK_PHONE,
        reply_markup=texts.phone_reply_keyboard(),
        parse_mode=ParseMode.HTML,
    )
    return PHONE


async def vol_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text.strip()
    context.user_data["application"]["phone"] = phone
    from telegram import ReplyKeyboardRemove

    # Two messages: the first clears the contact keyboard (a reply keyboard
    # and an inline keyboard can't travel on the same message), the second
    # carries the direction buttons.
    await update.message.reply_text(
        f"📞 Qabul qilindi: {_e(phone)}",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.HTML,
    )
    await update.message.reply_text(
        texts.VOL_ASK_INTERESTS,
        reply_markup=texts.interests_keyboard(),
        parse_mode=ParseMode.HTML,
    )
    return INTERESTS


async def vol_interests_btn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """A direction button was tapped: record it and move straight on.

    Storing the canonical label keeps every application spelled the same,
    which is what makes filtering them worthwhile.
    """
    query = update.callback_query
    if "application" not in context.user_data:
        await query.answer("Ariza yakunlangan.", show_alert=True)
        return ConversationHandler.END

    item = config.INTEREST_BY_KEY.get(query.data.split(":", 1)[1])
    if item is None:
        await query.answer()
        return INTERESTS

    await query.answer(item["label"])
    context.user_data["application"]["interests"] = item["label"]

    # Replace the buttons with the choice, so it reads as recorded and
    # can't be tapped twice.
    await query.edit_message_text(
        texts.VOL_INTEREST_CHOSEN.format(label=_e(item["label"])),
        parse_mode=ParseMode.HTML,
    )
    await query.message.reply_text(texts.VOL_ASK_BIO)
    return BIO


async def vol_interests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Typed instead of tapped — accepted, for anything not on the list."""
    context.user_data["application"]["interests"] = update.message.text.strip()
    await update.message.reply_text(texts.VOL_ASK_BIO)
    return BIO


async def stale_interest_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """A direction button tapped after the form was finished or abandoned."""
    await update.callback_query.answer(
        "Bu ariza yakunlangan. Yangi ariza uchun menyudan boshlang.",
        show_alert=True,
    )


async def vol_bio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data["application"]
    data["bio"] = update.message.text.strip()

    user = update.effective_user
    data["user_id"] = user.id
    data["username"] = user.username

    # Persist.
    try:
        db.add_application(data)
        db.set_user_city(user.id, data["city"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to save application: %s", exc)

    # Forward to the city's group.
    await send_application_to_group(context, data)

    await update.message.reply_text(texts.VOL_DONE, parse_mode=ParseMode.HTML)
    await update.message.reply_text(
        texts.MENU_TITLE,
        reply_markup=texts.main_menu_keyboard(),
        parse_mode=ParseMode.HTML,
    )
    context.user_data.pop("application", None)
    return ConversationHandler.END


async def vol_nav_away(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Abandon the volunteer form when the user navigates away via a button."""
    from telegram import ReplyKeyboardRemove

    context.user_data.pop("application", None)
    data = update.callback_query.data
    if data == "menu":
        await show_menu(update, context)
    elif data == "events":
        await events_pick_city(update, context)
    elif data == "about":
        await show_about(update, context)
    else:
        await show_event_card(update, context)
    # Drop the lingering city/phone reply keyboard.
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="ℹ️ Ariza to‘ldirish bekor qilindi.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def vol_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from telegram import ReplyKeyboardRemove

    context.user_data.pop("application", None)
    await update.message.reply_text(
        texts.VOL_CANCELLED, reply_markup=ReplyKeyboardRemove()
    )
    await update.message.reply_text(
        texts.MENU_TITLE,
        reply_markup=texts.main_menu_keyboard(),
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


def _format_application(data: dict) -> str:
    username = f"@{_e(data['username'])}" if data.get("username") else "—"
    return (
        "🆕 <b>Yangi volontyor arizasi</b>\n\n"
        f"👤 <b>Ism:</b> {_e(data.get('full_name'))}\n"
        f"🎂 <b>Yosh:</b> {_e(data.get('age'))}\n"
        f"📞 <b>Telefon:</b> {_e(data.get('phone'))}\n"
        f"📍 <b>Shahar:</b> {_e(data.get('city_name'))}\n"
        f"🎯 <b>Qiziqishlar:</b> {_e(data.get('interests'))}\n"
        f"📝 <b>Bio:</b> {_e(data.get('bio'))}\n\n"
        f"🔗 <b>Telegram:</b> {username} (id: <code>{data.get('user_id')}</code>)"
    )


# ── Event registration conversation ──────────────────────────────

async def evreg_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    event_id = int(query.data.split(":", 1)[1])
    event = db.get_event(event_id)
    # is_active == 0 means an admin deleted it while this card was still
    # open on someone's screen.
    if event is None or event.is_active == 0:
        await query.message.reply_text(texts.EVREG_EVENT_GONE)
        return ConversationHandler.END

    # Don't let the same person apply twice while a decision is outstanding.
    existing = db.active_registration(event_id, update.effective_user.id)
    if existing is not None:
        message = (
            texts.EVREG_ALREADY_APPROVED
            if existing.status == db.APPROVED
            else texts.EVREG_ALREADY_PENDING
        )
        await query.message.reply_text(message)
        return ConversationHandler.END

    context.user_data["evreg"] = {"event_id": event_id}

    city = config.CITY_BY_KEY.get(event.city)
    header = (
        f"🎫 <b>{_e(event.title)}</b>\n"
        f"{('🗓 ' + _e(event.date)) if event.date else ''}\n"
        f"📍 {_e(city['name']) if city else '—'}\n"
    )
    if event.price:
        header += f"💰 <b>To‘lov summasi:</b> {_e(event.price)}\n"

    await query.message.reply_text(
        header + "\n" + texts.EVREG_ASK_NAME, parse_mode=ParseMode.HTML
    )
    return REG_NAME


async def evreg_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["evreg"]["full_name"] = update.message.text.strip()
    await update.message.reply_text(texts.EVREG_ASK_AGE)
    return REG_AGE


async def evreg_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if not raw.isdigit() or not (5 <= int(raw) <= 100):
        await update.message.reply_text(texts.EVREG_AGE_INVALID)
        return REG_AGE
    context.user_data["evreg"]["age"] = int(raw)
    await update.message.reply_text(
        texts.EVREG_ASK_PHONE,
        reply_markup=texts.phone_reply_keyboard(),
        parse_mode=ParseMode.HTML,
    )
    return REG_PHONE


async def evreg_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from telegram import ReplyKeyboardRemove

    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text.strip()
    data = context.user_data["evreg"]
    data["phone"] = phone

    # Remind them of the amount right where they need to pay it.
    event = db.get_event(data["event_id"])
    await update.message.reply_text(
        texts.receipt_prompt(event.price if event else None),
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.HTML,
    )
    return REG_RECEIPT


async def evreg_receipt_invalid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Text, stickers, voice notes and the like are refused."""
    await update.message.reply_text(
        texts.EVREG_RECEIPT_INVALID, parse_mode=ParseMode.HTML
    )
    return REG_RECEIPT


# File types a receipt can plausibly be.
ALLOWED_RECEIPT_MIME_PREFIXES = ("image/",)
ALLOWED_RECEIPT_MIME = ("application/pdf",)


async def evreg_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data.get("evreg")
    if not data:
        return ConversationHandler.END

    message = update.message
    if message.photo:
        # photo is a list of sizes; the last one is the highest resolution.
        data["receipt_file_id"] = message.photo[-1].file_id
        data["receipt_kind"] = "photo"
        data["receipt_mime"] = "image/jpeg"
    else:
        doc = message.document
        mime = (doc.mime_type or "").lower()
        allowed = mime.startswith(ALLOWED_RECEIPT_MIME_PREFIXES) or mime in ALLOWED_RECEIPT_MIME
        if not allowed:
            await message.reply_text(
                texts.EVREG_RECEIPT_BAD_FILE, parse_mode=ParseMode.HTML
            )
            return REG_RECEIPT
        data["receipt_file_id"] = doc.file_id
        data["receipt_kind"] = "document"
        data["receipt_mime"] = mime

    user = update.effective_user
    data["user_id"] = user.id
    data["username"] = user.username

    try:
        reg_id = db.add_registration(data)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to save event registration: %s", exc)
        await update.message.reply_text(
            "❗️ Xatolik yuz berdi. Iltimos, birozdan so‘ng qayta urinib ko‘ring."
        )
        context.user_data.pop("evreg", None)
        return ConversationHandler.END

    await update.message.reply_text(texts.EVREG_DONE, parse_mode=ParseMode.HTML)

    await send_registration_for_review(context, reg_id, data)

    context.user_data.pop("evreg", None)
    return ConversationHandler.END


async def evreg_nav_away(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User tapped a navigation button while filling the form.

    Without this, the old event card's buttons would still navigate while
    the conversation stayed active, and the next message they typed would
    be silently swallowed as a form answer.
    """
    context.user_data.pop("evreg", None)
    data = update.callback_query.data
    if data == "menu":
        await show_menu(update, context)
    elif data == "events":
        await events_pick_city(update, context)
    else:
        await show_event_card(update, context)
    return ConversationHandler.END


async def evreg_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from telegram import ReplyKeyboardRemove

    context.user_data.pop("evreg", None)
    await update.message.reply_text(
        texts.EVREG_CANCELLED, reply_markup=ReplyKeyboardRemove()
    )
    await update.message.reply_text(
        texts.MENU_TITLE,
        reply_markup=texts.main_menu_keyboard(),
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


async def send_registration_for_review(
    context: ContextTypes.DEFAULT_TYPE, reg_id: int, data: dict
) -> None:
    """Send the registration + receipt photo to every admin for approval."""
    event = db.get_event(data["event_id"])
    city = config.CITY_BY_KEY.get(event.city) if event else None
    username = f"@{_e(data['username'])}" if data.get("username") else "—"

    caption = (
        "🧾 <b>Yangi tadbir arizasi</b>\n\n"
        f"🎉 <b>Tadbir:</b> {_e(event.title) if event else '—'}\n"
        f"📍 <b>Shahar:</b> {_e(city['name']) if city else '—'}\n"
        f"💰 <b>To‘lov:</b> {_e(event.price) if event and event.price else '—'}\n\n"
        f"👤 <b>Ism:</b> {_e(data.get('full_name'))}\n"
        f"🎂 <b>Yosh:</b> {_e(data.get('age'))}\n"
        f"📞 <b>Telefon:</b> {_e(data.get('phone'))}\n"
        f"🔗 <b>Telegram:</b> {username} (id: <code>{data.get('user_id')}</code>)\n\n"
        f"🆔 Ariza №{reg_id}"
    )

    if not config.ADMIN_IDS:
        logger.warning(
            "Registration %s has no admins to review it — set ADMIN_IDS.", reg_id
        )
        return

    is_photo = data.get("receipt_kind", "photo") == "photo"
    for admin_id in config.ADMIN_IDS:
        try:
            kwargs = dict(
                chat_id=admin_id,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=texts.review_keyboard(reg_id),
            )
            if is_photo:
                await context.bot.send_photo(photo=data["receipt_file_id"], **kwargs)
            else:
                # A file receipt must go back out as a document, not a photo.
                await context.bot.send_document(
                    document=data["receipt_file_id"], **kwargs
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("Could not send registration %s to admin %s: %s", reg_id, admin_id, exc)


async def send_application_to_group(context: ContextTypes.DEFAULT_TYPE, data: dict) -> None:
    chat_id = config.group_chat_id(data["city"])
    if not chat_id:
        logger.info(
            "No group configured for city '%s'; application not forwarded.",
            data["city"],
        )
        return
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=_format_application(data),
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not send application to group %s: %s", chat_id, exc)


# ── App wiring ───────────────────────────────────────────────────

def build_application() -> Application:
    application = Application.builder().token(config.BOT_TOKEN).build()

    volunteer_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(vol_start, pattern="^volunteer$")],
        states={
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, vol_city)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, vol_name)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, vol_age)],
            PHONE: [
                MessageHandler(
                    (filters.TEXT & ~filters.COMMAND) | filters.CONTACT, vol_phone
                )
            ],
            INTERESTS: [
                CallbackQueryHandler(vol_interests_btn, pattern=r"^vint:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, vol_interests),
            ],
            BIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, vol_bio)],
        },
        fallbacks=[
            CommandHandler("bekor", vol_cancel),
            CommandHandler("cancel", vol_cancel),
            CommandHandler("start", vol_cancel),
            CallbackQueryHandler(
                vol_nav_away, pattern=r"^(menu|about|events|evcity:|ev:)"
            ),
        ],
        allow_reentry=True,
    )

    event_reg_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(evreg_start, pattern=r"^evreg:\d+$")],
        states={
            REG_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, evreg_name)],
            REG_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, evreg_age)],
            REG_PHONE: [
                MessageHandler(
                    (filters.TEXT & ~filters.COMMAND) | filters.CONTACT, evreg_phone
                )
            ],
            REG_RECEIPT: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, evreg_receipt),
                # Text, stickers, voice, etc. are refused with an
                # explanation and the user stays on this step.
                MessageHandler(
                    ~(filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND,
                    evreg_receipt_invalid,
                ),
            ],
        },
        fallbacks=[
            CommandHandler("bekor", evreg_cancel),
            CommandHandler("cancel", evreg_cancel),
            CommandHandler("start", evreg_cancel),
            CallbackQueryHandler(
                evreg_nav_away, pattern=r"^(menu|events|evcity:|ev:)"
            ),
        ],
        allow_reentry=True,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("id", chat_id_cmd))
    application.add_handler(volunteer_conv)
    application.add_handler(event_reg_conv)
    application.add_handler(CallbackQueryHandler(check_subscription, pattern="^check_sub$"))
    application.add_handler(CallbackQueryHandler(show_menu, pattern="^menu$"))
    application.add_handler(CallbackQueryHandler(show_about, pattern="^about$"))
    application.add_handler(CallbackQueryHandler(events_pick_city, pattern="^events$"))
    application.add_handler(CallbackQueryHandler(show_event_card, pattern="^evcity:"))
    application.add_handler(CallbackQueryHandler(show_event_card, pattern=r"^ev:"))
    # Registered after the conversation, so it only catches taps on
    # buttons left over from a form that is no longer running.
    application.add_handler(
        CallbackQueryHandler(stale_interest_button, pattern=r"^vint:")
    )

    register_admin_handlers(application)

    return application


def main() -> None:
    for problem in config.validate():
        logger.warning("CONFIG: %s", problem)

    if not config.BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN is required. Set it in your environment / Railway variables."
        )

    db.init_db()
    application = build_application()
    logger.info("Atlon Group bot is starting (polling)…")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
