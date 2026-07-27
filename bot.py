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


async def chat_id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with the current chat's id — used to configure city groups.

    Run this inside each city group to get the value for the matching
    GROUP_* environment variable. Works even with privacy mode on,
    because Telegram always delivers slash commands to the bot.
    """
    chat = update.effective_chat
    await update.message.reply_text(
        f"🆔 <b>Chat ID:</b> <code>{chat.id}</code>\n"
        f"📂 <b>Turi:</b> {chat.type}\n"
        f"📛 <b>Nomi:</b> {_e(chat.title or chat.full_name)}",
        parse_mode=ParseMode.HTML,
    )
    logger.info("Chat id requested: %s (%s, %s)", chat.id, chat.type, chat.title)


# ── Events ───────────────────────────────────────────────────────

async def events_pick_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        texts.EVENTS_PICK_CITY,
        reply_markup=texts.city_inline_keyboard("evcity"),
    )


async def events_for_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    city_key = query.data.split(":", 1)[1]
    city = config.CITY_BY_KEY.get(city_key)
    if not city:
        return

    # Remember the user's city interest for future notifications.
    db.set_user_city(update.effective_user.id, city_key)

    events = db.events_for_city(city_key)
    if not events:
        text = f"📍 <b>{city['name']}</b>\n\n{texts.NO_EVENTS}"
    else:
        parts = [f"📍 <b>{city['name']} — tadbirlar</b>\n"]
        for ev in events:
            block = f"\n🎉 <b>{html.escape(ev.title)}</b>"
            if ev.date:
                block += f"\n🗓 {html.escape(ev.date)}"
            if ev.description:
                block += f"\n{html.escape(ev.description)}"
            parts.append(block)
        text = "\n".join(parts)

    await query.edit_message_text(
        text,
        reply_markup=texts.city_inline_keyboard("evcity"),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


# ── Volunteer application conversation ───────────────────────────

async def vol_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["application"] = {}
    # The region grid rides along with the intro message as an inline
    # keyboard, so it doesn't cover the user's typing keyboard.
    await query.edit_message_text(
        texts.VOL_INTRO,
        reply_markup=texts.volunteer_city_keyboard(),
        parse_mode=ParseMode.HTML,
    )
    return CITY


async def vol_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    city_key = query.data.split(":", 1)[1]
    city = config.CITY_BY_KEY.get(city_key)
    if not city:
        return CITY

    # Guard against a stale button from an application the user already
    # finished or cancelled — restart cleanly instead of raising KeyError.
    app = context.user_data.setdefault("application", {})
    app["city"] = city["key"]
    app["city_name"] = city["name"]

    # Freeze the choice into the original message and drop the buttons,
    # so old messages in the chat can't be tapped again later.
    await query.edit_message_text(
        f"📍 <b>Hudud:</b> {html.escape(city['name'])}",
        parse_mode=ParseMode.HTML,
    )
    await query.message.reply_text(texts.VOL_ASK_NAME)
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

    await update.message.reply_text(
        texts.VOL_ASK_INTERESTS, reply_markup=ReplyKeyboardRemove()
    )
    return INTERESTS


async def vol_interests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["application"]["interests"] = update.message.text.strip()
    await update.message.reply_text(texts.VOL_ASK_BIO)
    return BIO


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


async def vol_cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel from the inline ❌ button on the region picker."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop("application", None)
    await query.edit_message_text(
        texts.MENU_TITLE,
        reply_markup=texts.main_menu_keyboard(),
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


def _e(value) -> str:
    """HTML-escape a dynamic value for safe insertion into HTML messages."""
    if value is None:
        return "—"
    return html.escape(str(value))


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
            CITY: [
                CallbackQueryHandler(vol_city, pattern="^volcity:"),
                CallbackQueryHandler(vol_cancel_cb, pattern="^volcancel$"),
            ],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, vol_name)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, vol_age)],
            PHONE: [
                MessageHandler(
                    (filters.TEXT & ~filters.COMMAND) | filters.CONTACT, vol_phone
                )
            ],
            INTERESTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, vol_interests)],
            BIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, vol_bio)],
        },
        fallbacks=[
            CommandHandler("bekor", vol_cancel),
            CommandHandler("cancel", vol_cancel),
        ],
        allow_reentry=True,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("id", chat_id_cmd))
    application.add_handler(volunteer_conv)
    application.add_handler(CallbackQueryHandler(check_subscription, pattern="^check_sub$"))
    application.add_handler(CallbackQueryHandler(show_menu, pattern="^menu$"))
    application.add_handler(CallbackQueryHandler(show_about, pattern="^about$"))
    application.add_handler(CallbackQueryHandler(events_pick_city, pattern="^events$"))
    application.add_handler(CallbackQueryHandler(events_for_city, pattern="^evcity:"))

    register_admin_handlers(application)

    return application


def main() -> None:
    for problem in config.validate():
        logger.warning("CONFIG: %s", problem)

    if not config.BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN is required. Set it in your environment / Railway variables."
        )

    # Show which city groups are wired up — the most common deploy mistake
    # is a missing or wrong GROUP_* variable, and this makes it obvious.
    for city in config.CITIES:
        chat_id = config.group_chat_id(city["key"])
        if chat_id:
            logger.info("GROUP: %-10s → %s", city["name"], chat_id)
        else:
            logger.warning(
                "GROUP: %-10s → not set (%s). Applications for this city "
                "will not be forwarded anywhere.",
                city["name"],
                city["group_env"],
            )

    db.init_db()
    application = build_application()
    logger.info("Atlon Group bot is starting (polling)…")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
