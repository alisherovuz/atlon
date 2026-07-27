"""User-facing text and reusable keyboards (Uzbek).

Keeping copy in one place makes it easy to edit wording without
touching the bot logic.
"""

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

import config

# ── Static copy ──────────────────────────────────────────────────

WELCOME = (
    "👋 <b>Assalomu alaykum va Atlon Group botiga xush kelibsiz!</b>\n\n"
    "Bu bot orqali siz:\n"
    "• Loyihamiz haqida ma’lumot olasiz\n"
    "• Shaharlar bo‘yicha tadbirlarni ko‘rasiz\n"
    "• Volontyor bo‘lib ro‘yxatdan o‘tasiz\n\n"
    "Davom etish uchun avval rasmiy kanalimizga obuna bo‘ling 👇"
)

NOT_SUBSCRIBED = (
    "❗️ Botdan foydalanish uchun avval kanalimizga obuna bo‘lishingiz kerak.\n\n"
    "Obuna bo‘lgach, <b>“✅ Obuna bo‘ldim”</b> tugmasini bosing."
)

STILL_NOT_SUBSCRIBED = (
    "🚫 Hali obuna bo‘lmadingiz shekilli.\n\n"
    "Iltimos, kanalga obuna bo‘ling va qaytadan <b>“✅ Obuna bo‘ldim”</b> "
    "tugmasini bosing."
)

MENU_TITLE = "🏠 <b>Asosiy menyu</b>\n\nQuyidagilardan birini tanlang:"

ABOUT = (
    "🏆 <b>ATLON GROUP HAQIDA</b>\n\n"
    "<b>Atlon Group nima?</b>\n"
    "Atlon Group — yoshlarni birlashtiruvchi, ularning bilim, ko‘nikma va "
    "salohiyatini rivojlantirishga qaratilgan yoshlar tashkiloti/loyihasi.\n\n"
    "<b>🎯 Maqsad va missiya</b>\n"
    "Yoshlar uchun o‘sish, tanishuv va o‘zini namoyon qilish uchun ochiq "
    "maydon yaratish. Har bir yoshning imkoniyatini kuchaytirish.\n\n"
    "<b>💡 Foydalari</b>\n"
    "• <i>Ishtirokchi (participant)</i> sifatida: yangi bilim, tajriba, "
    "tanishuvlar va tadbirlarda qatnashish imkoniyati.\n"
    "• <i>Volontyor (volunteer)</i> sifatida: tashkilotchilik tajribasi, "
    "sertifikat, jamoada ishlash va yetakchilik ko‘nikmalari.\n\n"
    "<b>🧭 Yo‘nalishlar</b>\n"
    "• 🏅 Sport\n"
    "• 🗣 Debate (munozara)\n"
    "• 🧠 Intellektual o‘yinlar\n"
    "• 🎬 Media\n"
    "• va boshqa ko‘plab yo‘nalishlar\n\n"
    "Biz bilan birga o‘s! 🚀"
)

EVENTS_PICK_CITY = "📍 Tadbirlarni ko‘rish uchun hududni tanlang:"
NO_EVENTS = "ℹ️ Hozircha bu hudud uchun tadbirlar mavjud emas. Tez orada qo‘shiladi!"

VOL_INTRO = (
    "📝 <b>Volontyorlik uchun ariza</b>\n\n"
    "Bir necha savolga javob bering. Istalgan vaqtda /bekor buyrug‘i bilan "
    "bekor qilishingiz mumkin.\n\n"
    "1️⃣ Avval hududingizni tanlang:"
)
VOL_ASK_NAME = "2️⃣ Ism va familiyangizni yozing:"
VOL_ASK_AGE = "3️⃣ Yoshingizni kiriting (faqat raqam):"
VOL_AGE_INVALID = "❗️ Iltimos, yoshingizni raqam bilan kiriting (masalan: 19)."
VOL_ASK_PHONE = (
    "4️⃣ Telefon raqamingizni yuboring.\n\n"
    "Pastdagi <b>“📱 Raqamni yuborish”</b> tugmasidan foydalaning yoki "
    "raqamni qo‘lda yozing."
)
VOL_ASK_INTERESTS = (
    "5️⃣ Qiziqishlaringiz qaysi yo‘nalishlarda?\n"
    "(masalan: media, tashkilotchilik, sport, debate ...)"
)
VOL_ASK_BIO = (
    "6️⃣ O‘zingiz haqingizda qisqacha yozing:\n"
    "• tajribangiz\n"
    "• kuchli tomonlaringiz\n"
    "• nega volontyor bo‘lmoqchisiz"
)
VOL_DONE = (
    "✅ <b>Arizangiz qabul qilindi!</b>\n\n"
    "Ma’lumotlaringiz tegishli shahar jamoasiga yuborildi. Tez orada siz "
    "bilan bog‘lanamiz. Rahmat! 🙌"
)
VOL_CANCELLED = "❌ Ariza bekor qilindi. Asosiy menyuga qaytdingiz."

# ── Main-menu labels ─────────────────────────────────────────────
BTN_ABOUT = "ℹ️ Atlon Group haqida"
BTN_EVENTS = "📅 Tadbirlar"
BTN_VOLUNTEER = "🤝 Volontyor bo‘lish"
BTN_BACK = "⬅️ Orqaga"
BTN_CANCEL = "❌ Bekor qilish"

# ── Inline keyboards ─────────────────────────────────────────────

def subscribe_keyboard() -> InlineKeyboardMarkup:
    rows = []
    if config.CHANNEL_URL:
        rows.append([InlineKeyboardButton("📢 Kanalga obuna bo‘lish", url=config.CHANNEL_URL)])
    rows.append([InlineKeyboardButton("✅ Obuna bo‘ldim", callback_data="check_sub")])
    return InlineKeyboardMarkup(rows)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(BTN_ABOUT, callback_data="about")],
            [InlineKeyboardButton(BTN_EVENTS, callback_data="events")],
            [InlineKeyboardButton(BTN_VOLUNTEER, callback_data="volunteer")],
        ]
    )


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(BTN_BACK, callback_data="menu")]]
    )


def _in_pairs(items: list) -> list[list]:
    """Chunk buttons into rows of two — 14 regions in one column is a lot
    of scrolling on a phone."""
    return [items[i:i + 2] for i in range(0, len(items), 2)]


def city_inline_keyboard(
    prefix: str,
    footer_label: str = BTN_BACK,
    footer_callback: str = "menu",
) -> InlineKeyboardMarkup:
    """City buttons, two per row (callback_data = '<prefix>:<city_key>').

    The footer button is configurable so the same grid can act as
    "back to menu" while browsing events, and "cancel" inside the
    volunteer application.
    """
    buttons = [
        InlineKeyboardButton(c["name"], callback_data=f"{prefix}:{c['key']}")
        for c in config.CITIES
    ]
    rows = _in_pairs(buttons)
    rows.append([InlineKeyboardButton(footer_label, callback_data=footer_callback)])
    return InlineKeyboardMarkup(rows)


def volunteer_city_keyboard() -> InlineKeyboardMarkup:
    """Region picker shown inline under the volunteer intro message."""
    return city_inline_keyboard(
        "volcity", footer_label=BTN_CANCEL, footer_callback="volcancel"
    )


# ── Reply keyboards (for the conversation flow) ──────────────────


def phone_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
