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

EVENTS_PICK_CITY = "📍 Tadbirlarni ko‘rish uchun shaharni tanlang:"
NO_EVENTS = "ℹ️ Hozircha bu shahar uchun tadbirlar mavjud emas. Tez orada qo‘shiladi!"

# ── Event registration ───────────────────────────────────────────

EVREG_ASK_NAME = (
    "📝 <b>Tadbirga ro‘yxatdan o‘tish</b>\n\n"
    "Istalgan vaqtda /bekor buyrug‘i bilan bekor qilishingiz mumkin.\n\n"
    "1️⃣ Ism va familiyangizni yozing:"
)
EVREG_ASK_AGE = "2️⃣ Yoshingizni kiriting (faqat raqam):"
EVREG_AGE_INVALID = "❗️ Iltimos, yoshingizni raqam bilan kiriting (masalan: 19)."
EVREG_ASK_PHONE = (
    "3️⃣ Telefon raqamingizni yuboring.\n\n"
    "Pastdagi <b>“📱 Raqamni yuborish”</b> tugmasidan foydalaning yoki "
    "raqamni qo‘lda yozing."
)
EVREG_ASK_RECEIPT = (
    "4️⃣ To‘lov chekini yuboring.\n\n"
    "⚠️ <b>Diqqat:</b> chek <b>faqat rasm (foto) ko‘rinishida</b> qabul qilinadi. "
    "Fayl, hujjat yoki matn ko‘rinishida yuborilgan cheklar qabul qilinmaydi."
)
EVREG_RECEIPT_INVALID = (
    "❗️ Chek <b>faqat rasm (foto) ko‘rinishida</b> qabul qilinadi.\n\n"
    "Iltimos, chek rasmini foto sifatida yuboring (fayl/hujjat sifatida emas)."
)
EVREG_DONE = (
    "✅ <b>Ariza yuborildi!</b>\n\n"
    "To‘lov chekingiz tekshirilmoqda. Tasdiqlangach, sizga xabar beramiz. "
    "Rahmat! 🙌"
)
EVREG_CANCELLED = "❌ Ro‘yxatdan o‘tish bekor qilindi."
EVREG_ALREADY_PENDING = (
    "ℹ️ Siz bu tadbirga allaqachon ariza yuborgansiz. "
    "Arizangiz tekshirilmoqda — natijani kutib turing."
)
EVREG_ALREADY_APPROVED = (
    "✅ Siz bu tadbirga allaqachon ro‘yxatdan o‘tgansiz va arizangiz tasdiqlangan."
)
EVREG_EVENT_GONE = "❗️ Kechirasiz, bu tadbir topilmadi."

APPROVED_HEADER = (
    "🎉 <b>Tabriklaymiz!</b>\n\n"
    "Sizning Atlon Group tadbiriga yuborgan arizangiz muvaffaqiyatli "
    "tasdiqlandi. ✅"
)
LOCATION_NOTE = "ℹ️ Aniq lokatsiya telegram kanalga yuboriladi."
REJECTED_MSG = (
    "❌ <b>Afsuski, arizangiz tasdiqlanmadi.</b>\n\n"
    "To‘lov cheki tasdiqlanmadi yoki noto‘g‘ri yuborilgan bo‘lishi mumkin. "
    "Iltimos, qaytadan urinib ko‘ring yoki adminlarga murojaat qiling."
)

def decision_message(approved: bool, event=None) -> str:
    """The message an applicant receives once their payment is reviewed.

    Shared by the Telegram admin buttons and the web panel so both send
    exactly the same wording.
    """
    import html as _html

    if not approved:
        return REJECTED_MSG

    lines = [APPROVED_HEADER, ""]
    if event is not None:
        lines.append(f"🎉 <b>{_html.escape(event.title)}</b>")
        if event.date:
            lines.append(f"🗓 {_html.escape(event.date)}")
        city = config.CITY_BY_KEY.get(event.city)
        if city:
            lines.append(f"📍 {_html.escape(city['name'])}")
        lines.append("")
    lines.append(LOCATION_NOTE)
    return "\n".join(lines)


BTN_REGISTER = "✅ Ro‘yxatdan o‘tish"
BTN_PREV = "⬅️ Avvalgisi"
BTN_NEXT = "Keyingisi ➡️"
BTN_CHANGE_CITY = "🏙 Shaharni o‘zgartirish"
BTN_MAIN_MENU = "🏠 Asosiy menyu"

VOL_INTRO = (
    "📝 <b>Volontyorlik uchun ariza</b>\n\n"
    "Bir necha savolga javob bering. Istalgan vaqtda /bekor buyrug‘i bilan "
    "bekor qilishingiz mumkin.\n\n"
    "1️⃣ Avval shahringizni tanlang:"
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


def event_card_keyboard(
    city_key: str, index: int, total: int, event_id: int
) -> InlineKeyboardMarkup:
    """Navigation + register buttons shown under a single event card."""
    rows = []

    nav = []
    if index > 0:
        nav.append(
            InlineKeyboardButton(BTN_PREV, callback_data=f"ev:{city_key}:{index - 1}")
        )
    if index < total - 1:
        nav.append(
            InlineKeyboardButton(BTN_NEXT, callback_data=f"ev:{city_key}:{index + 1}")
        )
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(BTN_REGISTER, callback_data=f"evreg:{event_id}")])
    rows.append([InlineKeyboardButton(BTN_CHANGE_CITY, callback_data="events")])
    rows.append([InlineKeyboardButton(BTN_MAIN_MENU, callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def no_events_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(BTN_CHANGE_CITY, callback_data="events")],
            [InlineKeyboardButton(BTN_MAIN_MENU, callback_data="menu")],
        ]
    )


def review_keyboard(reg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"regok:{reg_id}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"regno:{reg_id}"),
            ]
        ]
    )


def chunk(items: list, size: int) -> list[list]:
    """Split a flat list into rows of at most `size` items."""
    return [items[i : i + size] for i in range(0, len(items), size)]


def city_inline_keyboard(prefix: str) -> InlineKeyboardMarkup:
    """City buttons for browsing (callback_data = '<prefix>:<city_key>')."""
    buttons = [
        InlineKeyboardButton(c["name"], callback_data=f"{prefix}:{c['key']}")
        for c in config.CITIES
    ]
    rows = chunk(buttons, config.CITY_COLUMNS)
    rows.append([InlineKeyboardButton(BTN_BACK, callback_data="menu")])
    return InlineKeyboardMarkup(rows)


# ── Reply keyboards (for the conversation flow) ──────────────────

def city_reply_keyboard() -> ReplyKeyboardMarkup:
    rows = chunk([c["name"] for c in config.CITIES], config.CITY_COLUMNS)
    return ReplyKeyboardMarkup(
        rows, resize_keyboard=True, one_time_keyboard=True
    )


def phone_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
