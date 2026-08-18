"""Central configuration, loaded from environment variables.

All secrets and deployment-specific values live here so nothing
sensitive is hard-coded. Locally these come from a `.env` file;
on Railway they come from the project's Variables tab.
"""

import os

from dotenv import load_dotenv

load_dotenv()  # no-op on Railway (vars already in env), helpful locally


def _clean(value: str | None) -> str:
    return (value or "").strip()


# ── Core ─────────────────────────────────────────────────────────
BOT_TOKEN: str = _clean(os.getenv("BOT_TOKEN"))

# Channel the user must subscribe to (subscription gate).
CHANNEL_USERNAME: str = _clean(os.getenv("CHANNEL_USERNAME"))
if CHANNEL_USERNAME and not CHANNEL_USERNAME.startswith("@"):
    CHANNEL_USERNAME = "@" + CHANNEL_USERNAME

_channel_url_env = _clean(os.getenv("CHANNEL_URL"))
if _channel_url_env:
    CHANNEL_URL = _channel_url_env
elif CHANNEL_USERNAME:
    CHANNEL_URL = "https://t.me/" + CHANNEL_USERNAME.lstrip("@")
else:
    CHANNEL_URL = ""


def _parse_ids(raw: str | None) -> list[int]:
    ids: list[int] = []
    for part in _clean(raw).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            pass
    return ids


ADMIN_IDS: list[int] = _parse_ids(os.getenv("ADMIN_IDS"))


# ── Payment ──────────────────────────────────────────────────────
# Card applicants transfer the event fee to. Shown at the receipt step.
# Kept here rather than in code so it can be changed without a deploy.
PAYMENT_CARD: str = _clean(os.getenv("PAYMENT_CARD"))


# ── Web admin panel ──────────────────────────────────────────────
# Password for the browser panel. If unset, the panel refuses every
# login rather than falling open.
ADMIN_PASSWORD: str = _clean(os.getenv("ADMIN_PASSWORD"))

# Signs the login cookie. Defaults to a value derived from the bot token
# so sessions stay valid across restarts without extra configuration.
SESSION_SECRET: str = _clean(os.getenv("SESSION_SECRET")) or (
    "atlon-session-" + BOT_TOKEN
)

# How long a browser login stays valid.
SESSION_MAX_AGE = 60 * 60 * 12  # 12 hours

PORT: int = int(_clean(os.getenv("PORT")) or 8000)


# ── Cities ───────────────────────────────────────────────────────
# `key` is stored in the database and used internally.
# `name` is the label shown to users (Uzbek).
# `group_env` is the env var holding that city's Telegram group id.
# All 14 administrative regions of Uzbekistan (12 viloyat + Qoraqalpog‘iston
# + Toshkent shahri), listed alphabetically by Uzbek name.
#
# NOTE: the five original keys (namangan, fergana, tashkent, samarkand,
# andijan) and their GROUP_* variable names are kept exactly as they were,
# so existing Railway variables and rows already stored in the database
# keep working. Only new regions were added.
CITIES: list[dict] = [
    {"key": "andijan", "name": "Andijon", "group_env": "GROUP_ANDIJAN"},
    {"key": "bukhara", "name": "Buxoro", "group_env": "GROUP_BUKHARA"},
    {"key": "fergana", "name": "Farg‘ona", "group_env": "GROUP_FERGANA"},
    {"key": "jizzakh", "name": "Jizzax", "group_env": "GROUP_JIZZAKH"},
    {"key": "namangan", "name": "Namangan", "group_env": "GROUP_NAMANGAN"},
    {"key": "navoi", "name": "Navoiy", "group_env": "GROUP_NAVOI"},
    {"key": "kashkadarya", "name": "Qashqadaryo", "group_env": "GROUP_KASHKADARYA"},
    {
        "key": "karakalpakstan",
        "name": "Qoraqalpog‘iston",
        "group_env": "GROUP_KARAKALPAKSTAN",
    },
    {"key": "samarkand", "name": "Samarqand", "group_env": "GROUP_SAMARKAND"},
    {"key": "syrdarya", "name": "Sirdaryo", "group_env": "GROUP_SYRDARYA"},
    {"key": "surkhandarya", "name": "Surxondaryo", "group_env": "GROUP_SURKHANDARYA"},
    {"key": "tashkent", "name": "Toshkent shahri", "group_env": "GROUP_TASHKENT"},
    {
        "key": "tashkent_region",
        "name": "Toshkent viloyati",
        "group_env": "GROUP_TASHKENT_REGION",
    },
    {"key": "khorezm", "name": "Xorazm", "group_env": "GROUP_KHOREZM"},
]

# How many region buttons to place per keyboard row.
CITY_COLUMNS = 2


# ── Volunteer directions ─────────────────────────────────────────
# Offered as buttons in the volunteer form. Tapping one stores `label`
# exactly, so every application uses the same spelling and the list can
# be filtered reliably — that is the whole point of the buttons.
# To add a direction, add a line here; the keyboard follows automatically.
INTERESTS: list[dict] = [
    {"key": "sport", "emoji": "🏅", "label": "Sport"},
    {"key": "debate", "emoji": "🗣", "label": "Debate"},
    {"key": "intellect", "emoji": "🧠", "label": "Intellektual o‘yinlar"},
    {"key": "media", "emoji": "🎬", "label": "Media"},
    {"key": "organizer", "emoji": "📋", "label": "Tashkilotchilik"},
    {"key": "coordinator", "emoji": "🤝", "label": "Koordinator"},
    {"key": "speaker", "emoji": "🎤", "label": "Speaker"},
    {"key": "design", "emoji": "🎨", "label": "Dizayn"},
]

INTEREST_BY_KEY: dict[str, dict] = {i["key"]: i for i in INTERESTS}

INTEREST_COLUMNS = 2

CITY_BY_KEY: dict[str, dict] = {c["key"]: c for c in CITIES}
CITY_BY_NAME: dict[str, dict] = {c["name"]: c for c in CITIES}


def group_chat_id(city_key: str) -> str:
    """Return the configured group chat id for a city, or '' if unset."""
    city = CITY_BY_KEY.get(city_key)
    if not city:
        return ""
    return _clean(os.getenv(city["group_env"]))


# ── Database ─────────────────────────────────────────────────────
# Railway's Postgres plugin injects DATABASE_URL. If absent we use a
# local SQLite file so the bot still runs during development.
DATABASE_URL: str = _clean(os.getenv("DATABASE_URL")) or "sqlite:///atlon.db"


def validate() -> list[str]:
    """Return a list of human-readable configuration problems."""
    problems: list[str] = []
    if not BOT_TOKEN:
        problems.append("BOT_TOKEN is not set — get one from @BotFather.")
    if not CHANNEL_USERNAME:
        problems.append(
            "CHANNEL_USERNAME is not set — the subscription gate will be skipped."
        )
    if not ADMIN_IDS:
        problems.append(
            "ADMIN_IDS is not set — no one will be able to use the admin panel."
        )
    if not ADMIN_PASSWORD:
        problems.append(
            "ADMIN_PASSWORD is not set — the web panel will reject all logins."
        )
    if not PAYMENT_CARD:
        problems.append(
            "PAYMENT_CARD is not set — applicants won't see a card to pay to."
        )
    return problems
