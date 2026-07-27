# ATLON GROUP — Telegram bot

Yoshlar loyihasi uchun Telegram bot: kanalga obuna nazorati, loyiha haqida
ma’lumot, shaharlar bo‘yicha tadbirlar, volontyor arizalarini yig‘ish, ularni
shahar guruhlariga yuborish va shahar bo‘yicha bildirishnomalar.

## Imkoniyatlar

- **Obuna nazorati** — foydalanuvchi avval kanalga obuna bo‘lishi shart.
- **Asosiy menyu** — *Atlon Group haqida*, *Tadbirlar*, *Volontyor bo‘lish*.
- **Tadbirlar** — shahar tanlab, o‘sha shahardagi tadbirlarni ko‘rish.
- **Volontyor arizasi** — shahar, ism-familiya, yosh, telefon (kontakt tugmasi),
  qiziqishlar, bio.
- **Saqlash** — ma’lumotlar bazasi (Postgres/SQLite) + Excel export (`/export`).
- **Guruhlarga yuborish** — ariza tanlangan shaharning guruhiga yuboriladi.
- **Bildirishnoma** — yangi tadbir qo‘shilganda, o‘sha shaharni tanlagan
  foydalanuvchilarga xabar boradi.
- **Admin panel** — `/addevent`, `/broadcast`, `/export`, `/stats`.

## Texnologiya

Python 3.11 · `python-telegram-bot` v21 (polling) · SQLAlchemy ·
Postgres (Railway) yoki SQLite (lokal) · openpyxl.

## 1) Botni yaratish (@BotFather)

1. Telegramda [@BotFather](https://t.me/BotFather) ga yozing → `/newbot`.
2. Nom va username bering → sizga **token** beriladi.
3. Kanalingizga botni **admin** qilib qo‘shing (obunani tekshirish uchun shart).
4. Har bir shahar guruhiga botni qo‘shing (arizalar shu yerga tushadi).

## 2) Muhit o‘zgaruvchilari (environment variables)

`.env.example` faylidan nusxa oling. Asosiylari:

| Variable | Tavsif |
|---|---|
| `BOT_TOKEN` | @BotFather bergan token (**majburiy**) |
| `CHANNEL_USERNAME` | Obuna kanali, masalan `@atlongroup` |
| `CHANNEL_URL` | Ixtiyoriy — tugmadagi havola |
| `ADMIN_IDS` | Admin Telegram ID lari, vergul bilan (`@userinfobot`) |
| `GROUP_NAMANGAN` … `GROUP_ANDIJAN` | Har shahar guruhining chat ID si (`-100…`) |
| `DATABASE_URL` | Postgres URL (Railwayda avtomatik) |

> Guruh chat ID sini bilish uchun botni guruhga qo‘shing, guruhga bir xabar
> yozing va logdan `chat_id` ni ko‘ring, yoki `@getidsbot` dan foydalaning.

## 3) Lokal ishga tushirish

```bash
pip install -r requirements.txt
cp .env.example .env      # va qiymatlarni to‘ldiring
python bot.py
```

## 4) Railwayda deploy

1. Bu repozitoriyni GitHubga yuklang.
2. [Railway](https://railway.app) da **New Project → Deploy from GitHub repo**.
3. **Variables** bo‘limiga yuqoridagi o‘zgaruvchilarni qo‘shing.
4. (Tavsiya) **New → Database → PostgreSQL** qo‘shing — `DATABASE_URL`
   avtomatik ulanadi va ma’lumotlar deploylar orasida saqlanadi.
5. Railway `Procfile` (`worker: python bot.py`) orqali botni ishga tushiradi.

> SQLite (default) faylida ma’lumotlar redeploy paytida yo‘qoladi — shu sabab
> productionда Postgres ishlatilsin.

## Admin buyruqlari

| Buyruq | Vazifa |
|---|---|
| `/admin` | Admin yordam menyusi |
| `/addevent` | Tadbir qo‘shish (+ shahar bo‘yicha bildirishnoma) |
| `/broadcast` | Hammaga yoki shahar bo‘yicha xabar |
| `/export` | Arizalarni Excel qilib yuklab olish |
| `/stats` | Statistika |
| `/bekor` | Jarayonni bekor qilish |

## Loyiha tuzilishi

```
bot.py        — kirish nuqtasi, asosiy user flow, volontyor arizasi
admin.py      — admin panel (tadbir, broadcast, export, stats)
config.py     — muhit o‘zgaruvchilari, shaharlar, guruh ID lari
texts.py      — barcha matnlar va tugmalar (o‘zbekcha)
db.py         — ma’lumotlar bazasi modellari va yordamchi funksiyalar
```

Matnlarni tahrirlash uchun `texts.py`, shahar/guruh sozlamalari uchun
`config.py` ni o‘zgartiring.
